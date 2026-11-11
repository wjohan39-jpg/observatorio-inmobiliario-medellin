"""Adaptador de Arrendamientos Nutibara (https://anutibara.com).

El sitio consulta una API JSON en otro host, ``api.arrendamientosnutibara.com``:

* ``GET /promotion/filter/nearest?latitude&longitude&page&priceStart=1&status=…`` devuelve
  ``{data: {total, promotions[]}}``, 20 por página. ``status`` es ``PROMOCION`` (arriendo)
  o ``VENTAS`` (venta; incluye inventario compartido ``"VENTAS - MLS"``).

La búsqueda solo devuelve inmuebles a unos 3 km del punto dado, y no hay un parámetro para
ampliar ese radio. Por eso se consulta desde una cuadrícula de puntos que cubre el Valle de
Aburrá y se descartan los anuncios repetidos entre círculos vecinos. Cuando no hay inmuebles
cerca de un punto, la API responde 404 ("No elements were found") en vez de una lista vacía.
"""

import logging
import math
from collections.abc import Iterator
from datetime import date
from typing import Any, Final

import httpx
from pydantic import ValidationError

from observatorio_inmobiliario.http import ClienteCortes, ErrorDeDescarga
from observatorio_inmobiliario.modelos import AnuncioNormalizado, Operacion
from observatorio_inmobiliario.parseo import (
    parsear_coordenada,
    parsear_decimal,
    parsear_entero,
    parsear_estrato,
    parsear_precio,
)

logger = logging.getLogger(__name__)

URL_BASE: Final = "https://api.arrendamientosnutibara.com"
"""Host de la API, que es el que consulta el cliente HTTP."""
URL_SITIO: Final = "https://anutibara.com"
"""Sitio público, para armar el enlace de cada anuncio."""

RADIO_KM: Final = 2.9
"""Radio de búsqueda de la API, medido el 2026-11-11 (el resultado más lejano estaba a 2,99 km)."""
TAMANO_PAGINA: Final = 20

STATUS: Final = ("PROMOCION", "VENTAS")
"""Valores del parámetro ``status``: arriendo y venta."""

# Ids de ``facility`` en la API. Se usa el id porque el nombre llega mal codificado ("Ba�os").
_AREA: Final = 112
_ALCOBAS: Final = 82
_BANOS: Final = 105


def cuadricula(
    sur: float, norte: float, oeste: float, este: float, paso: float
) -> tuple[tuple[float, float], ...]:
    """Puntos ``(lat, lon)`` igualmente espaciados que incluyen los cuatro bordes.

    El espaciado real es igual o menor que ``paso`` (en grados).

    >>> cuadricula(6.0, 6.1, -75.6, -75.5, 0.1)
    ((6.0, -75.6), (6.0, -75.5), (6.1, -75.6), (6.1, -75.5))
    """

    def ejes(inicio: float, fin: float) -> list[float]:
        tramos = max(1, math.ceil(round((fin - inicio) / paso, 9)))
        return [round(inicio + i * (fin - inicio) / tramos, 6) for i in range(tramos + 1)]

    return tuple((lat, lon) for lat in ejes(sur, norte) for lon in ejes(oeste, este))


CENTROS: Final = cuadricula(6.09, 6.38, -75.66, -75.50, 0.035)
"""Puntos desde los que se busca: cubren el Valle de Aburrá con círculos de ``RADIO_KM``."""


def _es_404(error: ErrorDeDescarga) -> bool:
    causa = error.__cause__
    return isinstance(causa, httpx.HTTPStatusError) and causa.response.status_code == 404


def _slug(texto: str) -> str:
    return texto.strip().lower().replace(" ", "-")


def _operacion(status: Any) -> Any:
    """``PROMOCION`` es arriendo; ``VENTAS`` y ``VENTAS - MLS`` son venta.

    Cualquier otro valor se devuelve tal cual, para que pydantic rechace el anuncio.
    """
    if status == "PROMOCION":
        return Operacion.ARRIENDO
    if isinstance(status, str) and status.startswith("VENTAS"):
        return Operacion.VENTA
    return status.lower() if isinstance(status, str) else status


