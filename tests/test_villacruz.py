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
from observatorio_inmobiliario.fuentes.villacruz import (
    RUTA_SITEMAP,
    URL_BASE,
    FuenteVillacruz,
    extraer_propiedad,
    mapear_anuncio,
    slugs_propios,
)
from observatorio_inmobiliario.http import ClienteCortes
from observatorio_inmobiliario.modelos import Operacion

FIXTURES = Path(__file__).parent / "fixtures" / "villacruz"
FECHA = date(2026, 11, 11)
BELLO = "apartamento-enarriendo-en-bello-53744"


def _leer(nombre: str) -> str:
    return (FIXTURES / nombre).read_text(encoding="utf-8")


def _propiedad(nombre: str) -> dict[str, Any]:
    propiedad = extraer_propiedad(_leer(nombre))
    assert propiedad is not None
    return propiedad


def _sitemap(slugs: list[str]) -> str:
    urls = "".join(f"<url><loc>{URL_BASE}/detalle-propiedad/{s}</loc></url>" for s in slugs)
    return f'<?xml version="1.0"?><urlset>{urls}</urlset>'


def _detalle(propiedad: dict[str, Any]) -> str:
    return f"<script>let property= {json.dumps(propiedad)};</script>"


@pytest.fixture
def sitio() -> Iterator[respx.MockRouter]:
    with respx.mock(base_url=URL_BASE, assert_all_called=False) as router:
        router.get("/robots.txt").respond(200, text="User-agent: *\nDisallow: /login\n")
        yield router


@pytest.fixture
def cliente() -> Iterator[ClienteCortes]:
    with ClienteCortes(URL_BASE, segundos_entre_peticiones=0) as c:
        yield c


# --------------------------------------------------------------------- Extracción y mapeo


def test_slugs_propios() -> None:
    """Sin las ventas MLS de otras agencias, sin Rionegro y sin páginas que no son anuncios."""
    assert slugs_propios(_leer("sitemap.xml")) == [
        BELLO,
        "apartaestudio-enarriendo-en-laureles-53817",
        "apartamento-enventa-en-san-javier-53184",
    ]


def test_pagina_sin_propiedad_es_none() -> None:
    """Un código inexistente redirige a la portada, que no trae ``let property=``."""
    assert extraer_propiedad("<html><body>Inicio</body></html>") is None


def test_mapear_arriendo_bello() -> None:
    a = mapear_anuncio(_propiedad("detalle_arriendo_bello.html"), BELLO, FECHA)

    assert (a.fuente, a.id_fuente) == ("villacruz", "53744")
    assert a.url == f"{URL_BASE}/detalle-propiedad/{BELLO}"
    assert a.operacion is Operacion.ARRIENDO
    assert (a.tipo_inmueble, a.precio, a.area_m2) == ("apartamento", 1_500_000, 60.0)
    assert (a.habitaciones, a.banos, a.parqueaderos, a.estrato) == (3, 2, 0, 3)
    assert (a.barrio, a.municipio) == ("BELLO", "Bello")
    assert (a.latitud, a.longitud) == (6.3555136, -75.5676543)


def test_amoblado_es_arriendo() -> None:
    propiedad = _propiedad("detalle_amoblado.html")
    assert propiedad["management"] == "Amoblado"

    a = mapear_anuncio(propiedad, propiedad["slug"], FECHA)

    assert a.operacion is Operacion.ARRIENDO


def test_venta_propia() -> None:
    propiedad = _propiedad("detalle_venta_propia.html")

    a = mapear_anuncio(propiedad, propiedad["slug"], FECHA)

    assert a.operacion is Operacion.VENTA
    assert a.estrato == 3


def test_area_con_punto_de_miles() -> None:
    propiedad = _propiedad("detalle_lote.html")
    assert propiedad["area"] == "7.089"

    assert mapear_anuncio(propiedad, propiedad["slug"], FECHA).area_m2 == 7089.0


def test_barrio_que_no_es_municipio() -> None:
    propiedad = _propiedad("detalle_amoblado.html")

    a = mapear_anuncio(propiedad, propiedad["slug"], FECHA)

    assert (a.barrio, a.municipio) == ("LAURELES", None)


@pytest.mark.parametrize(("barrio", "municipio"), [("MEDELLIN", "Medellín"), ("Itagüí", "Itagüí")])
def test_municipio_sin_tildes_ni_mayusculas(barrio: str, municipio: str) -> None:
    propiedad = {**_propiedad("detalle_arriendo_bello.html"), "neighborhood": barrio}

    assert mapear_anuncio(propiedad, BELLO, FECHA).municipio == municipio


# --------------------------------------------------------------------- Protocolo y registro


def test_cumple_protocolo_fuente(cliente: ClienteCortes) -> None:
    assert isinstance(FuenteVillacruz(cliente), Fuente)


