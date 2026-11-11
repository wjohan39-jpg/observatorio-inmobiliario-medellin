"""Adaptador de Activo Urbano (https://activourbano.com.co).

El sitio es WordPress + WooCommerce con Elementor. Sus API (``/wp-json/``) responden 403 y
**no se intenta evitarlo**: se lee el HTML público.

* Listado: ``GET /inmuebles/?jsf=epro-loop-builder:products&pagenum=N``, 6 tarjetas por
  página, ordenadas de la más nueva a la más vieja. ``/page/N/`` no pagina en este sitio.
  ``JetSmartFilterSettings`` trae ``"found_posts":480,"max_num_pages":80``.
* Las clases de cada tarjeta dicen la operación (``product_cat-en-arriendo``), el municipio
  y el barrio (``ubicacion-…``) y el tipo (``tipo-de-propiedad-…``).
* Detalle: ``/propiedades/inmueble/<código>/``. Solo se pide para el estrato y los
  parqueaderos; no tiene coordenadas ni administración.

Los términos del sitio reservan su propiedad intelectual: el proyecto solo publica agregados.
"""

import logging
import re
from collections.abc import Iterator
from datetime import date
from typing import Final

from pydantic import ValidationError

from observatorio_inmobiliario.html import analizar, texto
from observatorio_inmobiliario.http import ClienteCortes, ErrorDeDescarga
from observatorio_inmobiliario.modelos import AnuncioNormalizado, Operacion
from observatorio_inmobiliario.parseo import (
    parsear_area,
    parsear_conteo,
    parsear_estrato,
    parsear_precio,
)

logger = logging.getLogger(__name__)

URL_BASE: Final = "https://activourbano.com.co"
RUTA_LISTADO: Final = "/inmuebles/"

MUNICIPIOS: Final[dict[str, str]] = {
    "medellin": "Medellín",
    "envigado": "Envigado",
    "sabaneta": "Sabaneta",
    "itagui": "Itagüí",
    "bello": "Bello",
    "la-estrella": "La Estrella",
    "caldas": "Caldas",
    "copacabana": "Copacabana",
    "girardota": "Girardota",
    "barbosa": "Barbosa",
}
"""Municipios del Valle de Aburrá, por su slug en las clases ``ubicacion-…``."""

OPERACIONES: Final = {
    "en-arriendo": Operacion.ARRIENDO,
    "en-venta": Operacion.VENTA,
    # "Ambos" trae un solo precio, rotulado "Valor del arriendo".
    "ambos": Operacion.ARRIENDO,
}

TIPOS: Final[dict[str, str]] = {
    "apartamentos": "apartamento",
    "apartaestudio": "apartaestudio",
    "amoblados": "apartamento amoblado",
    "casa": "casa",
    "oficina": "oficina",
    "bodega": "bodega",
}

type Tarjeta = dict[str, str | None]

_PAGINACION: Final = re.compile(r'"found_posts":(\d+),"max_num_pages":(\d+)')
_CODIGO: Final = re.compile(r"AU\s*-\s*(\d+)")
_SUFIJO_NUMERICO: Final = re.compile(r"-\d+$")
_ICONOS: Final = {
    "gicon-full-screen": "area",
    "gicon-habitaciones": "alcobas",
    "gicon-baths": "banos",
}
_ETIQUETAS_DETALLE: Final = {"Estrato": "estrato", "Parqueadero": "parqueaderos"}


def extraer_paginacion(html: str) -> tuple[int, int]:
    """``(found_posts, max_num_pages)``; ``(0, 0)`` si la página no lo trae."""
    coincidencia = _PAGINACION.search(html)
    if coincidencia is None:
        return 0, 0
    return int(coincidencia.group(1)), int(coincidencia.group(2))


def _con_prefijo(clases: list[str], prefijo: str) -> list[str]:
    return [c.removeprefix(prefijo) for c in clases if c.startswith(prefijo)]


def extraer_tarjetas(html: str) -> list[Tarjeta]:
    """Datos crudos de cada tarjeta del listado (excluye las del blog en el pie de página)."""
    tarjetas: list[Tarjeta] = []
    for item in analizar(html).css("#products .elementor-loop-container > .e-loop-item.product"):
        clases = (item.attributes.get("class") or "").split()
        ubicaciones = _con_prefijo(clases, "ubicacion-")
        municipio = next((u for u in ubicaciones if u in MUNICIPIOS), None)
        barrio = next((u for u in ubicaciones if u != municipio), None)
        # El código se busca encabezado por encabezado: el texto de toda la tarjeta une
        # widgets vecinos sin espacio ("AU - 1" + "70 m²" se leería "AU - 170").
        codigos = (_CODIGO.fullmatch(texto(h) or "") for h in item.css(".elementor-widget-heading"))
        codigo = next((c for c in codigos if c is not None), None)
        tarjeta: Tarjeta = {
            "codigo": codigo.group(1) if codigo else None,
            "operacion": next(iter(_con_prefijo(clases, "product_cat-")), None),
            "municipio_slug": municipio,
            "barrio_slug": barrio,
            "tipo_slug": next(iter(_con_prefijo(clases, "tipo-de-propiedad-")), None),
            "precio": texto(item.css_first(".woocommerce-Price-amount")),
            "area": None,
            "alcobas": None,
            "banos": None,
        }
        # Los widgets van en orden: un icono y, después, el encabezado con su valor.
        # Se toma la primera aparición (versión de escritorio; luego se repite para móvil).
        pendiente: str | None = None
        for widget in item.css(".elementor-widget-icon, .elementor-widget-heading"):
            clases_widget = widget.attributes.get("class") or ""
            if "elementor-widget-icon" in clases_widget:
                icono = widget.css_first("i")
                clases_icono = (icono.attributes.get("class") or "").split() if icono else []
                pendiente = next((_ICONOS[c] for c in clases_icono if c in _ICONOS), None)
            elif pendiente is not None:
                if tarjeta[pendiente] is None:
                    tarjeta[pendiente] = texto(widget)
                pendiente = None
        tarjetas.append(tarjeta)
    return tarjetas


