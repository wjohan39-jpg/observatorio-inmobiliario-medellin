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
    """Anuncios, mediana y cuartiles del precio y del precio por m² de cada grupo.

    Cada estadística exige :data:`MINIMO_PUBLICACION` valores **con dato**, no filas: un
    anuncio sin precio por m² no cuenta para la mediana del m². Si no los tiene, queda nula.
    """
    columnas = {}
    for campo in ("precio", "precio_m2"):
        valores = grupos[campo]
        suficientes = valores.count() >= MINIMO_PUBLICACION
        columnas[f"{campo}_mediana"] = valores.median().where(suficientes)
        columnas[f"{campo}_p25"] = valores.quantile(0.25).where(suficientes)
        columnas[f"{campo}_p75"] = valores.quantile(0.75).where(suficientes)
    return pd.DataFrame({"anuncios": grupos.size(), **columnas})


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
    con_precio = tabla["precio_mediana"].notna() | tabla["precio_m2_mediana"].notna()
    tabla = tabla[(tabla["anuncios"] >= MINIMO_PUBLICACION) & con_precio]
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

    Una fila por fuente, operación y tipo con al menos :data:`MINIMO_PUBLICACION` anuncios. Cada
    mediana es nula si menos de ese mínimo de anuncios tiene el dato (precio, m² o índice).
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
            "precio_mediana": grupos["precio"]
            .median()
            .where(grupos["precio"].count() >= MINIMO_PUBLICACION),
            "precio_m2_mediana": grupos["precio_m2"]
            .median()
            .where(grupos["precio_m2"].count() >= MINIMO_PUBLICACION),
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


# ------------------------------------------------------------- Compartidos

NIVELES: Final = ("alta", "media", "baja")
"""Niveles de confianza de mayor a menor, los mismos de ``emparejamiento.Confianza``.

Se repiten aquí porque ``emparejamiento`` importa de este módulo; una prueba verifica que
coinciden."""

COLUMNAS_COMPARTIDOS_FUENTES: Final = [
    "semana",
    "fuente_a",
    "fuente_b",
    "nivel",
    "parejas",
    "diferencia_precio_mediana_pct",
    "pct_a_mas_barata",
    "pct_mismo_precio",
]
COLUMNAS_GRUPOS_COMPARTIDOS: Final = [
    "semana",
    "nivel",
    "grupo",
    "operacion",
    "tipo",
    "comuna",
    "nombre_comuna",
    "barrio",
    "area_m2",
    "estrato",
    "habitaciones",
    "fuente",
    "precio",
]


def _hasta(nivel: str) -> list[str]:
    """Los niveles iguales o mayores que ``nivel``: ``"media"`` → ``["alta", "media"]``."""
    return list(NIVELES[: NIVELES.index(nivel) + 1])


def compartidos_fuentes(parejas: pd.DataFrame, semana: str) -> pd.DataFrame:
    """Parejas y diferencia de precio por par de inmobiliarias y nivel (pregunta 7).

    El nivel es acumulado: ``"media"`` cuenta las parejas alta y media. Los porcentajes de
    "más barata" y "mismo precio" se calculan sobre las parejas con los dos precios.
    """
    partes = []
    for nivel in NIVELES:
        datos = parejas[parejas["confianza"].isin(_hasta(nivel))]
        if datos.empty:
            continue
        precio_a = datos["precio_a"].astype("Float64")
        precio_b = datos["precio_b"].astype("Float64")
        con_precios = (precio_a.notna() & precio_b.notna()).astype(bool)
        datos = datos.assign(
            con_precios=con_precios,
            a_mas_barata=((precio_a < precio_b).fillna(False) & con_precios).astype(bool),
            mismo_precio=((precio_a == precio_b).fillna(False) & con_precios).astype(bool),
        )
        grupos = datos.groupby(["fuente_a", "fuente_b"])
        resumen = pd.DataFrame(
            {
                "parejas": grupos.size(),
                "diferencia_precio_mediana_pct": grupos["diferencia_precio_pct"].median(),
                "pct_a_mas_barata": grupos["a_mas_barata"].sum() / grupos["con_precios"].sum(),
                "pct_mismo_precio": grupos["mismo_precio"].sum() / grupos["con_precios"].sum(),
            }
        ).reset_index()
        resumen["nivel"] = nivel
        partes.append(resumen)

    tabla = pd.concat(partes, ignore_index=True) if partes else pd.DataFrame()
    if not tabla.empty:
        for columna in ("pct_a_mas_barata", "pct_mismo_precio"):
            tabla[columna] = (tabla[columna].astype("float64") * 100).round(1)
        tabla["diferencia_precio_mediana_pct"] = (
            tabla["diferencia_precio_mediana_pct"].astype("float64").round(1)
        )
        tabla["semana"] = semana
    tipos = {
        "parejas": "Int64",
        "diferencia_precio_mediana_pct": "float64",
        "pct_a_mas_barata": "float64",
        "pct_mismo_precio": "float64",
    }
    return _tipar(tabla, COLUMNAS_COMPARTIDOS_FUENTES, tipos)


