import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import respx

from observatorio_inmobiliario.catalogo import (
    RUTA_CATALOGO,
    URL_BASE_CATALOGO,
    Catalogo,
    descargar_catalogo,
)
from observatorio_inmobiliario.http import ClienteCortes

MINI = Path(__file__).parent / "fixtures" / "catalogo" / "mini.geojson"


def _alias(tmp_path: Path, filas: str = "") -> Path:
    ruta = tmp_path / "alias.csv"
    ruta.write_text("alias,codigo\n" + filas, encoding="utf-8")
    return ruta


@pytest.fixture
def catalogo(tmp_path: Path) -> Catalogo:
    """Tres cuadrados: Laureles (1101) y Naranjal (1103) urbanos, Naranjal (6005) rural."""
    return Catalogo.cargar(MINI, _alias(tmp_path))


@pytest.fixture
def catalogo_con_alias(tmp_path: Path) -> Catalogo:
    return Catalogo.cargar(MINI, _alias(tmp_path, "laureles,11\n"))


@pytest.fixture
def catalogo_dos_urbanos(tmp_path: Path) -> Catalogo:
    geojson = json.loads(MINI.read_text(encoding="utf-8"))
    for feature in geojson["features"]:
        if feature["properties"]["codigo"] == "6005":
            feature["properties"]["indicador_ur"] = "U"
    ruta = tmp_path / "dos.geojson"
    ruta.write_text(json.dumps(geojson), encoding="utf-8")
    return Catalogo.cargar(ruta, _alias(tmp_path))


@pytest.fixture(scope="module")
def catalogo_real() -> Catalogo:
    """El catálogo versionado en ``datos_referencia/``."""
    return Catalogo.cargar()


# --------------------------------------------------------------------- Por coordenadas


def test_punto_dentro(catalogo: Catalogo) -> None:
    ubicacion = catalogo.por_coordenadas(6.245, -75.595)

    assert ubicacion is not None
    assert (ubicacion.codigo_barrio, ubicacion.barrio) == ("1101", "Laureles")
    assert (ubicacion.comuna, ubicacion.nombre_comuna) == ("11", "LAURELES")
    assert ubicacion.metodo == "coordenadas"


def test_punto_fuera(catalogo: Catalogo) -> None:
    assert catalogo.por_coordenadas(6.10, -75.60) is None


def test_punto_en_el_borde_es_el_de_menor_codigo(catalogo: Catalogo) -> None:
    """El borde entre 1101 y 1103 queda en 1101, siempre."""
    ubicacion = catalogo.por_coordenadas(6.245, -75.59)

    assert ubicacion is not None and ubicacion.codigo_barrio == "1101"


def test_punto_en_el_vertice(catalogo: Catalogo) -> None:
    """El vértice que comparten los tres cuadrados."""
    ubicacion = catalogo.por_coordenadas(6.25, -75.59)

    assert ubicacion is not None and ubicacion.codigo_barrio == "1101"


# --------------------------------------------------------------------- Por nombre


@pytest.mark.parametrize("texto", ["Laureles", "LAURELES", "laureles "])
def test_alias_de_zona_da_solo_la_comuna(catalogo_con_alias: Catalogo, texto: str) -> None:
    ubicacion = catalogo_con_alias.por_nombre(texto)

    assert ubicacion is not None
    assert (ubicacion.codigo_barrio, ubicacion.barrio) == (None, None)
    assert (ubicacion.comuna, ubicacion.nombre_comuna, ubicacion.metodo) == (
        "11",
        "LAURELES",
        "alias",
    )


def test_nombre_exacto(catalogo: Catalogo) -> None:
    ubicacion = catalogo.por_nombre("LAURELES")

    assert ubicacion is not None
    assert (ubicacion.codigo_barrio, ubicacion.metodo) == ("1101", "nombre")


def test_repetido_elige_el_unico_urbano(catalogo: Catalogo) -> None:
    ubicacion = catalogo.por_nombre("Naranjal")

    assert ubicacion is not None and ubicacion.codigo_barrio == "1103"


def test_repetido_sin_urbano_unico_es_none(catalogo_dos_urbanos: Catalogo) -> None:
    assert catalogo_dos_urbanos.por_nombre("Naranjal") is None


@pytest.mark.parametrize("texto", [None, "", "  "])
def test_vacio(catalogo: Catalogo, texto: str | None) -> None:
    assert catalogo.por_nombre(texto) is None


def test_alias_a_codigo_inexistente(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="poblado"):
        Catalogo.cargar(MINI, _alias(tmp_path, "poblado,14\n"))


# --------------------------------------------------------------------- Catálogo real


def test_catalogo_real(catalogo_real: Catalogo) -> None:
    assert len(catalogo_real) == 349


@pytest.mark.parametrize(
    ("latitud", "longitud", "comuna"),
    [
        (6.2566, -75.5904, "11"),  # estadio Atanasio Girardot
        (6.2087, -75.5676, "14"),  # parque Lleras
    ],
)
def test_catalogo_real_por_coordenadas(
    catalogo_real: Catalogo, latitud: float, longitud: float, comuna: str
) -> None:
    ubicacion = catalogo_real.por_coordenadas(latitud, longitud)

    assert ubicacion is not None and ubicacion.comuna == comuna


