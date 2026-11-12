from datetime import date
from typing import Any

import pandas as pd
import pytest

from conftest import fila
from observatorio_inmobiliario.evolucion import (
    con_semana,
    evolucion_precios,
    rotacion_inmobiliaria,
)

S45, S46, S47, S48 = date(2026, 11, 3), date(2026, 11, 10), date(2026, 11, 17), date(2026, 11, 24)

COLUMNAS_EVOLUCION = ["semana", "operacion", "tipo", "anuncios", "precio_m2_mediana"]
COLUMNAS_ROTACION = [
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


def _en(fecha: date, *ids: str, **cambios: Any) -> list[dict[str, Any]]:
    """Un anuncio por id en la semana de ``fecha``."""
    return [fila(id_fuente=i, fecha_observacion=fecha, **cambios) for i in ids]


def _semana(tabla: pd.DataFrame, semana: str) -> pd.Series:  # type: ignore[type-arg]
    filas = tabla[tabla["semana"] == semana]
    assert len(filas) == 1, filas
    return filas.iloc[0]


def test_con_semana(limpio: Any) -> None:
    tabla = con_semana(limpio(*_en(date(2026, 11, 11), "A")))
    assert list(tabla["semana"]) == ["2026-S46"]
    assert str(tabla["semana"].dtype) == "string"


def test_evolucion_por_semana(limpio: Any) -> None:
    precios = {"precio_m2": 30_000.0}
    tabla = evolucion_precios(
        limpio(
            *_en(S45, "1", "2", "3", "4", "5", **precios),
            *_en(S46, "1", "2", "3", "4", "5", **precios),
        )
    )
    apartamentos = tabla[tabla["tipo"] == "apartamento"]
    assert list(apartamentos["semana"]) == ["2026-S45", "2026-S46"]
    assert set(apartamentos["anuncios"]) == {5}
    assert set(apartamentos["precio_m2_mediana"]) == {30_000}
    assert list(tabla.columns) == COLUMNAS_EVOLUCION


def test_evolucion_minimo(limpio: Any) -> None:
    assert evolucion_precios(limpio(*_en(S46, "1", "2", "3", "4"))).empty


def test_una_sola_semana(limpio: Any) -> None:
    rotacion = rotacion_inmobiliaria(limpio(*_en(S46, "A", "B")))
    unica = _semana(rotacion, "2026-S46")
    assert unica["anuncios"] == 2
    assert unica["retirados"] == 0
    assert pd.isna(unica["tasa_retiro_pct"])
    assert pd.isna(unica["nuevos"])
    assert unica["comparables"] == 0
    assert list(rotacion.columns) == COLUMNAS_ROTACION


def test_retirados_y_tasa(limpio: Any) -> None:
    rotacion = rotacion_inmobiliaria(limpio(*_en(S45, "A", "B", "C", "D"), *_en(S46, "A", "B")))
    s46 = _semana(rotacion, "2026-S46")
    assert (s46["anuncios"], s46["retirados"]) == (2, 2)
    assert s46["tasa_retiro_pct"] == pytest.approx(50.0)


def test_nuevos(limpio: Any) -> None:
    rotacion = rotacion_inmobiliaria(limpio(*_en(S45, "A", "B"), *_en(S46, "A", "B", "E")))
    assert _semana(rotacion, "2026-S46")["nuevos"] == 1


def test_semanas_publicado_excluye_primera_semana(limpio: Any) -> None:
    rotacion = rotacion_inmobiliaria(
        limpio(
            *_en(S45, "A", "B"),
            *_en(S46, "A", "E"),
            *_en(S47, "A", "E"),
            *_en(S48, "A"),
        )
    )
    # B ya estaba en la primera semana del histórico: no se sabe cuándo empezó.
    assert pd.isna(_semana(rotacion, "2026-S46")["semanas_publicado_mediana"])
    # E estuvo en S46 y S47.
    assert _semana(rotacion, "2026-S48")["semanas_publicado_mediana"] == 2


def test_anuncio_que_vuelve(limpio: Any) -> None:
    rotacion = rotacion_inmobiliaria(
        limpio(*_en(S45, "A", "B"), *_en(S46, "B"), *_en(S47, "A", "B"))
    )
    assert _semana(rotacion, "2026-S46")["retirados"] == 1
    assert _semana(rotacion, "2026-S47")["nuevos"] == 1


def test_cambio_de_precio(limpio: Any) -> None:
    rotacion = rotacion_inmobiliaria(
        limpio(
            fila(id_fuente="A", fecha_observacion=S45, precio=2_000_000),
            fila(id_fuente="B", fecha_observacion=S45, precio=3_000_000),
            fila(id_fuente="A", fecha_observacion=S46, precio=2_100_000),
            fila(id_fuente="B", fecha_observacion=S46, precio=3_000_000),
        )
    )
    s46 = _semana(rotacion, "2026-S46")
    assert (s46["comparables"], s46["con_cambio_precio"]) == (2, 1)
    assert s46["cambio_precio_mediana_pct"] == pytest.approx(5.0)


def test_semana_faltante_no_es_retiro(limpio: Any) -> None:
    rotacion = rotacion_inmobiliaria(limpio(*_en(S45, "A", "B"), *_en(S47, "A")))
    assert list(rotacion["semana"]) == ["2026-S45", "2026-S47"]
    s47 = _semana(rotacion, "2026-S47")
    assert s47["retirados"] == 1
    assert s47["tasa_retiro_pct"] == pytest.approx(50.0)


def test_rotacion_cuenta_atipicos_y_separa_fuentes(limpio: Any) -> None:
    rotacion = rotacion_inmobiliaria(
        limpio(
            *_en(S46, "A", es_atipico=True, motivo_atipico="precio_fuera_de_rango"),
            *_en(S46, "N1", fuente="nutibara"),
            *_en(S46, "X", es_medellin=False),
        )
    )
    assert dict(zip(rotacion["fuente"], rotacion["anuncios"], strict=True)) == {
        "nutibara": 1,
        "santafe": 1,
    }


def test_fuente_sin_datos_no_tiene_fila(limpio: Any) -> None:
    # Una semana sin datos de una fuente es un scraping que no corrió: no hay fila de rotación.
    rotacion = rotacion_inmobiliaria(
        limpio(*_en(S45, "A"), *_en(S45, "N1", fuente="nutibara"), *_en(S46, "A"))
    )
    nutibara = rotacion[rotacion["fuente"] == "nutibara"]
    assert list(nutibara["semana"]) == ["2026-S45"]


def test_evolucion_vacia(limpio: Any) -> None:
    vacio = limpio()
    evolucion, rotacion = evolucion_precios(vacio), rotacion_inmobiliaria(vacio)
    assert evolucion.empty and rotacion.empty
    assert list(evolucion.columns) == COLUMNAS_EVOLUCION
    assert list(rotacion.columns) == COLUMNAS_ROTACION
    assert str(rotacion["anuncios"].dtype) == "Int64"
    assert str(rotacion["tasa_retiro_pct"].dtype) == "float64"


# ------------------------------------------------------- Revisión final del plan 6


def test_evolucion_minimo_cuenta_precios(limpio: Any) -> None:
    filas = _en(S46, "1", "2", "3", "4", "5", precio_m2=30_000.0)
    filas[0]["precio_m2"] = None
    assert evolucion_precios(limpio(*filas)).empty


def test_fuente_que_empieza_tarde(limpio: Any) -> None:
    rotacion = rotacion_inmobiliaria(
        limpio(
            *_en(S45, "A"),
            *_en(S46, "A"),
            *_en(S47, "A"),
            *_en(S46, "X", "Y", fuente="nutibara"),
            *_en(S47, "Y", fuente="nutibara"),
        )
    )
    nutibara = rotacion[rotacion["fuente"] == "nutibara"].set_index("semana")
    # Su primera semana es la primera de su histórico: no se sabe qué es nuevo.
    assert pd.isna(nutibara.loc["2026-S46", "nuevos"])
    assert pd.isna(nutibara.loc["2026-S46", "tasa_retiro_pct"])
    # X ya estaba cuando empezó a scrapearse: no se sabe cuánto llevaba publicado.
    assert nutibara.loc["2026-S47", "retirados"] == 1
    assert pd.isna(nutibara.loc["2026-S47", "semanas_publicado_mediana"])


def test_fuente_que_falla_una_semana(limpio: Any) -> None:
    rotacion = rotacion_inmobiliaria(
        limpio(
            *_en(S45, "A"),
            *_en(S46, "A"),
            *_en(S47, "A"),
            *_en(S45, "X", fuente="nutibara"),
            *_en(S47, "X", fuente="nutibara"),
        )
    )
    nutibara = rotacion[rotacion["fuente"] == "nutibara"].set_index("semana")
    # El scraping de nutibara falló en S46: se compara S47 con S45, sin retiros falsos.
    assert list(nutibara.index) == ["2026-S45", "2026-S47"]
    assert nutibara.loc["2026-S47", "retirados"] == 0
    assert nutibara.loc["2026-S47", "nuevos"] == 0
