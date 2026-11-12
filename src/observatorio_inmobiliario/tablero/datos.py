"""Carga de los datos públicos que muestra el dashboard.

El dashboard lee solo ``data/agregados/`` y ``datos_referencia/``: nada de anuncios
individuales. Estas funciones no dependen de Streamlit; las páginas las envuelven con
``st.cache_data``.
"""

import json
from pathlib import Path
from typing import Any, Final

import pandas as pd

from observatorio_inmobiliario import agregados
from observatorio_inmobiliario.almacenamiento import TABLAS_AGREGADAS, leer_agregado, leer_limpio
from observatorio_inmobiliario.emparejamiento import agrupar, emparejar
from observatorio_inmobiliario.evolucion import evolucion_precios, rotacion_inmobiliaria


def _raiz() -> Path:
    """La carpeta del repositorio.

    En desarrollo, el paquete está dentro del repo (``src/``). Si está instalado en otro lugar
    (por ejemplo, en Streamlit Cloud), se usa la carpeta de trabajo, que es la raíz del repo.
    """
    candidata = Path(__file__).resolve().parents[3]
    return candidata if (candidata / "pyproject.toml").exists() else Path.cwd()


RAIZ: Final = _raiz()
AGREGADOS: Final = RAIZ / "data" / "agregados"
GEOJSON: Final = RAIZ / "datos_referencia" / "barrios_medellin.geojson"


def tablas_vacias() -> dict[str, pd.DataFrame]:
    """Las 9 tablas agregadas vacías, con sus columnas y tipos.

    Se arman con las mismas funciones que las generan, aplicadas a una tabla limpia vacía,
    así nunca se desalinean con ellas.
    """
    limpio = leer_limpio(Path("no-existe"))
    base = agregados.base_analisis(limpio)
    parejas = emparejar(limpio)
    semana = ""
    return {
        "precios_zona": agregados.precios_zona(base, semana),
        "cobertura_inmobiliaria": agregados.cobertura_inmobiliaria(base, semana),
        "cobertura_comuna": agregados.cobertura_comuna(base, semana),
        "economia_inmobiliaria": agregados.economia_inmobiliaria(base, semana),
        "estratos_inmobiliaria": agregados.estratos_inmobiliaria(base, semana),
        "compartidos_fuentes": agregados.compartidos_fuentes(parejas, semana),
        "grupos_compartidos": agregados.grupos_compartidos(agrupar(parejas), base, semana),
        "evolucion_precios": evolucion_precios(limpio),
        "rotacion_inmobiliaria": rotacion_inmobiliaria(limpio),
    }


def cargar_agregados(directorio: Path | None = None) -> dict[str, pd.DataFrame]:
    """Las 9 tablas agregadas. Si falta un archivo, su tabla llega vacía (con columnas)."""
    directorio = directorio or AGREGADOS
    vacias = tablas_vacias()
    return {
        nombre: (
            leer_agregado(directorio, nombre)
            if (directorio / f"{nombre}.parquet").exists()
            else vacias[nombre]
        )
        for nombre in TABLAS_AGREGADAS
    }


def cargar_geojson(ruta: Path | None = None) -> dict[str, Any]:
    """Límites oficiales de barrios y veredas de Medellín (catálogo del Plan 4)."""
    datos: dict[str, Any] = json.loads((ruta or GEOJSON).read_text(encoding="utf-8"))
    return datos
