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


# ------------------------------------------------------------- Inmobiliarias

TODAS: Final = "todas"
"""Valor de ``operacion`` que reúne venta y arriendo en las tablas de cobertura."""
MINIMO_ESTRATO_BARRIO: Final = 5
CONSENSO_ESTRATO: Final = 0.6
"""Un barrio tiene estrato inferido si al menos 5 anuncios declaran estrato y el más frecuente
reúne al menos el 60 %. En la semana 2026-S46 la regla acierta en el 76 % de los anuncios
que sí declaran estrato, por eso el inferido nunca se mezcla con el declarado."""

COLUMNAS_COBERTURA: Final = [
    "semana",
    "fuente",
    "operacion",
    "anuncios",
    "barrios",
    "comunas",
    "comuna_principal",
    "pct_comuna_principal",
]
COLUMNAS_COBERTURA_COMUNA: Final = [
    "semana",
    "fuente",
    "operacion",
    "comuna",
    "nombre_comuna",
    "anuncios",
    "pct_de_la_fuente",
]
COLUMNAS_ECONOMIA: Final = [
    "semana",
    "fuente",
    "operacion",
    "tipo",
    "anuncios",
    "precio_mediana",
    "precio_m2_mediana",
    "anuncios_indice",
    "indice_relativo_mediana",
]
COLUMNAS_ESTRATOS: Final = ["semana", "fuente", "operacion", "estrato", "declarados", "inferidos"]


def _tipar(df: pd.DataFrame, columnas: list[str], tipos: dict[str, str]) -> pd.DataFrame:
    """``df`` con solo ``columnas``, en ese orden y con los tipos dados (por defecto string)."""
    if df.empty:
        df = pd.DataFrame(columns=columnas)
    return df[columnas].astype({c: tipos.get(c, "string") for c in columnas}).reset_index(drop=True)


def _con_todas(base: pd.DataFrame) -> pd.DataFrame:
    """``base`` más una copia de sus filas con ``operacion = "todas"``."""
    todas = base.assign(operacion=pd.Series(TODAS, index=base.index, dtype="string"))
    return pd.concat([base, todas], ignore_index=True)


def cobertura_inmobiliaria(base: pd.DataFrame, semana: str) -> pd.DataFrame:
    """Anuncios, barrios y comunas de cada inmobiliaria (preguntas 2 y 6).

    Solo tiene conteos, así que no aplica el mínimo de publicación. La comuna principal es la
    de más anuncios; si hay empate, la de menor código.
    """
    datos = _con_todas(base)
    grupos = datos.groupby(["fuente", "operacion"])
    tabla = pd.DataFrame(
        {
            "anuncios": grupos.size(),
            "barrios": grupos["codigo_barrio"].nunique(),
            "comunas": grupos["comuna"].nunique(),
        }
    ).reset_index()
    por_comuna = (
        datos[datos["comuna"].notna()]
        .groupby(["fuente", "operacion", "comuna"])
        .size()
        .rename("en_comuna")
        .reset_index()
        .sort_values(
            ["fuente", "operacion", "en_comuna", "comuna"], ascending=[True, True, False, True]
        )
        .drop_duplicates(["fuente", "operacion"])
    )
    tabla = tabla.merge(por_comuna, on=["fuente", "operacion"], how="left")
    tabla = tabla.rename(columns={"comuna": "comuna_principal"})
    tabla["pct_comuna_principal"] = (tabla["en_comuna"] / tabla["anuncios"] * 100).round(1)
    tabla["semana"] = semana
    tabla = tabla.sort_values(["fuente", "operacion"])
    enteros = {"anuncios": "Int64", "barrios": "Int64", "comunas": "Int64"}
    return _tipar(tabla, COLUMNAS_COBERTURA, {**enteros, "pct_comuna_principal": "float64"})


def cobertura_comuna(base: pd.DataFrame, semana: str) -> pd.DataFrame:
    """Anuncios de cada inmobiliaria por comuna y su peso dentro de la inmobiliaria (pregunta 2).

    El porcentaje se calcula sobre los anuncios con comuna.
    """
    datos = _con_todas(base[base["comuna"].notna()])
    tabla = (
        datos.groupby(["fuente", "operacion", "comuna"])
        .agg(nombre_comuna=("nombre_comuna", "first"), anuncios=("comuna", "size"))
        .reset_index()
    )
    total = tabla.groupby(["fuente", "operacion"])["anuncios"].transform("sum")
    tabla["pct_de_la_fuente"] = (tabla["anuncios"] / total * 100).round(1)
    tabla["semana"] = semana
    tabla = tabla.sort_values(["fuente", "operacion", "comuna"])
    return _tipar(
        tabla, COLUMNAS_COBERTURA_COMUNA, {"anuncios": "Int64", "pct_de_la_fuente": "float64"}
    )