def grupos_compartidos(grupos: pd.DataFrame, base: pd.DataFrame, semana: str) -> pd.DataFrame:
    """Los grupos de inmuebles compartidos, anónimos (página de compartidos del dashboard).

    Una fila por nivel, grupo y anuncio con los datos de hecho que permite el spec §7.1:
    barrio, área, estrato y precio por fuente. **Sin id, URL ni coordenadas.** Los grupos se
    numeran de 1 a n en cada nivel, en el orden de su id, así la numeración no depende del
    orden de las filas.
    """
    datos = grupos.merge(anuncios_unicos(base), on=CLAVE, how="inner")
    partes = []
    for nivel in NIVELES:
        columna = f"grupo_{nivel}"
        del_nivel = datos[datos[columna].notna()]
        if del_nivel.empty:
            continue
        partes.append(
            del_nivel.assign(
                nivel=nivel,
                grupo=del_nivel[columna].rank(method="dense").astype("Int64"),
            )
        )

    tabla = pd.concat(partes, ignore_index=True) if partes else pd.DataFrame()
    if not tabla.empty:
        tabla = tabla.assign(
            semana=semana,
            tipo=tabla["tipo_normalizado"],
            barrio=tabla["barrio_normalizado"].fillna(tabla["nombre_comuna"]),
            area_m2=tabla["area_m2"].astype("Float64").round().astype("Int64"),
            orden_nivel=tabla["nivel"].map(NIVELES.index),
        )
        tabla = tabla.sort_values(["orden_nivel", "grupo", "fuente", "precio"], kind="stable")
    tipos = {
        "grupo": "Int64",
        "area_m2": "Int64",
        "estrato": "Int64",
        "habitaciones": "Int64",
        "precio": "Int64",
    }
    return _tipar(tabla, COLUMNAS_GRUPOS_COMPARTIDOS, tipos)


# ------------------------------------------------------------ Análisis de precios

TIPOS_COMPARADOS: Final = ("apartamento", "casa", "local", "oficina")
"""Tipos que se comparan entre sí dentro de una comuna (pregunta 3)."""
RANGOS_AREA: Final = ("Menos de 40", "40 a 70", "70 a 100", "100 a 150", "Más de 150")
"""Rangos de área en m², de menor a mayor (pregunta 4)."""
_LIMITES_AREA: Final = [0, 40, 70, 100, 150, float("inf")]
ANALISIS_DISPERSION: Final = "dispersion"
ANALISIS_TIPO: Final = "tipo"
ANALISIS_AREA: Final = "area"
ANALISIS_ESTRATO: Final = "estrato"
CIUDAD: Final = "ciudad"
"""Valor de ``codigo`` de las filas que resumen toda la ciudad."""

COLUMNAS_MERCADO: Final = [
    "semana",
    "analisis",
    "codigo",
    "nombre",
    "comuna",
    "operacion",
    "categoria",
    "anuncios",
    "precio_m2_media",
    "precio_m2_mediana",
    "precio_m2_p25",
    "precio_m2_p75",
    "variacion_pct",
]
_TEXTO_MERCADO: Final = COLUMNAS_MERCADO[:7]
_CLAVES_MERCADO: Final = ["codigo", "nombre", "comuna", "operacion", "categoria"]


def _como_mercado(
    datos: pd.DataFrame,
    analisis: str,
    codigo: pd.Series,
    nombre: pd.Series,
    categoria: pd.Series,
) -> pd.DataFrame:
    """Deja ``datos`` con las columnas comunes de :data:`COLUMNAS_MERCADO` (sin estadísticas)."""
    return pd.DataFrame(
        {
            "analisis": pd.Series(analisis, index=datos.index, dtype="string"),
            "codigo": codigo.astype("string"),
            "nombre": nombre.astype("string"),
            "comuna": datos["comuna"].astype("string"),
            "operacion": datos["operacion"].astype("string"),
            "categoria": categoria.astype("string"),
            "precio_m2": datos["precio_m2"].astype("Float64"),
        }
    )


