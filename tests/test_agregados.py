from typing import Any

import pandas as pd
import pytest

from conftest import fila
from observatorio_inmobiliario.agregados import (
    anuncios_unicos,
    base_analisis,
    cobertura_comuna,
    cobertura_inmobiliaria,
    con_vivienda,
    economia_inmobiliaria,
    estrato_inferido,
    estratos_inmobiliaria,
    indice_relativo,
    precios_zona,
)

SEMANA = "2026-S46"
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
