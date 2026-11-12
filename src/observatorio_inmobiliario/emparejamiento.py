"""Inmuebles compartidos: el mismo inmueble publicado por distintas inmobiliarias.

:func:`emparejar` recibe la tabla limpia (la de ``leer_limpio``) y devuelve las **parejas** de
anuncios que parecen ser el mismo inmueble, cada una con una :class:`Confianza`. No borra ni
cambia ningún anuncio: las parejas son una tabla aparte.

Qué anuncios entran: los de Medellín que no son atípicos, con comuna, tipo y área mayor que 0.
Un anuncio se identifica con ``(fuente, id_fuente, operacion)``, porque algunas fuentes usan el
mismo id para el arriendo y la venta del mismo inmueble.

Dos anuncios son candidatos si son de fuentes distintas, con la misma operación, el mismo tipo
y la misma comuna, áreas a menos de :data:`TOLERANCIA_AREA` y las mismas habitaciones, baños y
estrato (un dato nulo en un lado no descarta la pareja). **El precio no es un criterio**: la
diferencia de precio es lo que se quiere medir.

Confianza de una candidata:

* Con coordenadas válidas en los dos: **alta** a :data:`DISTANCIA_ALTA_M` o menos, **media**
  a :data:`DISTANCIA_MEDIA_M` o menos. Más lejos no es pareja, aunque el barrio sea el mismo.
* Si a alguno le faltan coordenadas, hace falta el mismo barrio oficial: **media** si
  habitaciones, baños y estrato son conocidos e iguales en los dos; si no, **baja**.

Una pareja es **ambigua** si uno de sus anuncios tiene más de una pareja en la fuente del otro
(unidades iguales de una misma torre). No se sabe cuál es la buena, así que baja un nivel y,
si era baja, se descarta.
"""

from collections.abc import Iterable
from enum import StrEnum
from typing import Final

import numpy as np
import pandas as pd


class Confianza(StrEnum):
    """Qué tan seguro es que dos anuncios sean el mismo inmueble, de mayor a menor."""

    ALTA = "alta"
    MEDIA = "media"
    BAJA = "baja"


TOLERANCIA_AREA: Final = 0.03
"""Diferencia relativa de área permitida (spec §7: ±3 %)."""
DISTANCIA_ALTA_M: Final = 100.0
DISTANCIA_MEDIA_M: Final = 300.0
"""En la semana 2026-S46, las parejas a 100 m o menos difieren 2,4 % en precio (mediana) y las
de hasta 300 m, 4,9 %. A más de 1 km difieren 25 %: ya son coincidencias de características."""

RADIO_TIERRA_M: Final = 6_371_000.0
CLAVE: Final = ["fuente", "id_fuente", "operacion"]
_BLOQUE: Final = ["operacion", "tipo_normalizado", "comuna"]
_ATRIBUTOS: Final = ["habitaciones", "banos", "estrato"]
_POR_LADO: Final = [
    "fuente",
    "id_fuente",
    "codigo_barrio",
    "area_m2",
    "precio",
    "habitaciones",
    "banos",
    "estrato",
    "latitud",
    "longitud",
    "coordenadas_validas",
]
COLUMNAS: Final = [
    "fuente_a",
    "id_fuente_a",
    "fuente_b",
    "id_fuente_b",
    "operacion",
    "tipo_normalizado",
    "comuna",
    "codigo_barrio_a",
    "codigo_barrio_b",
    "area_m2_a",
    "area_m2_b",
    "precio_a",
    "precio_b",
    "distancia_m",
    "diferencia_precio_pct",
    "ambigua",
    "confianza",
]
_UN_NIVEL_MENOS: Final = {
    Confianza.ALTA.value: Confianza.MEDIA.value,
    Confianza.MEDIA.value: Confianza.BAJA.value,
    Confianza.BAJA.value: None,
}


def distancia_m(
    lat_a: np.ndarray, lon_a: np.ndarray, lat_b: np.ndarray, lon_b: np.ndarray
) -> np.ndarray:
    """Distancia en metros entre puntos (grados), con la aproximación equirectangular.

    A menos de 1 km el error frente a la fórmula exacta es menor de 1 m.
    """
    fi_a, fi_b = np.radians(lat_a), np.radians(lat_b)
    x = np.radians(lon_b - lon_a) * np.cos((fi_a + fi_b) / 2)
    y = fi_b - fi_a
    resultado: np.ndarray = RADIO_TIERRA_M * np.hypot(x, y)
    return resultado


