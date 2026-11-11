import json
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

import pytest
import respx

from observatorio_inmobiliario.fuentes import REGISTRO
from observatorio_inmobiliario.fuentes.base import Fuente
from observatorio_inmobiliario.fuentes.puertabierta import (
    MUNICIPIOS,
    URL_BASE,
    FuentePuertabierta,
    extraer_busqueda,
    mapear_anuncio,
    tipo_desde_titulo,
)
from observatorio_inmobiliario.http import ClienteCortes
from observatorio_inmobiliario.modelos import Operacion

FIXTURES = Path(__file__).parent / "fixtures" / "puertabierta"
FECHA = date(2026, 11, 11)


def _leer(nombre: str) -> str:
    return (FIXTURES / nombre).read_text(encoding="utf-8")


@pytest.fixture
def medellin() -> str:
    return _leer("arriendos_medellin_p1.html")


@pytest.fixture
def hits(medellin: str) -> list[dict[str, Any]]:
    busqueda = extraer_busqueda(medellin)
    assert busqueda is not None
    resultado: list[dict[str, Any]] = busqueda["hits"]
    return resultado


def _pagina(hits: list[dict[str, Any]], *, pagina: int, total_paginas: int) -> str:
    """HTML mínimo con la misma estructura RSC que publica el sitio."""
    consulta = {
        "state": {
            "data": {
                "hits": hits,
                "found": len(hits),
                "page": pagina,
                "totalPages": total_paginas,
                "perPage": 36,
            }
        },
        "queryKey": ["properties", "search", {"page": pagina}],
    }
    linea = "7:" + json.dumps(["$", "$L1d", None, {"state": {"queries": [consulta]}}]) + "\n"
    return f"<script>self.__next_f.push({json.dumps([1, linea])})</script>"


@pytest.fixture
def sitio() -> Iterator[respx.MockRouter]:
    with respx.mock(base_url=URL_BASE, assert_all_called=False) as router:
        router.get("/robots.txt").respond(200, text="User-Agent: *\nAllow: /\nDisallow: /sura\n")
        yield router


@pytest.fixture
def cliente() -> Iterator[ClienteCortes]:
    with ClienteCortes(URL_BASE, segundos_entre_peticiones=0) as c:
        yield c


# --------------------------------------------------------------------- Extracción y mapeo


def test_extraer_busqueda(medellin: str) -> None:
    busqueda = extraer_busqueda(medellin)

    assert busqueda is not None
    assert (busqueda["found"], busqueda["totalPages"], len(busqueda["hits"])) == (217, 7, 3)


def test_extraer_busqueda_con_la_linea_partida_en_dos(medellin: str) -> None:
    """Next.js puede partir una misma línea RSC en varios push."""
    inicio = medellin.index("self.__next_f.push(") + len("self.__next_f.push(")
    fin = medellin.index(")</script>", inicio)
    _, linea = json.loads(medellin[inicio:fin])
    mitad = len(linea) // 2
    partido = (
        f"<script>self.__next_f.push({json.dumps([1, linea[:mitad]])})</script>"
        f"<script>self.__next_f.push({json.dumps([1, linea[mitad:]])})</script>"
    )

    assert extraer_busqueda(partido) == extraer_busqueda(medellin)


def test_pagina_sin_busqueda_es_none() -> None:
    assert extraer_busqueda("<html><body>nada</body></html>") is None


def test_mapear_hit(hits: list[dict[str, Any]]) -> None:
    a = mapear_anuncio(hits[1], "Medellín", FECHA)

    assert a.fuente == "puertabierta"
    assert a.id_fuente == "1dca0cb1-373c-44df-b57d-01ed3f6bb999"
    assert a.url == "https://puertabierta.com.co/propiedades/1dca0cb1-373c-44df-b57d-01ed3f6bb999"
    assert a.operacion is Operacion.ARRIENDO
    assert (a.tipo_inmueble, a.precio, a.area_m2) == ("apartamento", 6_400_000, 126.0)
    assert (a.habitaciones, a.banos, a.parqueaderos) == (3, 2, 2)
    assert (a.barrio, a.municipio) == ("El Tesoro", "Medellín")
    assert (a.latitud, a.longitud) == (6.2067153, -75.5590962)
    assert a.estrato is None and a.administracion is None


@pytest.mark.parametrize("valor", [0, None])
def test_administracion_cero_o_nula_es_nula(hits: list[dict[str, Any]], valor: int | None) -> None:
    hit = {**hits[0], "pricing": {**hits[0]["pricing"], "monthlyAdministrationFee": valor}}

    assert mapear_anuncio(hit, "Medellín", FECHA).administracion is None


