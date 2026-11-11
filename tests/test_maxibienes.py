from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

import pytest
import respx

from observatorio_inmobiliario import fuentes
from observatorio_inmobiliario.fuentes import REGISTRO
from observatorio_inmobiliario.fuentes.base import Fuente
from observatorio_inmobiliario.fuentes.maxibienes import (
    MUNICIPIOS,
    RUTA,
    URL_BASE,
    ErrorFiltroIgnorado,
    FuenteMaxibienes,
    extraer_filtros,
    extraer_tarjetas,
    mapear_anuncio,
)
from observatorio_inmobiliario.http import ClienteCortes
from observatorio_inmobiliario.modelos import Operacion

FIXTURES = Path(__file__).parent / "fixtures" / "maxibienes"
FECHA = date(2026, 11, 11)


def _leer(nombre: str) -> str:
    return (FIXTURES / nombre).read_text(encoding="utf-8")


def _pagina(gs: int, ci: int, total: int, tarjetas: str = "") -> str:
    """Página mínima con los mismos marcadores que publica el sitio."""
    return (
        f"<script>var gs = {gs}</script><script>var ci = {ci}</script>"
        f"<script>var totalInmuebles = {total}; </script>"
        f'<div class="grid-style1 clearfix">{tarjetas}</div>'
    )


def _tarjeta(codigo: int, operacion: str = "ARRIENDO", precio: str = "$ 1.500.000") -> str:
    return (
        '<div class="item col-sm-4"><div class="image">'
        f'<a href="{URL_BASE}/descripcion-del-inmueble/codigo/{codigo}">'
        '<h3>APARTAMENTO<br>Estrato: 3</h3><span class="location">Barrio: Belén</span></a></div>'
        f'<div class="price"><i class="fa fa-home"></i>{operacion}<span>{precio}</span></div>'
        f'<ul class="amenities"><li>{codigo}</li>'
        '<li><i class="fa fa-compress"></i> 60 m<sup>2</sup></li>'
        '<li><i class="fa fa-bath"></i> 2</li><li><i class="fa fa-bed"></i> 3</li>'
        '<li><i class="fas fa-warehouse negro"></i> 1</li></ul></div>'
    )


@pytest.fixture
def sitio() -> Iterator[respx.MockRouter]:
    with respx.mock(base_url=URL_BASE, assert_all_called=False) as router:
        router.get("/robots.txt").respond(200, text="User-agent: *\nDisallow: /js/\n")
        yield router


@pytest.fixture
def cliente() -> Iterator[ClienteCortes]:
    with ClienteCortes(URL_BASE, segundos_entre_peticiones=0) as c:
        yield c


def _simular_vacios(sitio: respx.MockRouter, excepto: set[tuple[int, int]]) -> None:
    """Las demás combinaciones de gestión y ciudad, sin inventario.

    Se saltan las de ``excepto``: respx reemplaza una ruta si se registra otra igual.
    """
    for gestion in (1, 2):
        for ciudad in MUNICIPIOS:
            if (gestion, ciudad) in excepto:
                continue
            sitio.get(
                f"{RUTA}/pagina/1", params={"gestion": str(gestion), "ciudad": str(ciudad)}
            ).respond(200, text=_pagina(gestion, ciudad, 0))


# --------------------------------------------------------------------- Extracción y mapeo


def test_extraer_tarjetas() -> None:
    tarjetas = extraer_tarjetas(_leer("arriendo_medellin_p80.html"))

    assert len(tarjetas) == 8
    assert tarjetas[2] == {
        "codigo": "59516",
        "tipo": "APARTAMENTO",
        "estrato": "4",
        "barrio": "Calasanz",
        "operacion": "ARRIENDO",
        "precio": "$ 3.200.000",
        "area": "85 m2",
        "banos": "2",
        "alcobas": "3",
        "parqueaderos": "1",
    }


