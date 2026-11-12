import json
import logging
from pathlib import Path

import httpx
import pandas as pd
import pytest
import respx

from observatorio_inmobiliario.reputacion import (
    CAMPOS,
    URL_BUSQUEDA,
    URL_DETALLE,
    Reseñas,
    buscar_sedes,
    cargar_sedes,
    clave_api,
    consultar_sede,
    reconocimiento,
    reputacion,
)

CLAVE = "clave-secreta-de-prueba"


def _sedes(*filas: tuple[str, str, str]) -> pd.DataFrame:
    return pd.DataFrame(filas, columns=["fuente", "sede", "place_id"]).astype("string")


# ---------------------------------------------------------------- Consulta


@respx.mock
def test_consultar_sede_ok() -> None:
    ruta = respx.get(URL_DETALLE.format(place_id="P1")).respond(
        json={"rating": 4.6, "userRatingCount": 120}
    )
    with httpx.Client() as cliente:
        assert consultar_sede(cliente, "P1", CLAVE) == Reseñas(4.6, 120)
    peticion = ruta.calls.last.request
    assert peticion.headers["X-Goog-Api-Key"] == CLAVE
    assert peticion.headers["X-Goog-FieldMask"] == CAMPOS == "rating,userRatingCount"


@respx.mock
def test_consultar_sede_sin_resenas() -> None:
    respx.get(URL_DETALLE.format(place_id="P1")).respond(json={})
    with httpx.Client() as cliente:
        assert consultar_sede(cliente, "P1", CLAVE) == Reseñas(None, 0)


@respx.mock
@pytest.mark.parametrize("estado", [403, 404, 429, 500])
def test_consultar_sede_error(estado: int, caplog: pytest.LogCaptureFixture) -> None:
    respx.get(URL_DETALLE.format(place_id="P1")).respond(estado, json={"error": "x"})
    with caplog.at_level(logging.WARNING), httpx.Client() as cliente:
        assert consultar_sede(cliente, "P1", CLAVE) == Reseñas(None, 0)
    assert "P1" in caplog.text
    assert CLAVE not in caplog.text


@respx.mock
def test_consultar_sede_timeout(caplog: pytest.LogCaptureFixture) -> None:
    respx.get(URL_DETALLE.format(place_id="P1")).mock(side_effect=httpx.ReadTimeout("lento"))
    with caplog.at_level(logging.WARNING), httpx.Client() as cliente:
        assert consultar_sede(cliente, "P1", CLAVE) == Reseñas(None, 0)
    assert CLAVE not in caplog.text


@respx.mock
def test_consultar_sede_json_invalido() -> None:
    respx.get(URL_DETALLE.format(place_id="P1")).respond(text="no es json")
    with httpx.Client() as cliente:
        assert consultar_sede(cliente, "P1", CLAVE) == Reseñas(None, 0)


# ------------------------------------------------------------- Agregación


def test_reputacion_pondera_sedes() -> None:
    respuestas = {"P1": Reseñas(4.0, 100), "P2": Reseñas(5.0, 300)}
    tabla = reputacion(
        _sedes(("santafe", "Laureles", "P1"), ("santafe", "Poblado", "P2")),
        respuestas.__getitem__,
    )
    fila = tabla.set_index("fuente").loc["santafe"]
    assert fila["sedes"] == 2
    assert fila["resenas"] == 400
    assert fila["calificacion"] == pytest.approx(4.75)


def test_reputacion_sede_invalida() -> None:
    respuestas = {"P1": Reseñas(None, 0), "P2": Reseñas(4.2, 50), "P3": Reseñas(None, 0)}
    tabla = reputacion(
        _sedes(
            ("santafe", "Mala", "P1"),
            ("santafe", "Buena", "P2"),
            ("alnago", "Sin reseñas", "P3"),
        ),
        respuestas.__getitem__,
    ).set_index("fuente")
    assert tabla.loc["santafe", "calificacion"] == pytest.approx(4.2)
    assert tabla.loc["santafe", "resenas"] == 50
    assert tabla.loc["alnago", "resenas"] == 0
    assert pd.isna(tabla.loc["alnago", "calificacion"])


