"""Cliente HTTP cortés: todas las peticiones a las inmobiliarias pasan por aquí.

Reglas que aplica:

* Respeta ``robots.txt``: no pide rutas que el sitio prohíbe.
* Limita la velocidad: deja al menos ``segundos_entre_peticiones`` entre dos peticiones.
* Reintenta errores temporales (429, 5xx, timeouts) con espera creciente: 2 s, 4 s, 8 s...
* No reintenta errores definitivos (404, 403...).
* Se identifica con un User-Agent que enlaza al repositorio del proyecto.
"""

import logging
import time
from collections.abc import Callable, Mapping
from types import TracebackType
from typing import Any, Self

import httpx
from protego import Protego

from observatorio_inmobiliario.config import SEGUNDOS_ENTRE_PETICIONES, USER_AGENT

logger = logging.getLogger(__name__)

type Parametros = Mapping[str, str | int]


class ErrorDeDescarga(Exception):
    """No se pudo obtener una respuesta válida del sitio."""


class ErrorRutaBloqueadaPorRobots(Exception):
    """El ``robots.txt`` del sitio no permite pedir esta ruta."""


def _es_error_temporal(codigo: int) -> bool:
    return codigo == 429 or codigo >= 500


class ClienteCortes:
    """Cliente HTTP para un sitio, que respeta robots.txt, limita la velocidad y reintenta.

    Úsalo como *context manager* para cerrar la conexión al terminar::

        with ClienteCortes("https://sitio.com") as cliente:
            datos = cliente.get_json("/api/propiedades", params={"page": 1})
    """

    def __init__(
        self,
        url_base: str,
        *,
        segundos_entre_peticiones: float = SEGUNDOS_ENTRE_PETICIONES,
        max_intentos: int = 3,
        timeout: float = 30.0,
        dormir: Callable[[float], None] = time.sleep,
        reloj: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_intentos < 1:
            raise ValueError("max_intentos debe ser al menos 1")
        self._url_base = httpx.URL(url_base)
        self._pausa = segundos_entre_peticiones
        self._max_intentos = max_intentos
        self._dormir = dormir
        self._reloj = reloj
        self._ultima_peticion: float | None = None
        self._robots: Protego | None = None
        self._http = httpx.Client(
            base_url=self._url_base,
            headers={"User-Agent": USER_AGENT},
            timeout=timeout,
            follow_redirects=True,
        )

    # ------------------------------------------------------------------ API pública

    def get_json(self, ruta: str, params: Parametros | None = None) -> Any:
        """Pide ``ruta`` y devuelve el cuerpo JSON ya decodificado."""
        respuesta = self._get_permitido(ruta, params)
        try:
            return respuesta.json()
        except ValueError as error:
            raise ErrorDeDescarga(f"La respuesta de {respuesta.url} no es JSON válido") from error

    def get_texto(self, ruta: str, params: Parametros | None = None) -> str:
        """Pide ``ruta`` y devuelve el cuerpo como texto (HTML)."""
        return self._get_permitido(ruta, params).text

    def cerrar(self) -> None:
        self._http.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        tipo: type[BaseException] | None,
        error: BaseException | None,
        traza: TracebackType | None,
    ) -> None:
        self.cerrar()

    # ------------------------------------------------------------------ Internos

    def _get_permitido(self, ruta: str, params: Parametros | None) -> httpx.Response:
        url = self._url_base.join(ruta).copy_merge_params(dict(params or {}))
        if not self._obtener_robots().can_fetch(str(url), USER_AGENT):
            raise ErrorRutaBloqueadaPorRobots(f"robots.txt no permite {url}")
        return self._get_con_reintentos(ruta, params)

    def _obtener_robots(self) -> Protego:
        """Descarga y analiza robots.txt la primera vez; luego usa la copia en memoria.

        Se usa ``protego`` (el parser de Scrapy) y no ``urllib.robotparser`` porque este
        último, hasta Python 3.13, aplica la primera regla que coincide en lugar de la más
        específica (RFC 9309), y con ``Allow: /`` al inicio permitiría rutas prohibidas.
        """
        if self._robots is None:
            try:
                texto = self._get_con_reintentos("/robots.txt", None).text
            except ErrorDeDescarga as error:
                # Un 4xx en robots.txt significa "no hay reglas". Un 5xx o un fallo de red no.
                if not isinstance(error.__cause__, httpx.HTTPStatusError) or _es_error_temporal(
                    error.__cause__.response.status_code
                ):
                    raise
                texto = ""
            self._robots = Protego.parse(texto)
        return self._robots

    def _esperar_turno(self) -> None:
        if self._ultima_peticion is not None:
            faltante = self._pausa - (self._reloj() - self._ultima_peticion)
            if faltante > 0:
                self._dormir(faltante)
        self._ultima_peticion = self._reloj()

    def _get_con_reintentos(self, ruta: str, params: Parametros | None) -> httpx.Response:
        ultimo_error: Exception | None = None
        for intento in range(1, self._max_intentos + 1):
            self._esperar_turno()
            try:
                respuesta = self._http.get(ruta, params=dict(params) if params else None)
                respuesta.raise_for_status()
                return respuesta
            except httpx.HTTPStatusError as error:
                if not _es_error_temporal(error.response.status_code):
                    raise ErrorDeDescarga(
                        f"{error.response.status_code} en {error.request.url}"
                    ) from error
                ultimo_error = error
            except httpx.TransportError as error:  # incluye timeouts y fallos de conexión
                ultimo_error = error

            if intento < self._max_intentos:
                espera = 2**intento
                logger.warning(
                    "Intento %d/%d falló para %s (%s); reintento en %d s",
                    intento,
                    self._max_intentos,
                    ruta,
                    ultimo_error,
                    espera,
                )
                self._dormir(espera)

        raise ErrorDeDescarga(
            f"{ruta} falló tras {self._max_intentos} intentos: {ultimo_error}"
        ) from ultimo_error
