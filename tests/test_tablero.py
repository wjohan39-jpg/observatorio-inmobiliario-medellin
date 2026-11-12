from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import pytest

from observatorio_inmobiliario.almacenamiento import TABLAS_AGREGADAS
from observatorio_inmobiliario.tablero import graficas, vista
from observatorio_inmobiliario.tablero.datos import (
    RAIZ,
    cargar_agregados,
    cargar_geojson,
    tablas_vacias,
)


@pytest.fixture(scope="module")
def reales() -> dict[str, pd.DataFrame]:
    return cargar_agregados()


@pytest.fixture(scope="module")
def vacias() -> dict[str, pd.DataFrame]:
    return tablas_vacias()


# ------------------------------------------------------------------ Datos


def test_raiz_es_el_repo() -> None:
    assert (RAIZ / "pyproject.toml").exists()


def test_cargar_agregados_reales(reales: dict[str, pd.DataFrame]) -> None:
    assert set(reales) == set(TABLAS_AGREGADAS)
    assert all(len(tabla) > 0 for tabla in reales.values())


def test_cargar_agregados_falta_archivo(tmp_path: Path, reales: dict[str, pd.DataFrame]) -> None:
    tablas = cargar_agregados(tmp_path)
    assert set(tablas) == set(TABLAS_AGREGADAS)
    for nombre, tabla in tablas.items():
        assert tabla.empty
        assert list(tabla.columns) == list(reales[nombre].columns), nombre


def test_cargar_geojson() -> None:
    geojson = cargar_geojson()
    assert len(geojson["features"]) == 349
    assert "codigo" in geojson["features"][0]["properties"]


def test_hay_datos(reales: dict[str, pd.DataFrame], vacias: dict[str, pd.DataFrame]) -> None:
    assert graficas.hay_datos(reales["precios_zona"])
    assert not graficas.hay_datos(vacias["precios_zona"])


# ---------------------------------------------------------------- Gráficas


def _con_nulo(precios: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    """Copia de ``precios`` con la mediana del m² nula en un barrio de venta de vivienda."""
    filas = precios[
        (precios["nivel"] == "barrio")
        & (precios["operacion"] == "venta")
        & (precios["tipo"] == "vivienda")
    ]
    indice = filas.index[0]
    copia = precios.copy()
    copia.loc[indice, "precio_m2_mediana"] = pd.NA
    return copia, str(copia.loc[indice, "codigo"])


def test_mapa_barrios_omite_nulos(reales: dict[str, pd.DataFrame]) -> None:
    precios, codigo = _con_nulo(reales["precios_zona"])
    figura = graficas.mapa_barrios(precios, cargar_geojson(), "venta")
    ubicaciones = {
        str(u) for traza in figura.data if traza.locations is not None for u in traza.locations
    }
    assert ubicaciones
    assert codigo not in ubicaciones


def test_ranking_barrios_cuantos(reales: dict[str, pd.DataFrame]) -> None:
    figura = graficas.ranking_barrios(reales["precios_zona"], "venta", cuantos=15)
    valores = [v for traza in figura.data for v in traza.x]
    assert len(valores) == 30  # 15 más baratos y 15 más caros
    assert all(pd.notna(v) for v in valores)


def test_estratos_distingue_inferidos(reales: dict[str, pd.DataFrame]) -> None:
    figura = graficas.estratos(reales["estratos_inmobiliaria"])
    nombres = {traza.name for traza in figura.data}
    assert nombres == {
        "1-3, declarado",
        "1-3, inferido",
        "4-6, declarado",
        "4-6, inferido",
    }


def _llamadas(tablas: dict[str, pd.DataFrame]) -> list[go.Figure]:
    geojson = cargar_geojson()
    return [
        graficas.mapa_barrios(tablas["precios_zona"], geojson, "venta"),
        graficas.ranking_barrios(tablas["precios_zona"], "arriendo"),
        graficas.comparacion_comunas(tablas["precios_zona"]),
        graficas.cobertura(tablas["cobertura_inmobiliaria"]),
        graficas.concentracion(tablas["cobertura_comuna"]),
        graficas.indice_relativo(tablas["economia_inmobiliaria"], "arriendo"),
        graficas.estratos(tablas["estratos_inmobiliaria"]),
        graficas.compartidos(tablas["compartidos_fuentes"], "media"),
        graficas.evolucion(tablas["evolucion_precios"], "venta"),
    ]


def test_graficas_con_datos_reales(reales: dict[str, pd.DataFrame]) -> None:
    for figura in _llamadas(reales):
        assert isinstance(figura, go.Figure)
        assert figura.layout.title.text


def test_graficas_con_tablas_vacias(vacias: dict[str, pd.DataFrame]) -> None:
    for figura in _llamadas(vacias):
        assert isinstance(figura, go.Figure)


def test_colores_fijos_por_inmobiliaria(reales: dict[str, pd.DataFrame]) -> None:
    assert set(graficas.COLORES_FUENTE) >= set(reales["cobertura_inmobiliaria"]["fuente"])


# ---------------------------------------------------------------- Formato


@pytest.mark.parametrize(
    ("valor", "texto"),
    [
        (5_079_208, "$5,08 M"),
        (42_553, "$42.553"),
        (999, "$999"),
        (1_234_567_890, "$1.234,57 M"),
    ],
)
def test_pesos_en_formato_colombiano(valor: float, texto: str) -> None:
    assert vista.pesos(valor) == texto


def test_entero_en_formato_colombiano() -> None:
    assert vista.entero(5630) == "5.630"
