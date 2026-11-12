"""Limpieza de las observaciones crudas: ubicación oficial, municipio, tipo y precio por m².

:func:`limpiar` recibe la tabla cruda (la de ``leer_observaciones``) y devuelve una copia
con columnas nuevas. **No borra filas ni cambia las columnas crudas**: lo dudoso se marca
para que el análisis decida qué hacer con ello.

Cómo se ubica cada anuncio, en orden:

1. El municipio de la fuente se normaliza ("MEDELLIN" → "Medellín").
2. Si la fuente no dio municipio pero el barrio es el nombre de un municipio del valle
   ("SABANETA"), ese es el municipio.
3. Si el anuncio es de Medellín (o no tiene municipio) y sus coordenadas son válidas, se
   busca el polígono oficial que las contiene. No son válidas si caen fuera del valle o si
   son un **punto genérico**: el que pone un sitio cuando no sabe la dirección (ver
   :func:`puntos_genericos`).
4. Si no se ubicó así, se busca por el nombre del barrio en el catálogo.

Un anuncio de otro municipio nunca recibe un barrio de Medellín, aunque su punto caiga
dentro de la ciudad: en los bordes (El Poblado con Envigado) se respeta lo que dice la fuente.
"""

import math
from typing import Final

import numpy as np
import pandas as pd

from observatorio_inmobiliario.catalogo import Catalogo, Ubicacion
from observatorio_inmobiliario.modelos import Operacion
from observatorio_inmobiliario.normalizacion import (
    MUNICIPIOS_VALLE,
    normalizar_municipio,
    normalizar_texto,
    normalizar_tipo,
)

MEDELLIN: Final = "Medellín"
VALLE_LAT: Final = (6.00, 6.50)
VALLE_LON: Final = (-75.72, -75.30)
"""Rectángulo que contiene el Valle de Aburrá; una coordenada fuera de él es un error."""

PUNTO_GENERICO_MIN_ANUNCIOS: Final = 5
PUNTO_GENERICO_MIN_BARRIOS: Final = 5
"""Un punto con al menos 5 anuncios que nombran al menos 5 barrios distintos es genérico.

En la semana del 2026-11-11, 58 anuncios de una fuente estaban en el mismo punto del centro
con 48 barrios distintos. Un edificio también repite su punto, pero con un solo barrio."""

RANGOS_PRECIO: Final = {
    Operacion.ARRIENDO: (200_000, 200_000_000),
    Operacion.VENTA: (20_000_000, 50_000_000_000),
}
"""Precios posibles en COP. Fuera de ellos casi siempre es un error de digitación o un
arriendo publicado con el precio de venta (o al revés)."""
TIPOS_VIVIENDA: Final = frozenset({"apartamento", "apartaestudio", "casa"})
RANGO_AREA_VIVIENDA: Final = (10.0, 2_000.0)
"""Áreas posibles en m² para una vivienda."""
MINIMO_GRUPO: Final = 30
"""Filas con precio por m² que necesita un grupo para usar el criterio estadístico."""
FACTOR_IQR: Final = 3.0
"""Cercas de Tukey "lejanas": Q1 − 3·IQR y Q3 + 3·IQR, sobre el logaritmo del precio por m²."""


def _punto_del_valle(latitud: object, longitud: object) -> tuple[float, float] | None:
    """``(latitud, longitud)`` si las dos existen y caen en el valle; si no, ``None``."""
    if not isinstance(latitud, float | int) or not isinstance(longitud, float | int):
        return None
    lat, lon = float(latitud), float(longitud)
    if math.isnan(lat) or math.isnan(lon):
        return None
    dentro = VALLE_LAT[0] <= lat <= VALLE_LAT[1] and VALLE_LON[0] <= lon <= VALLE_LON[1]
    return (lat, lon) if dentro else None


def _texto(valor: object) -> str | None:
    return valor if isinstance(valor, str) else None  # las columnas de texto traen str o <NA>


def puntos_genericos(crudo: pd.DataFrame) -> set[tuple[float, float]]:
    """Coordenadas que los sitios usan por defecto, no la ubicación real del inmueble."""
    con_punto = crudo[crudo["latitud"].notna() & crudo["longitud"].notna()]
    barrios = pd.Series(
        [normalizar_texto(b) if isinstance(b, str) else "" for b in con_punto["barrio"]],
        index=con_punto.index,
    ).replace("", None)
    por_punto = barrios.groupby([con_punto["latitud"], con_punto["longitud"]])
    resumen = pd.DataFrame({"anuncios": por_punto.size(), "barrios": por_punto.nunique()})
    genericos = resumen[
        (resumen["anuncios"] >= PUNTO_GENERICO_MIN_ANUNCIOS)
        & (resumen["barrios"] >= PUNTO_GENERICO_MIN_BARRIOS)
    ]
    return {(float(lat), float(lon)) for lat, lon in genericos.index}


