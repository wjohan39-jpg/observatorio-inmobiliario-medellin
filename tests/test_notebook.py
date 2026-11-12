"""Reglas del notebook de análisis: tiene resultados, pesa poco y solo lee datos públicos."""

import json
import re
from pathlib import Path
from typing import Any

import pytest

RUTA = Path(__file__).parent.parent / "notebooks" / "01_analisis_exploratorio.ipynb"
LIMITE_KB = 500
PROHIBIDO = (
    "data/limpio",
    "data/crudo",
    "data/compartidos",
    "leer_limpio",
    "leer_compartidos",
    "leer_observaciones",
    "leer_semana",
)
"""El notebook se publica con sus resultados: solo puede leer los agregados públicos."""


@pytest.fixture(scope="module")
def celdas() -> list[dict[str, Any]]:
    notebook = json.loads(RUTA.read_text(encoding="utf-8"))
    resultado: list[dict[str, Any]] = notebook["cells"]
    return resultado


def _texto(celda: dict[str, Any]) -> str:
    fuente = celda["source"]
    return "".join(fuente) if isinstance(fuente, list) else str(fuente)


def test_notebook_existe_y_tiene_resultados(celdas: list[dict[str, Any]]) -> None:
    codigo = [c for c in celdas if c["cell_type"] == "code"]
    assert codigo
    assert all(c["execution_count"] is not None for c in codigo)
    assert not any(
        salida.get("output_type") == "error" for c in codigo for salida in c.get("outputs", [])
    )


def test_notebook_solo_lee_agregados(celdas: list[dict[str, Any]]) -> None:
    for celda in celdas:
        texto = _texto(celda).replace("\\", "/")
        for prohibido in PROHIBIDO:
            assert prohibido not in texto, f"el notebook menciona {prohibido!r}"


def test_notebook_pesa_menos_de_500_kb() -> None:
    assert RUTA.stat().st_size < LIMITE_KB * 1024


def test_notebook_responde_las_preguntas(celdas: list[dict[str, Any]]) -> None:
    encabezados = [
        linea
        for celda in celdas
        if celda["cell_type"] == "markdown"
        for linea in _texto(celda).splitlines()
        if linea.startswith("#")
    ]
    for numero in range(1, 9):
        assert any(re.search(rf"\b{numero}\.", e) for e in encabezados), (
            f"falta la pregunta {numero}"
        )
    assert any("Hallazgos" in e for e in encabezados)