def _filas_mercado(base: pd.DataFrame) -> pd.DataFrame:
    """Los anuncios con precio por m², listos para agrupar en las cuatro tablas de análisis."""
    con_m2 = base[base["precio_m2"].notna()]
    vivienda = con_vivienda(con_m2)
    vivienda = vivienda[vivienda["tipo"] == VIVIENDA]
    sin_comuna = pd.Series(pd.NA, index=vivienda.index, dtype="string")
    ciudad = pd.Series(CIUDAD, index=vivienda.index, dtype="string")
    todo_vivienda = pd.Series(VIVIENDA, index=vivienda.index, dtype="string")

    en_barrio = vivienda[vivienda["codigo_barrio"].notna()]
    dispersion = _como_mercado(
        en_barrio,
        ANALISIS_DISPERSION,
        en_barrio["codigo_barrio"],
        en_barrio["barrio_normalizado"],
        todo_vivienda.loc[en_barrio.index],
    )

    comparados = con_m2[
        con_m2["tipo_normalizado"].isin(TIPOS_COMPARADOS).fillna(False).astype(bool)
        & con_m2["comuna"].notna()
    ]
    por_tipo = _como_mercado(
        comparados,
        ANALISIS_TIPO,
        comparados["comuna"],
        comparados["nombre_comuna"],
        comparados["tipo_normalizado"],
    )

    con_area = vivienda[vivienda["area_m2"].notna()]
    rangos = pd.cut(
        con_area["area_m2"].astype("float64"),
        _LIMITES_AREA,
        labels=list(RANGOS_AREA),
        right=False,
    ).astype("string")
    por_area = _como_mercado(
        con_area.assign(comuna=sin_comuna.loc[con_area.index]),
        ANALISIS_AREA,
        ciudad.loc[con_area.index],
        ciudad.loc[con_area.index],
        rangos,
    )

    con_estrato = vivienda[vivienda["estrato"].notna()]
    por_estrato = _como_mercado(
        con_estrato.assign(comuna=sin_comuna.loc[con_estrato.index]),
        ANALISIS_ESTRATO,
        ciudad.loc[con_estrato.index],
        ciudad.loc[con_estrato.index],
        con_estrato["estrato"].astype("Int64"),
    )
    return pd.concat([dispersion, por_tipo, por_area, por_estrato], ignore_index=True)


def mercado_precios(base: pd.DataFrame, semana: str) -> pd.DataFrame:
    """Precio por m² con más detalle que :func:`precios_zona` (preguntas 1 a 4).

    Una sola tabla en formato largo; ``analisis`` dice qué compara cada fila:

    * ``"dispersion"``: vivienda por barrio, con la media y la variación (desviación estándar
      sobre la media, en %). Si la variación es alta, la media engaña.
    * ``"tipo"``: apartamento, casa, local y oficina por comuna.
    * ``"area"``: vivienda de toda la ciudad por rango de área.
    * ``"estrato"``: vivienda de toda la ciudad por estrato declarado.

    Cada fila resume al menos :data:`MINIMO_PUBLICACION` anuncios **con precio por m²**.
    """
    filas = _filas_mercado(base)
    if filas.empty:
        return _vacia(COLUMNAS_MERCADO, _TEXTO_MERCADO)
    grupos = filas.groupby(["analisis", *_CLAVES_MERCADO], observed=True, dropna=False)
    valores = grupos["precio_m2"]
    media = valores.mean()
    tabla = pd.DataFrame(
        {
            "anuncios": valores.count(),
            "precio_m2_media": media,
            "precio_m2_mediana": valores.median(),
            "precio_m2_p25": valores.quantile(0.25),
            "precio_m2_p75": valores.quantile(0.75),
            "variacion_pct": valores.std() / media * 100,
        }
    ).reset_index()
    tabla = tabla[tabla["anuncios"] >= MINIMO_PUBLICACION].assign(semana=semana)
    if tabla.empty:
        return _vacia(COLUMNAS_MERCADO, _TEXTO_MERCADO)
    tabla = _enteros(tabla, COLUMNAS_MERCADO[7:])
    tabla = tabla.astype({c: "string" for c in _TEXTO_MERCADO})
    orden = tabla.sort_values(["analisis", "codigo", "operacion", "categoria"], kind="stable")
    return orden[COLUMNAS_MERCADO].reset_index(drop=True)