def test_envigado_no_esta_en_el_catalogo(catalogo_real: Catalogo) -> None:
    assert catalogo_real.por_coordenadas(6.1700, -75.5900) is None


def test_articulo_opcional(catalogo_real: Catalogo) -> None:
    ubicacion = catalogo_real.por_nombre("Conquistadores")

    assert ubicacion is not None and ubicacion.codigo_barrio == "1105"


def test_prefijo_barrio(catalogo_real: Catalogo) -> None:
    ubicacion = catalogo_real.por_nombre("Barrio Córdoba")

    assert ubicacion is not None and ubicacion.barrio == "Córdoba"


def test_prefijo_de_comuna(catalogo_real: Catalogo) -> None:
    ubicacion = catalogo_real.por_nombre("Belén San Bernardo")

    assert ubicacion is not None and ubicacion.codigo_barrio == "1605"


@pytest.mark.parametrize(
    "texto", ["Manrique Central No.1", "manrique central 1", "MANRIQUE CENTRAL NO. 1"]
)
def test_variantes_de_numero(catalogo_real: Catalogo, texto: str) -> None:
    ubicacion = catalogo_real.por_nombre(texto)

    assert ubicacion is not None and ubicacion.codigo_barrio == "0409"


@pytest.mark.parametrize(("texto", "comuna"), [("Poblado", "14"), ("BELEN", "16")])
def test_alias_reales(catalogo_real: Catalogo, texto: str, comuna: str) -> None:
    ubicacion = catalogo_real.por_nombre(texto)

    assert ubicacion is not None
    assert (ubicacion.comuna, ubicacion.codigo_barrio, ubicacion.metodo) == (comuna, None, "alias")


def test_sin_coincidencia(catalogo_real: Catalogo) -> None:
    assert catalogo_real.por_nombre("Torres de Bomboná") is None


# --------------------------------------------------------------------- Descarga


@pytest.fixture
def servidor() -> Iterator[respx.MockRouter]:
    with respx.mock(base_url=URL_BASE_CATALOGO, assert_all_called=False) as router:
        router.get("/robots.txt").respond(200, text="User-agent: *\nDisallow: /test/*\n")
        yield router


def _coleccion(n: int) -> dict[str, Any]:
    feature = json.loads(MINI.read_text(encoding="utf-8"))["features"][0]
    return {"type": "FeatureCollection", "features": [feature] * n}


def test_descargar_catalogo(servidor: respx.MockRouter) -> None:
    ruta = servidor.get(RUTA_CATALOGO).respond(200, json=_coleccion(349))

    with ClienteCortes(URL_BASE_CATALOGO, segundos_entre_peticiones=0) as cliente:
        geojson = descargar_catalogo(cliente)

    assert len(geojson["features"]) == 349
    params = ruta.calls.last.request.url.params
    assert (params["outSR"], params["f"]) == ("4326", "geojson")
    assert params["outFields"] == "codigo,nombre_barrio,comuna,nombre_comuna,indicador_ur"


def test_descargar_catalogo_incompleto(servidor: respx.MockRouter) -> None:
    servidor.get(RUTA_CATALOGO).respond(200, json=_coleccion(10))

    with (
        ClienteCortes(URL_BASE_CATALOGO, segundos_entre_peticiones=0) as cliente,
        pytest.raises(ValueError, match="10"),
    ):
        descargar_catalogo(cliente)


def test_descargar_catalogo_que_no_es_geojson(servidor: respx.MockRouter) -> None:
    servidor.get(RUTA_CATALOGO).respond(200, json=["no", "es", "geojson"])

    with (
        ClienteCortes(URL_BASE_CATALOGO, segundos_entre_peticiones=0) as cliente,
        pytest.raises(ValueError, match="GeoJSON"),
    ):
        descargar_catalogo(cliente)


@pytest.mark.parametrize(
    ("texto", "comuna"),
    [("Belén Parque", "16"), ("BELEN LA NUBIA", "16"), ("Laureles 2do Parque", "11")],
)
def test_sector_con_nombre_de_comuna_da_la_comuna(
    catalogo_real: Catalogo, texto: str, comuna: str
) -> None:
    """Sectores que no son barrios oficiales, pero empiezan con el nombre de su comuna."""
    ubicacion = catalogo_real.por_nombre(texto)

    assert ubicacion is not None
    assert (ubicacion.comuna, ubicacion.codigo_barrio, ubicacion.metodo) == (comuna, None, "alias")


@pytest.mark.parametrize(
    ("texto", "comuna", "codigo"),
    [
        ("Avenida Nutibara", "11", None),
        ("Vía Las Palmas", "14", None),
        ("Malibú", "16", None),
        ("Vereda El Manzanillo", "70", "7089"),
    ],
)
def test_alias_agregados_tras_la_corrida_real(
    catalogo_real: Catalogo, texto: str, comuna: str, codigo: str | None
) -> None:
    ubicacion = catalogo_real.por_nombre(texto)

    assert ubicacion is not None
    assert (ubicacion.comuna, ubicacion.codigo_barrio) == (comuna, codigo)