def _url(id_: Any, tipo: Any, operacion: Any, barrio: Any, ciudad: Any) -> str | None:
    partes = (tipo, barrio, ciudad)
    if id_ is None or not isinstance(operacion, Operacion):
        return None
    if not all(isinstance(p, str) and p.strip() for p in partes):
        return None
    return f"{URL_SITIO}/{_slug(tipo)}-en-{operacion.value}/{_slug(barrio)}-{_slug(ciudad)}/{id_}"


def mapear_anuncio(promocion: dict[str, Any], fecha: date) -> AnuncioNormalizado:
    """Convierte una promoción de la API en un anuncio normalizado.

    Lanza ``ValidationError`` si no es válido, p. ej. un ``status`` desconocido.
    """
    inmueble = promocion.get("property") or {}
    datos = {
        (f.get("facility") or {}).get("id"): f.get("value")
        for f in inmueble.get("facilities") or []
    }
    id_ = promocion.get("id")
    operacion = _operacion(promocion.get("status"))
    precio = promocion.get("sellValue" if operacion is Operacion.VENTA else "rentValue")

    return AnuncioNormalizado.model_validate(
        {
            "fuente": FuenteNutibara.nombre,
            "id_fuente": None if id_ is None else str(id_),
            "url": _url(
                id_,
                inmueble.get("type"),
                operacion,
                inmueble.get("neighborhood"),
                inmueble.get("city"),
            ),
            "fecha_observacion": fecha,
            "operacion": operacion,
            "tipo_inmueble": inmueble.get("type"),
            "precio": parsear_precio(precio),
            "area_m2": parsear_decimal(datos.get(_AREA)),
            "habitaciones": parsear_entero(datos.get(_ALCOBAS)),
            "banos": parsear_entero(datos.get(_BANOS)),
            "estrato": parsear_estrato(inmueble.get("stratum")),
            "barrio": inmueble.get("neighborhood"),
            "municipio": inmueble.get("city"),
            "latitud": parsear_coordenada(inmueble.get("latitude")),
            "longitud": parsear_coordenada(inmueble.get("longitude")),
            # La API marca el inventario MLS, pero no dice qué agencia lo publicó.
            "anunciante_origen": None,
        }
    )


class FuenteNutibara:
    """Recorre arriendos y ventas de Nutibara desde cada punto de la cuadrícula."""

    nombre = "nutibara"

    def __init__(
        self,
        cliente: ClienteCortes,
        *,
        con_detalle: bool = True,
        max_paginas: int | None = None,
        fecha: date | None = None,
        centros: tuple[tuple[float, float], ...] = CENTROS,
    ) -> None:
        """``con_detalle`` no tiene efecto: el listado ya trae todos los datos disponibles.

        ``max_paginas`` limita las páginas de cada punto y operación.
        """
        self._cliente = cliente
        self._max_paginas = max_paginas
        self._fecha = fecha or date.today()
        self._centros = centros

    def listar_anuncios(self) -> Iterator[AnuncioNormalizado]:
        for status in STATUS:
            vistos: set[Any] = set()
            for latitud, longitud in self._centros:
                for promocion in self._resultados(status, latitud, longitud):
                    id_ = promocion.get("id")
                    if id_ in vistos:
                        continue
                    vistos.add(id_)
                    try:
                        yield mapear_anuncio(promocion, self._fecha)
                    except ValidationError as error:
                        logger.warning("Anuncio %s omitido por datos inválidos: %s", id_, error)

    def _resultados(self, status: str, latitud: float, longitud: float) -> Iterator[dict[str, Any]]:
        pagina = 1
        while True:
            try:
                respuesta = self._buscar(status, latitud, longitud, pagina)
            except ErrorDeDescarga as error:
                if _es_404(error):
                    return  # sin inmuebles cerca de este punto
                raise
            datos = respuesta.get("data") or {}
            promociones = datos.get("promotions") or []
            yield from promociones
            if not promociones or pagina * TAMANO_PAGINA >= (datos.get("total") or 0):
                return
            if self._max_paginas is not None and pagina >= self._max_paginas:
                return
            pagina += 1

    def _buscar(self, status: str, latitud: float, longitud: float, pagina: int) -> Any:
        return self._cliente.get_json(
            "/promotion/filter/nearest",
            params={
                # El cliente solo acepta textos y enteros como parámetros.
                "latitude": f"{latitud:.5f}",
                "longitude": f"{longitud:.5f}",
                "page": pagina,
                "priceStart": 1,
                "status": status,
            },
        )