# ----------------------------------------------------------------------- Oferta

TODOS_LOS_TIPOS: Final = "todos"
"""Valor de ``tipo`` que reúne todos los tipos de inmueble en :func:`oferta_zona`."""
NIVEL_CIUDAD: Final = "ciudad"

COLUMNAS_OFERTA_ZONA: Final = [
    "semana",
    "nivel",
    "codigo",
    "nombre",
    "comuna",
    "operacion",
    "tipo",
    "anuncios",
]
_TEXTO_OFERTA_ZONA: Final = COLUMNAS_OFERTA_ZONA[:7]

RANGOS_PRECIO: Final = {
    "arriendo": (
        ("Menos de $1 M", "$1 a 2 M", "$2 a 3 M", "$3 a 5 M", "$5 a 8 M", "Más de $8 M"),
        [0, 1_000_000, 2_000_000, 3_000_000, 5_000_000, 8_000_000, float("inf")],
    ),
    "venta": (
        (
            "Menos de $200 M",
            "$200 a 400 M",
            "$400 a 600 M",
            "$600 a 1.000 M",
            "$1.000 a 2.000 M",
            "Más de $2.000 M",
        ),
        [0, 200e6, 400e6, 600e6, 1_000e6, 2_000e6, float("inf")],
    ),
}
"""Rangos de precio en pesos (``M`` = millones) y sus límites, por operación: el arriendo es
mensual y la venta es el precio total, por eso no comparten rangos."""
ALCOBAS: Final = ("0", "1", "2", "3", "4", "5 o más", "Sin dato")
"""Etiquetas del número de alcobas, en orden."""

COLUMNAS_DISTRIBUCION: Final = [
    "semana",
    "operacion",
    "tipo",
    "rango_precio",
    "alcobas",
    "anuncios",
]
_TEXTO_DISTRIBUCION: Final = COLUMNAS_DISTRIBUCION[:5]


def _contar_zona(
    datos: pd.DataFrame,
    nivel: str,
    codigo: pd.Series,
    nombre: pd.Series,
    por: str = "tipo",
) -> pd.DataFrame:
    """Anuncios de ``datos`` por zona, operación y la columna ``por`` (``tipo`` o ``fuente``)."""
    zonas = pd.DataFrame(
        {
            "codigo": codigo.astype("string"),
            "nombre": nombre.astype("string"),
            "comuna": datos["comuna"].astype("string"),
            "operacion": datos["operacion"].astype("string"),
            por: datos[por].astype("string"),
        }
    )
    cuenta = zonas.groupby(list(zonas.columns), observed=True, dropna=False).size()
    return cuenta.rename("anuncios").reset_index().assign(nivel=nivel)


def oferta_zona(base: pd.DataFrame, semana: str) -> pd.DataFrame:
    """Anuncios activos por zona, operación y tipo de inmueble (pregunta 1 de la oferta).

    Cuenta los anuncios únicos de la semana en Medellín, sin los marcados como atípicos (cerca
    del 1 %). Una fila por nivel (``"ciudad"``, ``"comuna"`` o ``"barrio"``), zona, operación y
    tipo; ``tipo`` incluye cada tipo de inmueble, ``"vivienda"`` y ``"todos"``. Son conteos, no
    estadísticas de precio, así que se publican también las celdas pequeñas. Un anuncio sin
    barrio oficial cuenta en su comuna, y uno sin comuna solo en la ciudad.
    """
    por_tipo = base.assign(tipo=base["tipo_normalizado"].astype("string"))
    es_vivienda = base["tipo_normalizado"].isin(TIPOS_VIVIENDA).fillna(False).astype(bool)
    vivienda = base[es_vivienda].assign(tipo=VIVIENDA)
    todos = base.assign(tipo=TODOS_LOS_TIPOS)
    datos = pd.concat([por_tipo, vivienda, todos], ignore_index=True)
    if datos.empty:
        return _vacia(COLUMNAS_OFERTA_ZONA, _TEXTO_OFERTA_ZONA)

    ciudad = pd.Series(NIVEL_CIUDAD, index=datos.index, dtype="string")
    con_comuna = datos[datos["comuna"].notna()]
    con_barrio = datos[datos["codigo_barrio"].notna()]
    partes = [
        _contar_zona(
            datos.assign(comuna=ciudad.map(lambda _: pd.NA)), NIVEL_CIUDAD, ciudad, ciudad
        ),
        _contar_zona(con_comuna, "comuna", con_comuna["comuna"], con_comuna["nombre_comuna"]),
        _contar_zona(
            con_barrio, "barrio", con_barrio["codigo_barrio"], con_barrio["barrio_normalizado"]
        ),
    ]
    tabla = pd.concat(partes, ignore_index=True).assign(semana=semana)
    tabla = tabla.astype({c: "string" for c in _TEXTO_OFERTA_ZONA})
    tabla["anuncios"] = tabla["anuncios"].astype("Int64")
    orden = tabla.sort_values(["nivel", "codigo", "operacion", "tipo"], kind="stable")
    return orden[COLUMNAS_OFERTA_ZONA].reset_index(drop=True)


