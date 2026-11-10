"""Guardado y lectura de las observaciones en archivos Parquet semanales.

Cada fuente tiene su carpeta y cada semana ISO su archivo::

    data/crudo/santafe/2026-S46.parquet

Correr el scraper dos veces en la misma semana **sobrescribe** ese archivo, así que nunca
quedan filas duplicadas. Una semana nueva crea un archivo nuevo, y así se acumula el
histórico.
"""

import os
from collections import defaultdict
from collections.abc import Iterable
from datetime import date
from pathlib import Path
from typing import Any, Final

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from observatorio_inmobiliario.modelos import AnuncioNormalizado

ESQUEMA: Final = pa.schema(
    [
        ("fuente", pa.string()),
        ("id_fuente", pa.string()),
        ("url", pa.string()),
        ("fecha_observacion", pa.date32()),
        ("operacion", pa.string()),
        ("tipo_inmueble", pa.string()),
        ("precio", pa.int64()),
        ("administracion", pa.int64()),
        ("area_m2", pa.float64()),
        ("habitaciones", pa.int64()),
        ("banos", pa.int64()),
        ("parqueaderos", pa.int64()),
        ("estrato", pa.int64()),
        ("barrio", pa.string()),
        ("municipio", pa.string()),
        ("latitud", pa.float64()),
        ("longitud", pa.float64()),
        ("anunciante_origen", pa.string()),
    ]
)
"""Tipos de cada columna, fijos. Debe tener los mismos campos que :class:`AnuncioNormalizado`.

Se declaran en vez de inferirlos para que una columna que una semana venga toda vacía no
cambie de tipo, y para que los enteros con vacíos no se conviertan en decimales.
"""

_TIPOS_PANDAS: Final[dict[pa.DataType, Any]] = {
    pa.string(): pd.StringDtype(),
    pa.int64(): pd.Int64Dtype(),
}
"""Al leer, enteros y textos usan los tipos de pandas que admiten vacíos (``<NA>``)."""


def ruta_semana(directorio: Path, fuente: str, fecha: date) -> Path:
    """Archivo de la semana ISO de ``fecha``, p. ej. ``directorio/santafe/2026-S46.parquet``.

    Se usa el año ISO y no el del calendario: el 1 de enero de 2027 pertenece a la
    semana 53 de 2026.
    """
    año, semana, _ = fecha.isocalendar()
    return directorio / fuente / f"{año}-S{semana:02d}.parquet"


def guardar_observaciones(anuncios: Iterable[AnuncioNormalizado], directorio: Path) -> list[Path]:
    """Agrupa los anuncios por fuente y semana, y sobrescribe el archivo de cada grupo.

    Devuelve las rutas escritas, ordenadas.
    """
    grupos: defaultdict[Path, list[dict[str, Any]]] = defaultdict(list)
    for anuncio in anuncios:
        ruta = ruta_semana(directorio, anuncio.fuente, anuncio.fecha_observacion)
        fila = anuncio.model_dump()
        fila["operacion"] = anuncio.operacion.value
        grupos[ruta].append(fila)

    for ruta, filas in grupos.items():
        ruta.parent.mkdir(parents=True, exist_ok=True)
        # Se escribe a un temporal y luego se reemplaza: si el proceso se corta a mitad,
        # el archivo de la semana anterior queda intacto en vez de corrupto.
        temporal = ruta.with_suffix(".parquet.tmp")
        pq.write_table(pa.Table.from_pylist(filas, schema=ESQUEMA), temporal)
        os.replace(temporal, ruta)

    return sorted(grupos)


def leer_observaciones(directorio: Path, fuente: str | None = None) -> pd.DataFrame:
    """Une todos los Parquet de ``directorio`` (o solo los de ``fuente``) en un DataFrame.

    Si no hay archivos, devuelve un DataFrame vacío con las columnas del modelo.
    """
    rutas = sorted(directorio.glob(f"{fuente or '*'}/*.parquet"))
    tablas = [pq.read_table(ruta, schema=ESQUEMA) for ruta in rutas]
    tabla = pa.concat_tables(tablas) if tablas else ESQUEMA.empty_table()
    df: pd.DataFrame = tabla.to_pandas(types_mapper=_TIPOS_PANDAS.get)
    return df
