import json
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest
import respx

from observatorio_inmobiliario.fuentes import REGISTRO
from observatorio_inmobiliario.fuentes.activourbano import (
    RUTA_LISTADO,
    URL_BASE,
    FuenteActivoUrbano,
    extraer_detalle,
    extraer_paginacion,
    extraer_tarjetas,
    mapear_anuncio,
)
from observatorio_inmobiliario.fuentes.base import Fuente
from observatorio_inmobiliario.http import ClienteCortes
from observatorio_inmobiliario.modelos import Operacion

FIXTURES = Path(__file__).parent / "fixtures" / "activourbano"
FECHA = date(2026, 11, 11)


def _leer(nombre: str) -> str:
    return (FIXTURES / nombre).read_text(encoding="utf-8")


@pytest.fixture
def listado() -> str:
    return _leer("listado_p40.html")


def _pagina(tarjetas: list[str], *, pagina: int, paginas: int, total: int = 99) -> str:
    """Página mínima: la configuración de JetSmartFilters y el contenedor de tarjetas."""
    props = {"found_posts": total, "max_num_pages": paginas, "page": pagina}
    return (
        f'<script>var JetSmartFilterSettings = {{"props":{{"epro-loop-builder":'
        f'{{"products":{json.dumps(props, separators=(",", ":"))}}}}}}};</script>'
        f'<div id="products"><div class="elementor-loop-container">{"".join(tarjetas)}</div></div>'
    )


def _tarjeta(codigo: int, *, ubicacion: str = "ubicacion-medellin ubicacion-laureles-2") -> str:
    return (
        f'<div class="e-loop-item product product_cat-en-arriendo {ubicacion} '
        f'tipo-de-propiedad-apartamentos">'
        f'<div class="elementor-widget-heading"><h3>AU - {codigo}</h3></div>'
        '<div class="elementor-widget-icon"><i class="gicon gicon-full-screen"></i></div>'
        '<div class="elementor-widget-heading"><h3>70 m²</h3></div>'
        '<span class="woocommerce-Price-amount">$ 2.000.000</span></div>'
    )


@pytest.fixture
def sitio() -> Iterator[respx.MockRouter]:
    with respx.mock(base_url=URL_BASE, assert_all_called=False) as router:
        router.get("/robots.txt").respond(200, text="User-agent: *\nDisallow: /wp-admin/\n")
        yield router


@pytest.fixture
def cliente() -> Iterator[ClienteCortes]:
    with ClienteCortes(URL_BASE, segundos_entre_peticiones=0) as c:
        yield c


# --------------------------------------------------------------------- Extracción y mapeo


def test_extraer_paginacion(listado: str) -> None:
    assert extraer_paginacion(listado) == (480, 80)
    assert extraer_paginacion(_leer("listado_vacio.html")) == (0, 0)


def test_extraer_tarjetas(listado: str) -> None:
    tarjetas = extraer_tarjetas(listado)

    assert [t["codigo"] for t in tarjetas] == ["6174", "6157", "6139", "6128", "6125", "6067"]
    assert tarjetas[0] == {
        "codigo": "6174",
        "operacion": "en-arriendo",
        "municipio_slug": "medellin",
        "barrio_slug": "ciudad-del-rio-3",
        "tipo_slug": "apartamentos",
        "precio": "$ 4.500.000",
        "area": "88 m²",
        "alcobas": "3",
        "banos": "2",
    }


def test_tarjetas_de_la_pagina_vacia() -> None:
    assert extraer_tarjetas(_leer("listado_vacio.html")) == []


def test_mapear_tarjeta_con_detalle(listado: str) -> None:
    tarjeta = extraer_tarjetas(listado)[0]
    detalle = {"estrato": "6", "parqueaderos": "1"}

    a = mapear_anuncio(tarjeta, detalle, FECHA)

    assert (a.fuente, a.id_fuente) == ("activourbano", "6174")
    assert a.url == f"{URL_BASE}/propiedades/inmueble/6174/"
    assert a.operacion is Operacion.ARRIENDO
    assert (a.tipo_inmueble, a.precio, a.area_m2) == ("apartamento", 4_500_000, 88.0)
    assert (a.habitaciones, a.banos, a.parqueaderos, a.estrato) == (3, 2, 1, 6)
    assert (a.barrio, a.municipio) == ("ciudad del rio", "Medellín")
    assert a.latitud is None and a.administracion is None


def test_venta(listado: str) -> None:
    a = mapear_anuncio(extraer_tarjetas(listado)[5], None, FECHA)

    assert a.operacion is Operacion.VENTA
    assert a.precio == 1_800_000_000
    assert a.barrio == "poblado"


def test_ambos_se_guarda_como_arriendo(listado: str) -> None:
    """Su único precio está rotulado "Valor del arriendo"."""
    tarjeta = extraer_tarjetas(listado)[3]
    assert tarjeta["operacion"] == "ambos"

    assert mapear_anuncio(tarjeta, None, FECHA).operacion is Operacion.ARRIENDO


def test_solo_municipio_sin_barrio(listado: str) -> None:
    a = mapear_anuncio(extraer_tarjetas(listado)[1], None, FECHA)

    assert (a.barrio, a.municipio) == (None, "Envigado")


def test_detalle_completo() -> None:
    assert extraer_detalle(_leer("detalle_6752.html")) == {"estrato": "6", "parqueaderos": "1"}