def test_extraer_filtros() -> None:
    assert extraer_filtros(_leer("arriendo_medellin_p80.html")) == (1, 5001, 956)
    assert extraer_filtros("<html></html>") == (None, None, None)


def test_mapear_tarjeta() -> None:
    tarjeta = extraer_tarjetas(_leer("arriendo_medellin_p80.html"))[3]

    a = mapear_anuncio(tarjeta, Operacion.ARRIENDO, "Medellín", FECHA)

    assert (a.fuente, a.id_fuente) == ("maxibienes", "59171")
    assert a.url == f"{URL_BASE}/descripcion-del-inmueble/codigo/59171"
    assert (a.tipo_inmueble, a.precio, a.area_m2, a.estrato) == (
        "apartamento",
        10_000_000,
        260.0,
        5,
    )
    assert (a.habitaciones, a.banos, a.parqueaderos) == (7, 5, 2)
    assert (a.barrio, a.municipio) == ("Laureles", "Medellín")
    assert a.latitud is None and a.administracion is None


def test_precio_dual_toma_el_de_la_operacion() -> None:
    tarjeta = extraer_tarjetas(_leer("duales.html"))[1]  # $ $ 3.100.000 / $610.000.000

    assert mapear_anuncio(tarjeta, Operacion.ARRIENDO, "Medellín", FECHA).precio == 3_100_000
    assert mapear_anuncio(tarjeta, Operacion.VENTA, "Medellín", FECHA).precio == 610_000_000


def test_venta_con_precio_repetido() -> None:
    tarjeta = {**extraer_tarjetas(_leer("duales.html"))[0], "operacion": "VENTA"}
    tarjeta["precio"] = "$ $ 830.000.000 / $830.000.000"

    assert mapear_anuncio(tarjeta, Operacion.VENTA, "Medellín", FECHA).precio == 830_000_000


def test_estrato_siete_es_nulo() -> None:
    tarjeta = extraer_tarjetas(_leer("caldas.html"))[0]
    assert tarjeta["estrato"] == "7"

    assert mapear_anuncio(tarjeta, Operacion.ARRIENDO, "Caldas", FECHA).estrato is None


def test_pagina_en_cp1252() -> None:
    """La portada del sitio mezcla bytes cp1252; las tarjetas deben leerse igual."""
    html = _pagina(1, 5001, 1, _tarjeta(1).replace("Belén", "Suramérica"))
    tarjetas = extraer_tarjetas(html.encode("cp1252"))

    assert tarjetas[0]["barrio"] == "Suramérica"


# --------------------------------------------------------------------- Protocolo y registro


def test_cumple_protocolo_fuente(cliente: ClienteCortes) -> None:
    assert isinstance(FuenteMaxibienes(cliente), Fuente)


def test_registrada_en_cli() -> None:
    assert "maxibienes" in REGISTRO
    assert REGISTRO["maxibienes"].url_base == URL_BASE


# --------------------------------------------------------------------- Recorrido


def test_pagina_hasta_el_total(sitio: respx.MockRouter, cliente: ClienteCortes) -> None:
    filtros = {"gestion": "1", "ciudad": "5001"}
    pagina_1 = sitio.get(f"{RUTA}/pagina/1", params=filtros).respond(
        200, text=_pagina(1, 5001, 14, "".join(_tarjeta(c) for c in range(1, 13)))
    )
    pagina_2 = sitio.get(f"{RUTA}/pagina/2", params=filtros).respond(
        200, text=_pagina(1, 5001, 14, _tarjeta(13) + _tarjeta(14))
    )
    pagina_3 = sitio.get(f"{RUTA}/pagina/3", params=filtros).respond(200, text=_pagina(1, 5001, 14))
    _simular_vacios(sitio, excepto={(1, 5001)})

    anuncios = list(FuenteMaxibienes(cliente, fecha=FECHA).listar_anuncios())

    assert len(anuncios) == 14
    assert (pagina_1.call_count, pagina_2.call_count, pagina_3.call_count) == (1, 1, 0)
    assert all(a.municipio == "Medellín" for a in anuncios)


