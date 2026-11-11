"""Adaptador de Puertabierta (https://puertabierta.com.co). Solo publica arriendos.

El sitio usa Next.js (App Router). Los anuncios no están en el HTML visible sino en el
JSON de React Server Components que la página trae embebido::

    <script>self.__next_f.push([1, "7:[...{\\"state\\":{\\"queries\\":[...]}}]\\n"])</script>

* Listado: ``GET /arriendos/<municipio>?page=N``, 36 anuncios por página. La consulta
  ``["properties", "search", …]`` trae ``{hits, found, page, totalPages, perPage}``.
* Una página después de la última responde 404.

Por los términos del sitio solo se guardan datos de hecho: nunca la dirección, el número
de apartamento, las fotos ni la descripción.
"""

import json
import logging
from collections.abc import Iterator
from datetime import date
from typing import Any, Final

from pydantic import ValidationError

from observatorio_inmobiliario.http import ClienteCortes, ErrorDeDescarga, es_404
from observatorio_inmobiliario.modelos import AnuncioNormalizado, Operacion
from observatorio_inmobiliario.parseo import (
    parsear_area,
    parsear_conteo,
    parsear_coordenada,
    parsear_precio,
)

logger = logging.getLogger(__name__)

URL_BASE: Final = "https://puertabierta.com.co"

MUNICIPIOS: Final[dict[str, str]] = {
    "medellin": "Medellín",
    "envigado": "Envigado",
    "sabaneta": "Sabaneta",
    "itagui": "Itagüí",
    "la-estrella": "La Estrella",
}
"""Municipios del Valle de Aburrá con inventario, por su ruta en el sitio.

El nombre se toma de aquí y no del anuncio, que a veces escribe "Medellin" o "Itagüi".
"""

TIPOS: Final = ("apartaestudio", "penthouse", "casa", "apartamento")
"""Tipos que se reconocen en el título, en este orden ("apartaestudio" contiene "apart")."""

_INICIO_PUSH: Final = "self.__next_f.push("
_FIN_PUSH: Final = ")</script>"


def _flujo_rsc(html: str) -> str:
    """Une, en orden, el texto de todos los ``self.__next_f.push([1, "..."])`` de la página."""
    partes: list[str] = []
    inicio = html.find(_INICIO_PUSH)
    while inicio != -1:
        inicio += len(_INICIO_PUSH)
        fin = html.find(_FIN_PUSH, inicio)
        if fin == -1:
            break
        try:
            bloque = json.loads(html[inicio:fin])
        except ValueError:
            bloque = None
        if isinstance(bloque, list) and len(bloque) == 2 and bloque[0] == 1:
            partes.append(str(bloque[1]))
        inicio = html.find(_INICIO_PUSH, fin)
    return "".join(partes)


def extraer_busqueda(html: str) -> dict[str, Any] | None:
    """Resultado de la búsqueda (``{hits, found, page, totalPages, perPage}``) o ``None``."""
    for linea in _flujo_rsc(html).split("\n"):
        if '"queries"' not in linea or '"hits"' not in linea:
            continue
        _, _, cuerpo = linea.partition(":")
        try:
            datos = json.loads(cuerpo)
            consultas = datos[3]["state"]["queries"]
        except (ValueError, LookupError, TypeError):
            continue
        for consulta in consultas:
            if consulta.get("queryKey", [])[:2] == ["properties", "search"]:
                resultado = consulta.get("state", {}).get("data")
                if isinstance(resultado, dict):
                    return resultado
    return None


def tipo_desde_titulo(titulo: str | None) -> str | None:
    """El sitio no tiene un campo de tipo: se deduce del título ("Apartaestudio en …")."""
    if not titulo:
        return None
    minusculas = titulo.lower()
    return next((tipo for tipo in TIPOS if tipo in minusculas), None)


def mapear_anuncio(hit: dict[str, Any], municipio: str, fecha: date) -> AnuncioNormalizado:
    """Convierte un anuncio de la búsqueda en un anuncio normalizado.

    Lanza ``ValidationError`` si no es válido, p. ej. si no trae ``id``.
    """
    precio = hit.get("pricing") or {}
    plano = hit.get("layout") or {}
    ubicacion = hit.get("location") or {}
    id_ = hit.get("id")

    return AnuncioNormalizado.model_validate(
        {
            "fuente": FuentePuertabierta.nombre,
            "id_fuente": id_,
            "url": f"{URL_BASE}/propiedades/{id_}" if id_ else None,
            "fecha_observacion": fecha,
            "operacion": Operacion.ARRIENDO,
            "tipo_inmueble": tipo_desde_titulo(hit.get("title")),
            "precio": parsear_precio(precio.get("monthlyRent")),
            # El arriendo se publica sin administración; 0 significa "no la reportó".
            "administracion": parsear_precio(precio.get("monthlyAdministrationFee")),
            "area_m2": parsear_area(plano.get("areaM2")),
            "habitaciones": parsear_conteo(plano.get("numBedrooms")),
            "banos": parsear_conteo(plano.get("numBathrooms")),
            "parqueaderos": parsear_conteo(plano.get("numParkingLots")),
            "barrio": ubicacion.get("neighborhood") or ubicacion.get("zone"),
            "municipio": municipio,
            "latitud": parsear_coordenada(ubicacion.get("latitude"), limite=90),
            "longitud": parsear_coordenada(ubicacion.get("longitude")),
        }
    )


class FuentePuertabierta:
    """Recorre los arriendos de Puertabierta en cada municipio del Valle de Aburrá."""

    nombre = "puertabierta"

    def __init__(
        self,
        cliente: ClienteCortes,
        *,
        con_detalle: bool = True,
        max_paginas: int | None = None,
        fecha: date | None = None,
    ) -> None:
        """``con_detalle`` no tiene efecto: el detalle no agrega datos de hecho útiles.

        ``max_paginas`` limita las páginas de cada municipio.
        """
        self._cliente = cliente
        self._max_paginas = max_paginas
        self._fecha = fecha or date.today()

    def listar_anuncios(self) -> Iterator[AnuncioNormalizado]:
        vistos: set[str] = set()
        for slug, municipio in MUNICIPIOS.items():
            for hit in self._resultados(slug):
                id_ = hit.get("id")
                if id_ in vistos:
                    continue
                if isinstance(id_, str):
                    vistos.add(id_)
                try:
                    yield mapear_anuncio(hit, municipio, self._fecha)
                except ValidationError as error:
                    logger.warning("Anuncio %s omitido por datos inválidos: %s", id_, error)

    def _resultados(self, slug: str) -> Iterator[dict[str, Any]]:
        pagina = 1
        while True:
            try:
                html = self._cliente.get_texto(f"/arriendos/{slug}", params={"page": pagina})
            except ErrorDeDescarga as error:
                if es_404(error):
                    return  # municipio sin inventario o página después de la última
                raise
            busqueda = extraer_busqueda(html)
            if busqueda is None:
                logger.warning("La página %d de %s no trae la búsqueda", pagina, slug)
                return
            yield from busqueda.get("hits") or []
            if pagina >= (busqueda.get("totalPages") or 0):
                return
            if self._max_paginas is not None and pagina >= self._max_paginas:
                return
            pagina += 1