def indice_relativo(base: pd.DataFrame) -> pd.Series:
    """Precio por m² de cada anuncio dividido por la mediana de su barrio.

    El grupo es (operación, tipo, barrio). Solo para vivienda y para grupos con al menos
    :data:`MINIMO_PUBLICACION` anuncios con precio por m²; en el resto queda NaN. Compara a
    cada inmobiliaria con su propio barrio, así no parece cara solo por trabajar en El Poblado.
    """
    precio_m2 = base["precio_m2"].astype("float64")
    vivienda = base["tipo_normalizado"].isin(TIPOS_VIVIENDA).fillna(False).astype(bool)
    valido = vivienda & precio_m2.notna() & base["codigo_barrio"].notna()
    grupos = precio_m2.where(valido).groupby(
        [base["operacion"], base["tipo_normalizado"], base["codigo_barrio"]], dropna=False
    )
    mediana = grupos.transform("median")
    cuantos = grupos.transform("count")
    indice = (precio_m2 / mediana).where(valido & (cuantos >= MINIMO_PUBLICACION))
    return indice.astype("float64")


def economia_inmobiliaria(base: pd.DataFrame, semana: str) -> pd.DataFrame:
    """Precios de vivienda e índice relativo por inmobiliaria (pregunta 3).

    Una fila por fuente, operación y tipo con al menos :data:`MINIMO_PUBLICACION` anuncios. La
    mediana del índice es nula si menos de ese mínimo de anuncios tiene índice.
    """
    vivienda = con_vivienda(base.assign(indice=indice_relativo(base)))
    vivienda = vivienda.assign(
        precio=vivienda["precio"].astype("Float64"),
        precio_m2=vivienda["precio_m2"].astype("Float64"),
    )
    grupos = vivienda.groupby(["fuente", "operacion", "tipo"])
    tabla = pd.DataFrame(
        {
            "anuncios": grupos.size(),
            "precio_mediana": grupos["precio"].median(),
            "precio_m2_mediana": grupos["precio_m2"].median(),
            "anuncios_indice": grupos["indice"].count(),
            "indice_relativo_mediana": grupos["indice"].median(),
        }
    ).reset_index()
    tabla = tabla[tabla["anuncios"] >= MINIMO_PUBLICACION]
    pocos = tabla["anuncios_indice"] < MINIMO_PUBLICACION
    tabla["indice_relativo_mediana"] = (
        tabla["indice_relativo_mediana"].mask(pocos).astype("float64").round(3)
    )
    tabla = _enteros(tabla, ["precio_mediana", "precio_m2_mediana"])
    tabla["semana"] = semana
    tabla = tabla.sort_values(["fuente", "operacion", "tipo"])
    tipos = {
        "anuncios": "Int64",
        "precio_mediana": "Int64",
        "precio_m2_mediana": "Int64",
        "anuncios_indice": "Int64",
        "indice_relativo_mediana": "float64",
    }
    return _tipar(tabla, COLUMNAS_ECONOMIA, tipos)


def estrato_inferido(base: pd.DataFrame) -> pd.Series:
    """Estrato de cada barrio con consenso, según los anuncios que lo declaran.

    Índice: ``codigo_barrio``. Solo barrios con al menos :data:`MINIMO_ESTRATO_BARRIO`
    anuncios con estrato cuyo estrato más frecuente reúne al menos :data:`CONSENSO_ESTRATO`.
    Si hay empate, gana el menor estrato.
    """
    conocidos = base[base["estrato"].notna() & base["codigo_barrio"].notna()]
    conteo = conocidos.groupby(["codigo_barrio", "estrato"]).size().rename("n").reset_index()
    conteo["total"] = conteo.groupby("codigo_barrio")["n"].transform("sum")
    moda = conteo.sort_values(["codigo_barrio", "n", "estrato"], ascending=[True, False, True])
    moda = moda.drop_duplicates("codigo_barrio")
    aceptada = (moda["total"] >= MINIMO_ESTRATO_BARRIO) & (
        moda["n"] / moda["total"] >= CONSENSO_ESTRATO
    )
    moda = moda[aceptada]
    return pd.Series(
        moda["estrato"].to_numpy(),
        index=pd.Index(moda["codigo_barrio"].astype("string"), name="codigo_barrio"),
        dtype="Int64",
        name="estrato",
    )


def estratos_inmobiliaria(base: pd.DataFrame, semana: str) -> pd.DataFrame:
    """Anuncios por estrato de cada inmobiliaria, declarados e inferidos aparte (pregunta 4).

    ``inferidos`` cuenta los anuncios sin estrato que reciben el de su barrio
    (:func:`estrato_inferido`). Solo hay filas para estratos con algún anuncio.
    """
    inferido = base["codigo_barrio"].map(estrato_inferido(base))
    declarado = base["estrato"].notna()
    datos = base.assign(
        estrato_final=base["estrato"].where(declarado, inferido).astype("Int64"),
        declarados=declarado.astype(int),
        inferidos=(~declarado & inferido.notna()).astype(int),
    )
    datos = datos[datos["estrato_final"].notna()]
    tabla = (
        datos.groupby(["fuente", "operacion", "estrato_final"])[["declarados", "inferidos"]]
        .sum()
        .reset_index()
        .rename(columns={"estrato_final": "estrato"})
    )
    tabla["semana"] = semana
    tabla = tabla.sort_values(["fuente", "operacion", "estrato"])
    tipos = {"estrato": "Int64", "declarados": "Int64", "inferidos": "Int64"}
    return _tipar(tabla, COLUMNAS_ESTRATOS, tipos)
