"""Adaptador de Maxibienes (https://www.maxibienes.com).

El sitio (PHP sobre el CRM SIMI) genera el HTML en el servidor:

* Listado: ``GET /resultados-de-la-busqueda-de-inmueble/pagina/N?gestion=1|2&ciudad=<DANE>``,
  12 tarjetas por página. ``gestion=1`` es arriendo y ``gestion=2`` venta; ambas incluyen
  los inmuebles que se ofrecen en arriendo y venta a la vez.
* La página repite los filtros que entendió (``var gs = 1``, ``var ci = 5001``) y el total
  (``var totalInmuebles = 956``). Con un filtro mal escrito el sitio devuelve todo el país
  sin avisar, así que se verifica ese eco antes de seguir.

**No se piden las páginas de detalle.** Llevan a la vista un token de la API de SIMI: usarlo
sería usar una credencial filtrada. Además, la tarjeta ya trae todos los datos de hecho.
"""

import logging
import math
import re
from collections.abc import Iterator
from datetime import date
from typing import Final

from pydantic import ValidationError

from observatorio_inmobiliario.fuentes import uribienes
from observatorio_inmobiliario.html import analizar, decodificar, texto
from observatorio_inmobiliario.http import ClienteCortes, ErrorDeDescarga
from observatorio_inmobiliario.modelos import AnuncioNormalizado, Operacion
from observatorio_inmobiliario.parseo import (
    parsear_area,
    parsear_conteo,
    parsear_estrato,
    parsear_precio,
)

logger = logging.getLogger(__name__)

URL_BASE: Final = "https://www.maxibienes.com"
RUTA: Final = "/resultados-de-la-busqueda-de-inmueble"

MUNICIPIOS: Final = uribienes.MUNICIPIOS
"""Los mismos códigos DANE del Valle de Aburrá (el parámetro ``ciudad``)."""

GESTIONES: Final = {1: Operacion.ARRIENDO, 2: Operacion.VENTA}
TAMANO_PAGINA: Final = 12

type Tarjeta = dict[str, str | None]

_CODIGO: Final = re.compile(r"/codigo/(\d+)")
_ESTRATO: Final = re.compile(r"Estrato:\s*(\d+)")
_PRECIO: Final = re.compile(r"\$\s*([\d.]+)")
_ICONOS: Final = {
    "fa-compress": "area",
    "fa-bath": "banos",
    "fa-bed": "alcobas",
    "fa-warehouse": "parqueaderos",
}


class ErrorFiltroIgnorado(ErrorDeDescarga):
    """El sitio no aplicó el filtro pedido y devolvería inmuebles de todo el país."""


def _variable(html: str, nombre: str) -> int | None:
    coincidencia = re.search(rf"var {nombre} = (\d+)", html)
    return int(coincidencia.group(1)) if coincidencia else None


def extraer_filtros(html: str) -> tuple[int | None, int | None, int | None]:
    """``(gestión, ciudad, total)`` tal como los entendió el sitio."""
    return _variable(html, "gs"), _variable(html, "ci"), _variable(html, "totalInmuebles")


def extraer_tarjetas(html: str | bytes) -> list[Tarjeta]:
    """Datos crudos de cada tarjeta del listado, como texto."""
    if isinstance(html, bytes):
        html = decodificar(html)
    tarjetas: list[Tarjeta] = []
    for item in analizar(html).css("div.grid-style1 div.item"):
        enlace = item.css_first("div.image a")
        h3 = item.css_first("div.image h3")
        # El h3 es "APARTAMENTO<br>Estrato: 4": el tipo va antes del <br>.
        partes = h3.html.split("<br>") if h3 is not None and h3.html else []
        tipo = texto(analizar(partes[0]).body) if partes else None
        precio = item.css_first("div.price")
        operacion = None
        if precio is not None:
            operacion = precio.text(deep=False).strip() or None
        tarjeta: Tarjeta = {
            "codigo": _primer_grupo(_CODIGO, enlace.attributes.get("href") if enlace else None),
            "tipo": tipo,
            "estrato": _primer_grupo(_ESTRATO, texto(h3)),
            "barrio": _sin_prefijo(texto(item.css_first("span.location")), "Barrio:"),
            "operacion": operacion,
            "precio": texto(item.css_first("div.price span")),
            "area": None,
            "banos": None,
            "alcobas": None,
            "parqueaderos": None,
        }
        for li in item.css("ul.amenities li"):
            icono = li.css_first("i")
            clases = (icono.attributes.get("class") or "") if icono is not None else ""
            for clase, campo in _ICONOS.items():
                if clase in clases.split():
                    tarjeta[campo] = texto(li)
        tarjetas.append(tarjeta)
    return tarjetas


