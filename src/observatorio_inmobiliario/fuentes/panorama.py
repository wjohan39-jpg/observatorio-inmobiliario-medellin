"""Adaptador de Arrendamientos Panorama (https://arrendamientospanorama.com).

Sitio ASP clásico con HTML en cp1252 (sin declararlo en la cabecera):

1. Descubrimiento: ``GET /listado_<op>.asp?sZona=<tipo>`` enlaza solo los municipios que
   tienen inventario de ese tipo (``Resumen_Ciudad_…asp?pCiudad=…``).
2. Listado: ``GET /resumen_ciudad_<op>.asp?pCiudad=<c>&pTipoInmueble=<t>&offset=<n>``,
   50 tarjetas por página. El total sale de ``Página N / M``. **Al pedir una página después
   de la última, el sitio repite la última**: se corta siempre con M.
3. Ficha: ``GET /Ficha.asp?xId=<código>`` trae el estrato. Por decisión del autor solo se
   pide para apartamentos, apartaestudios y casas. Un anuncio retirado responde 500.

No publica coordenadas.
"""

import logging
import re
from collections.abc import Iterator
from datetime import date
from typing import Final

from pydantic import ValidationError
from selectolax.lexbor import LexborNode

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

URL_BASE: Final = "https://arrendamientospanorama.com"

TIPOS: Final[dict[int, str]] = {
    1: "apartamento",
    4: "apartaestudio",
    2: "casa",
    3: "casa campestre",
    12: "finca de recreo",
    6: "bodega",
    7: "local",
    8: "oficina",
    13: "finca agroindustrial",
    10: "lote",
}
"""Valores del parámetro ``pTipoInmueble``."""

TIPOS_RESIDENCIALES: Final = frozenset({1, 2, 4})
"""Tipos para los que se pide la ficha (el estrato solo está ahí)."""

MUNICIPIOS: Final[dict[int, str]] = {
    10000: "Medellín",
    10041: "Medellín",  # corregimiento San Antonio de Prado
    10037: "Medellín",  # corregimiento San Cristóbal
    10001: "Envigado",
    10002: "Itagüí",
    10003: "La Estrella",
    10005: "Sabaneta",
    10006: "Caldas",
    10007: "Bello",
    10008: "Copacabana",
}
"""Valores de ``pCiudad`` del Valle de Aburrá (el sitio también lista el Oriente)."""

OPERACIONES: Final = {
    Operacion.ARRIENDO: ("/listado_arriendos.asp", "/resumen_ciudad_arriendos.asp"),
    Operacion.VENTA: ("/listado_ventas.asp", "/resumen_ciudad_ventas.asp"),
}
"""Página de descubrimiento y página de listado de cada operación."""

TAMANO_PAGINA: Final = 50

type Tarjeta = dict[str, str | None]

_CIUDAD: Final = re.compile(r"Resumen_Ciudad_\w+\.asp\?pCiudad=(\d+)", re.IGNORECASE)
_PAGINAS: Final = re.compile(r"gina\s+\d+\s*/\s*(\d+)")
_ANUNCIO: Final = re.compile(r"Anuncio (\d+) - (.+)")
_PRECIO: Final = re.compile(r"Precio \$\s*([\d,.]+)")
_ICONOS: Final = {
    "fa-bed": "alcobas",
    "fa-bath": "banos",
    "fa-car-side": "parqueaderos",
    "fa-ruler-triangle": "area",
}


def extraer_ciudades(html: str) -> set[int]:
    """Municipios (``pCiudad``) con inventario. Ignora el bloque "TOP 10" de destacados."""
    fin = html.find("TOP 10")
    return {int(c) for c in _CIUDAD.findall(html if fin == -1 else html[:fin])}


def extraer_paginas(html: str) -> int:
    """El M de ``Página N / M``; 0 si no hay inventario o no aparece."""
    coincidencia = _PAGINAS.search(html)
    return int(coincidencia.group(1)) if coincidencia else 0


def _valor_del_icono(icono: LexborNode) -> str | None:
    """El ``<span>`` que sigue al icono trae el valor."""
    nodo = icono.next
    while nodo is not None and nodo.tag != "span":
        nodo = nodo.next
    return texto(nodo)


def extraer_tarjetas(html: str) -> list[Tarjeta]:
    """Datos crudos de cada tarjeta del listado."""
    tarjetas: list[Tarjeta] = []
    for bloque in analizar(html).css("div.col-sm-8"):
        anuncio = next(
            (m for p in bloque.css("p") if (m := _ANUNCIO.fullmatch(texto(p) or ""))), None
        )
        if anuncio is None:
            continue
        precio = next((m for h in bloque.css("h3") if (m := _PRECIO.search(texto(h) or ""))), None)
        tarjeta: Tarjeta = {
            "codigo": anuncio.group(1),
            "barrio": anuncio.group(2).strip() or None,
            "precio": precio.group(1) if precio else None,
            "alcobas": None,
            "banos": None,
            "parqueaderos": None,
            "area": None,
        }
        for icono in bloque.css("i"):
            clases = (icono.attributes.get("class") or "").split()
            for clase, campo in _ICONOS.items():
                if clase in clases:
                    tarjeta[campo] = _valor_del_icono(icono)
        tarjetas.append(tarjeta)
    return tarjetas


