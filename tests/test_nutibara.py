import itertools
import json
import logging
import math
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

import pytest
import respx

from observatorio_inmobiliario.fuentes import REGISTRO
from observatorio_inmobiliario.fuentes.base import Fuente
from observatorio_inmobiliario.fuentes.nutibara import (
    CENTROS,
    RADIO_KM,
    URL_BASE,
    FuenteNutibara,
    cuadricula,
    mapear_anuncio,
)
from observatorio_inmobiliario.http import ClienteCortes
from observatorio_inmobiliario.modelos import Operacion

FIXTURES = Path(__file__).parent / "fixtures" / "nutibara"
FECHA = date(2026, 11, 11)
RUTA = "/promotion/filter/nearest"
UN_CENTRO = ((6.2442, -75.5812),)


def _cargar(nombre: str) -> dict[str, Any]:
    datos: dict[str, Any] = json.loads((FIXTURES / nombre).read_text(encoding="utf-8"))
    return datos


def _respuesta(promociones: list[dict[str, Any]], total: int | None = None) -> dict[str, Any]:
    total = len(promociones) if total is None else total
    return {"code": 200, "success": True, "data": {"total": total, "promotions": promociones}}


def _promocion(id_: int, status: str = "PROMOCION") -> dict[str, Any]:
    """Copia de la primera promoción del fixture con otro id."""
    base = _cargar("arriendo_p1.json")["data"]["promotions"][0]
    return {**base, "id": id_, "status": status}


