"""Autocorrelación espacial: Moran global y local sobre cuadrículas de resultado conocido."""

from typing import Any

import numpy as np
import pytest
from shapely.geometry import box

from observatorio_inmobiliario.espacial import (
    ALTO_ALTO,
    BAJO_BAJO,
    NO_SIGNIFICATIVO,
    centroides,
    distancia_km,
    geometrias_del_catalogo,
    moran,
    sin_islas,
    vecinos_por_contiguidad,
)

LADO = 5


def cuadricula(lado: int = LADO) -> dict[str, Any]:
    """Un GeoJSON de ``lado`` × ``lado`` barrios cuadrados; el código es ``"fila-columna"``."""
    return {
        "features": [
            {
                "properties": {"codigo": f"{i}-{j}"},
                "geometry": box(j, i, j + 1, i + 1).__geo_interface__,
            }
            for i in range(lado)
            for j in range(lado)
        ]
    }


def _vecinos(lado: int = LADO) -> list[list[int]]:
    _, geometrias = geometrias_del_catalogo(cuadricula(lado))
    return vecinos_por_contiguidad(geometrias)


def test_vecindad_reina() -> None:
    vecinos = _vecinos()
    assert len(vecinos[0]) == 3  # esquina: lado, lado y diagonal
    assert len(vecinos[1]) == 5  # borde
    assert len(vecinos[LADO * 2 + 2]) == 8  # centro: toca a sus ocho alrededores
    assert all(i not in lista for i, lista in enumerate(vecinos))
    assert all(i in vecinos[j] for i, lista in enumerate(vecinos) for j in lista)  # simétrica


def test_vecinos_toleran_bordes_que_no_coinciden() -> None:
    geometrias = [box(0, 0, 1, 1), box(1 + 5e-6, 0, 2, 1), box(5, 5, 6, 6)]
    assert vecinos_por_contiguidad(geometrias) == [[1], [0], []]


def test_gradiente_tiene_autocorrelacion_positiva() -> None:
    valores = np.array([float(i + j) for i in range(LADO) for j in range(LADO)])
    resultado = moran(valores, _vecinos())
    assert resultado.i > 0.5
    assert resultado.p < 0.05
    assert resultado.cluster[LADO * LADO - 1] == ALTO_ALTO  # la esquina más alta
    assert resultado.cluster[0] == BAJO_BAJO  # la más baja


def test_franjas_alternas_tienen_autocorrelacion_negativa() -> None:
    # Con vecindad «reina» un tablero de ajedrez no sirve: las diagonales son del mismo color.
    valores = np.array([float(i % 2) for i in range(LADO) for _ in range(LADO)])
    resultado = moran(valores, _vecinos())
    assert resultado.i < -0.3
    assert resultado.p < 0.05


def test_azar_no_es_significativo() -> None:
    azar = np.random.default_rng(1)
    valores = azar.normal(size=LADO * LADO)
    resultado = moran(valores, _vecinos())
    assert abs(resultado.i) < 0.4
    assert resultado.p > 0.05
    assert resultado.cluster.count(NO_SIGNIFICATIVO) >= len(resultado.cluster) - 3


def test_valores_constantes() -> None:
    resultado = moran(np.full(LADO * LADO, 7.0), _vecinos())
    assert resultado.i == 0.0
    assert resultado.p == 1.0
    assert set(resultado.cluster) == {NO_SIGNIFICATIVO}


def test_resultado_reproducible() -> None:
    valores = np.array([float(i * j) for i in range(LADO) for j in range(LADO)])
    primero = moran(valores, _vecinos())
    segundo = moran(valores, _vecinos())
    assert primero.p == segundo.p
    assert primero.cluster == segundo.cluster
    assert np.allclose(primero.p_local, segundo.p_local)


def test_rezago_es_el_promedio_de_los_vecinos() -> None:
    valores = np.arange(float(LADO * LADO))
    resultado = moran(valores, _vecinos())
    centro = LADO * 2 + 2
    vecinos = _vecinos()[centro]
    esperado = valores[vecinos].mean() - valores.mean()
    assert resultado.rezago[centro] == pytest.approx(esperado)


def test_sin_islas_quita_las_zonas_sin_vecinos() -> None:
    vecinos = [[1], [0, 3], [], [1]]
    conservadas, nuevos = sin_islas(vecinos, [0, 1, 2, 3])
    assert conservadas == [0, 1, 3]
    assert nuevos == [[1], [0, 2], [1]]
    # solo cuentan los vecinos que también tienen datos
    conservadas, nuevos = sin_islas(vecinos, [0, 1])
    assert conservadas == [0, 1]
    assert nuevos == [[1], [0]]


def test_distancia_km() -> None:
    assert distancia_km(6.25, -75.57, 6.25, -75.57) == 0.0
    bogota = distancia_km(6.2442, -75.5812, 4.7110, -74.0721)
    assert 235 < bogota < 255
    assert distancia_km(6.0, -75.0, 6.1, -75.0) == pytest.approx(11.12, abs=0.05)


def test_centroides() -> None:
    puntos = centroides(cuadricula(2))
    assert puntos["0-0"] == (0.5, 0.5)  # (latitud, longitud)
    assert puntos["1-1"] == (1.5, 1.5)
