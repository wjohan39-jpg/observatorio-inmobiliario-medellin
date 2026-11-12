"""Evolución en el tiempo (pregunta 8): precios por semana y rotación del inventario.

Las funciones reciben la unión de todas las semanas limpias (``leer_limpio(directorio)``).

La rotación se mide **por inmobiliaria**: cada fuente se compara con su propia semana anterior
con datos. Si su scraping falló una semana, o empezó a scrapearse más tarde que las demás, no
se inventan retiros ni anuncios nuevos.

* Un anuncio es **nuevo** si no estaba en la semana anterior de su fuente, y **retirado** si
  estaba y ya no. En la primera semana de cada fuente no hay con qué comparar: ``nuevos`` y la
  tasa de retiro quedan nulos y ``retirados`` en 0.
* Las semanas publicado se cuentan como apariciones seguidas. Un anuncio que vuelve después de
  desaparecer empieza a contar de nuevo. Los que ya estaban en la primera semana de su fuente
  no entran en la mediana, porque no se sabe cuándo empezaron.
"""

from typing import Final

import pandas as pd

from observatorio_inmobiliario.agregados import (
    CLAVE,
    MINIMO_PUBLICACION,
    _tipar,
    anuncios_unicos,
    base_analisis,
    con_vivienda,
)
from observatorio_inmobiliario.almacenamiento import semana_de

COLUMNAS_EVOLUCION: Final = ["semana", "operacion", "tipo", "anuncios", "precio_m2_mediana"]
COLUMNAS_ROTACION: Final = [
    "semana",
    "fuente",
    "operacion",
    "anuncios",
    "nuevos",
    "retirados",
    "tasa_retiro_pct",
    "semanas_publicado_mediana",
    "comparables",
    "con_cambio_precio",
    "cambio_precio_mediana_pct",
]
_GRUPO: Final = ["fuente", "operacion"]


def con_semana(limpio: pd.DataFrame) -> pd.DataFrame:
    """Copia de ``limpio`` con la columna ``semana`` (``"2026-S46"``) de ``fecha_observacion``."""
    semanas = [semana_de(fecha) for fecha in limpio["fecha_observacion"]]
    return limpio.assign(semana=pd.Series(semanas, index=limpio.index, dtype="string"))


def evolucion_precios(limpio: pd.DataFrame) -> pd.DataFrame:
    """Mediana del precio por m² de vivienda por semana, operación y tipo.

    Cada semana usa su propia base de análisis (Medellín, sin atípicos). Solo filas con al
    menos :data:`MINIMO_PUBLICACION` anuncios.
    """
    datos = con_semana(limpio)
    por_semana = [
        con_vivienda(base_analisis(semana)).assign(semana=nombre)
        for nombre, semana in datos.groupby("semana")
    ]
    tabla = pd.concat(por_semana, ignore_index=True) if por_semana else pd.DataFrame()
    if not tabla.empty:
        tabla["precio_m2"] = tabla["precio_m2"].astype("Float64")
        grupos = tabla.groupby(["semana", "operacion", "tipo"])
        # Solo cuentan los anuncios con precio por m²: es el dato que se resume.
        tabla = pd.DataFrame(
            {
                "anuncios": grupos["precio_m2"].count(),
                "precio_m2_mediana": grupos["precio_m2"].median(),
            }
        ).reset_index()
        tabla = tabla[tabla["anuncios"] >= MINIMO_PUBLICACION]
        tabla["precio_m2_mediana"] = (
            tabla["precio_m2_mediana"].astype("Float64").round().astype("Int64")
        )
        tabla = tabla.sort_values(["semana", "operacion", "tipo"])
    return _tipar(tabla, COLUMNAS_EVOLUCION, {"anuncios": "Int64", "precio_m2_mediana": "Int64"})


def _presencia(limpio: pd.DataFrame) -> pd.DataFrame:
    """Una fila por anuncio de Medellín y semana, con la posición de la semana y su racha.

    ``pos`` es la posición (0, 1, 2…) de la semana entre las semanas **con datos de esa
    fuente**. ``inicio`` es la posición de la primera semana de la racha de apariciones
    seguidas a la que pertenece la fila.
    """
    datos = con_semana(limpio)
    # Semanas con datos de cada fuente: cuenta cualquier anuncio, no solo los de Medellín.
    semanas_fuente = datos.groupby("fuente")["semana"].unique()
    posicion = {
        (fuente, semana): i
        for fuente, semanas in semanas_fuente.items()
        for i, semana in enumerate(sorted(semanas))
    }
    datos = datos[datos["es_medellin"].fillna(False).astype(bool)]
    unicos = [anuncios_unicos(semana) for _, semana in datos.groupby("semana")]
    datos = pd.concat(unicos, ignore_index=True) if unicos else datos.iloc[0:0]
    datos = datos.assign(
        pos=[posicion[(f, s)] for f, s in zip(datos["fuente"], datos["semana"], strict=True)]
    )
    datos = datos.sort_values([*CLAVE, "pos"], kind="stable")
    otra_clave = (datos[CLAVE] != datos[CLAVE].shift()).fillna(True).any(axis=1)
    nueva_racha = (otra_clave | (datos["pos"].diff() != 1)).astype(bool)
    racha = nueva_racha.astype(int).cumsum()
    datos["inicio"] = datos["pos"].groupby(racha).transform("min")
    return datos[[*CLAVE, "semana", "pos", "inicio", "precio"]]


