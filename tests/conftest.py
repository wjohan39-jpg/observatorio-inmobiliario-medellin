"""Utilidades compartidas por las pruebas: filas limpias sintéticas con los tipos reales."""

from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from observatorio_inmobiliario.almacenamiento import ESQUEMA_LIMPIO, leer_limpio

PUNTO = {"latitud": 6.245, "longitud": -75.595}
GRADO_LAT_M = 111_195.0  # metros en 1° de latitud con R = 6.371.000 m


def fila(**cambios: Any) -> dict[str, Any]:
    """Un anuncio limpio de Medellín, válido y con coordenadas; ``cambios`` lo modifica."""
    fila: dict[str, Any] = {nombre: None for nombre in ESQUEMA_LIMPIO.names}
    fila.update(
        fuente="santafe",
        id_fuente="1",
        url="https://ejemplo.com/1",
        fecha_observacion=date(2026, 11, 12),
        operacion="arriendo",
        tipo_inmueble="Apartamento",
        precio=2_000_000,
        area_m2=80.0,
        habitaciones=3,
        banos=2,
        estrato=4,
        municipio="Medellín",
        municipio_normalizado="Medellín",
        en_valle=True,
        es_medellin=True,
        coordenadas_validas=True,
        codigo_barrio="1101",
        barrio_normalizado="Laureles",
        comuna="11",
        nombre_comuna="LAURELES ESTADIO",
        metodo_ubicacion="coordenadas",
        tipo_normalizado="apartamento",
        es_atipico=False,
        **PUNTO,
    )
    fila["precio_m2"] = None
    fila.update(cambios)
    return fila


def sin_coordenadas(**cambios: Any) -> dict[str, Any]:
    return fila(latitud=None, longitud=None, coordenadas_validas=False, **cambios)


def al_norte(metros: float) -> dict[str, float]:
    return {"latitud": PUNTO["latitud"] + metros / GRADO_LAT_M, "longitud": PUNTO["longitud"]}


@pytest.fixture
def limpio(tmp_path: Path) -> Any:
    """Arma una tabla limpia con el mismo guardado y lectura del proyecto (tipos reales)."""

    def armar(*filas: dict[str, Any]) -> pd.DataFrame:
        ruta = tmp_path / "limpio" / "2026-S46.parquet"
        ruta.parent.mkdir(parents=True, exist_ok=True)
        pq.write_table(pa.Table.from_pylist(list(filas), schema=ESQUEMA_LIMPIO), ruta)
        return leer_limpio(ruta.parent)

    return armar