def limpiar(crudo: pd.DataFrame, catalogo: Catalogo) -> pd.DataFrame:
    """Copia de ``crudo`` con las columnas de ubicación, tipo y precio por m²."""
    genericos = puntos_genericos(crudo)
    municipios: list[str | None] = []
    validas: list[bool] = []
    ubicaciones: list[Ubicacion | None] = []

    for fila in crudo[["municipio", "barrio", "latitud", "longitud"]].itertuples(index=False):
        barrio = _texto(fila.barrio)
        municipio = normalizar_municipio(_texto(fila.municipio))
        if municipio is None and normalizar_municipio(barrio) in MUNICIPIOS_VALLE:
            municipio = normalizar_municipio(barrio)

        punto = _punto_del_valle(fila.latitud, fila.longitud)
        if punto in genericos:
            punto = None
        ubicacion: Ubicacion | None = None
        if municipio in (None, MEDELLIN):
            if punto is not None:
                ubicacion = catalogo.por_coordenadas(*punto)
            if ubicacion is None:
                ubicacion = catalogo.por_nombre(barrio)
            if ubicacion is not None:
                municipio = MEDELLIN

        municipios.append(municipio)
        validas.append(punto is not None)
        ubicaciones.append(ubicacion)

    def columna(atributo: str) -> pd.Series:
        valores = [None if u is None else getattr(u, atributo) for u in ubicaciones]
        return pd.Series(valores, index=crudo.index, dtype="string")

    limpio = crudo.copy()
    limpio["municipio_normalizado"] = pd.Series(municipios, index=crudo.index, dtype="string")
    limpio["en_valle"] = pd.Series(
        [m in MUNICIPIOS_VALLE for m in municipios], index=crudo.index, dtype=bool
    )
    limpio["es_medellin"] = pd.Series(
        [m == MEDELLIN for m in municipios], index=crudo.index, dtype=bool
    )
    limpio["coordenadas_validas"] = pd.Series(validas, index=crudo.index, dtype=bool)
    limpio["codigo_barrio"] = columna("codigo_barrio")
    limpio["barrio_normalizado"] = columna("barrio")
    limpio["comuna"] = columna("comuna")
    limpio["nombre_comuna"] = columna("nombre_comuna")
    limpio["metodo_ubicacion"] = columna("metodo")
    limpio["tipo_normalizado"] = pd.Series(
        [normalizar_tipo(_texto(t)) for t in crudo["tipo_inmueble"]],
        index=crudo.index,
        dtype="string",
    )
    area = crudo["area_m2"].astype("Float64")
    # Mismo tipo que area_m2 (float64, con NaN si falta), para que el Parquet lo conserve.
    limpio["precio_m2"] = (crudo["precio"].astype("Float64") / area).where(area > 0).astype(float)
    return marcar_atipicos(limpio)


def marcar_atipicos(df: pd.DataFrame) -> pd.DataFrame:
    """Copia de ``df`` con ``es_atipico`` y ``motivo_atipico``. No borra filas.

    Motivos, unidos con ``"; "`` si hay varios:

    * ``precio_fuera_de_rango``: fuera de :data:`RANGOS_PRECIO` para su operación.
    * ``area_fuera_de_rango``: vivienda con área fuera de :data:`RANGO_AREA_VIVIENDA`.
    * ``precio_m2_extremo``: dentro de su grupo (operación y tipo), el logaritmo del precio
      por m² queda fuera de las cercas de Tukey con :data:`FACTOR_IQR`. Solo en grupos con al
      menos :data:`MINIMO_GRUPO` filas. Se usa el logaritmo porque los precios son asimétricos.

    Un dato nulo nunca marca un anuncio.
    """
    precio = df["precio"].astype("Float64")
    fuera_de_precio = pd.Series(False, index=df.index)
    for operacion, (minimo, maximo) in RANGOS_PRECIO.items():
        fuera = (df["operacion"] == operacion.value) & ((precio < minimo) | (precio > maximo))
        fuera_de_precio |= fuera.fillna(False).astype(bool)

    area = df["area_m2"].astype("Float64")
    vivienda = df["tipo_normalizado"].isin(TIPOS_VIVIENDA).fillna(False).astype(bool)
    fuera_de_area = vivienda & (
        ((area < RANGO_AREA_VIVIENDA[0]) | (area > RANGO_AREA_VIVIENDA[1])).fillna(False)
    ).astype(bool)

    log_precio_m2 = pd.Series(
        np.log10(df["precio_m2"].astype("float64")), index=df.index, dtype="float64"
    )
    grupos = log_precio_m2.groupby([df["operacion"], df["tipo_normalizado"]])
    q1 = grupos.transform("quantile", 0.25)
    q3 = grupos.transform("quantile", 0.75)
    iqr = q3 - q1
    extremo = (grupos.transform("count") >= MINIMO_GRUPO) & (
        (log_precio_m2 < q1 - FACTOR_IQR * iqr) | (log_precio_m2 > q3 + FACTOR_IQR * iqr)
    )

    motivos = [
        "; ".join(
            nombre
            for nombre, marcado in (
                ("precio_fuera_de_rango", p),
                ("area_fuera_de_rango", a),
                ("precio_m2_extremo", e),
            )
            if marcado
        )
        or None
        for p, a, e in zip(fuera_de_precio, fuera_de_area, extremo.fillna(False), strict=True)
    ]
    motivo = pd.Series(motivos, index=df.index, dtype="string")
    marcado = df.copy()
    marcado["es_atipico"] = motivo.notna().astype(bool)
    marcado["motivo_atipico"] = motivo
    return marcado


def filtrar_medellin(df: pd.DataFrame) -> pd.DataFrame:
    """Solo los anuncios de Medellín (el foco del análisis principal)."""
    return df[df["es_medellin"]]
