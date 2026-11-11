from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest
import respx

from observatorio_inmobiliario.fuentes import REGISTRO
from observatorio_inmobiliario.fuentes.base import Fuente
from observatorio_inmobiliario.fuentes.panorama import (
    MUNICIPIOS,
    TIPOS,
    URL_BASE,
    FuentePanorama,
    extraer_ciudades,
    extraer_ficha,
    extraer_paginas,
    extraer_tarjetas,
    mapear_anuncio,
)
from observatorio_inmobiliario.http import ClienteCortes
from observatorio_inmobiliario.modelos import Operacion

FIXTURES = Path(__file__).parent / "fixtures" / "panorama"
FECHA = date(2026, 11, 11)


def _leer(nombre: str) -> str:
    """Los fixtures se guardan en cp1252, igual que los envía el sitio."""
    return (FIXTURES / nombre).read_bytes().decode("cp1252")


def _bytes(nombre: str) -> bytes:
    return (FIXTURES / nombre).read_bytes()


def _pagina(tarjetas: list[str], *, pagina: int, paginas: int) -> bytes:
    pager = (
        f'<ul class="pagination"><li><a class="page-link">Página {pagina} / {paginas}</a></li></ul>'
    )
    return (pager + "<hr/>".join(tarjetas)).encode("cp1252")


def _tarjeta(codigo: int, barrio: str = "LAURELES") -> str:
    return (
        f'<div class="row" align="center"><div class="col-sm-8"><p>Anuncio {codigo} - {barrio}</p>'
        '<p><h3><i class="fa-light fa-bed"></i><span> 2 +1</span>'
        '<i class="fa-light fa-bath"></i><span> 2</span>'
        '<i class="fa-light fa-car-side"></i><span> 1</span>'
        '<i class="fa-light fa-ruler-triangle"></i><span> 70 M2</span></h3></p>'
        "<h3>Precio $2,000,000</h3>"
        f'<a href="Ficha.asp?xId={codigo} " class="btn">Ver</a></div></div>'
    )


@pytest.fixture
def sitio() -> Iterator[respx.MockRouter]:
    """Simula Panorama. Su robots.txt real solo tiene comentarios."""
    with respx.mock(base_url=URL_BASE, assert_all_called=False) as router:
        router.get("/robots.txt").respond(200, text="# solo comentarios\n")
        yield router


@pytest.fixture
def cliente() -> Iterator[ClienteCortes]:
    with ClienteCortes(URL_BASE, segundos_entre_peticiones=0) as c:
        yield c


# --------------------------------------------------------------------- Extracción y mapeo


def test_extraer_ciudades_ignora_el_top_10() -> None:
    ciudades = extraer_ciudades(_leer("descubrir_apto_arriendo.html"))

    assert {10000, 10001, 10007, 10041} <= ciudades
    assert 99999 not in ciudades


def test_extraer_paginas() -> None:
    assert extraer_paginas(_leer("apto_medellin_ultima.html")) == 7
    assert extraer_paginas(_leer("vacia.html")) == 0


def test_extraer_tarjetas() -> None:
    tarjetas = extraer_tarjetas(_leer("apto_medellin_p1.html"))

    assert [t["codigo"] for t in tarjetas] == ["1820790", "1820710", "1820708"]
    assert tarjetas[0] == {
        "codigo": "1820790",
        "barrio": "ROBLEDO",
        "precio": "1,800,000",
        "alcobas": "2",
        "banos": "1",
        "parqueaderos": "0",
        "area": "60 M2",
    }


def test_local_sin_alcobas() -> None:
    tarjeta = extraer_tarjetas(_leer("locales_medellin.html"))[0]

    assert tarjeta["alcobas"] is None
    assert (tarjeta["banos"], tarjeta["area"]) == ("0", "100 M2")


def test_codificacion_cp1252() -> None:
    tarjeta = extraer_tarjetas(_leer("apto_medellin_ultima.html"))[0]

    assert tarjeta["barrio"] == "BELÉN SAN BERNARDO"


