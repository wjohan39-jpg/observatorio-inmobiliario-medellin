"""Adaptador de Arrendamientos Villacruz (https://www.arrendamientosvillacruz.com.co).

El sitio (Laravel + Livewire) solo muestra 36 resultados por búsqueda; para ver más hay que
hacer peticiones POST de Livewire, que no se imitan. En cambio publica un sitemap completo:

1. ``GET /sitemaps/villacruz/sitemap.xml`` lista cada anuncio como
   ``/detalle-propiedad/<tipo>-<enarriendo|enventa>-en-<lugar>-<código>``.
2. ``GET /detalle-propiedad/<slug>`` trae los datos en ``let property= {...};``.

**Solo se toma el inventario propio** (decisión del autor). Las ventas compartidas de otras
agencias (MLS) usan ``-en-venta-en-`` en el slug y se descartan: son ~4.400, no dicen qué
agencia las publica e inflarían a Villacruz en los rankings.

``neighborhood`` trae a veces el barrio ("LAURELES") y a veces el municipio ("BELLO"). Si
no es un municipio, el municipio queda en ``None`` y lo resuelve la etapa de limpieza.
"""

import json
import logging
import re
import unicodedata
from collections.abc import Iterator
from datetime import date
from typing import Any, Final

from pydantic import ValidationError

from observatorio_inmobiliario.http import ClienteCortes, ErrorDeDescarga
from observatorio_inmobiliario.modelos import AnuncioNormalizado, Operacion
from observatorio_inmobiliario.parseo import (
    parsear_area,
    parsear_conteo,
    parsear_coordenada,
    parsear_estrato,
    parsear_precio,
)

logger = logging.getLogger(__name__)

URL_BASE: Final = "https://www.arrendamientosvillacruz.com.co"
RUTA_SITEMAP: Final = "/sitemaps/villacruz/sitemap.xml"

LUGARES_FUERA_DEL_VALLE: Final = frozenset(
    {
        "rionegro",
        "san-jeronimo",
        "sopetran",
        "retiro",
        "el-retiro",
        "amaga",
        "san-pedro-de-los-milagros",
        "cabaas",
        "guarne",
        "marinilla",
        "peol",
        "el-carmen-de-viboral",
        "jardin",
        "santa-fe-de-antioquia",
        "la-ceja",
    }
)
"""Lugares del slug que están fuera del Valle de Aburrá (revisión del 2026-11-11)."""

MUNICIPIOS: Final[dict[str, str]] = {
    "medellin": "Medellín",
    "bello": "Bello",
    "itagui": "Itagüí",
    "envigado": "Envigado",
    "sabaneta": "Sabaneta",
    "la estrella": "La Estrella",
    "caldas": "Caldas",
    "copacabana": "Copacabana",
    "girardota": "Girardota",
    "barbosa": "Barbosa",
}
"""``neighborhood`` normalizado (minúsculas, sin tildes) → municipio."""

OPERACIONES: Final = {
    "arriendo": Operacion.ARRIENDO,
    "amoblado": Operacion.ARRIENDO,  # arriendo amoblado
    "venta": Operacion.VENTA,
}

DETALLES_POR_PAGINA: Final = 12
"""Para ``max_paginas``: cada "página" equivale a esta cantidad de detalles."""

_SLUG_PROPIO: Final = re.compile(r"^(?P<tipo>.+?)-(?P<op>enarriendo|enventa)-en-(?P<lugar>.+)-\d+$")
_LOC: Final = re.compile(r"<loc>[^<]*/detalle-propiedad/([^<\s]+)</loc>")
_INICIO_PROPIEDAD: Final = "let property= "


def slugs_propios(sitemap: str) -> list[str]:
    """Slugs del inventario propio dentro del Valle de Aburrá, en el orden del sitemap."""
    slugs: list[str] = []
    for slug in _LOC.findall(sitemap):
        coincidencia = _SLUG_PROPIO.match(slug)
        if coincidencia is None or coincidencia.group("lugar") in LUGARES_FUERA_DEL_VALLE:
            continue
        if slug not in slugs:
            slugs.append(slug)
    return slugs


