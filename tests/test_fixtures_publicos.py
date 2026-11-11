"""Los fixtures van al repositorio público: no deben llevar datos personales ni secretos."""

from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"

PROHIBIDO = (
    "tel:",
    "wa.me",
    "authorization",
    "simi-api",
    '"address"',
    '"description"',
    '"unitnumber"',
    "<img",
)
"""Señales de teléfonos, el token de SIMI, direcciones, descripciones o fotos."""

ARCHIVOS = sorted(p for p in FIXTURES.rglob("*") if p.is_file())


@pytest.mark.parametrize("archivo", ARCHIVOS, ids=lambda p: str(p.relative_to(FIXTURES)))
def test_fixture_sin_datos_prohibidos(archivo: Path) -> None:
    contenido = archivo.read_bytes().decode("utf-8", errors="replace").lower()
    encontrados = [senal for senal in PROHIBIDO if senal in contenido]
    assert not encontrados, f"{archivo.name} contiene {encontrados}"
