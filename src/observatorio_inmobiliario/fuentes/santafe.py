"""Adaptador de Arrendamientos Santa Fe (https://arrendamientossantafe.com).

El sitio expone una API JSON:

* Listado: ``GET /apisf/properties?page=N&oferta=Arriendo|Venta`` devuelve
  ``{total, page, per_page, has_more, results[]}``.
* Detalle: ``GET /apisf/property/{codigo}`` añade estrato, parqueaderos y área exacta.
"""

import logging
from collections.abc import Iterator
from datetime import date
from typing import Any, Final

from pydantic import ValidationError

from observatorio_inmobiliario.http import ClienteCortes, ErrorDeDescarga
from observatorio_inmobiliario.modelos import AnuncioNormalizado
from observatorio_inmobiliario.parseo import (
    parsear_area,
    parsear_conteo,
    parsear_coordenada,
    parsear_estrato,
    parsear_precio,
)

logger = logging.getLogger(__name__)

URL_BASE: Final = "https://arrendamientossantafe.com"
OFERTAS: Final = ("Arriendo", "Venta")
"""Valores del parámetro ``oferta`` que acepta la API."""


def _primero(*valores: Any) -> Any:
    """El primer valor que no sea ``None``. Así el detalle tiene prioridad sobre el listado."""
    return next((v for v in valores if v is not None), None)


def mapear_anuncio(
    resultado: dict[str, Any], detalle: dict[str, Any] | None, fecha: date
) -> AnuncioNormalizado:
    """Convierte un resultado del listado (y su detalle, si lo hay) en un anuncio normalizado.

    Lanza ``ValidationError`` si el anuncio no es válido, p. ej. una oferta desconocida.
    """
    d = detalle or {}
    codigo = resultado.get("codigo")
    oferta = _primero(d.get("oferta"), resultado.get("oferta"))
    url = _primero(d.get("url"), resultado.get("url"))
    if isinstance(url, str) and url.startswith("/"):
        url = URL_BASE + url

    latitud = parsear_coordenada(_primero(d.get("lat"), resultado.get("lat")), limite=90)
    longitud = parsear_coordenada(_primero(d.get("lng"), resultado.get("lng")))
    if d.get("tiene_coords") is False:
        latitud = longitud = None

    # model_validate (y no el constructor) porque los datos vienen crudos de la API:
    # Pydantic se encarga de validarlos y de convertir, p. ej., "arriendo" en Operacion.
    return AnuncioNormalizado.model_validate(
        {
            "fuente": FuenteSantaFe.nombre,
            "id_fuente": None if codigo is None else str(codigo),
            "url": url,
            "fecha_observacion": fecha,
            "operacion": oferta.lower() if isinstance(oferta, str) else oferta,
            "tipo_inmueble": _primero(d.get("tipo"), resultado.get("type")),
            "precio": parsear_precio(_primero(d.get("price_raw"), resultado.get("price_raw"))),
            "area_m2": parsear_area(_primero(d.get("area"), resultado.get("size"))),
            "habitaciones": parsear_conteo(
                _primero(d.get("habitaciones"), resultado.get("bedrooms"))
            ),
            "banos": parsear_conteo(_primero(d.get("banos"), resultado.get("bathrooms"))),
            "parqueaderos": parsear_conteo(d.get("parqueaderos")),
            "estrato": parsear_estrato(d.get("estrato")),
            "barrio": _primero(d.get("sector"), resultado.get("location")),
            "municipio": _primero(d.get("ciudad"), resultado.get("ciudad")),
            "latitud": latitud,
            "longitud": longitud,
        }
    )


class FuenteSantaFe:
    """Recorre los listados de arriendo y venta de Santa Fe, página por página."""

    nombre = "santafe"

    def __init__(
        self,
        cliente: ClienteCortes,
        *,
        con_detalle: bool = True,
        max_paginas: int | None = None,
        fecha: date | None = None,
    ) -> None:
        self._cliente = cliente
        self._con_detalle = con_detalle
        self._max_paginas = max_paginas
        self._fecha = fecha or date.today()

    def listar_anuncios(self) -> Iterator[AnuncioNormalizado]:
        for oferta in OFERTAS:
            for resultado in self._resultados(oferta):
                detalle = self._detalle(resultado) if self._con_detalle else None
                try:
                    yield mapear_anuncio(resultado, detalle, self._fecha)
                except ValidationError as error:
                    logger.warning(
                        "Anuncio %s omitido por datos inválidos: %s",
                        resultado.get("codigo"),
                        error,
                    )

    def _resultados(self, oferta: str) -> Iterator[dict[str, Any]]:
        pagina = 1
        while True:
            datos = self._cliente.get_json(
                "/apisf/properties", params={"page": pagina, "oferta": oferta}
            )
            yield from datos.get("results", [])
            if not datos.get("has_more"):
                return
            if self._max_paginas is not None and pagina >= self._max_paginas:
                return
            pagina += 1

    def _detalle(self, resultado: dict[str, Any]) -> dict[str, Any] | None:
        codigo = resultado.get("codigo")
        if not codigo:
            return None
        try:
            detalle: dict[str, Any] = self._cliente.get_json(f"/apisf/property/{codigo}")
        except ErrorDeDescarga as error:
            logger.warning(
                "Sin detalle para el anuncio %s (%s); se usa solo el listado", codigo, error
            )
            return None
        return detalle
