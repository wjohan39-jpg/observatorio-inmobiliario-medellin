from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from observatorio_inmobiliario.almacenamiento import ESQUEMA_LIMPIO, leer_limpio
from observatorio_inmobiliario.emparejamiento import distancia_m, emparejar

PUNTO = {"latitud": 6.245, "longitud": -75.595}
GRADO_LAT_M = 111_195.0  # metros en 1° de latitud con R = 6.371.000 m

COLUMNAS_PAREJAS = [
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


def _fila(**cambios: Any) -> dict[str, Any]:
    """Un anuncio limpio de Medellín, válido y con coordenadas; ``cambios`` lo modifica."""
    fila: dict[str, Any] = {nombre: None for nombre in ESQUEMA_LIMPIO.names}
    fila.update(
        fuente="santafe",
        id_fuente="1",
        url="https://ejemplo.com/1",
        fecha_observacion=date(2026, 11, 12),
        operacion="arriendo",
        tipo_inmueble="Apartamento",
        precio=2_000_000,
        area_m2=80.0,
        habitaciones=3,
        banos=2,
        estrato=4,
        municipio="Medellín",
        municipio_normalizado="Medellín",
        en_valle=True,
        es_medellin=True,
        coordenadas_validas=True,
        codigo_barrio="1101",
        barrio_normalizado="Laureles",
        comuna="11",
        nombre_comuna="LAURELES ESTADIO",
        metodo_ubicacion="coordenadas",
        tipo_normalizado="apartamento",
        es_atipico=False,
        **PUNTO,
    )
    fila["precio_m2"] = None
    fila.update(cambios)
    return fila


def _sin_coordenadas(**cambios: Any) -> dict[str, Any]:
    return _fila(latitud=None, longitud=None, coordenadas_validas=False, **cambios)


def _al_norte(metros: float) -> dict[str, float]:
    return {"latitud": PUNTO["latitud"] + metros / GRADO_LAT_M, "longitud": PUNTO["longitud"]}


@pytest.fixture
def limpio(tmp_path: Path) -> Any:
    """Arma una tabla limpia con el mismo guardado y lectura del proyecto (tipos reales)."""

    def armar(*filas: dict[str, Any]) -> pd.DataFrame:
        ruta = tmp_path / "limpio" / "2026-S46.parquet"
        ruta.parent.mkdir(parents=True, exist_ok=True)
        pq.write_table(pa.Table.from_pylist(list(filas), schema=ESQUEMA_LIMPIO), ruta)
        return leer_limpio(ruta.parent)

    return armar


def _una(parejas: pd.DataFrame) -> pd.Series:  # type: ignore[type-arg]
    assert len(parejas) == 1
    return parejas.iloc[0]


# ---------------------------------------------------------------------- Distancia


def test_distancia_m() -> None:
    lat = np.array([6.245, 6.245])
    lon = np.array([-75.595, -75.595])
    resultado = distancia_m(lat, lon, lat + np.array([0.001, 0.0]), lon)
    assert resultado[0] == pytest.approx(111.2, abs=1)
    assert resultado[1] == 0


# -------------------------------------------------------------------- Confianza


def test_mismo_punto_es_alta(limpio: Any) -> None:
    pareja = _una(
        emparejar(
            limpio(
                _fila(fuente="santafe", id_fuente="S1"),
                _fila(fuente="nutibara", id_fuente="N1", area_m2=81.5),
            )
        )
    )
    assert pareja["confianza"] == "alta"
    assert pareja["fuente_a"] == "nutibara"  # el lado a es la fuente menor
    assert pareja["id_fuente_b"] == "S1"
    assert pareja["distancia_m"] == pytest.approx(0)
    assert not pareja["ambigua"]


def test_entre_100_y_300_m_es_media(limpio: Any) -> None:
    pareja = _una(
        emparejar(limpio(_fila(fuente="santafe"), _fila(fuente="nutibara", **_al_norte(200))))
    )
    assert pareja["confianza"] == "media"
    assert pareja["distancia_m"] == pytest.approx(200, abs=1)


def test_mas_de_300_m_no_es_pareja(limpio: Any) -> None:
    resultado = emparejar(
        limpio(_fila(fuente="santafe"), _fila(fuente="nutibara", **_al_norte(400)))
    )
    assert resultado.empty


def test_area_fuera_de_tolerancia(limpio: Any) -> None:
    resultado = emparejar(limpio(_fila(fuente="santafe"), _fila(fuente="nutibara", area_m2=83.0)))
    assert resultado.empty


def test_misma_fuente_no_se_empareja(limpio: Any) -> None:
    resultado = emparejar(limpio(_fila(id_fuente="1"), _fila(id_fuente="2")))
    assert resultado.empty


def test_venta_y_arriendo_no_se_emparejan(limpio: Any) -> None:
    resultado = emparejar(
        limpio(_fila(fuente="santafe"), _fila(fuente="nutibara", operacion="venta"))
    )
    assert resultado.empty


def test_habitaciones_distintas_no_se_emparejan(limpio: Any) -> None:
    resultado = emparejar(limpio(_fila(fuente="santafe"), _fila(fuente="nutibara", habitaciones=2)))
    assert resultado.empty


def test_nulo_es_compatible(limpio: Any) -> None:
    pareja = _una(emparejar(limpio(_fila(fuente="santafe"), _fila(fuente="alnago", estrato=None))))
    assert pareja["confianza"] == "alta"


def test_sin_coordenadas_mismo_barrio_completo_es_media(limpio: Any) -> None:
    pareja = _una(emparejar(limpio(_fila(fuente="santafe"), _sin_coordenadas(fuente="maxibienes"))))
    assert pareja["confianza"] == "media"
    assert pd.isna(pareja["distancia_m"])


def test_sin_coordenadas_con_nulos_es_baja(limpio: Any) -> None:
    pareja = _una(
        emparejar(
            limpio(_fila(fuente="santafe"), _sin_coordenadas(fuente="maxibienes", estrato=None))
        )
    )
    assert pareja["confianza"] == "baja"


def test_sin_coordenadas_otro_barrio_no_es_pareja(limpio: Any) -> None:
    resultado = emparejar(
        limpio(
            _fila(fuente="santafe"),
            _sin_coordenadas(fuente="maxibienes", codigo_barrio="1103"),
            _sin_coordenadas(fuente="panorama", codigo_barrio=None),
        )
    )
    assert resultado.empty


def test_sin_coordenadas_nunca_es_alta(limpio: Any) -> None:
    resultado = emparejar(
        limpio(_sin_coordenadas(fuente="panorama"), _sin_coordenadas(fuente="maxibienes"))
    )
    assert _una(resultado)["confianza"] == "media"


# -------------------------------------------------------------------- Ambigüedad


def test_gemelos_bajan_un_nivel(limpio: Any) -> None:
    parejas = emparejar(
        limpio(
            _fila(fuente="nutibara", id_fuente="N1"),
            _fila(fuente="villacruz", id_fuente="V1"),
            _fila(fuente="villacruz", id_fuente="V2"),
        )
    )
    assert len(parejas) == 2
    assert set(parejas["confianza"]) == {"media"}
    assert parejas["ambigua"].all()


def test_gemelos_baja_se_descarta(limpio: Any) -> None:
    resultado = emparejar(
        limpio(
            _fila(fuente="nutibara", id_fuente="N1"),
            _sin_coordenadas(fuente="maxibienes", id_fuente="M1", estrato=None),
            _sin_coordenadas(fuente="maxibienes", id_fuente="M2", estrato=None),
        )
    )
    assert resultado.empty


# --------------------------------------------------------------- Filas que entran


def test_atipicos_y_fuera_de_medellin_no_entran(limpio: Any) -> None:
    resultado = emparejar(
        limpio(
            _fila(fuente="santafe"),
            _fila(fuente="nutibara", es_atipico=True),
            _fila(fuente="alnago", es_medellin=False, municipio_normalizado="Envigado"),
        )
    )
    assert resultado.empty


def test_clave_incluye_operacion(limpio: Any) -> None:
    parejas = emparejar(
        limpio(
            _fila(fuente="maxibienes", id_fuente="54738", operacion="arriendo"),
            _fila(fuente="maxibienes", id_fuente="54738", operacion="venta"),
            _fila(fuente="santafe", id_fuente="S1", operacion="arriendo"),
            _fila(fuente="santafe", id_fuente="S2", operacion="venta"),
        )
    )
    assert sorted(parejas["operacion"]) == ["arriendo", "venta"]
    assert not parejas["ambigua"].any()


def test_filas_repetidas_cuentan_una_vez(limpio: Any) -> None:
    repetida = _fila(fuente="alnago", id_fuente="9037878")
    pareja = _una(emparejar(limpio(repetida, repetida, repetida, _fila(fuente="santafe"))))
    assert not pareja["ambigua"]
    assert pareja["confianza"] == "alta"


def test_area_cero_o_nula_no_falla(limpio: Any) -> None:
    resultado = emparejar(
        limpio(
            _fila(fuente="santafe", area_m2=0.0),
            _fila(fuente="nutibara", area_m2=0.0),
            _fila(fuente="alnago", area_m2=None),
        )
    )
    assert resultado.empty


def test_vacio_devuelve_columnas(limpio: Any) -> None:
    resultado = emparejar(limpio())
    assert resultado.empty
    assert list(resultado.columns) == COLUMNAS_PAREJAS


# ---------------------------------------------------------------- Determinismo


def test_orden_de_entrada_no_cambia_resultado(limpio: Any) -> None:
    tabla = limpio(
        _fila(fuente="nutibara", id_fuente="N1"),
        _fila(fuente="villacruz", id_fuente="V1"),
        _fila(fuente="villacruz", id_fuente="V2"),
        _fila(fuente="santafe", id_fuente="S1", **_al_norte(150)),
        _sin_coordenadas(fuente="maxibienes", id_fuente="M1"),
    )
    pd.testing.assert_frame_equal(emparejar(tabla), emparejar(tabla.sample(frac=1, random_state=0)))


def test_diferencia_precio_pct(limpio: Any) -> None:
    pareja = _una(
        emparejar(
            limpio(
                _fila(fuente="santafe", precio=100_000_000),
                _fila(fuente="nutibara", precio=110_000_000),
            )
        )
    )
    assert pareja["diferencia_precio_pct"] == pytest.approx(10.0)
    assert pareja["precio_a"] == 110_000_000
