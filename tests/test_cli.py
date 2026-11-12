import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from observatorio_inmobiliario import cli
from observatorio_inmobiliario.almacenamiento import guardar_observaciones, leer_limpio
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


# --------------------------------------------------------------------- catalogo


def test_catalogo_guarda_el_geojson(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    coleccion = {"type": "FeatureCollection", "features": [{"properties": {"nombre": "Belén"}}]}
    monkeypatch.setattr(cli, "descargar_catalogo", lambda cliente: coleccion)
    salida = tmp_path / "ref" / "barrios.geojson"

    assert cli.main(["catalogo", "--salida", str(salida)]) == 0

    assert json.loads(salida.read_text(encoding="utf-8")) == coleccion
    assert "Belén" in salida.read_text(encoding="utf-8")  # sin escapes é
    assert "1 barrios y veredas guardados" in capsys.readouterr().out


def test_catalogo_incompleto_no_guarda(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def falla(cliente: object) -> None:
        raise ValueError("El catálogo trajo 10 polígonos")

    monkeypatch.setattr(cli, "descargar_catalogo", falla)
    salida = tmp_path / "barrios.geojson"

    assert cli.main(["catalogo", "--salida", str(salida)]) == 1
    assert not salida.exists()


# --------------------------------------------------------------------- limpiar


def _crudo(directorio: Path, fecha: date = date(2026, 11, 11)) -> None:
    guardar_observaciones(
        [
            AnuncioNormalizado(
                fuente="santafe",
                id_fuente="A1",
                fecha_observacion=fecha,
                operacion=Operacion.ARRIENDO,
                precio=2_000_000,
                area_m2=50.0,
                municipio="MEDELLIN",
                latitud=6.2087,  # parque Lleras
                longitud=-75.5676,
            ),
            AnuncioNormalizado(
                fuente="nutibara",
                id_fuente="N1",
                fecha_observacion=fecha,
                operacion=Operacion.VENTA,
                precio=450_000_000,
                municipio="Envigado",
            ),
        ],
        directorio,
    )


def test_limpiar_guarda_y_resume(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _crudo(tmp_path / "crudo")
    _crudo(tmp_path / "crudo", date(2026, 11, 3))  # semana anterior

    codigo = cli.main(
        ["limpiar", "--crudo", str(tmp_path / "crudo"), "--salida", str(tmp_path / "limpio")]
    )

    assert codigo == 0
    limpio = leer_limpio(tmp_path / "limpio")
    assert list((tmp_path / "limpio").iterdir()) == [tmp_path / "limpio" / "2026-S46.parquet"]
    por_id = limpio.set_index("id_fuente")
    assert por_id.loc["A1", "comuna"] == "14"  # ubicado por coordenadas con el catálogo real
    assert por_id.loc["N1", "municipio_normalizado"] == "Envigado"
    salida = capsys.readouterr().out
    assert "2026-S46" in salida
    assert "santafe" in salida and "nutibara" in salida


def test_limpiar_una_semana(tmp_path: Path) -> None:
    _crudo(tmp_path / "crudo")
    _crudo(tmp_path / "crudo", date(2026, 11, 3))

    args = ["--crudo", str(tmp_path / "crudo"), "--salida", str(tmp_path / "limpio")]
    assert cli.main(["limpiar", "--semana", "2026-S45", *args]) == 0

    assert list((tmp_path / "limpio").iterdir()) == [tmp_path / "limpio" / "2026-S45.parquet"]


def test_limpiar_sin_datos(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["limpiar", "--crudo", str(tmp_path / "vacio")]) == 1

    assert "no hay datos crudos" in capsys.readouterr().err


def test_limpiar_semana_inexistente(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _crudo(tmp_path / "crudo")

    codigo = cli.main(["limpiar", "--semana", "2025-S01", "--crudo", str(tmp_path / "crudo")])

    assert codigo == 1
    assert "no hay datos de la semana 2025-S01" in capsys.readouterr().err


def test_limpiar_semana_mal_escrita(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        cli.main(["limpiar", "--semana", "46"])

    assert "AAAA-SNN" in capsys.readouterr().err