def _bool(serie: pd.Series) -> pd.Series:
    """Una comparación con nulos de pandas (``<NA>``) convertida a bool; el nulo es False."""
    return serie.fillna(False).astype(bool)


def _vacio() -> pd.DataFrame:
    return pd.DataFrame(
        {
            **{c: pd.Series(dtype="string") for c in COLUMNAS[:9]},
            "area_m2_a": pd.Series(dtype="float64"),
            "area_m2_b": pd.Series(dtype="float64"),
            "precio_a": pd.Series(dtype="Int64"),
            "precio_b": pd.Series(dtype="Int64"),
            "distancia_m": pd.Series(dtype="float64"),
            "diferencia_precio_pct": pd.Series(dtype="float64"),
            "ambigua": pd.Series(dtype=bool),
            "confianza": pd.Series(dtype="string"),
        }
    )


def _anuncios(limpio: pd.DataFrame) -> pd.DataFrame:
    """Las filas que pueden emparejarse, una por clave."""
    area = limpio["area_m2"].astype("float64")
    entran = (
        _bool(limpio["es_medellin"])
        & ~_bool(limpio["es_atipico"])
        & limpio["comuna"].notna()
        & limpio["tipo_normalizado"].notna()
        & (area > 0)
    )
    return limpio[entran].drop_duplicates(CLAVE)[_BLOQUE + _POR_LADO]


def emparejar(limpio: pd.DataFrame) -> pd.DataFrame:
    """Parejas de anuncios de distintas fuentes que parecen el mismo inmueble.

    El lado ``a`` es el de menor ``(fuente, id_fuente)``. Las filas salen ordenadas por
    ``fuente_a, id_fuente_a, fuente_b, id_fuente_b`` para que el resultado no dependa del
    orden de entrada.
    """
    anuncios = _anuncios(limpio)
    lado_a = anuncios.rename(columns={c: f"{c}_a" for c in _POR_LADO})
    lado_b = anuncios.rename(columns={c: f"{c}_b" for c in _POR_LADO})
    p = lado_a.merge(lado_b, on=_BLOQUE)
    # Fuentes distintas, y cada par una sola vez (a < b).
    p = p[p["fuente_a"] < p["fuente_b"]]

    area_a, area_b = p["area_m2_a"].astype("float64"), p["area_m2_b"].astype("float64")
    candidata: pd.Series[bool] = ((area_a - area_b).abs() / np.maximum(area_a, area_b)).le(
        TOLERANCIA_AREA
    )
    completos = pd.Series(True, index=p.index)
    for atributo in _ATRIBUTOS:
        x, y = p[f"{atributo}_a"], p[f"{atributo}_b"]
        candidata &= _bool(x.isna() | y.isna() | (x == y))
        completos &= _bool(x.notna() & y.notna())
    p = p.loc[candidata]
    completos = completos.loc[candidata]

    con_coordenadas = _bool(p["coordenadas_validas_a"]) & _bool(p["coordenadas_validas_b"])
    distancia = pd.Series(
        distancia_m(
            p["latitud_a"].to_numpy("float64", na_value=np.nan),
            p["longitud_a"].to_numpy("float64", na_value=np.nan),
            p["latitud_b"].to_numpy("float64", na_value=np.nan),
            p["longitud_b"].to_numpy("float64", na_value=np.nan),
        ),
        index=p.index,
    ).where(con_coordenadas)
    mismo_barrio = _bool(p["codigo_barrio_a"] == p["codigo_barrio_b"])

    confianza = pd.Series(
        np.select(
            [
                con_coordenadas & (distancia <= DISTANCIA_ALTA_M),
                con_coordenadas & (distancia <= DISTANCIA_MEDIA_M),
                ~con_coordenadas & mismo_barrio & completos,
                ~con_coordenadas & mismo_barrio,
            ],
            [
                Confianza.ALTA.value,
                Confianza.MEDIA.value,
                Confianza.MEDIA.value,
                Confianza.BAJA.value,
            ],
            default="",
        ),
        index=p.index,
    )
    p = p.assign(distancia_m=distancia, confianza=confianza)
    p = p[p["confianza"] != ""]

    # Ambigua: un anuncio con varias parejas en la misma fuente del otro lado.
    varias_a = p.groupby(["fuente_a", "id_fuente_a", "operacion", "fuente_b"])["fuente_a"]
    varias_b = p.groupby(["fuente_b", "id_fuente_b", "operacion", "fuente_a"])["fuente_b"]
    ambigua = (varias_a.transform("size") > 1) | (varias_b.transform("size") > 1)
    p = p.assign(
        ambigua=ambigua.astype(bool),
        confianza=p["confianza"].where(~ambigua, p["confianza"].map(_UN_NIVEL_MENOS)),
    )
    p = p[p["confianza"].notna()]
    if p.empty:
        return _vacio()

    precio_a, precio_b = p["precio_a"].astype("Float64"), p["precio_b"].astype("Float64")
    diferencia = (np.maximum(precio_a, precio_b) / np.minimum(precio_a, precio_b) - 1) * 100
    p = p.assign(diferencia_precio_pct=diferencia.astype("float64"))
    p = p.sort_values(["fuente_a", "id_fuente_a", "fuente_b", "id_fuente_b", "operacion"])
    return p[COLUMNAS].astype(_vacio().dtypes.to_dict()).reset_index(drop=True)