def extraer_detalle(html: str) -> dict[str, str | None]:
    """Estrato y parqueaderos de la página de detalle.

    Cada dato es un contenedor con el valor y su etiqueta. Si falta el valor (p. ej. sin
    parqueadero), el contenedor solo trae la etiqueta y el dato queda en ``None``.
    """
    detalle: dict[str, str | None] = {"estrato": None, "parqueaderos": None}
    for contenedor in analizar(html).css(".e-con"):
        encabezados = [texto(h) for h in contenedor.css(".elementor-widget-heading")]
        if not encabezados or len(encabezados) > 2:
            continue
        campo = _ETIQUETAS_DETALLE.get(encabezados[-1] or "")
        if campo is not None:
            detalle[campo] = encabezados[0] if len(encabezados) == 2 else None
    return detalle


def _barrio(slug: str | None) -> str | None:
    """``ciudad-del-rio-3`` → ``ciudad del rio`` (WordPress agrega ``-N`` a slugs repetidos)."""
    if not slug:
        return None
    return _SUFIJO_NUMERICO.sub("", slug).replace("-", " ") or None


def mapear_anuncio(
    tarjeta: Tarjeta, detalle: dict[str, str | None] | None, fecha: date
) -> AnuncioNormalizado:
    """Convierte una tarjeta (y su detalle, si lo hay) en un anuncio normalizado.

    Lanza ``ValidationError`` si no es válido, p. ej. una operación desconocida.
    """
    d = detalle or {}
    codigo = tarjeta.get("codigo")
    slug_operacion = tarjeta.get("operacion")
    slug_tipo = tarjeta.get("tipo_slug")
    slug_municipio = tarjeta.get("municipio_slug")

    return AnuncioNormalizado.model_validate(
        {
            "fuente": FuenteActivoUrbano.nombre,
            "id_fuente": codigo,
            "url": f"{URL_BASE}/propiedades/inmueble/{codigo}/" if codigo else None,
            "fecha_observacion": fecha,
            "operacion": OPERACIONES.get(slug_operacion or "", slug_operacion),
            "tipo_inmueble": TIPOS.get(slug_tipo or "", (slug_tipo or "").replace("-", " ")),
            "precio": parsear_precio(tarjeta.get("precio")),
            "area_m2": parsear_area(tarjeta.get("area")),
            "habitaciones": parsear_conteo(tarjeta.get("alcobas")),
            "banos": parsear_conteo(tarjeta.get("banos")),
            "parqueaderos": parsear_conteo(d.get("parqueaderos")),
            "estrato": parsear_estrato(d.get("estrato")),
            "barrio": _barrio(tarjeta.get("barrio_slug")),
            "municipio": MUNICIPIOS.get(slug_municipio or ""),
        }
    )


class FuenteActivoUrbano:
    """Recorre el listado completo de Activo Urbano y pide el detalle de cada anuncio."""

    nombre = "activourbano"

    def __init__(
        self,
        cliente: ClienteCortes,
        *,
        con_detalle: bool = True,
        max_paginas: int | None = None,
        fecha: date | None = None,
    ) -> None:
        """``con_detalle=False`` omite el estrato y los parqueaderos (corrida más corta).

        ``max_paginas`` limita las páginas del listado (6 anuncios cada una).
        """
        self._cliente = cliente
        self._con_detalle = con_detalle
        self._max_paginas = max_paginas
        self._fecha = fecha or date.today()

    def listar_anuncios(self) -> Iterator[AnuncioNormalizado]:
        vistos: set[str] = set()
        for tarjeta in self._tarjetas():
            codigo = tarjeta.get("codigo")
            if codigo is not None:
                if codigo in vistos:
                    continue  # el sitio tiene anuncios republicados con el mismo código
                vistos.add(codigo)
            if tarjeta.get("municipio_slug") is None:
                continue  # fuera del Valle de Aburrá
            detalle = self._detalle(codigo) if self._con_detalle and codigo else None
            try:
                yield mapear_anuncio(tarjeta, detalle, self._fecha)
            except ValidationError as error:
                logger.warning("Anuncio %s omitido por datos inválidos: %s", codigo, error)

    def _tarjetas(self) -> Iterator[Tarjeta]:
        pagina = 1
        while True:
            html = self._cliente.get_texto(
                RUTA_LISTADO, params={"jsf": "epro-loop-builder:products", "pagenum": pagina}
            )
            _, paginas = extraer_paginacion(html)
            tarjetas = extraer_tarjetas(html)
            if not tarjetas:
                return
            yield from tarjetas
            if pagina >= paginas:
                return
            if self._max_paginas is not None and pagina >= self._max_paginas:
                return
            pagina += 1

    def _detalle(self, codigo: str) -> dict[str, str | None] | None:
        try:
            return extraer_detalle(self._cliente.get_texto(f"/propiedades/inmueble/{codigo}/"))
        except ErrorDeDescarga as error:
            logger.warning("Sin detalle para el anuncio %s (%s); se usa el listado", codigo, error)
            return None