def test_detalle_sin_parqueadero_es_nulo() -> None:
    """El widget del valor falta: no hay que tomar "Baños" por error."""
    assert extraer_detalle(_leer("detalle_6754.html")) == {"estrato": "5", "parqueaderos": None}


def test_estrato_sin_especificar_es_nulo(listado: str) -> None:
    detalle = extraer_detalle(_leer("detalle_6163.html"))
    assert detalle["estrato"] == "Sin especificar"

    assert mapear_anuncio(extraer_tarjetas(listado)[0], detalle, FECHA).estrato is None


def test_banos_decimales(listado: str) -> None:
    tarjeta = {**extraer_tarjetas(listado)[0], "banos": "2.5"}

    assert mapear_anuncio(tarjeta, None, FECHA).banos == 2


# --------------------------------------------------------------------- Protocolo y registro


def test_cumple_protocolo_fuente(cliente: ClienteCortes) -> None:
    assert isinstance(FuenteActivoUrbano(cliente), Fuente)


def test_registrada_en_cli() -> None:
    assert "activourbano" in REGISTRO
    assert REGISTRO["activourbano"].url_base == URL_BASE


# --------------------------------------------------------------------- Recorrido


def _simular_listado(sitio: respx.MockRouter, paginas: list[str]) -> list[respx.Route]:
    return [
        sitio.get(RUTA_LISTADO, params__contains={"pagenum": str(n)}).respond(200, text=html)
        for n, html in enumerate(paginas, start=1)
    ]


def test_pagina_hasta_max_num_pages(sitio: respx.MockRouter, cliente: ClienteCortes) -> None:
    rutas = _simular_listado(
        sitio,
        [
            _pagina([_tarjeta(1), _tarjeta(2)], pagina=1, paginas=2),
            _pagina([_tarjeta(3)], pagina=2, paginas=2),
        ],
    )
    pagina_3 = sitio.get(RUTA_LISTADO, params__contains={"pagenum": "3"}).respond(
        200, text=_pagina([], pagina=3, paginas=0, total=0)
    )

    anuncios = list(FuenteActivoUrbano(cliente, con_detalle=False).listar_anuncios())

    assert [a.id_fuente for a in anuncios] == ["1", "2", "3"]
    assert [r.call_count for r in rutas] == [1, 1]
    assert pagina_3.call_count == 0


def test_pagina_vacia_corta(sitio: respx.MockRouter, cliente: ClienteCortes) -> None:
    """Si el total cambia a mitad de corrida, una página sin tarjetas termina el recorrido."""
    rutas = _simular_listado(
        sitio,
        [
            _pagina([_tarjeta(1)], pagina=1, paginas=3),
            _pagina([], pagina=2, paginas=0, total=0),
        ],
    )

    anuncios = list(FuenteActivoUrbano(cliente, con_detalle=False).listar_anuncios())

    assert len(anuncios) == 1
    assert [r.call_count for r in rutas] == [1, 1]


def test_codigo_repetido_sale_una_vez(sitio: respx.MockRouter, cliente: ClienteCortes) -> None:
    _simular_listado(sitio, [_pagina([_tarjeta(1), _tarjeta(1)], pagina=1, paginas=1)])

    assert len(list(FuenteActivoUrbano(cliente, con_detalle=False).listar_anuncios())) == 1


def test_fuera_del_valle_se_omite(sitio: respx.MockRouter, cliente: ClienteCortes) -> None:
    tarjetas = [_tarjeta(1, ubicacion="ubicacion-rionegro"), _tarjeta(2)]
    _simular_listado(sitio, [_pagina(tarjetas, pagina=1, paginas=1)])

    anuncios = list(FuenteActivoUrbano(cliente, con_detalle=False).listar_anuncios())

    assert [a.id_fuente for a in anuncios] == ["2"]


def test_pide_el_detalle_de_cada_anuncio(sitio: respx.MockRouter, cliente: ClienteCortes) -> None:
    _simular_listado(sitio, [_pagina([_tarjeta(6752)], pagina=1, paginas=1)])
    ruta = sitio.get("/propiedades/inmueble/6752/").respond(200, text=_leer("detalle_6752.html"))

    (anuncio,) = FuenteActivoUrbano(cliente).listar_anuncios()

    assert ruta.call_count == 1
    assert (anuncio.estrato, anuncio.parqueaderos) == (6, 1)


def test_detalle_que_falla_deja_datos_del_listado(
    sitio: respx.MockRouter, cliente: ClienteCortes
) -> None:
    _simular_listado(sitio, [_pagina([_tarjeta(6752)], pagina=1, paginas=1)])
    sitio.get("/propiedades/inmueble/6752/").respond(404)

    (anuncio,) = FuenteActivoUrbano(cliente).listar_anuncios()

    assert anuncio.estrato is None and anuncio.area_m2 == 70.0


def test_max_paginas(sitio: respx.MockRouter, cliente: ClienteCortes) -> None:
    rutas = _simular_listado(
        sitio,
        [
            _pagina([_tarjeta(1)], pagina=1, paginas=2),
            _pagina([_tarjeta(2)], pagina=2, paginas=2),
        ],
    )

    list(FuenteActivoUrbano(cliente, con_detalle=False, max_paginas=1).listar_anuncios())

    assert [r.call_count for r in rutas] == [1, 0]