def test_mapear_tarjeta_sin_ficha() -> None:
    tarjeta = extraer_tarjetas(_leer("apto_medellin_p1.html"))[0]

    a = mapear_anuncio(tarjeta, None, Operacion.ARRIENDO, "apartamento", "Medellín", FECHA)

    assert (a.fuente, a.id_fuente) == ("panorama", "1820790")
    assert a.url == f"{URL_BASE}/Ficha.asp?xId=1820790"
    assert (a.tipo_inmueble, a.precio, a.area_m2) == ("apartamento", 1_800_000, 60.0)
    assert (a.habitaciones, a.banos, a.parqueaderos) == (2, 1, 0)
    assert (a.barrio, a.municipio, a.estrato) == ("ROBLEDO", "Medellín", None)


def test_ficha_estrato_y_barrio_tienen_prioridad() -> None:
    tarjeta = extraer_tarjetas(_leer("apto_medellin_p1.html"))[1]
    ficha = extraer_ficha(_leer("ficha_arriendo.html"))

    a = mapear_anuncio(tarjeta, ficha, Operacion.ARRIENDO, "apartamento", "Medellín", FECHA)

    assert (a.estrato, a.barrio) == (3, "Rodeo Alto")


def test_extraer_ficha_convierte_entidades() -> None:
    ficha = extraer_ficha(_leer("ficha_venta.html"))

    assert ficha["Estrato"] == "5"
    assert ficha["Valor Administracion"] == "cop $0"
    assert ficha["Baños familiares"].startswith("3")


def test_administracion_cero_es_nula() -> None:
    tarjeta = extraer_tarjetas(_leer("apto_medellin_p1.html"))[1]
    ficha = extraer_ficha(_leer("ficha_venta.html"))

    a = mapear_anuncio(tarjeta, ficha, Operacion.VENTA, "apartamento", "Medellín", FECHA)

    assert a.administracion is None


def test_ficha_de_local_sin_estrato() -> None:
    assert "Estrato" not in extraer_ficha(_leer("ficha_local.html"))


def test_valores_como_dos_mas_uno() -> None:
    (tarjeta,) = extraer_tarjetas(_pagina([_tarjeta(5)], pagina=1, paginas=1).decode("cp1252"))

    a = mapear_anuncio(tarjeta, None, Operacion.ARRIENDO, "apartamento", "Bello", FECHA)

    assert a.habitaciones == 2


def test_corregimientos_son_medellin() -> None:
    assert MUNICIPIOS[10041] == MUNICIPIOS[10037] == "Medellín"


# --------------------------------------------------------------------- Protocolo y registro


def test_cumple_protocolo_fuente(cliente: ClienteCortes) -> None:
    assert isinstance(FuentePanorama(cliente), Fuente)


def test_registrada_en_cli() -> None:
    assert "panorama" in REGISTRO
    assert REGISTRO["panorama"].url_base == URL_BASE


# --------------------------------------------------------------------- Recorrido


@pytest.fixture
def solo_apartamentos_en_medellin(sitio: respx.MockRouter) -> None:
    """Descubrimiento: solo Medellín tiene apartamentos en arriendo; nada más tiene inventario."""
    descubrir = '<a href="/Resumen_Ciudad_arriendos.asp?pCiudad=10000&pTipoInmueble=1">M</a>'
    sitio.get("/listado_arriendos.asp", params={"sZona": "1"}).respond(
        200, content=descubrir.encode("cp1252")
    )
    sitio.get("/listado_arriendos.asp").respond(200, content=b"<html></html>")
    sitio.get("/listado_ventas.asp").respond(200, content=b"<html></html>")


