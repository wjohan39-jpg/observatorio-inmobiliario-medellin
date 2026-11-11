import math

import pytest

from observatorio_inmobiliario.parseo import (
    ValorCrudo,
    parsear_coordenada,
    parsear_decimal,
    parsear_entero,
    parsear_estrato,
    parsear_precio,
)


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        # Formato colombiano: punto para miles, coma para decimales
        ("$ 2.500.000", 2_500_000),
        ("$1.200.000,50", 1_200_000),
        ("COP 850.000", 850_000),
        # Formato numérico de APIs
        (2500000, 2_500_000),
        (2500000.0, 2_500_000),
        ("2500000", 2_500_000),
        ("2500000.00", 2_500_000),
        # Formato estadounidense
        ("2,500,000", 2_500_000),
        ("1,200,000.50", 1_200_000),
        # Sin precio válido
        ("Consultar", None),
        ("", None),
        (None, None),
        (0, None),
        ("$ 0", None),
        (-5, None),
        (math.nan, None),
        (True, None),
    ],
)
def test_parsear_precio(entrada: ValorCrudo, esperado: int | None) -> None:
    assert parsear_precio(entrada) == esperado


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("3 habitaciones", 3),
        (2, 2),
        (0, 0),  # 0 habitaciones = apartaestudio, es válido
        ("2.0", 2),
        (3.0, 3),
        ("", None),
        (None, None),
        ("N/A", None),
        ("1.2.3", None),  # formato numérico imposible
        (math.nan, None),
        (False, None),
    ],
)
def test_parsear_entero(entrada: ValorCrudo, esperado: int | None) -> None:
    assert parsear_entero(entrada) == esperado


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("85,5 m²", 85.5),
        ("120 m2", 120.0),
        (64, 64.0),
        (72.5, 72.5),
        ("1.250 m²", 1250.0),
        ("64.5", 64.5),
        ("", None),
        (None, None),
        ("0", None),
        (-10, None),
        (math.nan, None),
    ],
)
def test_parsear_decimal(entrada: ValorCrudo, esperado: float | None) -> None:
    resultado = parsear_decimal(entrada)
    if esperado is None:
        assert resultado is None
    else:
        assert resultado == pytest.approx(esperado)


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        (6.2442, 6.2442),
        (-75.5812, -75.5812),
        ("-75.170916308256", -75.170916308256),
        (" 6.24 ", 6.24),
        (0, None),
        ("0", None),
        ("", None),
        ("sin dato", None),
        (None, None),
        (True, None),
        (float("nan"), None),
        (181, None),
    ],
)
def test_parsear_coordenada(valor: ValorCrudo, esperado: float | None) -> None:
    assert parsear_coordenada(valor) == esperado


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [(3, 3), ("5", 5), ("Estrato 4", 4), (0, None), (7, None), (None, None), ("", None)],
)
def test_parsear_estrato(valor: ValorCrudo, esperado: int | None) -> None:
    assert parsear_estrato(valor) == esperado
