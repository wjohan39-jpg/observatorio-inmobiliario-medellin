import json
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

import pytest
import respx

from observatorio_inmobiliario.fuentes import crear_fuente
from observatorio_inmobiliario.fuentes.base import Fuente
from observatorio_inmobiliario.fuentes.santafe import URL_BASE, FuenteSantaFe, mapear_anuncio
from observatorio_inmobiliario.http import ClienteCortes
from observatorio_inmobiliario.modelos import Operacion

FIXTURES = Path(__file__).parent / "fixtures" / "santafe"
FECHA = date(2026, 11, 10)
RUTA_LISTADO = "/apisf/properties"


def _cargar(nombre: str) -> Any:
    return json.loads((FIXTURES / nombre).read_text(encoding="utf-8"))


@pytest.fixture
def listado() -> dict[str, Any]:
    datos: dict[str, Any] = _cargar("listado_arriendo_p1.json")
    return datos


@pytest.fixture
def detalle() -> dict[str, Any]:
    datos: dict[str, Any] = _cargar("detalle.json")
    return datos


@pytest.fixture
def sitio() -> Iterator[respx.MockRouter]:
    """Simula la API de Santa Fe. Por defecto, su robots.txt permite todo."""
    with respx.mock(base_url=URL_BASE, assert_all_called=False) as router:
        router.get("/robots.txt").respond(200, text="User-agent: *\nAllow: /\n")
        yield router


@pytest.fixture
def cliente() -> Iterator[ClienteCortes]:
    with ClienteCortes(URL_BASE, segundos_entre_peticiones=0) as c:
        yield c


def _pagina(resultados: list[dict[str, Any]], *, pagina: int, hay_mas: bool) -> dict[str, Any]:
    return {
        "total": len(resultados),
        "page": pagina,
        "per_page": 12,
        "has_more": hay_mas,
        "results": resultados,
    }


def _simular_listado(
    sitio: respx.MockRouter, oferta: str, paginas: list[dict[str, Any]]
) -> list[respx.Route]:
    return [
        sitio.get(RUTA_LISTADO, params={"page": str(n), "oferta": oferta}).respond(200, json=pagina)
        for n, pagina in enumerate(paginas, start=1)
    ]


# --------------------------------------------------------------------- Mapeo


def test_mapear_anuncio_con_detalle(listado: dict[str, Any], detalle: dict[str, Any]) -> None:
    resultado = listado["results"][0]
    anuncio = mapear_anuncio(resultado, detalle, FECHA)

    assert anuncio.fuente == "santafe"
    assert anuncio.id_fuente == resultado["codigo"]
    assert anuncio.operacion == Operacion.ARRIENDO
    assert anuncio.estrato == detalle["estrato"]
    assert anuncio.area_m2 == detalle["area"]
    assert anuncio.parqueaderos == detalle["parqueaderos"]
    assert anuncio.barrio == detalle["sector"]
    assert anuncio.municipio == "Medellín"
    assert anuncio.url == f"{URL_BASE}/propiedad/{resultado['codigo']}"
    assert anuncio.fecha_observacion == FECHA


def test_mapear_anuncio_sin_detalle(listado: dict[str, Any]) -> None:
    resultado = listado["results"][0]
    anuncio = mapear_anuncio(resultado, None, FECHA)

    assert anuncio.estrato is None
    assert anuncio.parqueaderos is None
    assert anuncio.precio == resultado["price_raw"]
    assert anuncio.area_m2 == 253  # sale de "size": "253 M²"
    assert anuncio.habitaciones == resultado["bedrooms"]
    assert anuncio.banos == resultado["bathrooms"]
    assert anuncio.barrio == resultado["location"]
    assert anuncio.tipo_inmueble == "casa local"


def test_dato_del_detalle_tiene_prioridad(listado: dict[str, Any], detalle: dict[str, Any]) -> None:
    resultado = {**listado["results"][0], "bedrooms": 1, "location": "Otro"}
    anuncio = mapear_anuncio(resultado, {**detalle, "habitaciones": 4}, FECHA)

    assert anuncio.habitaciones == 4
    assert anuncio.barrio == detalle["sector"]


def test_oferta_sin_importar_mayusculas(listado: dict[str, Any]) -> None:
    resultado = {**listado["results"][0], "oferta": "VENTA"}
    assert mapear_anuncio(resultado, None, FECHA).operacion == Operacion.VENTA


# --------------------------------------------------------------------- Protocolo y registro


def test_cumple_protocolo_fuente(cliente: ClienteCortes) -> None:
    assert isinstance(FuenteSantaFe(cliente), Fuente)


def test_crear_fuente_por_nombre(sitio: respx.MockRouter) -> None:
    with crear_fuente("santafe", con_detalle=False) as fuente:
        assert fuente.nombre == "santafe"


