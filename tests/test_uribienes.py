import json
import logging
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

import pytest
import respx

from observatorio_inmobiliario.fuentes import REGISTRO
from observatorio_inmobiliario.fuentes.base import Fuente
from observatorio_inmobiliario.fuentes.uribienes import (
    MUNICIPIOS,
    URL_BASE,
    FuenteUribienes,
    mapear_anuncio,
)
from observatorio_inmobiliario.http import ClienteCortes
from observatorio_inmobiliario.modelos import Operacion

FIXTURES = Path(__file__).parent / "fixtures" / "uribienes"
FECHA = date(2026, 11, 11)
RUTA = "/api/properties"


def _pagina(inmuebles: list[dict[str, Any]], *, pagina: int = 1, ultima: int = 1) -> dict[str, Any]:
    return {
        "total": len(inmuebles),
        "per_page": 12,
        "current_page": pagina,
        "last_page": ultima,
        "data": inmuebles,
    }


@pytest.fixture
def listado() -> dict[str, Any]:
    datos: dict[str, Any] = json.loads((FIXTURES / "arriendo_p1.json").read_text(encoding="utf-8"))
    return datos


@pytest.fixture
def sitio() -> Iterator[respx.MockRouter]:
    """Simula Uribienes con su robots.txt real, que prohíbe '/?*'."""
    robots = (FIXTURES / "robots.txt").read_text(encoding="utf-8")
    with respx.mock(base_url=URL_BASE, assert_all_called=False) as router:
        router.get("/robots.txt").respond(200, text=robots)
        yield router


@pytest.fixture
def cliente() -> Iterator[ClienteCortes]:
    with ClienteCortes(URL_BASE, segundos_entre_peticiones=0) as c:
        yield c


# --------------------------------------------------------------------- Mapeo


def test_mapear_arriendo(listado: dict[str, Any]) -> None:
    a = mapear_anuncio(listado["data"][0], Operacion.ARRIENDO, FECHA)

    assert (a.fuente, a.id_fuente) == ("uribienes", "220400")
    assert a.url == "https://uribienes.com/inmuebles/220400"
    assert a.operacion is Operacion.ARRIENDO
    assert a.tipo_inmueble == "apartamento"
    assert (a.precio, a.administracion, a.area_m2) == (2_500_000, 350_000, 85.0)
    assert (a.habitaciones, a.banos, a.parqueaderos, a.estrato) == (3, 2, 1, 5)
    assert (a.barrio, a.municipio) == ("Laureles", "Medellín")
    assert (a.latitud, a.longitud) == (6.2441, -75.59)
    assert a.fecha_observacion == FECHA


def test_arriendo_venta_toma_el_precio_de_la_operacion(listado: dict[str, Any]) -> None:
    inmueble = listado["data"][1]

    assert mapear_anuncio(inmueble, Operacion.ARRIENDO, FECHA).precio == 1_700_000
    assert mapear_anuncio(inmueble, Operacion.VENTA, FECHA).precio == 250_000_000


def test_ceros_quedan_nulos(listado: dict[str, Any]) -> None:
    a = mapear_anuncio(listado["data"][1], Operacion.ARRIENDO, FECHA)

    assert a.administracion is None and a.area_m2 is None and a.estrato is None
    assert a.latitud is None and a.longitud is None
    assert a.parqueaderos == 0


# --------------------------------------------------------------------- Protocolo y registro


def test_cumple_protocolo_fuente(cliente: ClienteCortes) -> None:
    assert isinstance(FuenteUribienes(cliente), Fuente)


def test_registrada_en_cli() -> None:
    assert "uribienes" in REGISTRO
    assert REGISTRO["uribienes"].url_base == URL_BASE


def test_robots_real_permite_la_api(sitio: respx.MockRouter, cliente: ClienteCortes) -> None:
    """El robots de Uribienes prohíbe '/?*'; eso no debe bloquear /api/properties."""
    ruta = sitio.get(RUTA).respond(200, json=_pagina([]))

    cliente.get_json(RUTA, params={"city": 5001, "biz": 1, "page": 1})

    assert ruta.call_count == 1


# --------------------------------------------------------------------- Recorrido


def test_recorre_municipios_y_negocios(
    sitio: respx.MockRouter, cliente: ClienteCortes, listado: dict[str, Any]
) -> None:
    medellin = sitio.get(RUTA, params__contains={"city": "5001", "biz": "1"}).respond(
        200, json=listado
    )
    vacia = sitio.get(RUTA).respond(200, json=_pagina([]))  # después: respx usa la primera

    anuncios = list(FuenteUribienes(cliente, fecha=FECHA).listar_anuncios())

    assert [a.id_fuente for a in anuncios] == ["220400", "220401"]
    assert all(a.operacion is Operacion.ARRIENDO for a in anuncios)
    assert medellin.call_count + vacia.call_count == len(MUNICIPIOS) * 2


def test_pagina_hasta_last_page(
    sitio: respx.MockRouter, cliente: ClienteCortes, listado: dict[str, Any]
) -> None:
    paginas = [
        sitio.get(RUTA, params__contains={"city": "5001", "biz": "1", "page": str(n)}).respond(
            200, json=_pagina(listado["data"][:1], pagina=n, ultima=3)
        )
        for n in (1, 2, 3)
    ]
    sitio.get(RUTA).respond(200, json=_pagina([]))

    anuncios = list(FuenteUribienes(cliente).listar_anuncios())

    assert [r.call_count for r in paginas] == [1, 1, 1]
    assert len(anuncios) == 3


def test_max_paginas(
    sitio: respx.MockRouter, cliente: ClienteCortes, listado: dict[str, Any]
) -> None:
    ruta = sitio.get(RUTA).respond(200, json=_pagina(listado["data"][:1], ultima=3))

    list(FuenteUribienes(cliente, max_paginas=1).listar_anuncios())

    assert ruta.call_count == len(MUNICIPIOS) * 2
    assert {c.request.url.params["page"] for c in ruta.calls} == {"1"}


def test_anuncio_invalido_se_omite(
    sitio: respx.MockRouter,
    cliente: ClienteCortes,
    listado: dict[str, Any],
    caplog: pytest.LogCaptureFixture,
) -> None:
    sin_codigo = {k: v for k, v in listado["data"][0].items() if k != "codpro"}
    sitio.get(RUTA, params__contains={"city": "5001", "biz": "1"}).respond(
        200, json=_pagina([sin_codigo, listado["data"][1]])
    )
    sitio.get(RUTA).respond(200, json=_pagina([]))

    with caplog.at_level(logging.WARNING):
        anuncios = list(FuenteUribienes(cliente).listar_anuncios())

    assert [a.id_fuente for a in anuncios] == ["220401"]
    assert "omitido" in caplog.text


def test_conteo_negativo_queda_nulo_sin_perder_el_anuncio(listado: dict[str, Any]) -> None:
    """En la corrida real del 2026-11-11, 3 inmuebles traían parking -1 o -3."""
    inmueble = {**listado["data"][0], "parking": -1, "bathrooms": -3}

    a = mapear_anuncio(inmueble, Operacion.ARRIENDO, FECHA)

    assert a.parqueaderos is None and a.banos is None
    assert a.habitaciones == 3
