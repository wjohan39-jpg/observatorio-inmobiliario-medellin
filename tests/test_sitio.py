"""Sitio estático para GitHub Pages: misma información que el dashboard, sin servidor."""

from pathlib import Path

import pandas as pd
import pytest

from observatorio_inmobiliario.tablero.datos import (
    cargar_agregados,
    cargar_geojson,
    tablas_vacias,
)
from observatorio_inmobiliario.tablero.formato import entero, indicadores, pesos
from observatorio_inmobiliario.tablero.sitio import generar_sitio

SECCIONES = ["resumen", "barrios", "inmobiliarias", "compartidos", "evolucion", "metodologia"]


@pytest.fixture(scope="module")
def reales() -> dict[str, pd.DataFrame]:
    return cargar_agregados()


def test_generar_sitio_con_datos_reales(tmp_path: Path, reales: dict[str, pd.DataFrame]) -> None:
    ruta = generar_sitio(reales, cargar_geojson(), tmp_path / "sitio")

    assert ruta == tmp_path / "sitio" / "index.html"
    html = ruta.read_text(encoding="utf-8")
    for seccion in SECCIONES:
        assert f'id="{seccion}"' in html, seccion
    assert html.count("Plotly.newPlot") >= 10
    assert html.count("cdn.plot.ly") == 1  # plotly.js se carga una sola vez
    assert "2026-S46" in html
    assert "Villa Carlota" in html
    for privada in ("id_fuente", "latitud", "longitud", "anunciante_origen"):
        assert privada not in html, privada
    assert '<html lang="es">' in html


def test_generar_sitio_con_tablas_vacias(tmp_path: Path) -> None:
    html = generar_sitio(tablas_vacias(), cargar_geojson(), tmp_path).read_text(encoding="utf-8")
    assert "Todavía no hay datos" in html or "Sin datos" in html
    for seccion in SECCIONES:
        assert f'id="{seccion}"' in html


def test_indicadores(reales: dict[str, pd.DataFrame]) -> None:
    kpis = dict(indicadores(reales))
    assert list(kpis) == [
        "Anuncios analizados",
        "Barrios con precio",
        "m² de vivienda en venta",
        "m² de vivienda en arriendo",
        "Inmobiliarias",
    ]
    assert kpis["Anuncios analizados"] == "5.630"
    assert kpis["Inmobiliarias"] == "9"
    assert kpis["m² de vivienda en venta"].endswith(" M")


def test_indicadores_vacios() -> None:
    kpis = dict(indicadores(tablas_vacias()))
    assert kpis["Anuncios analizados"] == "0"
    assert kpis["m² de vivienda en venta"] == "—"


def test_formato_movido() -> None:
    assert entero(5630) == "5.630"
    assert pesos(5_079_208) == "$5,08 M"