@pytest.mark.usefixtures("solo_apartamentos_en_medellin")
def test_corta_con_el_total_aunque_el_sitio_repita_la_ultima(
    sitio: respx.MockRouter, cliente: ClienteCortes
) -> None:
    """Después de la última página el sitio la repite en vez de responder vacío."""
    ruta = sitio.get("/resumen_ciudad_arriendos.asp").mock(
        side_effect=lambda request: respx.MockResponse(
            200,
            content=_pagina(
                [_tarjeta(1000 + int(request.url.params["offset"]))], pagina=3, paginas=3
            ),
        )
    )

    anuncios = list(FuentePanorama(cliente, con_detalle=False).listar_anuncios())

    assert ruta.call_count == 3
    assert [r.request.url.params["offset"] for r in ruta.calls] == ["0", "50", "100"]
    assert len(anuncios) == 3


@pytest.mark.usefixtures("solo_apartamentos_en_medellin")
def test_combinacion_vacia(sitio: respx.MockRouter, cliente: ClienteCortes) -> None:
    ruta = sitio.get("/resumen_ciudad_arriendos.asp").respond(200, content=_bytes("vacia.html"))

    assert list(FuentePanorama(cliente, con_detalle=False).listar_anuncios()) == []
    assert ruta.call_count == 1


@pytest.mark.usefixtures("solo_apartamentos_en_medellin")
def test_pide_la_ficha_de_los_residenciales(
    sitio: respx.MockRouter, cliente: ClienteCortes
) -> None:
    sitio.get("/resumen_ciudad_arriendos.asp").respond(
        200, content=_pagina([_tarjeta(1820710)], pagina=1, paginas=1)
    )
    ficha = sitio.get("/Ficha.asp", params={"xId": "1820710"}).respond(
        200, content=_bytes("ficha_arriendo.html")
    )

    (anuncio,) = FuentePanorama(cliente).listar_anuncios()

    assert ficha.call_count == 1
    assert (anuncio.estrato, anuncio.barrio, anuncio.tipo_inmueble) == (
        3,
        "Rodeo Alto",
        "apartamento",
    )


def test_ficha_solo_para_residenciales() -> None:
    assert {TIPOS[c] for c in (1, 2, 4)} == {"apartamento", "casa", "apartaestudio"}
    assert FuentePanorama.necesita_ficha(1) and not FuentePanorama.necesita_ficha(7)


@pytest.mark.usefixtures("solo_apartamentos_en_medellin")
def test_ficha_500_deja_datos_del_listado(sitio: respx.MockRouter, cliente: ClienteCortes) -> None:
    """Un anuncio retirado responde 500 en su ficha."""
    sitio.get("/resumen_ciudad_arriendos.asp").respond(
        200, content=_pagina([_tarjeta(9999999)], pagina=1, paginas=1)
    )
    sitio.get("/Ficha.asp").respond(500)

    with ClienteCortes(URL_BASE, segundos_entre_peticiones=0, max_intentos=1) as rapido:
        (anuncio,) = FuentePanorama(rapido).listar_anuncios()

    assert anuncio.estrato is None and anuncio.precio == 2_000_000


@pytest.mark.usefixtures("solo_apartamentos_en_medellin")
def test_duplicados_salen_una_vez(sitio: respx.MockRouter, cliente: ClienteCortes) -> None:
    sitio.get("/resumen_ciudad_arriendos.asp").respond(
        200, content=_pagina([_tarjeta(1), _tarjeta(1)], pagina=1, paginas=1)
    )

    assert len(list(FuentePanorama(cliente, con_detalle=False).listar_anuncios())) == 1


@pytest.mark.usefixtures("solo_apartamentos_en_medellin")
def test_max_paginas(sitio: respx.MockRouter, cliente: ClienteCortes) -> None:
    ruta = sitio.get("/resumen_ciudad_arriendos.asp").respond(
        200, content=_pagina([_tarjeta(1)], pagina=1, paginas=5)
    )

    list(FuentePanorama(cliente, con_detalle=False, max_paginas=2).listar_anuncios())

    assert ruta.call_count == 2
