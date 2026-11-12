"""Guardado y lectura de las observaciones en archivos Parquet semanales.

Cada fuente tiene su carpeta y cada semana ISO su archivo::

    data/crudo/santafe/2026-S46.parquet

La tabla limpia (ver :mod:`observatorio_inmobiliario.limpieza`) une todas las fuentes en un
archivo por semana::

    data/limpio/2026-S46.parquet

Las parejas y los grupos de inmuebles compartidos (ver
:mod:`observatorio_inmobiliario.emparejamiento`) van en dos carpetas::

    data/compartidos/parejas/2026-S46.parquet
    data/compartidos/grupos_inmueble/2026-S46.parquet

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

ESQUEMA_LIMPIO: Final = pa.schema(
    [
        *ESQUEMA,
        ("municipio_normalizado", pa.string()),
        ("en_valle", pa.bool_()),
        ("es_medellin", pa.bool_()),
        ("coordenadas_validas", pa.bool_()),
        ("codigo_barrio", pa.string()),
        ("barrio_normalizado", pa.string()),
        ("comuna", pa.string()),
        ("nombre_comuna", pa.string()),
        ("metodo_ubicacion", pa.string()),
        ("tipo_normalizado", pa.string()),
        ("precio_m2", pa.float64()),
        ("es_atipico", pa.bool_()),
        ("motivo_atipico", pa.string()),
    ]
)
"""Columnas crudas más las que agrega la limpieza, en el mismo orden que ``limpiar``."""

ESQUEMA_PAREJAS: Final = pa.schema(
    [
        ("fuente_a", pa.string()),
        ("id_fuente_a", pa.string()),
        ("fuente_b", pa.string()),
        ("id_fuente_b", pa.string()),
        ("operacion", pa.string()),
        ("tipo_normalizado", pa.string()),
        ("comuna", pa.string()),
        ("codigo_barrio_a", pa.string()),
        ("codigo_barrio_b", pa.string()),
        ("area_m2_a", pa.float64()),
        ("area_m2_b", pa.float64()),
        ("precio_a", pa.int64()),
        ("precio_b", pa.int64()),
        ("distancia_m", pa.float64()),
        ("diferencia_precio_pct", pa.float64()),
        ("ambigua", pa.bool_()),
        ("confianza", pa.string()),
    ]
)
"""Columnas de ``emparejar``, en su orden."""

ESQUEMA_GRUPOS: Final = pa.schema(
    [
        ("fuente", pa.string()),
        ("id_fuente", pa.string()),
        ("operacion", pa.string()),
        ("grupo_alta", pa.string()),
        ("grupo_media", pa.string()),
        ("grupo_baja", pa.string()),
    ]
)
"""Columnas de ``agrupar``, en su orden."""

_TIPOS_PANDAS: Final[dict[pa.DataType, Any]] = {
    pa.string(): pd.StringDtype(),
    pa.int64(): pd.Int64Dtype(),
}
"""Al leer, enteros y textos usan los tipos de pandas que admiten vacíos (``<NA>``)."""


def semana_de(fecha: date) -> str:
    """Semana ISO de ``fecha``, p. ej. ``"2026-S46"``.

    Se usa el año ISO y no el del calendario: el 1 de enero de 2027 pertenece a la
    semana 53 de 2026.
    """
    año, semana, _ = fecha.isocalendar()
    return f"{año}-S{semana:02d}"


def ruta_semana(directorio: Path, fuente: str, fecha: date) -> Path:
    """Archivo de la semana ISO de ``fecha``, p. ej. ``directorio/santafe/2026-S46.parquet``."""
    return directorio / fuente / f"{semana_de(fecha)}.parquet"


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
        _escribir(pa.Table.from_pylist(filas, schema=ESQUEMA), ruta)

    return sorted(grupos)


def _leer(rutas: list[Path], esquema: pa.Schema) -> pd.DataFrame:
    tablas = [pq.read_table(ruta, schema=esquema) for ruta in sorted(rutas)]
    tabla = pa.concat_tables(tablas) if tablas else esquema.empty_table()
    df: pd.DataFrame = tabla.to_pandas(types_mapper=_TIPOS_PANDAS.get)
    return df


def _escribir(tabla: pa.Table, ruta: Path) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    # Se escribe a un temporal y luego se reemplaza: si el proceso se corta a mitad,
    # el archivo anterior queda intacto en vez de corrupto.
    temporal = ruta.with_suffix(".parquet.tmp")
    pq.write_table(tabla, temporal)
    os.replace(temporal, ruta)


def leer_observaciones(directorio: Path, fuente: str | None = None) -> pd.DataFrame:
    """Une todos los Parquet de ``directorio`` (o solo los de ``fuente``) en un DataFrame.

    Si no hay archivos, devuelve un DataFrame vacío con las columnas del modelo.
    """
    return _leer(list(directorio.glob(f"{fuente or '*'}/*.parquet")), ESQUEMA)


def semanas_disponibles(directorio: Path) -> list[str]:
    """Semanas con datos crudos de al menos una fuente, p. ej. ``["2026-S45", "2026-S46"]``."""
    return sorted({ruta.stem for ruta in directorio.glob("*/*.parquet")})


def leer_semana(directorio: Path, semana: str) -> pd.DataFrame:
    """Las observaciones crudas de todas las fuentes en ``semana`` (``"2026-S46"``)."""
    return _leer(list(directorio.glob(f"*/{semana}.parquet")), ESQUEMA)


def guardar_limpio(df: pd.DataFrame, directorio: Path, semana: str) -> Path:
    """Sobrescribe ``directorio/<semana>.parquet`` con la tabla limpia y devuelve la ruta."""
    ruta = directorio / f"{semana}.parquet"
    tabla = pa.Table.from_pandas(
        df[ESQUEMA_LIMPIO.names], schema=ESQUEMA_LIMPIO, preserve_index=False
    )
    _escribir(tabla, ruta)
    return ruta


def leer_limpio(directorio: Path, semana: str | None = None) -> pd.DataFrame:
    """Une las tablas limpias de ``directorio`` (o solo la de ``semana``)."""
    return _leer(list(directorio.glob(f"{semana or '*'}.parquet")), ESQUEMA_LIMPIO)


def semanas_limpias(directorio: Path) -> list[str]:
    """Semanas con tabla limpia, p. ej. ``["2026-S45", "2026-S46"]``."""
    return sorted(ruta.stem for ruta in directorio.glob("*.parquet"))


def guardar_compartidos(
    parejas: pd.DataFrame, grupos: pd.DataFrame, directorio: Path, semana: str
) -> list[Path]:
    """Sobrescribe las parejas y los grupos de ``semana`` y devuelve las dos rutas."""
    rutas = []
    for nombre, df, esquema in (
        ("parejas", parejas, ESQUEMA_PAREJAS),
        ("grupos_inmueble", grupos, ESQUEMA_GRUPOS),
    ):
        ruta = directorio / nombre / f"{semana}.parquet"
        _escribir(
            pa.Table.from_pandas(df[esquema.names], schema=esquema, preserve_index=False), ruta
        )
        rutas.append(ruta)
    return rutas


def leer_compartidos(
    directorio: Path, semana: str | None = None
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """``(parejas, grupos)`` de ``directorio``: todas las semanas, o solo ``semana``."""
    patron = f"{semana or '*'}.parquet"
    return (
        _leer(list((directorio / "parejas").glob(patron)), ESQUEMA_PAREJAS),
        _leer(list((directorio / "grupos_inmueble").glob(patron)), ESQUEMA_GRUPOS),
    )