def test_crear_fuente_desconocida() -> None:
    with pytest.raises(ValueError, match="santafe"), crear_fuente("no-existe"):
        pass


# --------------------------------------------------------------------- Recorrido


def test_pagina_hasta_has_more_false(
    sitio: respx.MockRouter, cliente: ClienteCortes, listado: dict[str, Any]
) -> None:
    resultados = listado["results"]
    _simular_listado(
        sitio,
        "Arriendo",
        [
            _pagina(resultados[:2], pagina=1, hay_mas=True),
            _pagina(resultados[2:], pagina=2, hay_mas=False),
        ],
    )
    _simular_listado(sitio, "Venta", [_pagina([], pagina=1, hay_mas=False)])

    anuncios = list(FuenteSantaFe(cliente, con_detalle=False, fecha=FECHA).listar_anuncios())

    assert [a.id_fuente for a in anuncios] == [r["codigo"] for r in resultados]


def test_max_paginas(
    sitio: respx.MockRouter, cliente: ClienteCortes, listado: dict[str, Any]
) -> None:
    resultados = listado["results"]
    arriendo = _simular_listado(
        sitio,
        "Arriendo",
        [
            _pagina(resultados[:1], pagina=1, hay_mas=True),
            _pagina(resultados[1:], pagina=2, hay_mas=False),
        ],
    )
    venta = _simular_listado(
        sitio,
        "Venta",
        [_pagina([], pagina=1, hay_mas=True), _pagina([], pagina=2, hay_mas=False)],
    )

    anuncios = list(FuenteSantaFe(cliente, con_detalle=False, max_paginas=1).listar_anuncios())

    assert len(anuncios) == 1
    assert [r.call_count for r in arriendo] == [1, 0]
    assert [r.call_count for r in venta] == [1, 0]


def test_con_detalle_pide_cada_anuncio(
    sitio: respx.MockRouter,
    cliente: ClienteCortes,
    listado: dict[str, Any],
    detalle: dict[str, Any],
) -> None:
    resultado = listado["results"][0]
    _simular_listado(sitio, "Arriendo", [_pagina([resultado], pagina=1, hay_mas=False)])
    _simular_listado(sitio, "Venta", [_pagina([], pagina=1, hay_mas=False)])
    ruta_detalle = sitio.get(f"/apisf/property/{resultado['codigo']}").respond(200, json=detalle)

    (anuncio,) = FuenteSantaFe(cliente).listar_anuncios()

    assert ruta_detalle.call_count == 1
    assert anuncio.estrato == detalle["estrato"]


def test_detalle_falla_no_tumba_corrida(
    sitio: respx.MockRouter,
    cliente: ClienteCortes,
    listado: dict[str, Any],
    caplog: pytest.LogCaptureFixture,
) -> None:
    resultado = listado["results"][0]
    _simular_listado(sitio, "Arriendo", [_pagina([resultado], pagina=1, hay_mas=False)])
    _simular_listado(sitio, "Venta", [_pagina([], pagina=1, hay_mas=False)])
    sitio.get(f"/apisf/property/{resultado['codigo']}").respond(404)

    (anuncio,) = FuenteSantaFe(cliente).listar_anuncios()

    assert anuncio.id_fuente == resultado["codigo"]
    assert anuncio.estrato is None
    assert resultado["codigo"] in caplog.text


def test_anuncio_invalido_se_omite(
    sitio: respx.MockRouter,
    cliente: ClienteCortes,
    listado: dict[str, Any],
    caplog: pytest.LogCaptureFixture,
) -> None:
    validos = listado["results"][:2]
    invalido = {**listado["results"][2], "oferta": "Permuta"}
    _simular_listado(
        sitio, "Arriendo", [_pagina([validos[0], invalido, validos[1]], pagina=1, hay_mas=False)]
    )
    _simular_listado(sitio, "Venta", [_pagina([], pagina=1, hay_mas=False)])

    anuncios = list(FuenteSantaFe(cliente, con_detalle=False).listar_anuncios())

    assert [a.id_fuente for a in anuncios] == [r["codigo"] for r in validos]
    assert invalido["codigo"] in caplog.text


def test_valores_fuera_de_rango_no_tumban_el_anuncio(
    listado: dict[str, Any], detalle: dict[str, Any]
) -> None:
    raro = {**detalle, "area": 200_000, "habitaciones": -1, "parqueaderos": 99, "lat": 95}

    anuncio = mapear_anuncio(listado["results"][0], raro, FECHA)

    assert anuncio.area_m2 is None and anuncio.habitaciones is None
    assert anuncio.parqueaderos is None and anuncio.latitud is None