def _km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distancia en km entre dos puntos (fórmula del haversine)."""
    dlat, dlon = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    )
    return 6371 * 2 * math.asin(math.sqrt(a))


@pytest.fixture
def arriendo() -> dict[str, Any]:
    return _cargar("arriendo_p1.json")


@pytest.fixture
def venta() -> dict[str, Any]:
    return _cargar("venta_p1.json")


@pytest.fixture
def sitio() -> Iterator[respx.MockRouter]:
    """Simula la API de Nutibara. Su robots.txt real responde 404 (sin reglas)."""
    with respx.mock(base_url=URL_BASE, assert_all_called=False) as router:
        router.get("/robots.txt").respond(404)
        yield router


@pytest.fixture
def cliente() -> Iterator[ClienteCortes]:
    with ClienteCortes(URL_BASE, segundos_entre_peticiones=0) as c:
        yield c


def _simular(sitio: respx.MockRouter, status: str, respuesta: dict[str, Any]) -> respx.Route:
    return sitio.get(RUTA, params__contains={"status": status}).respond(200, json=respuesta)


# --------------------------------------------------------------------- Mapeo


def test_mapear_arriendo_completo(arriendo: dict[str, Any]) -> None:
    a = mapear_anuncio(arriendo["data"]["promotions"][0], FECHA)

    assert a.fuente == "nutibara"
    assert a.id_fuente == "68776"
    assert a.operacion is Operacion.ARRIENDO
    assert a.url == "https://anutibara.com/apartamento-en-arriendo/conquistadores-medellin/68776"
    assert (a.tipo_inmueble, a.precio, a.area_m2) == ("apartamento", 3_600_000, 170.0)
    assert (a.habitaciones, a.banos, a.estrato) == (3, 2, 5)
    assert (a.barrio, a.municipio) == ("CONQUISTADORES", "MEDELLIN")
    assert (a.latitud, a.longitud) == (6.2426, -75.5828)
    assert a.fecha_observacion == FECHA


def test_estrato_cero_queda_nulo(arriendo: dict[str, Any]) -> None:
    a = mapear_anuncio(arriendo["data"]["promotions"][1], FECHA)

    assert a.estrato is None
    assert a.habitaciones is None and a.banos is None
    assert a.area_m2 == 35.0


def test_venta_mls_usa_precio_de_venta(venta: dict[str, Any]) -> None:
    a = mapear_anuncio(venta["data"]["promotions"][0], FECHA)

    assert a.operacion is Operacion.VENTA
    assert a.precio == 335_000_000
    assert a.url == "https://anutibara.com/apartamento-en-venta/laureles-medellin/70001"


# --------------------------------------------------------------------- Cuadrícula


def test_cuadricula_incluye_bordes_y_respeta_paso() -> None:
    puntos = cuadricula(6.0, 6.1, -75.6, -75.5, 0.035)
    lats = sorted({p[0] for p in puntos})
    lons = sorted({p[1] for p in puntos})

    assert lats[0] == 6.0 and lats[-1] == pytest.approx(6.1)
    assert lons[0] == -75.6 and lons[-1] == pytest.approx(-75.5)
    assert max(b - a for a, b in itertools.pairwise(lats)) <= 0.035
    assert max(b - a for a, b in itertools.pairwise(lons)) <= 0.035
    assert len(puntos) == len(lats) * len(lons)


def test_centros_cubren_el_valle_de_aburra() -> None:
    """Todo punto del rectángulo queda a menos de RADIO_KM de algún centro."""
    for i in range(30):
        lat = 6.09 + i * (6.38 - 6.09) / 29
        for j in range(20):
            lon = -75.66 + j * (-75.50 + 75.66) / 19
            assert min(_km(lat, lon, c_lat, c_lon) for c_lat, c_lon in CENTROS) <= RADIO_KM


# --------------------------------------------------------------------- Protocolo y registro


def test_cumple_protocolo_fuente(cliente: ClienteCortes) -> None:
    assert isinstance(FuenteNutibara(cliente), Fuente)


def test_registrada_en_cli() -> None:
    assert "nutibara" in REGISTRO
    assert REGISTRO["nutibara"].url_base == URL_BASE


# --------------------------------------------------------------------- Recorrido


def test_recorre_ambas_operaciones(
    sitio: respx.MockRouter,
    cliente: ClienteCortes,
    arriendo: dict[str, Any],
    venta: dict[str, Any],
) -> None:
    ruta_arriendo = _simular(sitio, "PROMOCION", arriendo)
    _simular(sitio, "VENTAS", venta)

    anuncios = list(FuenteNutibara(cliente, fecha=FECHA, centros=UN_CENTRO).listar_anuncios())

    assert [a.operacion for a in anuncios] == [Operacion.ARRIENDO] * 2 + [Operacion.VENTA]
    params = ruta_arriendo.calls.last.request.url.params
    assert params["priceStart"] == "1"
    assert params["page"] == "1"
    assert float(params["latitude"]) == pytest.approx(6.2442)
    assert float(params["longitude"]) == pytest.approx(-75.5812)


def test_pagina_hasta_completar_total(sitio: respx.MockRouter, cliente: ClienteCortes) -> None:
    pagina_1 = sitio.get(RUTA, params__contains={"status": "PROMOCION", "page": "1"}).respond(
        200, json=_respuesta([_promocion(i) for i in range(20)], total=25)
    )
    pagina_2 = sitio.get(RUTA, params__contains={"status": "PROMOCION", "page": "2"}).respond(
        200, json=_respuesta([_promocion(i) for i in range(20, 25)], total=25)
    )
    _simular(sitio, "VENTAS", _respuesta([]))

    anuncios = list(FuenteNutibara(cliente, centros=UN_CENTRO).listar_anuncios())

    assert len(anuncios) == 25
    assert (pagina_1.call_count, pagina_2.call_count) == (1, 1)


def test_centro_sin_resultados_no_cicla(sitio: respx.MockRouter, cliente: ClienteCortes) -> None:
    ruta = sitio.get(RUTA).respond(200, json=_respuesta([]))

    assert list(FuenteNutibara(cliente, centros=UN_CENTRO).listar_anuncios()) == []
    assert ruta.call_count == 2  # una por operación


def test_duplicados_entre_centros_salen_una_vez(
    sitio: respx.MockRouter, cliente: ClienteCortes
) -> None:
    _simular(sitio, "PROMOCION", _respuesta([_promocion(1)]))
    _simular(sitio, "VENTAS", _respuesta([]))
    dos_centros = ((6.24, -75.58), (6.25, -75.59))

    anuncios = list(FuenteNutibara(cliente, centros=dos_centros).listar_anuncios())

    assert [a.id_fuente for a in anuncios] == ["1"]


def test_max_paginas(sitio: respx.MockRouter, cliente: ClienteCortes) -> None:
    arriendo = _simular(
        sitio, "PROMOCION", _respuesta([_promocion(i) for i in range(20)], total=60)
    )
    venta = _simular(
        sitio, "VENTAS", _respuesta([_promocion(i, "VENTAS") for i in range(100, 120)], total=60)
    )

    anuncios = list(FuenteNutibara(cliente, max_paginas=1, centros=UN_CENTRO).listar_anuncios())

    assert (arriendo.call_count, venta.call_count) == (1, 1)
    assert len(anuncios) == 40


def test_anuncio_invalido_se_omite(
    sitio: respx.MockRouter, cliente: ClienteCortes, caplog: pytest.LogCaptureFixture
) -> None:
    promociones = [_promocion(1), _promocion(2, status="PERMUTA"), _promocion(3)]
    _simular(sitio, "PROMOCION", _respuesta(promociones))
    _simular(sitio, "VENTAS", _respuesta([]))

    with caplog.at_level(logging.WARNING):
        anuncios = list(FuenteNutibara(cliente, centros=UN_CENTRO).listar_anuncios())

    assert [a.id_fuente for a in anuncios] == ["1", "3"]
    assert "2" in caplog.text


def test_404_sin_elementos_es_un_centro_vacio(
    sitio: respx.MockRouter, cliente: ClienteCortes
) -> None:
    """La API responde 404 "No elements were found" cuando no hay inmuebles cerca del punto."""
    sin_elementos = {"code": 404, "success": False, "message": "No elements were found"}
    vacio = sitio.get(RUTA, params__contains={"latitude": "6.09000"}).respond(
        404, json=sin_elementos
    )
    _simular(sitio, "PROMOCION", _respuesta([_promocion(1)]))
    _simular(sitio, "VENTAS", _respuesta([]))
    centros = ((6.09, -75.66), (6.24, -75.58))

    anuncios = list(FuenteNutibara(cliente, centros=centros).listar_anuncios())

    assert [a.id_fuente for a in anuncios] == ["1"]
    assert vacio.call_count == 2  # una por operación, sin reintentos


def test_valores_fuera_de_rango_no_tumban_el_anuncio(arriendo: dict[str, Any]) -> None:
    promocion = arriendo["data"]["promotions"][0]
    inmueble = {
        **promocion["property"],
        "latitude": 95,
        "facilities": [
            {"id": 1, "value": "770000", "facility": {"id": 112, "name": "Area"}},
            {"id": 2, "value": "-1", "facility": {"id": 82, "name": "Alcobas"}},
            {"id": 3, "value": "99", "facility": {"id": 105, "name": "Baños"}},
        ],
    }

    a = mapear_anuncio({**promocion, "property": inmueble}, FECHA)

    assert a.area_m2 is None and a.habitaciones is None and a.banos is None
    assert a.latitud is None and a.precio == 3_600_000
