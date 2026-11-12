"""Formato de números en estilo colombiano y los indicadores del resumen.

No depende de Streamlit: lo usan las páginas de ``app/`` y el sitio estático.
"""

import pandas as pd


def entero(valor: float) -> str:
    """Entero con punto de miles, como se escribe en Colombia: ``5630`` → ``"5.630"``."""
    return f"{round(valor):,}".replace(",", ".")


def pesos(valor: float) -> str:
    """Pesos en formato colombiano: ``"$42.553"``, o en millones con coma: ``"$5,08 M"``."""
    if valor >= 1_000_000:
        millones = f"{valor / 1_000_000:,.2f}"  # 1,234.57 → 1.234,57
        return "$" + millones.replace(",", "_").replace(".", ",").replace("_", ".") + " M"
    return "$" + entero(valor)


def _mediana_ciudad(evolucion: pd.DataFrame, operacion: str) -> str:
    """Mediana del m² de vivienda en toda la ciudad, en la última semana que la tenga."""
    filas = evolucion[(evolucion["operacion"] == operacion) & (evolucion["tipo"] == "vivienda")]
    filas = filas.dropna(subset=["precio_m2_mediana"])
    if filas.empty:
        return "—"
    return pesos(float(filas.sort_values("semana")["precio_m2_mediana"].iloc[-1]))


def indicadores(tablas: dict[str, pd.DataFrame]) -> list[tuple[str, str]]:
    """Los 5 indicadores del resumen del mercado, como ``(etiqueta, valor)``."""
    cobertura = tablas["cobertura_inmobiliaria"]
    todas = cobertura[cobertura["operacion"] == "todas"]
    precios = tablas["precios_zona"]
    evolucion = tablas["evolucion_precios"]
    return [
        ("Anuncios analizados", entero(int(todas["anuncios"].sum()))),
        ("Barrios con precio", str(precios.loc[precios["nivel"] == "barrio", "codigo"].nunique())),
        ("m² de vivienda en venta", _mediana_ciudad(evolucion, "venta")),
        ("m² de vivienda en arriendo", _mediana_ciudad(evolucion, "arriendo")),
        ("Inmobiliarias", str(todas["fuente"].nunique())),
    ]
