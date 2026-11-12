"""Pruebas de punta a punta de las páginas del dashboard, sin navegador ni red."""

from collections.abc import Iterator
from pathlib import Path

import pandas as pd
import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from observatorio_inmobiliario import reputacion
from observatorio_inmobiliario.reputacion import Reseñas

APP = Path(__file__).parent.parent / "app"
PAGINAS_1 = ["Inicio.py", "pages/2_Barrios.py", "pages/3_Inmobiliarias.py"]


@pytest.fixture(autouse=True)
def sin_clave_ni_cache(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Cada prueba arranca sin clave de Google y con la caché de Streamlit vacía."""
    monkeypatch.delenv(reputacion.VARIABLE_CLAVE, raising=False)
    st.cache_data.clear()
    yield
    st.cache_data.clear()


def _correr(pagina: str) -> AppTest:
    app = AppTest.from_file(str(APP / pagina), default_timeout=60)
    app.run()
    assert not app.exception, app.exception
    return app


@pytest.mark.parametrize("pagina", PAGINAS_1)
def test_pagina_corre_sin_errores(pagina: str) -> None:
    app = _correr(pagina)
    assert app.title


def test_inicio_muestra_kpis() -> None:
    app = _correr("Inicio.py")
    assert len(app.metric) == 5
    assert all(m.value for m in app.metric)


def test_barrios_cambia_operacion() -> None:
    app = _correr("pages/2_Barrios.py")
    app.radio(key="operacion_barrios").set_value("arriendo").run()
    assert not app.exception


def test_inmobiliarias_sin_clave() -> None:
    app = _correr("pages/3_Inmobiliarias.py")
    avisos = " ".join(i.value for i in app.info)
    assert "Google" in avisos


def test_inmobiliarias_con_reputacion_falsa(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(reputacion.VARIABLE_CLAVE, "clave-falsa")
    sedes = pd.DataFrame(
        {"fuente": ["alnago", "santafe"], "sede": ["A", "S"], "place_id": ["P1", "P2"]}
    ).astype("string")
    monkeypatch.setattr(reputacion, "cargar_sedes", lambda ruta=None: sedes)
    respuestas = {"P1": Reseñas(4.5, 200), "P2": Reseñas(3.9, 40)}
    monkeypatch.setattr(
        reputacion, "consultar_sede", lambda cliente, place_id, clave: respuestas[place_id]
    )

    app = _correr("pages/3_Inmobiliarias.py")

    tablas = [d.value for d in app.dataframe]
    con_reputacion = [t for t in tablas if "calificacion" in t.columns]
    assert con_reputacion
    assert set(con_reputacion[0]["fuente"]) == {"alnago", "santafe"}
