import json
import logging
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

import pytest
import respx

from observatorio_inmobiliario.fuentes import REGISTRO
from observatorio_inmobiliario.fuentes.alnago import (
    MUNICIPIOS,
    URL_BASE,
    FuenteAlnago,
    mapear_anuncio,
)
from observatorio_inmobiliario.fuentes.base import Fuente
from observatorio_inmobiliario.http import ClienteCortes
from observatorio_inmobiliario.modelos import Operacion

FIXTURES = Path(__file__).parent / "fixtures" / "alnago"
FECHA = date(2026, 11, 11)
RUTA = "/property/map"


@pytest.fixture
def mapa() -> dict[str, Any]:
    datos: dict[str, Any] = json.loads(
        (FIXTURES / "mapa_arriendo.json").read_text(encoding="utf-8")
    )
    return datos


@pytest.fixture
def sitio() -> Iterator[respx.MockRouter]:
    """Simula api.alnago.com. Su robots.txt real solo tiene comentarios (sin reglas)."""
    with respx.mock(base_url=URL_BASE, assert_all_called=False) as router:
        router.get("/robots.txt").respond(200, text="# solo comentarios\n")
        yield router


@pytest.fixture
def cliente() -> Iterator[ClienteCortes]:
    with ClienteCortes(URL_BASE, segundos_entre_peticiones=0) as c:
        yield c


# --------------------------------------------------------------------- Mapeo


def test_mapear_item(mapa: dict[str, Any]) -> None:
    a = mapear_anuncio(mapa["items"][0], Operacion.ARRIENDO, "Sabaneta", FECHA)

    assert (a.fuente, a.id_fuente) == ("alnago", "10569564")
    assert a.url == "https://alnago.com/es/inmueble/10569564"
    assert a.operacion is Operacion.ARRIENDO
    assert (a.tipo_inmueble, a.precio, a.area_m2) == ("apartamento", 1_950_000, 72.5)
    assert (a.habitaciones, a.banos, a.parqueaderos) == (3, 2, 1)
    assert (a.barrio, a.municipio) == ("María Auxiliadora", "Sabaneta")
    assert (a.latitud, a.longitud) == (6.1512, -75.6169)
    assert a.estrato is None and a.administracion is None
    assert a.fecha_observacion == FECHA


def test_precio_cero_barrio_nulo_y_tipo_desconocido(mapa: dict[str, Any]) -> None:
    a = mapear_anuncio(mapa["items"][1], Operacion.VENTA, "Medellín", FECHA)

    assert a.precio is None and a.barrio is None and a.tipo_inmueble is None
    assert a.operacion is Operacion.VENTA


# --------------------------------------------------------------------- Protocolo y registro


def test_cumple_protocolo_fuente(cliente: ClienteCortes) -> None:
    assert isinstance(FuenteAlnago(cliente), Fuente)


def test_registrada_en_cli() -> None:
    assert "alnago" in REGISTRO
    assert REGISTRO["alnago"].url_base == URL_BASE


# --------------------------------------------------------------------- Recorrido


def test_una_peticion_por_municipio_y_operacion(
    sitio: respx.MockRouter, cliente: ClienteCortes, mapa: dict[str, Any]
) -> None:
    medellin = sitio.get(RUTA, params__contains={"id_city": "496", "for_rent": "true"}).respond(
        200, json=mapa
    )
    # Después de la específica: respx usa la primera ruta que coincide.
    vacia = sitio.get(RUTA).respond(200, json={"total": 0, "items": []})

    anuncios = list(FuenteAlnago(cliente, fecha=FECHA).listar_anuncios())

    assert [a.id_fuente for a in anuncios] == ["10569564", "4283268"]
    assert all(a.operacion is Operacion.ARRIENDO and a.municipio == "Medellín" for a in anuncios)
    llamadas = [*medellin.calls, *vacia.calls]
    assert len(llamadas) == len(MUNICIPIOS) * 2
    for llamada in llamadas:
        params = llamada.request.url.params
        assert {params["for_rent"], params["for_sale"]} == {"true", "false"}


def test_respuesta_sin_items_no_falla(sitio: respx.MockRouter, cliente: ClienteCortes) -> None:
    sitio.get(RUTA).respond(200, json={})

    assert list(FuenteAlnago(cliente).listar_anuncios()) == []


def test_anuncio_invalido_se_omite(
    sitio: respx.MockRouter,
    cliente: ClienteCortes,
    mapa: dict[str, Any],
    caplog: pytest.LogCaptureFixture,
) -> None:
    invalido = {**mapa["items"][0], "id_property": 1, "beds": 99}
    sitio.get(RUTA, params__contains={"id_city": "496", "for_rent": "true"}).respond(
        200, json={"total": 2, "items": [invalido, mapa["items"][1]]}
    )
    sitio.get(RUTA).respond(200, json={"total": 0, "items": []})

    with caplog.at_level(logging.WARNING):
        anuncios = list(FuenteAlnago(cliente).listar_anuncios())

    assert [a.id_fuente for a in anuncios] == ["4283268"]
    assert "omitido" in caplog.text