def _resumen_semana(actual: pd.DataFrame, anterior: pd.DataFrame | None) -> pd.DataFrame:
    """Rotación de una semana de una fuente frente a su semana anterior con datos."""
    if anterior is None:
        tabla = actual.groupby(_GRUPO).size().rename("anuncios").reset_index()
        nulo = float("nan")
        return tabla.assign(
            nuevos=pd.Series(pd.NA, index=tabla.index, dtype="Int64"),
            retirados=0,
            tasa_retiro_pct=nulo,
            semanas_publicado_mediana=nulo,
            comparables=0,
            con_cambio_precio=0,
            cambio_precio_mediana_pct=nulo,
        )

    union = anterior.merge(actual, on=CLAVE, how="outer", suffixes=("_ant", ""), indicator=True)
    estaba = union["_merge"].isin(["left_only", "both"])
    esta = union["_merge"].isin(["right_only", "both"])
    ambas = union["_merge"] == "both"
    precio_ant = union["precio_ant"].astype("Float64")
    precio = union["precio"].astype("Float64")
    comparable = ambas & precio_ant.notna() & precio.notna()
    cambio = comparable & (precio != precio_ant).fillna(False)
    retirado = estaba & ~esta
    # Racha del retirado: desde su inicio hasta la semana anterior; nula si empezó en la primera.
    semanas_publicado = (union["pos_ant"] - union["inicio_ant"] + 1).where(
        retirado & (union["inicio_ant"] > 0)
    )
    union = union.assign(
        anuncios=esta.astype(int),
        anteriores=estaba.astype(int),
        nuevos=(esta & ~estaba).astype(int),
        retirados=retirado.astype(int),
        comparables=comparable.astype(bool).astype(int),
        con_cambio_precio=cambio.astype(bool).astype(int),
        cambio_pct=((precio / precio_ant - 1) * 100).where(cambio).astype("float64"),
        semanas_publicado=semanas_publicado.astype("float64"),
    )
    grupos = union.groupby(_GRUPO)
    tabla = grupos[
        ["anuncios", "anteriores", "nuevos", "retirados", "comparables", "con_cambio_precio"]
    ].sum()
    tabla["tasa_retiro_pct"] = (tabla["retirados"] / tabla["anteriores"] * 100).where(
        tabla["anteriores"] > 0
    )
    tabla["semanas_publicado_mediana"] = grupos["semanas_publicado"].median()
    tabla["cambio_precio_mediana_pct"] = grupos["cambio_pct"].median()
    return tabla.reset_index()


def rotacion_inmobiliaria(limpio: pd.DataFrame) -> pd.DataFrame:
    """Nuevos, retirados, semanas publicado y cambios de precio por semana e inmobiliaria.

    Usa todos los anuncios de Medellín, también los atípicos: la marca de atípico puede
    cambiar de una semana a otra y eso no es una rotación.
    """
    presencia = _presencia(limpio)
    partes = []
    for _, de_la_fuente in presencia.groupby("fuente"):
        for pos in sorted(de_la_fuente["pos"].unique()):
            actual = de_la_fuente[de_la_fuente["pos"] == pos]
            anterior = de_la_fuente[de_la_fuente["pos"] == pos - 1] if pos > 0 else None
            semana = actual["semana"].iloc[0]
            partes.append(_resumen_semana(actual, anterior).assign(semana=semana))

    tabla = pd.concat(partes, ignore_index=True) if partes else pd.DataFrame()
    if not tabla.empty:
        for columna in ("tasa_retiro_pct", "cambio_precio_mediana_pct"):
            tabla[columna] = tabla[columna].astype("float64").round(1)
        tabla = tabla.sort_values(["semana", "fuente", "operacion"])
    tipos = {
        "anuncios": "Int64",
        "nuevos": "Int64",
        "retirados": "Int64",
        "tasa_retiro_pct": "float64",
        "semanas_publicado_mediana": "float64",
        "comparables": "Int64",
        "con_cambio_precio": "Int64",
        "cambio_precio_mediana_pct": "float64",
    }
    return _tipar(tabla, COLUMNAS_ROTACION, tipos)