def test_reputacion_sin_sedes() -> None:
    tabla = reputacion(_sedes(), lambda _: Reseñas(None, 0))
    assert tabla.empty
    assert list(tabla.columns) == ["fuente", "sedes", "resenas", "calificacion"]


def _cobertura() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "fuente": ["a", "b", "a", "b"],
            "operacion": ["todas", "todas", "venta", "venta"],
            "anuncios": [100, 50, 60, 30],
            "barrios": [10, 20, 5, 10],
        }
    )


def test_reconocimiento_con_resenas() -> None:
    rep = pd.DataFrame(
        {"fuente": ["a", "b"], "sedes": [1, 1], "resenas": [0, 400], "calificacion": [None, 4.0]}
    )
    tabla = reconocimiento(_cobertura(), rep).set_index("fuente")
    # a: anuncios 1, barrios 0,5, reseñas 0 → 0,5; b: 0,5, 1, 1 → 0,833
    assert tabla.loc["a", "indice"] == pytest.approx(0.5)
    assert tabla.loc["b", "indice"] == pytest.approx(2.5 / 3, abs=1e-3)
    assert tabla["con_resenas"].all()


def test_reconocimiento_sin_resenas() -> None:
    tabla = reconocimiento(_cobertura(), None).set_index("fuente")
    assert tabla.loc["a", "indice"] == pytest.approx(0.75)
    assert tabla.loc["b", "indice"] == pytest.approx(0.75)
    assert not tabla["con_resenas"].any()
    assert list(tabla.reset_index().columns) == [
        "fuente",
        "anuncios",
        "barrios",
        "resenas",
        "indice",
        "con_resenas",
    ]


def test_reconocimiento_reputacion_vacia() -> None:
    vacia = reputacion(_sedes(), lambda _: Reseñas(None, 0))
    assert not reconocimiento(_cobertura(), vacia)["con_resenas"].any()


# ------------------------------------------------------- Sedes y búsqueda


def test_cargar_sedes_vacio(tmp_path: Path) -> None:
    ruta = tmp_path / "sedes.csv"
    ruta.write_text("fuente,sede,place_id\n", encoding="utf-8")
    sedes = cargar_sedes(ruta)
    assert sedes.empty
    assert list(sedes.columns) == ["fuente", "sede", "place_id"]


def test_cargar_sedes_del_repo() -> None:
    assert list(cargar_sedes().columns) == ["fuente", "sede", "place_id"]


def test_clave_api(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GOOGLE_PLACES_API_KEY", raising=False)
    assert clave_api() is None
    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", " abc ")
    assert clave_api() == "abc"
    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "")
    assert clave_api() is None


@respx.mock
def test_buscar_sedes() -> None:
    ruta = respx.post(URL_BUSQUEDA).respond(
        json={
            "places": [
                {
                    "id": "ChIJ1",
                    "displayName": {"text": "Arrendamientos Santa Fe"},
                    "formattedAddress": "Cra. 70, Medellín",
                }
            ]
        }
    )
    with httpx.Client() as cliente:
        sedes = buscar_sedes(cliente, "Santa Fe Medellín", CLAVE)
    assert sedes == [
        {"id": "ChIJ1", "nombre": "Arrendamientos Santa Fe", "direccion": "Cra. 70, Medellín"}
    ]
    peticion = ruta.calls.last.request
    assert peticion.headers["X-Goog-Api-Key"] == CLAVE
    assert "places.id" in peticion.headers["X-Goog-FieldMask"]
    cuerpo = json.loads(peticion.content)
    assert cuerpo["textQuery"] == "Santa Fe Medellín"
    assert "locationBias" in cuerpo


def test_reconocimiento_cobertura_vacia() -> None:
    from observatorio_inmobiliario.tablero.datos import tablas_vacias

    vacia = tablas_vacias()["cobertura_inmobiliaria"]  # columnas Int64, con NA
    tabla = reconocimiento(vacia, None)
    assert tabla.empty
    assert list(tabla.columns) == [
        "fuente",
        "anuncios",
        "barrios",
        "resenas",
        "indice",
        "con_resenas",
    ]
