"""Piezas de Streamlit compartidas por las páginas de ``app/``: datos con caché y reputación.

Están en el paquete, y no junto a las páginas, para que se importen igual desde
``streamlit run``, desde Streamlit Cloud y desde las pruebas.
"""

import os
from typing import Any, Final

import httpx
import pandas as pd
import streamlit as st

from observatorio_inmobiliario import reputacion
from observatorio_inmobiliario.tablero.datos import cargar_agregados, cargar_geojson

CACHE_GOOGLE_S: Final = 6 * 60 * 60
"""La reputación se guarda en memoria 6 horas; nunca en disco (spec §7.2)."""
OPERACIONES: Final = ("venta", "arriendo")
TIPOS: Final = ("vivienda", "apartamento", "apartaestudio", "casa")


def entero(valor: float) -> str:
    """Entero con punto de miles, como se escribe en Colombia: ``5630`` → ``"5.630"``."""
    return f"{round(valor):,}".replace(",", ".")


def pesos(valor: float) -> str:
    """Pesos en formato colombiano: ``"$42.553"``, o en millones con coma: ``"$5,08 M"``."""
    if valor >= 1_000_000:
        millones = f"{valor / 1_000_000:,.2f}"  # 1,234.57 → 1.234,57
        return "$" + millones.replace(",", "_").replace(".", ",").replace("_", ".") + " M"
    return "$" + entero(valor)


def configurar(titulo: str) -> None:
    """Configuración común de cada página: título de la pestaña y ancho completo."""
    st.set_page_config(page_title=f"{titulo} · Observatorio inmobiliario", layout="wide")


@st.cache_data(show_spinner=False)
def tablas() -> dict[str, pd.DataFrame]:
    """Las 9 tablas agregadas, leídas una vez por sesión del servidor."""
    return cargar_agregados()


@st.cache_data(show_spinner=False)
def geojson() -> dict[str, Any]:
    return cargar_geojson()


def semana() -> str:
    """La semana de la foto, p. ej. ``"2026-S46"``, o ``"sin datos"``."""
    cobertura = tablas()["cobertura_inmobiliaria"]
    return str(cobertura["semana"].iloc[0]) if not cobertura.empty else "sin datos"


def sin_datos(que: str) -> None:
    st.info(f"Todavía no hay datos de {que}.")


def _clave() -> str | None:
    """La clave de Google: primero los secrets de Streamlit, luego el entorno."""
    try:
        clave = st.secrets.get(reputacion.VARIABLE_CLAVE)
    except (FileNotFoundError, KeyError, st.errors.StreamlitSecretNotFoundError):
        clave = None
    if clave:
        os.environ.setdefault(reputacion.VARIABLE_CLAVE, str(clave))
    return reputacion.clave_api()


@st.cache_data(ttl=CACHE_GOOGLE_S, show_spinner="Consultando Google…")
def _reputacion_cacheada(clave: str) -> pd.DataFrame:
    with httpx.Client() as cliente:
        return reputacion.reputacion(
            reputacion.cargar_sedes(),
            lambda place_id: reputacion.consultar_sede(cliente, place_id, clave),
        )


def reputacion_en_vivo() -> pd.DataFrame | None:
    """Reputación por inmobiliaria consultada en Google, o ``None`` sin clave o sin sedes."""
    clave = _clave()
    if clave is None:
        return None
    tabla = _reputacion_cacheada(clave)
    return tabla if not tabla.empty else None