def _etiqueta_alcobas(habitaciones: pd.Series) -> pd.Series:
    """``"0"`` a ``"4"``, ``"5 o más"`` o ``"Sin dato"``."""
    valores = habitaciones.astype("Float64")
    texto = valores.clip(upper=5).astype("Int64").astype("string")
    # El nulo se resuelve antes: ``mask`` trata una condición nula como verdadera.
    return texto.mask((valores >= 5).fillna(False).astype(bool), "5 o más").fillna("Sin dato")


def distribucion_oferta(base: pd.DataFrame, semana: str) -> pd.DataFrame:
    """Anuncios de vivienda por rango de precio y número de alcobas (pregunta 3 de la oferta).

    Una fila por operación, tipo (``"apartamento"``, ``"apartaestudio"``, ``"casa"`` y
    ``"vivienda"``), rango de precio (:data:`RANGOS_PRECIO`) y alcobas (:data:`ALCOBAS`). Con
    ella se arma la distribución por precio, por alcobas o las dos a la vez. Son conteos de
    toda la ciudad: no se publica el barrio, así que no hay celdas con pocos anuncios.
    """
    vivienda = con_vivienda(base)
    vivienda = vivienda[vivienda["precio"].notna()]
    partes = []
    for operacion, (etiquetas, limites) in RANGOS_PRECIO.items():
        filas = vivienda[vivienda["operacion"] == operacion]
        rangos = pd.cut(
            filas["precio"].astype("float64"), limites, labels=list(etiquetas), right=False
        ).astype("string")
        claves = pd.DataFrame(
            {
                "operacion": pd.Series(operacion, index=filas.index, dtype="string"),
                "tipo": filas["tipo"].astype("string"),
                "rango_precio": rangos,
                "alcobas": _etiqueta_alcobas(filas["habitaciones"]),
            }
        )
        cuenta = claves.groupby(list(claves.columns), observed=True).size()
        partes.append(cuenta.rename("anuncios").reset_index())
    tabla = pd.concat(partes, ignore_index=True) if partes else pd.DataFrame()
    if tabla.empty:
        return _vacia(COLUMNAS_DISTRIBUCION, _TEXTO_DISTRIBUCION)
    tabla = tabla.assign(semana=semana).astype({c: "string" for c in _TEXTO_DISTRIBUCION})
    tabla["anuncios"] = tabla["anuncios"].astype("Int64")
    orden = tabla.sort_values(["operacion", "tipo", "rango_precio", "alcobas"], kind="stable")
    return orden[COLUMNAS_DISTRIBUCION].reset_index(drop=True)


# ------------------------------------------------------- Cuota, perfil y calidad

COLUMNAS_CUOTA_ZONA: Final = [
    "semana",
    "nivel",
    "codigo",
    "nombre",
    "comuna",
    "operacion",
    "fuente",
    "anuncios",
]
_TEXTO_CUOTA_ZONA: Final = COLUMNAS_CUOTA_ZONA[:7]
COLUMNAS_PERFIL: Final = ["semana", "fuente", "operacion", "tipo", "anuncios"]
_TEXTO_PERFIL: Final = COLUMNAS_PERFIL[:4]
CAMPOS_CALIDAD: Final = {
    "pct_area": "area_m2",
    "pct_habitaciones": "habitaciones",
    "pct_banos": "banos",
    "pct_parqueaderos": "parqueaderos",
    "pct_estrato": "estrato",
    "pct_coordenadas": "coordenadas_validas",
    "pct_barrio": "codigo_barrio",
}
"""Campos de calidad de los datos y la columna de la base de la que salen."""
COLUMNAS_CALIDAD: Final = [
    "semana",
    "fuente",
    "anuncios",
    *CAMPOS_CALIDAD,
    "indice_completitud",
]
_TEXTO_CALIDAD: Final = COLUMNAS_CALIDAD[:2]