def extraer_ficha(html: str) -> dict[str, str]:
    """Tabla de la ficha como ``etiqueta → valor`` (con las entidades HTML ya convertidas)."""
    ficha: dict[str, str] = {}
    for fila in analizar(html).css("table.table-striped tr"):
        celdas = fila.css("td")
        if len(celdas) < 2:
            continue
        etiqueta, valor = texto(celdas[0]), texto(celdas[1])
        if etiqueta and valor:
            ficha[etiqueta] = valor
    return ficha


def mapear_anuncio(
    tarjeta: Tarjeta,
    ficha: dict[str, str] | None,
    operacion: Operacion,
    tipo: str,
    municipio: str,
    fecha: date,
) -> AnuncioNormalizado:
    """Convierte una tarjeta (y su ficha, si la hay) en un anuncio normalizado.

    Lanza ``ValidationError`` si no es válido, p. ej. si no trae código.
    """
    f = ficha or {}
    codigo = tarjeta.get("codigo")
    return AnuncioNormalizado.model_validate(
        {
            "fuente": FuentePanorama.nombre,
            "id_fuente": codigo,
            "url": f"{URL_BASE}/Ficha.asp?xId={codigo}" if codigo else None,
            "fecha_observacion": fecha,
            "operacion": operacion,
            "tipo_inmueble": tipo,
            "precio": parsear_precio(tarjeta.get("precio")),
            # "cop $0" es la forma del sitio de decir que no hay dato.
            "administracion": parsear_precio(f.get("Valor Administracion")),
            "area_m2": parsear_area(tarjeta.get("area") or f.get("Area total")),
            "habitaciones": parsear_conteo(tarjeta.get("alcobas")),
            "banos": parsear_conteo(tarjeta.get("banos")),
            "parqueaderos": parsear_conteo(tarjeta.get("parqueaderos")),
            "estrato": parsear_estrato(f.get("Estrato")),
            # La ficha trae el barrio con mayúsculas normales; la tarjeta, en mayúsculas.
            "barrio": f.get("Barrio / Sector") or tarjeta.get("barrio"),
            "municipio": municipio,
        }
    )


class FuentePanorama:
    """Recorre Panorama por operación, tipo de inmueble y municipio."""

    nombre = "panorama"

    def __init__(
        self,
        cliente: ClienteCortes,
        *,
        con_detalle: bool = True,
        max_paginas: int | None = None,
        fecha: date | None = None,
    ) -> None:
        """``con_detalle`` pide la ficha (estrato) de los inmuebles residenciales.

        ``max_paginas`` limita las páginas de cada operación, tipo y municipio.
        """
        self._cliente = cliente
        self._con_detalle = con_detalle
        self._max_paginas = max_paginas
        self._fecha = fecha or date.today()

    @staticmethod
    def necesita_ficha(tipo: int) -> bool:
        return tipo in TIPOS_RESIDENCIALES

    def listar_anuncios(self) -> Iterator[AnuncioNormalizado]:
        for operacion, (descubrir, listado) in OPERACIONES.items():
            vistos: set[str] = set()
            for codigo_tipo, tipo in TIPOS.items():
                ciudades = self._ciudades(descubrir, codigo_tipo)
                for ciudad, municipio in MUNICIPIOS.items():
                    if ciudad not in ciudades:
                        continue
                    for tarjeta in self._tarjetas(listado, ciudad, codigo_tipo):
                        codigo = tarjeta.get("codigo")
                        if codigo is not None:
                            if codigo in vistos:
                                continue
                            vistos.add(codigo)
                        ficha = None
                        if self._con_detalle and codigo and self.necesita_ficha(codigo_tipo):
                            ficha = self._ficha(codigo)
                        try:
                            yield mapear_anuncio(
                                tarjeta, ficha, operacion, tipo, municipio, self._fecha
                            )
                        except ValidationError as error:
                            logger.warning(
                                "Anuncio %s omitido por datos inválidos: %s", codigo, error
                            )

    def _html(self, ruta: str, params: dict[str, str | int]) -> str:
        return decodificar(self._cliente.get_bytes(ruta, params=params))

    def _ciudades(self, ruta: str, tipo: int) -> set[int]:
        return extraer_ciudades(self._html(ruta, {"sZona": tipo}))

    def _tarjetas(self, ruta: str, ciudad: int, tipo: int) -> Iterator[Tarjeta]:
        pagina, paginas = 0, 1
        while pagina < paginas:
            html = self._html(
                ruta,
                {"pCiudad": ciudad, "pTipoInmueble": tipo, "offset": pagina * TAMANO_PAGINA},
            )
            if pagina == 0:
                paginas = extraer_paginas(html)
            yield from extraer_tarjetas(html)
            pagina += 1
            if self._max_paginas is not None and pagina >= self._max_paginas:
                return

    def _ficha(self, codigo: str) -> dict[str, str] | None:
        try:
            return extraer_ficha(self._html("/Ficha.asp", {"xId": codigo}))
        except ErrorDeDescarga as error:
            logger.warning("Sin ficha para el anuncio %s (%s); se usa el listado", codigo, error)
            return None
