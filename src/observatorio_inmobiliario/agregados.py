"""Tablas agregadas que responden las preguntas del análisis (una foto de una semana).

Estas tablas **van al repo público**: no llevan ids, URL, coordenadas ni textos de anuncios.
Cada fila con estadísticas de precio resume al menos :data:`MINIMO_PUBLICACION` anuncios.

La base de todo es :func:`base_analisis`: los anuncios de Medellín que no son atípicos, una
fila por anuncio. Los precios se resumen solo para vivienda (:func:`con_vivienda`): mezclar un
local con un apartamento no dice nada del precio de un barrio. Venta y arriendo van siempre
por separado.
"""

from typing import Final

import pandas as pd
from pandas.core.groupby import DataFrameGroupBy

MINIMO_PUBLICACION: Final = 5
"""Anuncios que debe resumir una fila con precios para publicarse. Con menos, una mediana es
casi el precio de un anuncio puntual y no representa a la zona."""
TIPOS_VIVIENDA: Final = ("apartamento", "apartaestudio", "casa")
VIVIENDA: Final = "vivienda"
"""Valor de ``tipo`` que reúne los tres tipos de vivienda."""
CLAVE: Final = ["fuente", "id_fuente", "operacion"]
"""Identifica un anuncio en una semana: algunas fuentes usan el mismo id en venta y arriendo."""

COLUMNAS_PRECIOS_ZONA: Final = [
    "semana",
    "nivel",
    "codigo",
    "nombre",
    "comuna",
    "operacion",
    "tipo",
    "anuncios",
    "precio_mediana",
    "precio_p25",
    "precio_p75",
    "precio_m2_mediana",
    "precio_m2_p25",
    "precio_m2_p75",
]
_TEXTO_PRECIOS_ZONA: Final = COLUMNAS_PRECIOS_ZONA[:7]


def anuncios_unicos(df: pd.DataFrame) -> pd.DataFrame:
    """Una fila por :data:`CLAVE`.

    Si una clave se repite con datos distintos, gana la primera al ordenar por todas las
    columnas, así el resultado no depende del orden en que llegaron las filas.
    """
    ordenado = df.sort_values(list(df.columns), kind="stable", na_position="last")
    return ordenado.drop_duplicates(CLAVE)


def base_analisis(limpio: pd.DataFrame) -> pd.DataFrame:
    """Los anuncios únicos de Medellín que no son atípicos."""
    unicos = anuncios_unicos(limpio)
    entran = unicos["es_medellin"].fillna(False).astype(bool) & ~unicos["es_atipico"].fillna(
        False
    ).astype(bool)
    return unicos[entran]


def con_vivienda(df: pd.DataFrame) -> pd.DataFrame:
    """Las filas de vivienda con la columna ``tipo``, más una copia de ellas como ``"vivienda"``."""
    vivienda = df[df["tipo_normalizado"].isin(TIPOS_VIVIENDA).fillna(False).astype(bool)]
    por_tipo = vivienda.assign(tipo=vivienda["tipo_normalizado"].astype("string"))
    juntas = vivienda.assign(tipo=pd.Series(VIVIENDA, index=vivienda.index, dtype="string"))
    return pd.concat([por_tipo, juntas], ignore_index=True)


def _resumen_precios(grupos: DataFrameGroupBy) -> pd.DataFrame:  # type: ignore[type-arg]
    """Anuncios, mediana y cuartiles del precio y del precio por m² de cada grupo."""
    precio = grupos["precio"]
    precio_m2 = grupos["precio_m2"]
    return pd.DataFrame(
        {
            "anuncios": grupos.size(),
            "precio_mediana": precio.median(),
            "precio_p25": precio.quantile(0.25),
            "precio_p75": precio.quantile(0.75),
            "precio_m2_mediana": precio_m2.median(),
            "precio_m2_p25": precio_m2.quantile(0.25),
            "precio_m2_p75": precio_m2.quantile(0.75),
        }
    )


def _enteros(df: pd.DataFrame, columnas: list[str]) -> pd.DataFrame:
    """Redondea ``columnas`` a enteros con nulos (Int64)."""
    return df.assign(**{c: df[c].astype("Float64").round().astype("Int64") for c in columnas})


def _vacia(columnas: list[str], texto: list[str]) -> pd.DataFrame:
    return pd.DataFrame({c: pd.Series(dtype="string" if c in texto else "Int64") for c in columnas})


def precios_zona(base: pd.DataFrame, semana: str) -> pd.DataFrame:
    """Precios de vivienda por barrio y por comuna (pregunta 1).

    Una fila por nivel (``"barrio"`` o ``"comuna"``), zona, operación y tipo, solo si resume
    al menos :data:`MINIMO_PUBLICACION` anuncios. Un anuncio sin barrio oficial cuenta en su
    comuna.
    """
    vivienda = con_vivienda(base).assign(
        precio=lambda d: d["precio"].astype("Float64"),
        precio_m2=lambda d: d["precio_m2"].astype("Float64"),
    )
    partes = []
    for nivel, codigo, nombre in (
        ("barrio", "codigo_barrio", "barrio_normalizado"),
        ("comuna", "comuna", "nombre_comuna"),
    ):
        con_zona = vivienda[vivienda[codigo].notna()]
        grupos = con_zona.groupby([codigo, "operacion", "tipo"], observed=True)
        resumen = _resumen_precios(grupos).reset_index()
        resumen = resumen.rename(columns={codigo: "codigo"})
        nombres = con_zona.drop_duplicates(codigo).set_index(codigo, drop=False)
        resumen["nombre"] = resumen["codigo"].map(nombres[nombre])
        resumen["comuna"] = resumen["codigo"].map(nombres["comuna"])
        resumen["nivel"] = nivel
        partes.append(resumen)

    tabla = pd.concat(partes, ignore_index=True) if partes else pd.DataFrame()
    if tabla.empty:
        return _vacia(COLUMNAS_PRECIOS_ZONA, _TEXTO_PRECIOS_ZONA)
    tabla["semana"] = semana
    tabla = tabla[tabla["anuncios"] >= MINIMO_PUBLICACION]
    tabla = _enteros(tabla, COLUMNAS_PRECIOS_ZONA[7:])
    tabla = tabla.astype({c: "string" for c in _TEXTO_PRECIOS_ZONA})
    orden = tabla.sort_values(["nivel", "codigo", "operacion", "tipo"], kind="stable")
    return orden[COLUMNAS_PRECIOS_ZONA].reset_index(drop=True)