def cuota_zona(base: pd.DataFrame, semana: str) -> pd.DataFrame:
    """Anuncios de cada inmobiliaria por zona y operación: la base de la cuota y del HHI.

    Una fila por nivel (``"ciudad"``, ``"comuna"`` o ``"barrio"``), zona, operación (``venta``,
    ``arriendo`` y ``todas``) e inmobiliaria. Son conteos del inventario **observado** en las
    inmobiliarias que se scrapean, sin los anuncios atípicos: no es el mercado completo, y una
    propiedad publicada por varias inmobiliarias cuenta una vez en cada una. Los anuncios sin
    barrio cuentan en su comuna, y los que no tienen comuna, solo en la ciudad.
    """
    datos = _con_todas(base)
    if datos.empty:
        return _vacia(COLUMNAS_CUOTA_ZONA, _TEXTO_CUOTA_ZONA)
    ciudad = pd.Series(NIVEL_CIUDAD, index=datos.index, dtype="string")
    con_comuna = datos[datos["comuna"].notna()]
    con_barrio = datos[datos["codigo_barrio"].notna()]
    partes = [
        _contar_zona(
            datos.assign(comuna=ciudad.map(lambda _: pd.NA)),
            NIVEL_CIUDAD,
            ciudad,
            ciudad,
            "fuente",
        ),
        _contar_zona(
            con_comuna, "comuna", con_comuna["comuna"], con_comuna["nombre_comuna"], "fuente"
        ),
        _contar_zona(
            con_barrio,
            "barrio",
            con_barrio["codigo_barrio"],
            con_barrio["barrio_normalizado"],
            "fuente",
        ),
    ]
    tabla = pd.concat(partes, ignore_index=True).assign(semana=semana)
    tabla = tabla.astype({c: "string" for c in _TEXTO_CUOTA_ZONA})
    tabla["anuncios"] = tabla["anuncios"].astype("Int64")
    orden = tabla.sort_values(["nivel", "codigo", "operacion", "fuente"], kind="stable")
    return orden[COLUMNAS_CUOTA_ZONA].reset_index(drop=True)


def perfil_inmobiliaria(base: pd.DataFrame, semana: str) -> pd.DataFrame:
    """Anuncios de cada inmobiliaria por operación y tipo de inmueble (en qué se especializa).

    Incluye todos los tipos, no solo vivienda. El estrato está en ``estratos_inmobiliaria``.
    """
    datos = base[base["tipo_normalizado"].notna()]
    if datos.empty:
        return _vacia(COLUMNAS_PERFIL, _TEXTO_PERFIL)
    claves = pd.DataFrame(
        {
            "fuente": datos["fuente"].astype("string"),
            "operacion": datos["operacion"].astype("string"),
            "tipo": datos["tipo_normalizado"].astype("string"),
        }
    )
    cuenta = claves.groupby(list(claves.columns), observed=True).size()
    tabla = cuenta.rename("anuncios").reset_index().assign(semana=semana)
    tabla = tabla.astype({c: "string" for c in _TEXTO_PERFIL})
    tabla["anuncios"] = tabla["anuncios"].astype("Int64")
    orden = tabla.sort_values(["fuente", "operacion", "tipo"], kind="stable")
    return orden[COLUMNAS_PERFIL].reset_index(drop=True)


def calidad_inmobiliaria(base: pd.DataFrame, semana: str) -> pd.DataFrame:
    """Qué % de los anuncios de vivienda de cada inmobiliaria trae cada dato.

    Solo vivienda, para que alcobas, baños y parqueaderos apliquen a todos los anuncios; con
    al menos :data:`MINIMO_PUBLICACION` anuncios. ``pct_coordenadas`` cuenta las coordenadas
    válidas y ``pct_estrato`` el estrato **declarado** (algunas fuentes no lo publican).
    ``indice_completitud`` es el promedio de los siete porcentajes. Fotos y descripciones no se
    miden: el proyecto no las guarda.
    """
    es_vivienda = base["tipo_normalizado"].isin(TIPOS_VIVIENDA).fillna(False).astype(bool)
    vivienda = base[es_vivienda]
    if vivienda.empty:
        return _vacia(COLUMNAS_CALIDAD, _TEXTO_CALIDAD)
    presentes = pd.DataFrame(
        {
            nombre: vivienda[columna].fillna(False).astype(bool)
            if columna == "coordenadas_validas"
            else vivienda[columna].notna()
            for nombre, columna in CAMPOS_CALIDAD.items()
        }
    ).assign(fuente=vivienda["fuente"].astype("string"))
    grupos = presentes.groupby("fuente", observed=True)
    tabla = (grupos[list(CAMPOS_CALIDAD)].mean() * 100).assign(anuncios=grupos.size())
    tabla = tabla[tabla["anuncios"] >= MINIMO_PUBLICACION]
    if tabla.empty:
        return _vacia(COLUMNAS_CALIDAD, _TEXTO_CALIDAD)
    tabla["indice_completitud"] = tabla[list(CAMPOS_CALIDAD)].mean(axis=1)
    tabla = _enteros(
        tabla.reset_index().assign(semana=semana), [*CAMPOS_CALIDAD, "indice_completitud"]
    )
    tabla["anuncios"] = tabla["anuncios"].astype("Int64")
    tabla = tabla.astype({c: "string" for c in _TEXTO_CALIDAD})
    return tabla.sort_values("fuente", kind="stable")[COLUMNAS_CALIDAD].reset_index(drop=True)