def extraer_propiedad(html: str) -> dict[str, Any] | None:
    """El objeto ``let property= {...};`` de la página, o ``None`` si no está."""
    inicio = html.find(_INICIO_PROPIEDAD)
    if inicio == -1:
        return None
    try:
        propiedad, _ = json.JSONDecoder().raw_decode(html, inicio + len(_INICIO_PROPIEDAD))
    except ValueError:
        return None
    return propiedad if isinstance(propiedad, dict) else None


def _normalizar(texto: str) -> str:
    sin_tildes = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return " ".join(sin_tildes.lower().split())


def mapear_anuncio(propiedad: dict[str, Any], slug: str, fecha: date) -> AnuncioNormalizado:
    """Convierte la propiedad de una página de detalle en un anuncio normalizado.

    Lanza ``ValidationError`` si no es válida, p. ej. una gestión desconocida.
    """
    gestion = propiedad.get("management")
    barrio = propiedad.get("neighborhood")
    tipo = propiedad.get("property_type")
    return AnuncioNormalizado.model_validate(
        {
            "fuente": FuenteVillacruz.nombre,
            "id_fuente": propiedad.get("code"),
            "url": f"{URL_BASE}/detalle-propiedad/{slug}",
            "fecha_observacion": fecha,
            "operacion": OPERACIONES.get(_normalizar(gestion), gestion)
            if isinstance(gestion, str)
            else gestion,
            "tipo_inmueble": tipo,
            "precio": parsear_precio(propiedad.get("price_new")),
            "area_m2": parsear_area(propiedad.get("area")),
            "habitaciones": parsear_conteo(propiedad.get("bedrooms")),
            "banos": parsear_conteo(propiedad.get("bathrooms")),
            "parqueaderos": parsear_conteo(propiedad.get("garage")),
            "estrato": parsear_estrato(propiedad.get("stratum")),
            "barrio": barrio,
            "municipio": MUNICIPIOS.get(_normalizar(barrio)) if isinstance(barrio, str) else None,
            "latitud": parsear_coordenada(propiedad.get("latitude"), limite=90),
            "longitud": parsear_coordenada(propiedad.get("longitude")),
        }
    )


class FuenteVillacruz:
    """Recorre el sitemap de Villacruz y pide el detalle de cada anuncio propio."""

    nombre = "villacruz"

    def __init__(
        self,
        cliente: ClienteCortes,
        *,
        con_detalle: bool = True,
        max_paginas: int | None = None,
        fecha: date | None = None,
    ) -> None:
        """``con_detalle`` no tiene efecto: el detalle es la única fuente de datos.

        ``max_paginas=N`` limita a ``N × 12`` páginas de detalle, para corridas de prueba.
        """
        self._cliente = cliente
        self._max_detalles = None if max_paginas is None else max_paginas * DETALLES_POR_PAGINA
        self._fecha = fecha or date.today()

    def listar_anuncios(self) -> Iterator[AnuncioNormalizado]:
        slugs = slugs_propios(self._cliente.get_texto(RUTA_SITEMAP))
        if self._max_detalles is not None:
            slugs = slugs[: self._max_detalles]
        for slug in slugs:
            propiedad = self._propiedad(slug)
            if propiedad is None:
                continue
            try:
                yield mapear_anuncio(propiedad, slug, self._fecha)
            except ValidationError as error:
                logger.warning("Anuncio %s omitido por datos inválidos: %s", slug, error)

    def _propiedad(self, slug: str) -> dict[str, Any] | None:
        try:
            html = self._cliente.get_texto(f"/detalle-propiedad/{slug}")
        except ErrorDeDescarga as error:
            logger.warning("Anuncio %s omitido: no se pudo descargar (%s)", slug, error)
            return None
        propiedad = extraer_propiedad(html)
        if propiedad is None:
            # Un anuncio retirado redirige a la portada, que no trae los datos.
            logger.warning("Anuncio %s omitido: la página no trae sus datos", slug)
        return propiedad
