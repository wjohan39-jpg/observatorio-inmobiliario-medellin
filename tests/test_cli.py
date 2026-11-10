from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from observatorio_inmobiliario import cli
from observatorio_inmobiliario.http import ErrorDeDescarga
from observatorio_inmobiliario.modelos import AnuncioNormalizado, Operacion


class FuenteFalsa:
    nombre = "santafe"

    def __init__(self, cantidad: int = 2, error: Exception | None = None) -> None:
        self._cantidad = cantidad
        self._error = error

    def listar_anuncios(self) -> Iterator[AnuncioNormalizado]:
        for i in range(self._cantidad):
            yield AnuncioNormalizado(
                fuente=self.nombre,
                id_fuente=f"A{i}",
                fecha_observacion=date(2026, 11, 10),
                operacion=Operacion.ARRIENDO,
                precio=1_000_000,
            )
        if self._error is not None:
            raise self._error


@pytest.fixture
def opciones_recibidas(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Reemplaza ``crear_fuente`` por una fuente falsa y anota con qué opciones se llamó."""
    recibidas: dict[str, Any] = {}

    @contextmanager
    def crear_fuente_falsa(nombre: str, **opciones: Any) -> Iterator[FuenteFalsa]:
        recibidas.update(nombre=nombre, **opciones)
        yield FuenteFalsa()

    monkeypatch.setattr(cli, "crear_fuente", crear_fuente_falsa)
    return recibidas


def _usar_fuente(monkeypatch: pytest.MonkeyPatch, fuente: FuenteFalsa) -> None:
    @contextmanager
    def crear(nombre: str, **opciones: Any) -> Iterator[FuenteFalsa]:
        yield fuente

    monkeypatch.setattr(cli, "crear_fuente", crear)


def test_scrape_guarda_y_reporta(
    tmp_path: Path, opciones_recibidas: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["scrape", "santafe", "--salida", str(tmp_path)]) == 0

    archivos = list(tmp_path.rglob("*.parquet"))
    assert archivos == [tmp_path / "santafe" / "2026-S46.parquet"]
    salida = capsys.readouterr().out
    assert "santafe: 2 anuncios guardados en" in salida
    assert "2026-S46.parquet" in salida


def test_opciones_por_defecto(tmp_path: Path, opciones_recibidas: dict[str, Any]) -> None:
    cli.main(["scrape", "santafe", "--salida", str(tmp_path)])

    assert opciones_recibidas == {"nombre": "santafe", "con_detalle": True, "max_paginas": None}


def test_opciones_se_pasan(tmp_path: Path, opciones_recibidas: dict[str, Any]) -> None:
    cli.main(
        ["scrape", "santafe", "--salida", str(tmp_path), "--sin-detalle", "--max-paginas", "1"]
    )

    assert opciones_recibidas["con_detalle"] is False
    assert opciones_recibidas["max_paginas"] == 1


def test_fuente_desconocida(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as salida:
        cli.main(["scrape", "noexiste"])

    assert salida.value.code == 2
    assert "santafe" in capsys.readouterr().err  # el error muestra las fuentes válidas


@pytest.mark.parametrize("valor", ["0", "-1", "dos"])
def test_max_paginas_debe_ser_entero_positivo(valor: str) -> None:
    with pytest.raises(SystemExit) as salida:
        cli.main(["scrape", "santafe", "--max-paginas", valor])

    assert salida.value.code == 2


def test_sin_anuncios_es_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Cero anuncios casi siempre significa que el sitio cambió; la automatización debe enterarse.
    _usar_fuente(monkeypatch, FuenteFalsa(cantidad=0))

    assert cli.main(["scrape", "santafe", "--salida", str(tmp_path)]) == 1
    assert not any(tmp_path.iterdir())
    assert "0 anuncios" in capsys.readouterr().err


def test_error_de_descarga_no_guarda_nada(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Una corrida incompleta no debe sobrescribir el archivo bueno de la semana.
    _usar_fuente(monkeypatch, FuenteFalsa(error=ErrorDeDescarga("503 en /apisf/properties")))

    assert cli.main(["scrape", "santafe", "--salida", str(tmp_path)]) == 1
    assert not any(tmp_path.iterdir())
    assert "503" in capsys.readouterr().err