COLUMNAS_GRUPOS: Final = [
    "fuente",
    "id_fuente",
    "operacion",
    "grupo_alta",
    "grupo_media",
    "grupo_baja",
]
_PAREJA_A: Final = ["fuente_a", "id_fuente_a"]
_PAREJA_B: Final = ["fuente_b", "id_fuente_b"]
_ORDEN: Final = {Confianza.ALTA.value: 3, Confianza.MEDIA.value: 2, Confianza.BAJA.value: 1}


def clave_anuncio(fuente: str, id_fuente: str, operacion: str) -> str:
    """Texto que identifica un anuncio en una semana, p. ej. ``"nutibara:123:venta"``."""
    return f"{fuente}:{id_fuente}:{operacion}"


def _componentes(aristas: Iterable[tuple[str, str]]) -> dict[str, str]:
    """Unión-búsqueda: para cada clave, el id de su grupo (la menor clave del grupo).

    Cada clave apunta a un "padre"; la raíz de un grupo se apunta a sí misma. Unir dos grupos
    es colgar una raíz de la otra (siempre la mayor de la menor, así la raíz es el id). Al
    buscar una raíz se acortan los caminos para que las búsquedas siguientes sean directas.
    """
    padre: dict[str, str] = {}

    def raiz(clave: str) -> str:
        padre.setdefault(clave, clave)
        while padre[clave] != clave:
            padre[clave] = padre[padre[clave]]
            clave = padre[clave]
        return clave

    for a, b in aristas:
        ra, rb = raiz(a), raiz(b)
        if ra != rb:
            menor, mayor = sorted((ra, rb))
            padre[mayor] = menor
    return {clave: raiz(clave) for clave in padre}


def agrupar(parejas: pd.DataFrame) -> pd.DataFrame:
    """Los grupos de inmueble de cada anuncio emparejado, uno por nivel de confianza.

    ``grupo_<nivel>`` se arma solo con las parejas de ese nivel o uno mayor (``grupo_media``
    usa las alta y las media), para que una cadena de parejas débiles no una grupos fuertes.
    Es nulo si el anuncio no tiene parejas de ese nivel. El id del grupo es la menor
    :func:`clave_anuncio` de sus miembros, así no depende del orden de las parejas.
    """
    anuncios: dict[str, tuple[str, str, str]] = {}
    aristas: list[tuple[str, str, int]] = []
    columnas = [*_PAREJA_A, *_PAREJA_B, "operacion", "confianza"]
    for fuente_a, id_a, fuente_b, id_b, operacion, confianza in (
        parejas[columnas].astype(str).values
    ):
        lado_a, lado_b = (fuente_a, id_a, operacion), (fuente_b, id_b, operacion)
        clave_a, clave_b = clave_anuncio(*lado_a), clave_anuncio(*lado_b)
        anuncios[clave_a], anuncios[clave_b] = lado_a, lado_b
        aristas.append((clave_a, clave_b, _ORDEN[confianza]))

    claves = sorted(anuncios, key=anuncios.__getitem__)
    grupos: dict[str, list[str | None]] = {}
    for confianza in Confianza:
        nivel = _ORDEN[confianza.value]
        componentes = _componentes((a, b) for a, b, n in aristas if n >= nivel)
        grupos[f"grupo_{confianza.value}"] = [componentes.get(clave) for clave in claves]

    return pd.DataFrame(
        {
            "fuente": [anuncios[c][0] for c in claves],
            "id_fuente": [anuncios[c][1] for c in claves],
            "operacion": [anuncios[c][2] for c in claves],
            **grupos,
        },
        columns=COLUMNAS_GRUPOS,
    ).astype("string")
