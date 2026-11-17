from typing import Any

import pandas as pd
import pytest

from conftest import fila
from observatorio_inmobiliario.agregados import (
    NIVELES,
    anuncios_unicos,
    base_analisis,
    cobertura_comuna,
    cobertura_inmobiliaria,
    compartidos_fuentes,
    con_vivienda,
    distribucion_oferta,
    economia_inmobiliaria,
    estrato_inferido,
    estratos_inmobiliaria,
    grupos_compartidos,
    indice_relativo,
    mercado_precios,
    oferta_zona,
    precios_zona,
)
from observatorio_inmobiliario.emparejamiento import Confianza, agrupar, emparejar

SEMANA = "2026-S46"
COLUMNAS_MERCADO = [
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
COLUMNAS_PRECIOS_ZONA = [
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


def _apartamentos(n: int, **cambios: Any) -> list[dict[str, Any]]:
    """``n`` apartamentos en arriendo de 100 m², a 1, 2, 3… millones."""
    return [
        fila(
            id_fuente=f"{cambios.get('codigo_barrio', '1101')}-{i}",
            precio=(i + 1) * 1_000_000,
            area_m2=100.0,
            precio_m2=(i + 1) * 10_000.0,
            **cambios,
        )
        for i in range(n)
    ]


# ------------------------------------------------------------------ Base


def test_anuncios_unicos_quita_repetidas(limpio: Any) -> None:
    tabla = limpio(
        fila(id_fuente="A"),
        fila(id_fuente="A"),
        fila(id_fuente="A"),
        fila(id_fuente="B", operacion="arriendo"),
        fila(id_fuente="B", operacion="venta"),
    )
    assert len(anuncios_unicos(tabla)) == 3


def test_anuncios_unicos_no_depende_del_orden(limpio: Any) -> None:
    tabla = limpio(fila(id_fuente="A", area_m2=80.0), fila(id_fuente="A", area_m2=200.0))
    pd.testing.assert_frame_equal(
        anuncios_unicos(tabla).reset_index(drop=True),
        anuncios_unicos(tabla.iloc[::-1]).reset_index(drop=True),
    )


def test_base_analisis(limpio: Any) -> None:
    tabla = limpio(
        fila(id_fuente="1"),
        fila(id_fuente="2", es_medellin=False, municipio_normalizado="Envigado"),
        fila(id_fuente="3", es_atipico=True, motivo_atipico="precio_fuera_de_rango"),
    )
    assert list(base_analisis(tabla)["id_fuente"]) == ["1"]


def test_con_vivienda(limpio: Any) -> None:
    tabla = limpio(
        fila(id_fuente="1"),
        fila(id_fuente="2"),
        fila(id_fuente="3", tipo_normalizado="casa"),
        fila(id_fuente="4", tipo_normalizado="local"),
    )
    tipos = con_vivienda(tabla)["tipo"].value_counts().to_dict()
    assert tipos == {"vivienda": 3, "apartamento": 2, "casa": 1}


# ------------------------------------------------------------ Precios por zona


def _zona(tabla: pd.DataFrame, nivel: str, codigo: str, tipo: str = "apartamento") -> pd.Series:  # type: ignore[type-arg]
    filas = tabla[(tabla["nivel"] == nivel) & (tabla["codigo"] == codigo) & (tabla["tipo"] == tipo)]
    assert len(filas) == 1
    return filas.iloc[0]


def test_precios_zona_mediana_y_cuantiles(limpio: Any) -> None:
    tabla = precios_zona(base_analisis(limpio(*_apartamentos(5))), SEMANA)
    barrio = _zona(tabla, "barrio", "1101")
    assert barrio["anuncios"] == 5
    assert barrio["precio_mediana"] == 3_000_000
    assert barrio["precio_p25"] == 2_000_000
    assert barrio["precio_p75"] == 4_000_000
    assert barrio["precio_m2_mediana"] == 30_000
    assert barrio["nombre"] == "Laureles"
    assert barrio["comuna"] == "11"
    assert barrio["semana"] == SEMANA
    comuna = _zona(tabla, "comuna", "11", "vivienda")
    assert comuna["nombre"] == "LAURELES ESTADIO"


def test_minimo_de_publicacion(limpio: Any) -> None:
    tabla = precios_zona(
        base_analisis(limpio(*_apartamentos(4), *_apartamentos(2, codigo_barrio="1102"))), SEMANA
    )
    assert (tabla["nivel"] == "barrio").sum() == 0
    assert _zona(tabla, "comuna", "11")["anuncios"] == 6


def test_venta_y_arriendo_separados(limpio: Any) -> None:
    tabla = precios_zona(
        base_analisis(
            limpio(*_apartamentos(5), *_apartamentos(5, operacion="venta", fuente="nutibara"))
        ),
        SEMANA,
    )
    barrio = tabla[(tabla["nivel"] == "barrio") & (tabla["tipo"] == "apartamento")]
    assert sorted(barrio["operacion"]) == ["arriendo", "venta"]
    assert set(barrio["anuncios"]) == {5}


def test_sin_barrio_cuenta_en_comuna(limpio: Any) -> None:
    tabla = precios_zona(base_analisis(limpio(*_apartamentos(5, codigo_barrio=None))), SEMANA)
    assert set(tabla["nivel"]) == {"comuna"}


def test_precios_zona_vacia(limpio: Any) -> None:
    tabla = precios_zona(base_analisis(limpio()), SEMANA)
    assert tabla.empty
    assert list(tabla.columns) == COLUMNAS_PRECIOS_ZONA
    assert str(tabla["anuncios"].dtype) == "Int64"
    assert str(tabla["precio_mediana"].dtype) == "Int64"
    assert str(tabla["nombre"].dtype) == "string"


def test_tipos_con_datos(limpio: Any) -> None:
    tabla = precios_zona(base_analisis(limpio(*_apartamentos(5))), SEMANA)
    assert str(tabla["precio_m2_p75"].dtype) == "Int64"
    assert str(tabla["codigo"].dtype) == "string"


@pytest.mark.parametrize("tipo", ["local", "oficina"])
def test_solo_vivienda(limpio: Any, tipo: str) -> None:
    tabla = precios_zona(base_analisis(limpio(*_apartamentos(5, tipo_normalizado=tipo))), SEMANA)
    assert tabla.empty


# ------------------------------------------------------------- Inmobiliarias

COLUMNAS_COBERTURA = [
    "semana",
    "fuente",
    "operacion",
    "anuncios",
    "barrios",
    "comunas",
    "comuna_principal",
    "pct_comuna_principal",
]
COLUMNAS_COBERTURA_COMUNA = [
    "semana",
    "fuente",
    "operacion",
    "comuna",
    "nombre_comuna",
    "anuncios",
    "pct_de_la_fuente",
]
COLUMNAS_ECONOMIA = [
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
COLUMNAS_ESTRATOS = ["semana", "fuente", "operacion", "estrato", "declarados", "inferidos"]


def _una_fila(tabla: pd.DataFrame, **filtro: Any) -> pd.Series:  # type: ignore[type-arg]
    mascara = pd.Series(True, index=tabla.index)
    for columna, valor in filtro.items():
        mascara &= tabla[columna] == valor
    filas = tabla[mascara]
    assert len(filas) == 1, filas
    return filas.iloc[0]


def test_cobertura_inmobiliaria(limpio: Any) -> None:
    base = base_analisis(
        limpio(
            fila(id_fuente="1", codigo_barrio="1101", comuna="11"),
            fila(id_fuente="2", codigo_barrio="1102", comuna="11"),
            fila(id_fuente="3", codigo_barrio="1401", comuna="14", operacion="venta"),
        )
    )
    tabla = cobertura_inmobiliaria(base, SEMANA)
    todas = _una_fila(tabla, fuente="santafe", operacion="todas")
    assert (todas["anuncios"], todas["barrios"], todas["comunas"]) == (3, 3, 2)
    assert todas["comuna_principal"] == "11"
    assert todas["pct_comuna_principal"] == pytest.approx(66.7)
    assert _una_fila(tabla, fuente="santafe", operacion="arriendo")["barrios"] == 2
    assert list(tabla.columns) == COLUMNAS_COBERTURA


def test_comuna_principal_empate(limpio: Any) -> None:
    base = base_analisis(
        limpio(
            fila(id_fuente="1", comuna="14"),
            fila(id_fuente="2", comuna="14"),
            fila(id_fuente="3", comuna="11"),
            fila(id_fuente="4", comuna="11"),
        )
    )
    arriendo = _una_fila(cobertura_inmobiliaria(base, SEMANA), operacion="arriendo")
    assert arriendo["comuna_principal"] == "11"
    assert arriendo["pct_comuna_principal"] == pytest.approx(50.0)


def test_cobertura_cuenta_celdas_pequenas(limpio: Any) -> None:
    base = base_analisis(limpio(fila(operacion="venta", fuente="nutibara")))
    assert _una_fila(cobertura_inmobiliaria(base, SEMANA), operacion="venta")["anuncios"] == 1


def test_cobertura_comuna_porcentajes(limpio: Any) -> None:
    base = base_analisis(
        limpio(
            fila(id_fuente="1", comuna="11"),
            fila(id_fuente="2", comuna="14", nombre_comuna="EL POBLADO"),
            fila(id_fuente="3", comuna="14", nombre_comuna="EL POBLADO"),
            fila(id_fuente="4", comuna=None),
        )
    )
    tabla = cobertura_comuna(base, SEMANA)
    arriendo = tabla[tabla["operacion"] == "arriendo"]
    assert arriendo["pct_de_la_fuente"].sum() == pytest.approx(100.0)
    poblado = _una_fila(arriendo, comuna="14")
    assert (poblado["anuncios"], poblado["nombre_comuna"]) == (2, "EL POBLADO")
    assert list(tabla.columns) == COLUMNAS_COBERTURA_COMUNA


def _con_precio_m2(*precios_m2: float, **cambios: Any) -> list[dict[str, Any]]:
    fuente = cambios.get("fuente", "santafe")
    barrio = cambios.get("codigo_barrio", "1101")
    return [
        fila(
            id_fuente=f"{fuente}-{barrio}-{i}",
            precio=int(p * 100),
            area_m2=100.0,
            precio_m2=p,
            **cambios,
        )
        for i, p in enumerate(precios_m2)
    ]


def test_indice_relativo(limpio: Any) -> None:
    base = base_analisis(limpio(*_con_precio_m2(40_000, 40_000, 40_000, 40_000, 60_000)))
    indice = indice_relativo(base)
    assert sorted(indice.round(2)) == [1.0, 1.0, 1.0, 1.0, 1.5]
    assert indice.index.equals(base.index)


def test_indice_relativo_grupo_pequeno(limpio: Any) -> None:
    base = base_analisis(limpio(*_con_precio_m2(40_000, 40_000, 40_000, 60_000)))
    assert indice_relativo(base).isna().all()


def test_economia_minimo_y_vivienda(limpio: Any) -> None:
    base = base_analisis(
        limpio(
            *_con_precio_m2(40_000, 40_000, 40_000, 40_000, 60_000),
            *_con_precio_m2(40_000, 40_000, 40_000, 40_000, fuente="nutibara", operacion="venta"),
            *_con_precio_m2(*[30_000.0] * 5, fuente="alnago", tipo_normalizado="local"),
        )
    )
    tabla = economia_inmobiliaria(base, SEMANA)
    assert set(tabla["fuente"]) == {"santafe"}
    vivienda = _una_fila(tabla, tipo="vivienda")
    assert vivienda["anuncios"] == 5
    assert vivienda["precio_m2_mediana"] == 40_000
    assert vivienda["anuncios_indice"] == 5
    assert vivienda["indice_relativo_mediana"] == pytest.approx(1.0)
    assert list(tabla.columns) == COLUMNAS_ECONOMIA


def test_economia_indice_con_pocos_es_nulo(limpio: Any) -> None:
    # santafe tiene 5 anuncios, pero en dos barrios con menos de 5 cada uno: sin índice.
    base = base_analisis(
        limpio(
            *_con_precio_m2(40_000, 40_000, 40_000),
            *_con_precio_m2(50_000, 50_000, codigo_barrio="1102"),
        )
    )
    vivienda = _una_fila(economia_inmobiliaria(base, SEMANA), tipo="vivienda")
    assert vivienda["anuncios"] == 5
    assert vivienda["anuncios_indice"] == 0
    assert pd.isna(vivienda["indice_relativo_mediana"])


def test_economia_sin_operacion(limpio: Any) -> None:
    base = base_analisis(limpio(*_con_precio_m2(*[40_000.0] * 5, fuente="puertabierta")))
    tabla = economia_inmobiliaria(base, SEMANA)
    assert set(tabla["operacion"]) == {"arriendo"}
    assert (tabla["anuncios"] > 0).all()


def _con_estrato(estratos: list[int | None], **cambios: Any) -> list[dict[str, Any]]:
    fuente = cambios.pop("fuente", "santafe")
    barrio = cambios.get("codigo_barrio", "1101")
    return [
        fila(id_fuente=f"{fuente}-{barrio}-{i}", fuente=fuente, estrato=e, **cambios)
        for i, e in enumerate(estratos)
    ]


def test_estrato_inferido_consenso(limpio: Any) -> None:
    base = base_analisis(
        limpio(
            *_con_estrato([3, 3, 3, 3, 3, 4]),
            *_con_estrato([3, 3, 3, 4, 4, 4], codigo_barrio="1102", fuente="nutibara"),
        )
    )
    inferido = estrato_inferido(base)
    assert inferido.to_dict() == {"1101": 3}
    assert str(inferido.dtype) == "Int64"


def test_estrato_inferido_pocos(limpio: Any) -> None:
    assert estrato_inferido(base_analisis(limpio(*_con_estrato([3, 3, 3, 3])))).empty


def test_estratos_declarados_e_inferidos(limpio: Any) -> None:
    base = base_analisis(
        limpio(
            *_con_estrato([4, 4, 4, 4, 4]),
            *_con_estrato([None], fuente="alnago"),
            *_con_estrato([None], fuente="puertabierta", codigo_barrio="1102"),
        )
    )
    tabla = estratos_inmobiliaria(base, SEMANA)
    alnago = _una_fila(tabla, fuente="alnago")
    assert (alnago["estrato"], alnago["declarados"], alnago["inferidos"]) == (4, 0, 1)
    assert _una_fila(tabla, fuente="santafe")["declarados"] == 5
    assert "puertabierta" not in set(tabla["fuente"])  # su barrio no tiene consenso
    assert list(tabla.columns) == COLUMNAS_ESTRATOS


@pytest.mark.parametrize(
    ("funcion", "columnas"),
    [
        (cobertura_inmobiliaria, COLUMNAS_COBERTURA),
        (cobertura_comuna, COLUMNAS_COBERTURA_COMUNA),
        (economia_inmobiliaria, COLUMNAS_ECONOMIA),
        (estratos_inmobiliaria, COLUMNAS_ESTRATOS),
    ],
)
def test_tablas_inmobiliaria_vacias(limpio: Any, funcion: Any, columnas: list[str]) -> None:
    tabla = funcion(base_analisis(limpio()), SEMANA)
    assert tabla.empty
    assert list(tabla.columns) == columnas
    assert str(tabla[columnas[4]].dtype) in {"Int64", "string"}
    assert str(tabla["fuente"].dtype) == "string"


# ------------------------------------------------------------- Compartidos

COLUMNAS_COMPARTIDOS_FUENTES = [
    "semana",
    "fuente_a",
    "fuente_b",
    "nivel",
    "parejas",
    "diferencia_precio_mediana_pct",
    "pct_a_mas_barata",
    "pct_mismo_precio",
]
COLUMNAS_GRUPOS_COMPARTIDOS = [
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


def _parejas(*filas: tuple[str, str, str, int, int]) -> pd.DataFrame:
    """Parejas mínimas: ``(fuente_a, fuente_b, confianza, precio_a, precio_b)``."""
    datos = pd.DataFrame(
        filas, columns=["fuente_a", "fuente_b", "confianza", "precio_a", "precio_b"]
    )
    mayor = datos[["precio_a", "precio_b"]].max(axis=1)
    menor = datos[["precio_a", "precio_b"]].min(axis=1)
    return datos.assign(
        diferencia_precio_pct=((mayor / menor - 1) * 100).astype("float64"),
        precio_a=datos["precio_a"].astype("Int64"),
        precio_b=datos["precio_b"].astype("Int64"),
    ).astype({"fuente_a": "string", "fuente_b": "string", "confianza": "string"})


def test_compartidos_fuentes_niveles_acumulados() -> None:
    tabla = compartidos_fuentes(
        _parejas(("alnago", "santafe", "alta", 100, 100), ("alnago", "santafe", "baja", 100, 120)),
        SEMANA,
    )
    assert dict(zip(tabla["nivel"], tabla["parejas"], strict=True)) == {
        "alta": 1,
        "media": 1,
        "baja": 2,
    }
    assert list(tabla["nivel"]) == ["alta", "media", "baja"]
    assert _una_fila(tabla, nivel="baja")["diferencia_precio_mediana_pct"] == pytest.approx(10.0)
    assert list(tabla.columns) == COLUMNAS_COMPARTIDOS_FUENTES


def test_pct_a_mas_barata_y_mismo_precio() -> None:
    tabla = compartidos_fuentes(
        _parejas(
            ("alnago", "santafe", "alta", 1, 2),
            ("alnago", "santafe", "alta", 2, 1),
            ("alnago", "santafe", "alta", 3, 3),
        ),
        SEMANA,
    )
    alta = _una_fila(tabla, nivel="alta")
    assert alta["pct_a_mas_barata"] == pytest.approx(33.3)
    assert alta["pct_mismo_precio"] == pytest.approx(33.3)


def _compartidos(limpio: Any) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Base y grupos reales: el mismo apartamento en tres fuentes y una pareja en otra torre."""
    base = base_analisis(
        limpio(
            fila(fuente="santafe", id_fuente="S1", precio=2_000_000, area_m2=80.4),
            fila(fuente="nutibara", id_fuente="N1", precio=2_100_000, area_m2=80.4),
            fila(fuente="alnago", id_fuente="A1", precio=1_900_000, estrato=None),
            fila(
                fuente="uribienes",
                id_fuente="U1",
                operacion="venta",
                codigo_barrio=None,
                barrio_normalizado=None,
            ),
            fila(
                fuente="villacruz",
                id_fuente="V1",
                operacion="venta",
                codigo_barrio=None,
                barrio_normalizado=None,
            ),
        )
    )
    return base, agrupar(emparejar(base))


def test_grupos_compartidos_anonimos(limpio: Any) -> None:
    base, grupos = _compartidos(limpio)
    tabla = grupos_compartidos(grupos, base, SEMANA)
    assert list(tabla.columns) == COLUMNAS_GRUPOS_COMPARTIDOS
    for privada in ("id_fuente", "url", "latitud", "longitud"):
        assert privada not in tabla.columns
    alta = tabla[tabla["nivel"] == "alta"]
    assert sorted(set(alta["grupo"])) == [1, 2]
    primero = alta[alta["grupo"] == 1]
    assert sorted(primero["fuente"]) == ["alnago", "nutibara", "santafe"]
    assert set(primero["barrio"]) == {"Laureles"}
    assert set(primero["area_m2"]) == {80}
    venta = alta[alta["operacion"] == "venta"]
    assert set(venta["barrio"]) == {"LAURELES ESTADIO"}  # sin barrio: el nombre de la comuna


def test_grupos_compartidos_numeracion_estable(limpio: Any) -> None:
    base, grupos = _compartidos(limpio)
    pd.testing.assert_frame_equal(
        grupos_compartidos(grupos, base, SEMANA),
        grupos_compartidos(grupos.iloc[::-1], base.iloc[::-1], SEMANA),
    )


def test_compartidos_vacios(limpio: Any) -> None:
    base = base_analisis(limpio())
    parejas = emparejar(base)
    fuentes = compartidos_fuentes(parejas, SEMANA)
    grupos = grupos_compartidos(agrupar(parejas), base, SEMANA)
    assert fuentes.empty and grupos.empty
    assert list(fuentes.columns) == COLUMNAS_COMPARTIDOS_FUENTES
    assert list(grupos.columns) == COLUMNAS_GRUPOS_COMPARTIDOS
    assert str(fuentes["parejas"].dtype) == "Int64"
    assert str(grupos["grupo"].dtype) == "Int64"
    assert str(grupos["fuente"].dtype) == "string"


def test_niveles_coinciden_con_confianza() -> None:
    assert [c.value for c in Confianza] == list(NIVELES)


# ------------------------------------------------------- Revisión final del plan 6


def test_minimo_cuenta_precios_no_filas(limpio: Any) -> None:
    # 5 apartamentos, uno sin precio por m²: el precio total se publica (5), el m² no (4).
    filas = _apartamentos(5)
    filas[0]["precio_m2"] = None
    barrio = _zona(precios_zona(base_analisis(limpio(*filas)), SEMANA), "barrio", "1101")
    assert barrio["anuncios"] == 5
    assert barrio["precio_mediana"] == 3_000_000
    assert pd.isna(barrio["precio_m2_mediana"])
    assert pd.isna(barrio["precio_m2_p25"])
    assert pd.isna(barrio["precio_m2_p75"])


def test_minimo_sin_ningun_precio_publicable(limpio: Any) -> None:
    filas = _apartamentos(5)
    for f in filas[:2]:
        f["precio_m2"] = None
        f["precio"] = None
    tabla = precios_zona(base_analisis(limpio(*filas)), SEMANA)
    assert (tabla["nivel"] == "barrio").sum() == 0


def test_economia_minimo_por_estadistica(limpio: Any) -> None:
    filas = _con_precio_m2(*[40_000.0] * 5)
    filas[0]["precio_m2"] = None
    vivienda = _una_fila(
        economia_inmobiliaria(base_analisis(limpio(*filas)), SEMANA), tipo="vivienda"
    )
    assert vivienda["anuncios"] == 5
    assert vivienda["precio_mediana"] == 4_000_000
    assert pd.isna(vivienda["precio_m2_mediana"])


# ------------------------------------------------------- Análisis de precios


def _m2(*valores: float | None, **cambios: Any) -> list[dict[str, Any]]:
    """Anuncios de arriendo con ese precio por m² (``None`` = sin dato) y 100 m² de área."""
    return [
        fila(
            id_fuente=f"m-{cambios.get('tipo_normalizado', 'a')}-{cambios.get('area_m2')}-{i}",
            precio=None if v is None else int(v * 100),
            precio_m2=v,
            **{"area_m2": 100.0, **cambios},
        )
        for i, v in enumerate(valores)
    ]


def _mercado_de(tabla: pd.DataFrame, analisis: str, **filtro: Any) -> pd.Series:  # type: ignore[type-arg]
    filas = tabla[tabla["analisis"] == analisis]
    for columna, valor in filtro.items():
        filas = filas[filas[columna] == valor]
    assert len(filas) == 1, (analisis, filtro, len(filas))
    return filas.iloc[0]


def test_mercado_dispersion_media_y_variacion(limpio: Any) -> None:
    tabla = mercado_precios(
        base_analisis(limpio(*_m2(10_000, 20_000, 30_000, 40_000, 50_000))), SEMANA
    )
    barrio = _mercado_de(tabla, "dispersion", codigo="1101")
    assert barrio["nombre"] == "Laureles"
    assert barrio["comuna"] == "11"
    assert barrio["anuncios"] == 5
    assert barrio["precio_m2_media"] == 30_000
    assert barrio["precio_m2_mediana"] == 30_000
    assert barrio["precio_m2_p25"] == 20_000
    assert barrio["precio_m2_p75"] == 40_000
    assert barrio["variacion_pct"] == 53  # desviación estándar 15.811 sobre media 30.000
    assert barrio["semana"] == SEMANA


def test_mercado_media_se_aleja_de_la_mediana_con_un_extremo(limpio: Any) -> None:
    tabla = mercado_precios(
        base_analisis(limpio(*_m2(10_000, 10_000, 10_000, 10_000, 60_000))), SEMANA
    )
    barrio = _mercado_de(tabla, "dispersion", codigo="1101")
    assert barrio["precio_m2_mediana"] == 10_000
    assert barrio["precio_m2_media"] == 20_000


def test_mercado_minimo_de_publicacion(limpio: Any) -> None:
    tabla = mercado_precios(base_analisis(limpio(*_m2(10_000, 20_000, 30_000, 40_000))), SEMANA)
    assert tabla.empty


def test_mercado_sin_precio_m2_no_cuenta(limpio: Any) -> None:
    filas = _m2(10_000, 20_000, 30_000, 40_000, 50_000)
    filas[0]["precio_m2"] = None
    assert mercado_precios(base_analisis(limpio(*filas)), SEMANA).empty


def test_mercado_venta_y_arriendo_separados(limpio: Any) -> None:
    filas = [
        *_m2(10_000, 20_000, 30_000, 40_000, 50_000),
        *_m2(1_000_000, 2_000_000, 3_000_000, 4_000_000, 5_000_000, operacion="venta"),
    ]
    tabla = mercado_precios(base_analisis(limpio(*filas)), SEMANA)
    assert _mercado_de(tabla, "dispersion", operacion="arriendo")["precio_m2_mediana"] == 30_000
    assert _mercado_de(tabla, "dispersion", operacion="venta")["precio_m2_mediana"] == 3_000_000


def test_mercado_tipos_comparados(limpio: Any) -> None:
    filas = [
        *_m2(10_000, 20_000, 30_000, 40_000, 50_000),
        *_m2(1, 2, 3, 4, 5, tipo_normalizado="local"),
        *_m2(1, 2, 3, 4, 5, tipo_normalizado="apartaestudio"),
        *_m2(1, 2, 3, 4, 5, tipo_normalizado="bodega"),
    ]
    tabla = mercado_precios(base_analisis(limpio(*filas)), SEMANA)
    tipos = tabla[tabla["analisis"] == "tipo"]
    assert sorted(tipos["categoria"]) == ["apartamento", "local"]
    local = _mercado_de(tabla, "tipo", categoria="local")
    assert local["codigo"] == "11"
    assert local["nombre"] == "LAURELES ESTADIO"
    assert local["precio_m2_mediana"] == 3
    # la dispersión por barrio es solo de vivienda: el local no entra
    assert _mercado_de(tabla, "dispersion", codigo="1101")["anuncios"] == 10


@pytest.mark.parametrize(
    ("area", "rango"),
    [
        (39.9, "Menos de 40"),
        (40.0, "40 a 70"),
        (70.0, "70 a 100"),
        (149.9, "100 a 150"),
        (150.0, "Más de 150"),
    ],
)
def test_mercado_rangos_de_area(limpio: Any, area: float, rango: str) -> None:
    tabla = mercado_precios(
        base_analisis(limpio(*_m2(10_000, 20_000, 30_000, 40_000, 50_000, area_m2=area))), SEMANA
    )
    fila_area = _mercado_de(tabla, "area")
    assert fila_area["categoria"] == rango
    assert fila_area["codigo"] == "ciudad"
    assert pd.isna(fila_area["comuna"])


def test_mercado_estrato_solo_declarado(limpio: Any) -> None:
    con = _m2(10_000, 20_000, 30_000, 40_000, 50_000, estrato=5)
    sin = _m2(1, 2, 3, 4, 5, estrato=None, area_m2=50.0)
    tabla = mercado_precios(base_analisis(limpio(*con, *sin)), SEMANA)
    estratos = tabla[tabla["analisis"] == "estrato"]
    assert list(estratos["categoria"]) == ["5"]
    assert estratos.iloc[0]["precio_m2_mediana"] == 30_000


def test_mercado_atipicos_fuera(limpio: Any) -> None:
    filas = _m2(10_000, 20_000, 30_000, 40_000, 50_000)
    filas[0]["es_atipico"] = True
    assert mercado_precios(base_analisis(limpio(*filas)), SEMANA).empty


def test_mercado_vacia(limpio: Any) -> None:
    tabla = mercado_precios(base_analisis(limpio()), SEMANA)
    assert tabla.empty
    assert list(tabla.columns) == COLUMNAS_MERCADO
    assert str(tabla["anuncios"].dtype) == "Int64"
    assert str(tabla["variacion_pct"].dtype) == "Int64"
    assert str(tabla["categoria"].dtype) == "string"


def test_mercado_tipos_con_datos(limpio: Any) -> None:
    tabla = mercado_precios(
        base_analisis(limpio(*_m2(10_000, 20_000, 30_000, 40_000, 50_000))), SEMANA
    )
    assert list(tabla.columns) == COLUMNAS_MERCADO
    assert str(tabla["precio_m2_media"].dtype) == "Int64"
    assert str(tabla["codigo"].dtype) == "string"


# ----------------------------------------------------------------------- Oferta


def _anuncios(n: int, prefijo: str, **cambios: Any) -> list[dict[str, Any]]:
    return [fila(id_fuente=f"{prefijo}-{i}", **cambios) for i in range(n)]


def _oferta_de(tabla: pd.DataFrame, nivel: str, codigo: str, tipo: str, operacion: str) -> int:
    filas = tabla[
        (tabla["nivel"] == nivel)
        & (tabla["codigo"] == codigo)
        & (tabla["tipo"] == tipo)
        & (tabla["operacion"] == operacion)
    ]
    assert len(filas) == 1, (nivel, codigo, tipo, operacion, len(filas))
    return int(filas["anuncios"].iloc[0])


def test_oferta_zona_cuenta_por_nivel_y_tipo(limpio: Any) -> None:
    filas = [
        *_anuncios(3, "apto"),
        *_anuncios(2, "local", tipo_normalizado="local"),
        *_anuncios(1, "sin-barrio", codigo_barrio=None, barrio_normalizado=None),
        *_anuncios(1, "sin-comuna", codigo_barrio=None, comuna=None, nombre_comuna=None),
    ]
    tabla = oferta_zona(base_analisis(limpio(*filas)), SEMANA)

    assert _oferta_de(tabla, "ciudad", "ciudad", "todos", "arriendo") == 7
    assert _oferta_de(tabla, "ciudad", "ciudad", "vivienda", "arriendo") == 5
    assert _oferta_de(tabla, "comuna", "11", "todos", "arriendo") == 6  # sin el anuncio sin comuna
    assert (
        _oferta_de(tabla, "barrio", "1101", "todos", "arriendo") == 5
    )  # sin el anuncio sin barrio
    assert _oferta_de(tabla, "barrio", "1101", "apartamento", "arriendo") == 3
    assert _oferta_de(tabla, "barrio", "1101", "local", "arriendo") == 2
    assert set(tabla["semana"]) == {SEMANA}


def test_oferta_zona_publica_celdas_pequenas(limpio: Any) -> None:
    tabla = oferta_zona(base_analisis(limpio(*_anuncios(1, "solo"))), SEMANA)
    assert _oferta_de(tabla, "barrio", "1101", "apartamento", "arriendo") == 1


def test_oferta_zona_venta_y_arriendo_separados(limpio: Any) -> None:
    filas = [*_anuncios(2, "a"), *_anuncios(3, "v", operacion="venta")]
    tabla = oferta_zona(base_analisis(limpio(*filas)), SEMANA)
    assert _oferta_de(tabla, "ciudad", "ciudad", "todos", "arriendo") == 2
    assert _oferta_de(tabla, "ciudad", "ciudad", "todos", "venta") == 3


def test_oferta_zona_sin_atipicos_ni_otras_ciudades(limpio: Any) -> None:
    filas = [
        *_anuncios(2, "ok"),
        *_anuncios(1, "atipico", es_atipico=True),
        *_anuncios(1, "afuera", es_medellin=False),
    ]
    tabla = oferta_zona(base_analisis(limpio(*filas)), SEMANA)
    assert _oferta_de(tabla, "ciudad", "ciudad", "todos", "arriendo") == 2


def test_oferta_zona_vacia(limpio: Any) -> None:
    tabla = oferta_zona(base_analisis(limpio()), SEMANA)
    assert tabla.empty
    assert list(tabla.columns) == [
        "semana",
        "nivel",
        "codigo",
        "nombre",
        "comuna",
        "operacion",
        "tipo",
        "anuncios",
    ]
    assert str(tabla["anuncios"].dtype) == "Int64"


def _cuenta(tabla: pd.DataFrame, **filtro: Any) -> int:
    filas = tabla
    for columna, valor in filtro.items():
        filas = filas[filas[columna] == valor]
    return int(filas["anuncios"].sum())


def test_distribucion_por_precio_y_alcobas(limpio: Any) -> None:
    filas = [
        fila(id_fuente="a", precio=900_000, habitaciones=1),
        fila(id_fuente="b", precio=1_000_000, habitaciones=2),  # el límite va al rango de arriba
        fila(id_fuente="c", precio=9_000_000, habitaciones=7),
        fila(id_fuente="d", precio=2_500_000, habitaciones=None),
        fila(id_fuente="e", precio=2_500_000, habitaciones=0),
        fila(id_fuente="v", precio=450_000_000, habitaciones=3, operacion="venta"),
    ]
    tabla = distribucion_oferta(base_analisis(limpio(*filas)), SEMANA)

    arriendo = tabla[(tabla["operacion"] == "arriendo") & (tabla["tipo"] == "vivienda")]
    assert _cuenta(arriendo, rango_precio="Menos de $1 M") == 1
    assert _cuenta(arriendo, rango_precio="$1 a 2 M") == 1
    assert _cuenta(arriendo, rango_precio="$2 a 3 M") == 2
    assert _cuenta(arriendo, rango_precio="Más de $8 M") == 1
    assert _cuenta(arriendo, alcobas="5 o más") == 1
    assert _cuenta(arriendo, alcobas="Sin dato") == 1  # un nulo no es «5 o más»
    assert _cuenta(arriendo, alcobas="0") == 1
    assert arriendo["anuncios"].sum() == 5
    assert _cuenta(tabla, operacion="venta", tipo="vivienda", rango_precio="$400 a 600 M") == 1
    assert _cuenta(tabla, operacion="venta", tipo="vivienda", alcobas="3") == 1


def test_distribucion_solo_vivienda_con_precio(limpio: Any) -> None:
    filas = [
        fila(id_fuente="a", precio=2_000_000),
        fila(id_fuente="b", precio=None),
        fila(id_fuente="c", precio=2_000_000, tipo_normalizado="local"),
    ]
    tabla = distribucion_oferta(base_analisis(limpio(*filas)), SEMANA)
    assert set(tabla["tipo"]) == {"apartamento", "vivienda"}
    assert _cuenta(tabla, tipo="vivienda") == 1


def test_distribucion_vacia(limpio: Any) -> None:
    tabla = distribucion_oferta(base_analisis(limpio()), SEMANA)
    assert tabla.empty
    assert list(tabla.columns) == [
        "semana",
        "operacion",
        "tipo",
        "rango_precio",
        "alcobas",
        "anuncios",
    ]
