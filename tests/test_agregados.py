from typing import Any

import pandas as pd
import pytest

from conftest import fila
from observatorio_inmobiliario.agregados import (
    anuncios_unicos,
    base_analisis,
    con_vivienda,
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
