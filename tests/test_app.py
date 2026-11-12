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


# ------------------------------------------------------------------ Tarea 4

PAGINAS_2 = [
    "pages/4_Propiedades_compartidas.py",
    "pages/5_Evolución.py",
    "pages/6_Metodología.py",
]


@pytest.mark.parametrize("pagina", PAGINAS_2)
def test_pagina_2_corre_sin_errores(pagina: str) -> None:
    app = _correr(pagina)
    assert app.title


def test_compartidos_sin_columnas_privadas() -> None:
    app = _correr("pages/4_Propiedades_compartidas.py")
    assert app.dataframe
    for tabla in app.dataframe:
        columnas = {str(c).lower() for c in tabla.value.columns}
        assert not columnas & {"id_fuente", "url", "latitud", "longitud"}


def test_compartidos_cambia_nivel() -> None:
    app = _correr("pages/4_Propiedades_compartidas.py")
    app.radio(key="nivel_compartidos").set_value("baja").run()
    assert not app.exception


def test_evolucion_una_semana_muestra_aviso() -> None:
    app = _correr("pages/5_Evolución.py")
    assert any("una sola semana" in i.value for i in app.info)


def test_metodologia_tiene_aviso_legal() -> None:
    app = _correr("pages/6_Metodología.py")
    texto = " ".join(m.value for m in app.markdown)
    assert "retirar sus datos" in texto
    assert "Google Places" in texto


# ------------------------------------------------- Revisión final del plan 7


def _con_tablas(monkeypatch: pytest.MonkeyPatch, **cambios: pd.DataFrame) -> None:
    """Las páginas reciben las tablas reales con algunas reemplazadas."""
    from observatorio_inmobiliario.tablero import datos, vista

    reales = datos.cargar_agregados()
    monkeypatch.setattr(vista, "cargar_agregados", lambda directorio=None: {**reales, **cambios})


def test_inicio_mediana_nula_en_la_ultima_semana(monkeypatch: pytest.MonkeyPatch) -> None:
    from observatorio_inmobiliario.tablero import datos

    evolucion = datos.cargar_agregados()["evolucion_precios"]
    nueva = evolucion.assign(semana="2026-S47", precio_m2_mediana=pd.NA)
    _con_tablas(monkeypatch, evolucion_precios=pd.concat([evolucion, nueva], ignore_index=True))
    app = _correr("Inicio.py")
    assert all(m.value for m in app.metric)


def test_inmobiliarias_sin_barrios(monkeypatch: pytest.MonkeyPatch) -> None:
    from observatorio_inmobiliario.tablero import datos

    cobertura = datos.cargar_agregados()["cobertura_inmobiliaria"].assign(barrios=0)
    _con_tablas(monkeypatch, cobertura_inmobiliaria=cobertura)
    _correr("pages/3_Inmobiliarias.py")