# ------------------------------------------------- Compartidas por inmobiliaria

MINIMO_PARES_PRECIO: Final = 10
"""Parejas con los dos precios que debe tener una inmobiliaria para publicar cuánto por encima
o por debajo de las demás está: con menos, un par de casos decide el resultado."""
GLOBAL: Final = "todas"
"""Valor de ``fuente`` y de ``otra`` de la fila que resume a todas las inmobiliarias."""

COLUMNAS_COMPARTIDAS: Final = [
    "semana",
    "nivel",
    "fuente",
    "otra",
    "anuncios",
    "compartidos",
    "inmuebles",
    "pct_compartido",
    "parejas",
    "parejas_precio",
    "diferencia_mediana_pct",
    "diferencia_media_pct",
    "pct_mas_cara",
    "pct_mas_barata",
    "pct_mismo_precio",
]
_TIPOS_COMPARTIDAS: Final = {
    "anuncios": "Int64",
    "compartidos": "Int64",
    "inmuebles": "Int64",
    "pct_compartido": "float64",
    "parejas": "Int64",
    "parejas_precio": "Int64",
    "diferencia_mediana_pct": "float64",
    "diferencia_media_pct": "float64",
    "pct_mas_cara": "float64",
    "pct_mas_barata": "float64",
    "pct_mismo_precio": "float64",
}
_ANUNCIO: Final = ["fuente", "id_fuente", "operacion"]


def _lados(parejas: pd.DataFrame) -> pd.DataFrame:
    """Cada pareja vista desde sus dos anuncios: ``fuente``, ``otra``, su precio y el del otro."""
    lado_a = pd.DataFrame(
        {
            "fuente": parejas["fuente_a"],
            "otra": parejas["fuente_b"],
            "id_fuente": parejas["id_fuente_a"],
            "operacion": parejas["operacion"],
            "precio": parejas["precio_a"],
            "precio_otra": parejas["precio_b"],
            "confianza": parejas["confianza"],
        }
    )
    lado_b = lado_a.assign(
        fuente=parejas["fuente_b"],
        otra=parejas["fuente_a"],
        id_fuente=parejas["id_fuente_b"],
        precio=parejas["precio_b"],
        precio_otra=parejas["precio_a"],
    )
    return pd.concat([lado_a, lado_b], ignore_index=True)


def _precios_relativos(lados: pd.DataFrame) -> pd.DataFrame:
    """Por inmobiliaria, cuánto por encima o debajo (%) de la otra publica el mismo inmueble."""
    precio = lados["precio"].astype("Float64")
    precio_otra = lados["precio_otra"].astype("Float64")
    con_precios = (precio.notna() & precio_otra.notna() & (precio_otra > 0)).astype(bool)
    comparables = lados[con_precios].assign(
        relativa=((precio[con_precios] / precio_otra[con_precios] - 1) * 100).astype("float64")
    )
    grupos = comparables.groupby("fuente")["relativa"]
    resumen = pd.DataFrame(
        {
            "parejas_precio": grupos.size(),
            "diferencia_mediana_pct": grupos.median(),
            "diferencia_media_pct": grupos.mean(),
            "pct_mas_cara": grupos.apply(lambda r: (r > 0).mean() * 100),
            "pct_mas_barata": grupos.apply(lambda r: (r < 0).mean() * 100),
            "pct_mismo_precio": grupos.apply(lambda r: (r == 0).mean() * 100),
        }
    )
    estadisticas = [c for c in resumen.columns if c != "parejas_precio"]
    resumen.loc[resumen["parejas_precio"] < MINIMO_PARES_PRECIO, estadisticas] = float("nan")
    return resumen


