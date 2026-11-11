"""Adaptador de Alnago (https://alnago.com).

El sitio usa el CRM Wasi y consulta una API JSON en otro host, ``api.alnago.com``:

* ``GET /property/map?for_rent=true&for_sale=false&id_city=<id Wasi>`` (o al revés para
  venta) devuelve ``{total, items[]}`` con **todos** los inmuebles del municipio en una sola
  respuesta: no hay paginación.

Sobre robots.txt: ``alnago.com/robots.txt`` prohíbe ``/api/`` en *su propio* dominio. La API
está en ``api.alnago.com``, cuyo robots.txt no tiene reglas, y es la que llama el navegador
de cualquier visitante. RFC 9309 aplica el robots.txt de cada host, y así lo hace el
cliente. Se hace una sola petición por municipio y operación.

Alnago no publica el estrato ni la administración, y la respuesta no trae el municipio: se
toma del municipio consultado.
"""

import logging
from collections.abc import Iterator
from datetime import date
from typing import Any, Final

from pydantic import ValidationError

from observatorio_inmobiliario.http import ClienteCortes
from observatorio_inmobiliario.modelos import AnuncioNormalizado, Operacion
from observatorio_inmobiliario.parseo import (
    parsear_area,
    parsear_conteo,
    parsear_coordenada,
    parsear_precio,
)

logger = logging.getLogger(__name__)

URL_BASE: Final = "https://api.alnago.com"
"""Host de la API, que es el que consulta el cliente HTTP."""
URL_SITIO: Final = "https://alnago.com"
"""Sitio público, para armar el enlace de cada anuncio."""

MUNICIPIOS: Final[dict[int, str]] = {
    496: "Medellín",
    89: "Bello",
    389: "Itagüí",
    291: "Envigado",
    698: "Sabaneta",
    416: "La Estrella",
    130: "Caldas",
    219: "Copacabana",
}
"""Municipios del Valle de Aburrá con su id de ciudad en Wasi (de la página ``/es/categorias``)."""

FILTROS_OPERACION: Final = {
    Operacion.ARRIENDO: {"for_rent": "true", "for_sale": "false"},
    Operacion.VENTA: {"for_rent": "false", "for_sale": "true"},
}

TIPOS: Final[dict[int, str]] = {
    1: "casa",
    2: "apartamento",
    3: "local",
    4: "oficina",
    15: "oficina",
    5: "lote",
    6: "lote",
    32: "lote",
    7: "finca",
    11: "finca",
    28: "finca",
    8: "bodega",
    16: "bodega",
    14: "apartaestudio",
    26: "garaje",
}
"""``id_property_type`` de Wasi agrupado igual que en el buscador del sitio."""


def mapear_anuncio(
    item: dict[str, Any], operacion: Operacion, municipio: str, fecha: date
) -> AnuncioNormalizado:
    """Convierte un item del mapa en un anuncio de la ``operacion`` y el ``municipio`` consultados.

    Lanza ``ValidationError`` si no es válido, p. ej. si no trae ``id_property``.
    """
    id_ = item.get("id_property")
    tipo = item.get("id_property_type")

    return AnuncioNormalizado.model_validate(
        {
            "fuente": FuenteAlnago.nombre,
            "id_fuente": None if id_ is None else str(id_),
            "url": None if id_ is None else f"{URL_SITIO}/es/inmueble/{id_}",
            "fecha_observacion": fecha,
            "operacion": operacion,
            "tipo_inmueble": TIPOS.get(tipo) if isinstance(tipo, int) else None,
            "precio": parsear_precio(item.get("price")),
            "area_m2": parsear_area(item.get("area")),
            "habitaciones": parsear_conteo(item.get("beds")),
            "banos": parsear_conteo(item.get("baths")),
            "parqueaderos": parsear_conteo(item.get("garages")),
            "barrio": item.get("zone"),
            "municipio": municipio,
            "latitud": parsear_coordenada(item.get("lat"), limite=90),
            "longitud": parsear_coordenada(item.get("lng")),
        }
    )


class FuenteAlnago:
    """Pide el mapa de arriendos y ventas de Alnago en cada municipio del Valle de Aburrá."""

    nombre = "alnago"

    def __init__(
        self,
        cliente: ClienteCortes,
        *,
        con_detalle: bool = True,
        max_paginas: int | None = None,
        fecha: date | None = None,
    ) -> None:
        """``con_detalle`` y ``max_paginas`` no tienen efecto.

        La API no tiene página de detalle y devuelve todo el municipio en una sola respuesta.
        """
        self._cliente = cliente
        self._fecha = fecha or date.today()

    def listar_anuncios(self) -> Iterator[AnuncioNormalizado]:
        for operacion, filtros in FILTROS_OPERACION.items():
            for id_ciudad, municipio in MUNICIPIOS.items():
                datos = self._cliente.get_json(
                    "/property/map", params={**filtros, "id_city": id_ciudad}
                )
                for item in datos.get("items") or []:
                    try:
                        yield mapear_anuncio(item, operacion, municipio, self._fecha)
                    except ValidationError as error:
                        logger.warning(
                            "Anuncio %s omitido por datos inválidos: %s",
                            item.get("id_property"),
                            error,
                        )