def test_administracion_reportada(hits: list[dict[str, Any]]) -> None:
    hit = {**hits[0], "pricing": {**hits[0]["pricing"], "monthlyAdministrationFee": 553_000}}

    assert mapear_anuncio(hit, "Medellín", FECHA).administracion == 553_000


def test_banos_fraccionarios(hits: list[dict[str, Any]]) -> None:
    hit = {**hits[0], "layout": {**hits[0]["layout"], "numBathrooms": 2.5}}

    assert mapear_anuncio(hit, "Medellín", FECHA).banos == 2


def test_barrio_usa_zone_si_falta_neighborhood(hits: list[dict[str, Any]]) -> None:
    assert mapear_anuncio(hits[0], "Medellín", FECHA).barrio == "Belén"


@pytest.mark.parametrize(
    ("titulo", "tipo"),
    [
        ("Apartaestudio en Laureles", "apartaestudio"),
        ("Hermosa Casa en Envigado", "casa"),
        ("Apartamento de 3 habitaciones en Belén", "apartamento"),
        ("Penthouse en El Poblado", "penthouse"),
        ("Inmueble en Laureles", None),
        (None, None),
    ],
)
def test_tipo_desde_titulo(titulo: str | None, tipo: str | None) -> None:
    assert tipo_desde_titulo(titulo) == tipo


def test_municipio_sale_del_slug_consultado() -> None:
    busqueda = extraer_busqueda(_leer("arriendos_itagui.html"))
    assert busqueda is not None
    hit = busqueda["hits"][0]
    assert hit["location"]["city"] == "Itagüi"  # así lo escribe el sitio

    assert mapear_anuncio(hit, MUNICIPIOS["itagui"], FECHA).municipio == "Itagüí"


# --------------------------------------------------------------------- Protocolo y registro


def test_cumple_protocolo_fuente(cliente: ClienteCortes) -> None:
    assert isinstance(FuentePuertabierta(cliente), Fuente)


def test_registrada_en_cli() -> None:
    assert "puertabierta" in REGISTRO
    assert REGISTRO["puertabierta"].url_base == URL_BASE


# --------------------------------------------------------------------- Recorrido


def _solo_medellin(sitio: respx.MockRouter, paginas: list[str]) -> list[respx.Route]:
    rutas = [
        sitio.get("/arriendos/medellin", params={"page": str(n)}).respond(200, text=html)
        for n, html in enumerate(paginas, start=1)
    ]
    for slug in MUNICIPIOS:
        if slug != "medellin":
            sitio.get(f"/arriendos/{slug}").respond(404)
    return rutas


def test_recorre_hasta_total_pages(
    sitio: respx.MockRouter, cliente: ClienteCortes, hits: list[dict[str, Any]]
) -> None:
    rutas = _solo_medellin(
        sitio,
        [
            _pagina(hits[:2], pagina=1, total_paginas=2),
            _pagina(hits[2:], pagina=2, total_paginas=2),
        ],
    )
    pagina_3 = sitio.get("/arriendos/medellin", params={"page": "3"}).respond(404)

    anuncios = list(FuentePuertabierta(cliente, fecha=FECHA).listar_anuncios())

    assert [a.id_fuente for a in anuncios] == [h["id"] for h in hits]
    assert [r.call_count for r in rutas] == [1, 1]
    assert pagina_3.call_count == 0


def test_404_de_municipio_no_tumba_la_corrida(
    sitio: respx.MockRouter, cliente: ClienteCortes, hits: list[dict[str, Any]]
) -> None:
    _solo_medellin(sitio, [_pagina(hits, pagina=1, total_paginas=1)])

    assert len(list(FuentePuertabierta(cliente).listar_anuncios())) == 3


def test_duplicados_por_id_salen_una_vez(
    sitio: respx.MockRouter, cliente: ClienteCortes, hits: list[dict[str, Any]]
) -> None:
    """El orden por relevancia puede cambiar entre páginas y repetir un anuncio."""
    _solo_medellin(
        sitio,
        [
            _pagina(hits[:2], pagina=1, total_paginas=2),
            _pagina(hits[1:], pagina=2, total_paginas=2),
        ],
    )

    anuncios = list(FuentePuertabierta(cliente).listar_anuncios())

    assert len(anuncios) == 3


def test_max_paginas(
    sitio: respx.MockRouter, cliente: ClienteCortes, hits: list[dict[str, Any]]
) -> None:
    rutas = _solo_medellin(
        sitio,
        [
            _pagina(hits[:2], pagina=1, total_paginas=2),
            _pagina(hits[2:], pagina=2, total_paginas=2),
        ],
    )

    list(FuentePuertabierta(cliente, max_paginas=1).listar_anuncios())

    assert [r.call_count for r in rutas] == [1, 0]
