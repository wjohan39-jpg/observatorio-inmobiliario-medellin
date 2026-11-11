"""Conversión de valores crudos (texto o número) de los sitios web a números limpios.

Los sitios publican números en formatos distintos: ``"$ 2.500.000"`` (colombiano),
``"2,500,000"`` (estadounidense), ``"85,5 m²"`` o ``2500000.0`` desde una API.
Estas funciones los convierten a ``int`` o ``float``, o devuelven ``None`` cuando no
hay un valor válido. Nunca lanzan excepciones: un dato ilegible no debe detener
el scraping.
"""

import math
import re

type ValorCrudo = str | int | float | None
"""Lo que puede llegar desde un sitio web para un campo numérico."""

_PATRON_NUMERO = re.compile(r"\d[\d.,]*")
_MILES_CON_PUNTO = re.compile(r"^\d{1,3}(\.\d{3})+$")
_MILES_CON_COMA = re.compile(r"^\d{1,3}(,\d{3})+$")


def _a_numero(valor: ValorCrudo) -> float | None:
    """Convierte un valor crudo a ``float``, interpretando separadores de miles y decimales."""
    # bool es subclase de int en Python; un True/False nunca es un dato numérico válido.
    if valor is None or isinstance(valor, bool):
        return None
    if isinstance(valor, int | float):
        return None if math.isnan(valor) else float(valor)

    coincidencia = _PATRON_NUMERO.search(valor)
    if coincidencia is None:
        return None
    texto = coincidencia.group().rstrip(".,")

    if "." in texto and "," in texto:
        # El separador que aparece de último es el decimal: "1.200.000,50" o "1,200,000.50".
        decimal = "," if texto.rfind(",") > texto.rfind(".") else "."
        miles = "." if decimal == "," else ","
        texto = texto.replace(miles, "").replace(decimal, ".")
    elif "," in texto:
        texto = texto.replace(",", "") if _MILES_CON_COMA.match(texto) else texto.replace(",", ".")
    elif "." in texto and _MILES_CON_PUNTO.match(texto):
        texto = texto.replace(".", "")

    try:
        return float(texto)
    except ValueError:
        return None


def parsear_precio(valor: ValorCrudo) -> int | None:
    """Precio en pesos colombianos. Devuelve ``None`` si no hay precio o si es ≤ 0.

    >>> parsear_precio("$ 2.500.000")
    2500000
    >>> parsear_precio("Consultar") is None
    True
    """
    numero = _a_numero(valor)
    if numero is None or numero <= 0:
        return None
    return int(numero)


def parsear_entero(valor: ValorCrudo) -> int | None:
    """Primer número entero del valor (habitaciones, baños, estrato...). Acepta 0.

    >>> parsear_entero("3 habitaciones")
    3
    """
    numero = _a_numero(valor)
    return None if numero is None else int(numero)


def parsear_decimal(valor: ValorCrudo) -> float | None:
    """Número decimal positivo, como un área en m². Devuelve ``None`` si es ≤ 0.

    >>> parsear_decimal("85,5 m²")
    85.5
    """
    numero = _a_numero(valor)
    if numero is None or numero <= 0:
        return None
    return numero


def parsear_coordenada(valor: ValorCrudo) -> float | None:
    """Latitud o longitud en grados. Conserva el signo negativo de los textos.

    Devuelve ``None`` si no hay valor, si es ``0`` (muchas API lo usan para "sin
    ubicación") o si está fuera de rango (más de 180 grados).

    >>> parsear_coordenada("-75.5812")
    -75.5812
    >>> parsear_coordenada(0) is None
    True
    """
    if valor is None or isinstance(valor, bool):
        return None
    if isinstance(valor, str):
        # No se usa _a_numero: su patrón ignora el signo "-" y las longitudes son negativas.
        try:
            numero = float(valor.strip())
        except ValueError:
            return None
    else:
        numero = float(valor)
    if math.isnan(numero) or numero == 0 or abs(numero) > 180:
        return None
    return numero


def parsear_estrato(valor: ValorCrudo) -> int | None:
    """Estrato socioeconómico, de 1 a 6. Otro valor, como el ``0`` de "sin dato", es ``None``.

    >>> parsear_estrato("Estrato 4")
    4
    >>> parsear_estrato(0) is None
    True
    """
    estrato = parsear_entero(valor)
    return estrato if estrato is not None and 1 <= estrato <= 6 else None