def test_registrada_en_cli() -> None:
    assert "villacruz" in REGISTRO
    assert REGISTRO["villacruz"].url_base == URL_BASE


# --------------------------------------------------------------------- Recorrido


def test_pide_el_detalle_de_cada_anuncio_propio(
    sitio: respx.MockRouter, cliente: ClienteCortes
) -> None:
    sitio.get(RUTA_SITEMAP).respond(200, text=_leer("sitemap.xml"))
    rutas = [
        sitio.get(f"/detalle-propiedad/{slug}").respond(200, text=_leer(fixture))
        for slug, fixture in [
            (BELLO, "detalle_arriendo_bello.html"),
            ("apartaestudio-enarriendo-en-laureles-53817", "detalle_amoblado.html"),
            ("apartamento-enventa-en-san-javier-53184", "detalle_venta_propia.html"),
        ]
    ]

    anuncios = list(FuenteVillacruz(cliente, fecha=FECHA).listar_anuncios())

    assert [a.id_fuente for a in anuncios] == ["53744", "53817", "53184"]
    assert [r.call_count for r in rutas] == [1, 1, 1]


def test_redireccion_al_inicio_se_omite(
    sitio: respx.MockRouter, cliente: ClienteCortes, caplog: pytest.LogCaptureFixture
) -> None:
    retirado = "apartamento-enarriendo-en-belen-99999"
    sitio.get(RUTA_SITEMAP).respond(200, text=_sitemap([retirado, BELLO]))
    sitio.get(f"/detalle-propiedad/{retirado}").respond(302, headers={"Location": "/"})
    sitio.get("/").respond(200, text="<html><body>Inicio</body></html>")
    sitio.get(f"/detalle-propiedad/{BELLO}").respond(200, text=_leer("detalle_arriendo_bello.html"))

    with caplog.at_level(logging.WARNING):
        anuncios = list(FuenteVillacruz(cliente).listar_anuncios())

    assert [a.id_fuente for a in anuncios] == ["53744"]
    assert retirado in caplog.text


def test_detalle_que_falla_no_tumba_la_corrida(
    sitio: respx.MockRouter, cliente: ClienteCortes
) -> None:
    roto = "apartamento-enarriendo-en-belen-88888"
    sitio.get(RUTA_SITEMAP).respond(200, text=_sitemap([roto, BELLO]))
    sitio.get(f"/detalle-propiedad/{roto}").respond(404)
    sitio.get(f"/detalle-propiedad/{BELLO}").respond(200, text=_leer("detalle_arriendo_bello.html"))

    assert [a.id_fuente for a in FuenteVillacruz(cliente).listar_anuncios()] == ["53744"]


def test_max_paginas_limita_detalles(sitio: respx.MockRouter, cliente: ClienteCortes) -> None:
    slugs = [f"apartamento-enarriendo-en-laureles-{n}" for n in range(1, 31)]
    sitio.get(RUTA_SITEMAP).respond(200, text=_sitemap(slugs))
    propiedad = _propiedad("detalle_amoblado.html")
    detalles = sitio.get(path__startswith="/detalle-propiedad/").mock(
        side_effect=lambda request: respx.MockResponse(
            200, text=_detalle({**propiedad, "code": request.url.path.rsplit("-", 1)[-1]})
        )
    )

    anuncios = list(FuenteVillacruz(cliente, max_paginas=2).listar_anuncios())

    assert detalles.call_count == 24  # 2 × 12
    assert len(anuncios) == 24


def test_codigo_repetido_sale_una_vez(sitio: respx.MockRouter, cliente: ClienteCortes) -> None:
    """El sitemap puede listar el mismo anuncio con un slug viejo y uno nuevo."""
    viejo = "casa-enarriendo-en-bello-53744"
    sitio.get(RUTA_SITEMAP).respond(200, text=_sitemap([BELLO, viejo]))
    sitio.get(path__startswith="/detalle-propiedad/").respond(
        200, text=_leer("detalle_arriendo_bello.html")
    )

    assert [a.id_fuente for a in FuenteVillacruz(cliente).listar_anuncios()] == ["53744"]


def test_redireccion_a_otro_anuncio_se_omite(
    sitio: respx.MockRouter, cliente: ClienteCortes, caplog: pytest.LogCaptureFixture
) -> None:
    """Si el código de la página no es el del slug, la página es de otro anuncio."""
    ajeno = "apartamento-enarriendo-en-belen-77777"
    sitio.get(RUTA_SITEMAP).respond(200, text=_sitemap([ajeno]))
    sitio.get(f"/detalle-propiedad/{ajeno}").respond(200, text=_leer("detalle_arriendo_bello.html"))

    with caplog.at_level(logging.WARNING):
        assert list(FuenteVillacruz(cliente).listar_anuncios()) == []
    assert ajeno in caplog.text
