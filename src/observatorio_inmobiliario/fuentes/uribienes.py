"""Adaptador de Uribienes (https://uribienes.com).

El sitio usa el CRM Domus y expone una API JSON:

* ``GET /api/properties?city=<código DANE>&biz=1|2&page=N`` devuelve
  ``{total, per_page, current_page, last_page, data[]}``, 12 por página (fijo).
  ``biz=1`` es arriendo y ``biz=2`` es venta. Un inmueble "ARRIENDO/VENTA" aparece en
  ambos, con ``rent`` y ``saleprice`` por separado.

La API trae inmuebles de todo el país, así que se consulta municipio por municipio del
Valle de Aburrá. No se piden las páginas de detalle: el ``robots.txt`` del sitio indica
que no quiere que se rastreen.
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
    parsear_estrato,
    parsear_precio,
)

logger = logging.getLogger(__name__)

URL_BASE: Final = "https://uribienes.com"

MUNICIPIOS: Final[dict[int, str]] = {
    5001: "Medellín",
    5088: "Bello",
    5360: "Itagüí",
    5266: "Envigado",
    5631: "Sabaneta",
    5380: "La Estrella",
    5129: "Caldas",
    5212: "Copacabana",
    5308: "Girardota",
    5079: "Barbosa",
}
"""Municipios del Valle de Aburrá, por código DANE (el parámetro ``city`` de la API)."""

NEGOCIOS: Final = {1: Operacion.ARRIENDO, 2: Operacion.VENTA}
"""Valores del parámetro ``biz`` de la API."""


def mapear_anuncio(
    inmueble: dict[str, Any], operacion: Operacion, fecha: date
) -> AnuncioNormalizado:
    """Convierte un inmueble de la API en un anuncio de la ``operacion`` consultada.

    Lanza ``ValidationError`` si no es válido, p. ej. si no trae código.
    """
    codigo = inmueble.get("codpro")
    precio = inmueble.get("rent" if operacion is Operacion.ARRIENDO else "saleprice")

    return AnuncioNormalizado.model_validate(
        {
            "fuente": FuenteUribienes.nombre,
            "id_fuente": None if codigo is None else str(codigo),
            "url": None if codigo is None else f"{URL_BASE}/inmuebles/{codigo}",
            "fecha_observacion": fecha,
            "operacion": operacion,
            "tipo_inmueble": inmueble.get("type"),
            # parsear_precio convierte los 0 ("sin dato") en None.
            "precio": parsear_precio(precio),
            "administracion": parsear_precio(inmueble.get("administration")),
            "area_m2": parsear_area(inmueble.get("area_cons")),
            "habitaciones": parsear_conteo(inmueble.get("bedrooms")),
            "banos": parsear_conteo(inmueble.get("bathrooms")),
            "parqueaderos": parsear_conteo(inmueble.get("parking")),
            "estrato": parsear_estrato(inmueble.get("stratum")),
            "barrio": inmueble.get("neighborhood"),
            "municipio": inmueble.get("city"),
            "latitud": parsear_coordenada(inmueble.get("latitude"), limite=90),
            "longitud": parsear_coordenada(inmueble.get("longitude")),
        }
    )


class FuenteUribienes:
    """Recorre arriendos y ventas de Uribienes en cada municipio del Valle de Aburrá."""

    nombre = "uribienes"

    def __init__(
        self,
        cliente: ClienteCortes,
        *,
        con_detalle: bool = True,
        max_paginas: int | None = None,
        fecha: date | None = None,
    ) -> None:
        """``con_detalle`` no tiene efecto: no se piden detalles, por respeto al robots.txt.

        ``max_paginas`` limita las páginas de cada municipio y operación.
        """
        self._cliente = cliente
        self._max_paginas = max_paginas
        self._fecha = fecha or date.today()

    def listar_anuncios(self) -> Iterator[AnuncioNormalizado]:
        for biz, operacion in NEGOCIOS.items():
            for codigo in MUNICIPIOS:
                for inmueble in self._resultados(codigo, biz):
                    try:
                        yield mapear_anuncio(inmueble, operacion, self._fecha)
                    except ValidationError as error:
                        logger.warning(
                            "Anuncio %s omitido por datos inválidos: %s",
                            inmueble.get("codpro"),
                            error,
                        )

    def _resultados(self, codigo: int, biz: int) -> Iterator[dict[str, Any]]:
        pagina = 1
        while True:
            datos = self._cliente.get_json(
                "/api/properties", params={"city": codigo, "biz": biz, "page": pagina}
            )
            yield from datos.get("data") or []
            if pagina >= (datos.get("last_page") or 1):
                return
            if self._max_paginas is not None and pagina >= self._max_paginas:
                return
            pagina += 1