def compartidas_inmobiliaria(
    parejas: pd.DataFrame, grupos: pd.DataFrame, base: pd.DataFrame, semana: str
) -> pd.DataFrame:
    """Cuánto inventario comparte cada inmobiliaria, con quién y a qué precio.

    Una fila por nivel de confianza (acumulado, como en :func:`compartidos_fuentes`) e
    inmobiliaria, con ``otra`` = ``"todas"`` (el resumen) o cada inmobiliaria con la que
    comparte (la matriz). Hay además una fila ``fuente = otra = "todas"`` con el total.

    * ``anuncios``: anuncios de la inmobiliaria en la base de análisis.
    * ``compartidos``: de esos, los que forman pareja con otra inmobiliaria. ``pct_compartido``
      es la parte que representan.
    * ``inmuebles``: solo en la fila global, cuántos inmuebles distintos hay (grupos).
    * Precio (solo en el resumen, y solo con :data:`MINIMO_PARES_PRECIO` parejas con los dos
      precios): ``diferencia_*_pct`` es cuánto por encima (+) o por debajo (−) de la otra
      inmobiliaria publica el mismo inmueble, y los ``pct_*`` son la proporción de parejas en
      que publica más caro, más barato o igual.
    """
    if base.empty:
        return _tipar(pd.DataFrame(), COLUMNAS_COMPARTIDAS, _TIPOS_COMPARTIDAS)
    totales = base.groupby("fuente").size()
    unicos = anuncios_unicos(base)
    en_grupos = grupos.merge(unicos[CLAVE], on=CLAVE, how="inner")
    lados = _lados(parejas)
    partes = []
    for nivel in NIVELES:
        del_nivel = lados[lados["confianza"].isin(_hasta(nivel))]
        columna = f"grupo_{nivel}"
        agrupados = en_grupos[en_grupos[columna].notna()]

        resumen = pd.DataFrame({"anuncios": totales})
        resumen["compartidos"] = (
            del_nivel.drop_duplicates(_ANUNCIO).groupby("fuente").size().reindex(totales.index)
        )
        resumen["parejas"] = del_nivel.groupby("fuente").size().reindex(totales.index)
        resumen = resumen.join(_precios_relativos(del_nivel)).fillna(
            {"compartidos": 0, "parejas": 0}
        )
        resumen = resumen.reset_index().assign(otra=GLOBAL)

        cruce = del_nivel.drop_duplicates([*_ANUNCIO, "otra"]).groupby(["fuente", "otra"]).size()
        parejas_cruce = del_nivel.groupby(["fuente", "otra"]).size()
        pares = pd.DataFrame({"compartidos": cruce, "parejas": parejas_cruce}).reset_index()
        pares["anuncios"] = pares["fuente"].map(totales)

        total = pd.DataFrame(
            [
                {
                    "fuente": GLOBAL,
                    "otra": GLOBAL,
                    "anuncios": int(totales.sum()),
                    "compartidos": len(agrupados),
                    "inmuebles": agrupados[columna].nunique(),
                    "parejas": len(parejas[parejas["confianza"].isin(_hasta(nivel))]),
                }
            ]
        )
        partes.append(pd.concat([resumen, pares, total], ignore_index=True).assign(nivel=nivel))

    tabla = pd.concat(partes, ignore_index=True) if partes else pd.DataFrame()
    if tabla.empty:
        return _tipar(tabla, COLUMNAS_COMPARTIDAS, _TIPOS_COMPARTIDAS)
    tabla["pct_compartido"] = (
        tabla["compartidos"].astype("float64") / tabla["anuncios"].astype("float64") * 100
    ).round(1)
    for columna in (
        "diferencia_mediana_pct",
        "diferencia_media_pct",
        "pct_mas_cara",
        "pct_mas_barata",
        "pct_mismo_precio",
    ):
        tabla[columna] = tabla[columna].astype("float64").round(1)
    tabla["semana"] = semana
    tabla["orden"] = tabla["nivel"].map(NIVELES.index)
    tabla = tabla.sort_values(["orden", "fuente", "otra"], kind="stable")
    return _tipar(tabla, COLUMNAS_COMPARTIDAS, _TIPOS_COMPARTIDAS)