def test_filtro_ignorado_detiene_la_fuente(sitio: respx.MockRouter, cliente: ClienteCortes) -> None:
    """Si el sitio ignora el filtro, devuelve TODO el país: es mejor fallar que guardar eso."""
    sitio.get(f"{RUTA}/pagina/1").respond(200, text=_pagina(1, 0, 3658, _tarjeta(1)))

    with pytest.raises(ErrorFiltroIgnorado):
        list(FuenteMaxibienes(cliente).listar_anuncios())


def test_duales_salen_una_vez_por_operacion(
    sitio: respx.MockRouter, cliente: ClienteCortes
) -> None:
    dual = _tarjeta(7, "ARRIENDO/VENTA", "$ $ 2.000.000 / $409.000.000")
    for gestion in (1, 2):
        filtros = {"gestion": str(gestion), "ciudad": "5001"}
        sitio.get(f"{RUTA}/pagina/1", params=filtros).respond(
            200, text=_pagina(gestion, 5001, 24, dual * 12)
        )
        sitio.get(f"{RUTA}/pagina/2", params=filtros).respond(
            200, text=_pagina(gestion, 5001, 24, dual)
        )
    _simular_vacios(sitio, excepto={(1, 5001), (2, 5001)})

    anuncios = list(FuenteMaxibienes(cliente).listar_anuncios())

    assert [(a.operacion, a.precio) for a in anuncios] == [
        (Operacion.ARRIENDO, 2_000_000),
        (Operacion.VENTA, 409_000_000),
    ]


def test_max_paginas(sitio: respx.MockRouter, cliente: ClienteCortes) -> None:
    filtros = {"gestion": "1", "ciudad": "5001"}
    pagina_1 = sitio.get(f"{RUTA}/pagina/1", params=filtros).respond(
        200, text=_pagina(1, 5001, 30, "".join(_tarjeta(c) for c in range(1, 13)))
    )
    pagina_2 = sitio.get(f"{RUTA}/pagina/2", params=filtros).respond(
        200, text=_pagina(1, 5001, 30, _tarjeta(99))
    )
    _simular_vacios(sitio, excepto={(1, 5001)})

    list(FuenteMaxibienes(cliente, max_paginas=1).listar_anuncios())

    assert (pagina_1.call_count, pagina_2.call_count) == (1, 0)


def test_anuncio_invalido_se_omite(
    sitio: respx.MockRouter, cliente: ClienteCortes, caplog: pytest.LogCaptureFixture
) -> None:
    sin_codigo = _tarjeta(5).replace("codigo/5", "codigo/").replace("<li>5</li>", "<li></li>")
    sitio.get(f"{RUTA}/pagina/1", params={"gestion": "1", "ciudad": "5001"}).respond(
        200, text=_pagina(1, 5001, 2, sin_codigo + _tarjeta(6))
    )
    _simular_vacios(sitio, excepto={(1, 5001)})

    anuncios = list(FuenteMaxibienes(cliente).listar_anuncios())

    assert [a.id_fuente for a in anuncios] == ["6"]
    assert "omitido" in caplog.text


def test_cliente_tolera_un_servidor_lento(monkeypatch: pytest.MonkeyPatch) -> None:
    """En la corrida real del 2026-11-11 una página tardó más de 30 s tres veces seguidas."""
    usados: dict[str, Any] = {}

    class ClienteEspia(ClienteCortes):
        def __init__(self, url_base: str, **opciones: Any) -> None:
            usados.update(opciones)
            super().__init__(url_base, **opciones)

    monkeypatch.setattr(fuentes, "ClienteCortes", ClienteEspia)

    with fuentes.crear_fuente("maxibienes"):
        pass

    assert usados["timeout"] >= 90
    assert usados["max_intentos"] >= 5