def _primer_grupo(patron: re.Pattern[str], valor: str | None) -> str | None:
    coincidencia = patron.search(valor or "")
    return coincidencia.group(1) if coincidencia else None


def _sin_prefijo(valor: str | None, prefijo: str) -> str | None:
    if valor is None:
        return None
    return valor.removeprefix(prefijo).strip() or None


def _precio(valor: str | None, operacion: Operacion) -> int | None:
    """``$ 4.000.000``, o ``$ $ 3.100.000 / $610.000.000`` (arriendo / venta) en los duales."""
    numeros = _PRECIO.findall(valor or "")
    if not numeros:
        return None
    elegido = numeros[-1] if operacion is Operacion.VENTA else numeros[0]
    return parsear_precio(elegido)


def mapear_anuncio(
    tarjeta: Tarjeta, operacion: Operacion, municipio: str, fecha: date
) -> AnuncioNormalizado:
    """Convierte una tarjeta en un anuncio de la ``operacion`` consultada.

    Lanza ``ValidationError`` si no es válido, p. ej. si no trae código.
    """
    codigo = tarjeta.get("codigo")
    return AnuncioNormalizado.model_validate(
        {
            "fuente": FuenteMaxibienes.nombre,
            "id_fuente": codigo,
            "url": f"{URL_BASE}/descripcion-del-inmueble/codigo/{codigo}" if codigo else None,
            "fecha_observacion": fecha,
            "operacion": operacion,
            "tipo_inmueble": tarjeta.get("tipo"),
            "precio": _precio(tarjeta.get("precio"), operacion),
            "area_m2": parsear_area(tarjeta.get("area")),
            "habitaciones": parsear_conteo(tarjeta.get("alcobas")),
            "banos": parsear_conteo(tarjeta.get("banos")),
            "parqueaderos": parsear_conteo(tarjeta.get("parqueaderos")),
            # El sitio usa 7 para locales y bodegas: "no aplica".
            "estrato": parsear_estrato(tarjeta.get("estrato")),
            "barrio": tarjeta.get("barrio"),
            "municipio": municipio,
        }
    )


class FuenteMaxibienes:
    """Recorre arriendos y ventas de Maxibienes en cada municipio del Valle de Aburrá."""

    nombre = "maxibienes"

    def __init__(
        self,
        cliente: ClienteCortes,
        *,
        con_detalle: bool = True,
        max_paginas: int | None = None,
        fecha: date | None = None,
    ) -> None:
        """``con_detalle`` no tiene efecto: el detalle no se pide (lleva el token de SIMI).

        ``max_paginas`` limita las páginas de cada municipio y operación.
        """
        self._cliente = cliente
        self._max_paginas = max_paginas
        self._fecha = fecha or date.today()

    def listar_anuncios(self) -> Iterator[AnuncioNormalizado]:
        for gestion, operacion in GESTIONES.items():
            vistos: set[str] = set()
            for ciudad, municipio in MUNICIPIOS.items():
                for tarjeta in self._tarjetas(gestion, ciudad):
                    codigo = tarjeta.get("codigo")
                    if codigo is not None and codigo in vistos:
                        continue
                    if codigo is not None:
                        vistos.add(codigo)
                    try:
                        yield mapear_anuncio(tarjeta, operacion, municipio, self._fecha)
                    except ValidationError as error:
                        logger.warning("Anuncio %s omitido por datos inválidos: %s", codigo, error)

    def _tarjetas(self, gestion: int, ciudad: int) -> Iterator[Tarjeta]:
        pagina, paginas = 1, 1
        while pagina <= paginas:
            html = decodificar(
                self._cliente.get_bytes(
                    f"{RUTA}/pagina/{pagina}", params={"gestion": gestion, "ciudad": ciudad}
                )
            )
            if pagina == 1:
                gs, ci, total = extraer_filtros(html)
                if (gs, ci) != (gestion, ciudad):
                    raise ErrorFiltroIgnorado(
                        f"Se pidió gestion={gestion}, ciudad={ciudad} y el sitio aplicó "
                        f"gestion={gs}, ciudad={ci}"
                    )
                paginas = math.ceil((total or 0) / TAMANO_PAGINA)
            tarjetas = extraer_tarjetas(html)
            yield from tarjetas
            if not tarjetas:
                return
            if self._max_paginas is not None and pagina >= self._max_paginas:
                return
            pagina += 1
