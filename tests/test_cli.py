import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Any

import pytest
import respx

from observatorio_inmobiliario import cli
from observatorio_inmobiliario.almacenamiento import (
    COLUMNAS_PRIVADAS,
    TABLAS_AGREGADAS,
    guardar_observaciones,
    leer_agregado,
    leer_compartidos,
    leer_limpio,
)
from observatorio_inmobiliario.http import ErrorDeDescarga
from observatorio_inmobiliario.modelos import AnuncioNormalizado, Operacion
from observatorio_inmobiliario.reputacion import URL_BUSQUEDA


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


# ----------------------------------------------------------------- compartidos


def _limpio(tmp_path: Path, fecha: date = date(2026, 11, 11)) -> Path:
    """Limpia con el comando real dos anuncios del mismo apartamento en santafe y nutibara."""
    comunes: dict[str, Any] = {
        "fecha_observacion": fecha,
        "operacion": Operacion.ARRIENDO,
        "tipo_inmueble": "Apartamento",
        "area_m2": 80.0,
        "habitaciones": 3,
        "banos": 2,
        "municipio": "Medellín",
        "latitud": 6.2087,  # parque Lleras
        "longitud": -75.5676,
    }
    guardar_observaciones(
        [
            AnuncioNormalizado(fuente="santafe", id_fuente="S1", precio=2_000_000, **comunes),
            AnuncioNormalizado(fuente="nutibara", id_fuente="N1", precio=2_200_000, **comunes),
        ],
        tmp_path / "crudo",
    )
    args = ["--crudo", str(tmp_path / "crudo"), "--salida", str(tmp_path / "limpio")]
    assert cli.main(["limpiar", *args]) == 0
    return tmp_path / "limpio"


def test_compartidos_guarda_y_resume(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    limpio = _limpio(tmp_path)
    _limpio(tmp_path, date(2026, 11, 3))  # semana anterior
    capsys.readouterr()

    codigo = cli.main(
        ["compartidos", "--limpio", str(limpio), "--salida", str(tmp_path / "compartidos")]
    )

    assert codigo == 0
    parejas, grupos = leer_compartidos(tmp_path / "compartidos")
    assert list((tmp_path / "compartidos" / "parejas").iterdir()) == [
        tmp_path / "compartidos" / "parejas" / "2026-S46.parquet"
    ]
    assert len(parejas) == 1
    assert parejas.loc[0, "confianza"] == "alta"
    assert parejas.loc[0, "diferencia_precio_pct"] == pytest.approx(10.0)
    assert set(grupos["grupo_alta"]) == {"nutibara:N1:arriendo"}
    salida = capsys.readouterr().out
    assert "2026-S46" in salida
    assert "alta" in salida and "nutibara" in salida


def test_compartidos_sin_datos(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["compartidos", "--limpio", str(tmp_path / "vacio")]) == 1

    assert "no hay datos limpios en" in capsys.readouterr().err


def test_compartidos_semana_inexistente(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    limpio = _limpio(tmp_path)

    codigo = cli.main(["compartidos", "--semana", "2025-S01", "--limpio", str(limpio)])

    assert codigo == 1
    assert "no hay datos limpios de la semana 2025-S01" in capsys.readouterr().err


# ------------------------------------------------------------------- agregados


def _agregados(tmp_path: Path) -> list[str]:
    return [
        "agregados",
        "--limpio",
        str(tmp_path / "limpio"),
        "--compartidos",
        str(tmp_path / "compartidos"),
        "--salida",
        str(tmp_path / "agregados"),
    ]


def test_agregados_guarda_y_resume(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    limpio = _limpio(tmp_path)
    assert (
        cli.main(
            ["compartidos", "--limpio", str(limpio), "--salida", str(tmp_path / "compartidos")]
        )
        == 0
    )
    capsys.readouterr()

    assert cli.main(_agregados(tmp_path)) == 0

    archivos = sorted(ruta.stem for ruta in (tmp_path / "agregados").iterdir())
    assert archivos == sorted(TABLAS_AGREGADAS)
    cobertura = leer_agregado(tmp_path / "agregados", "cobertura_inmobiliaria")
    assert set(cobertura["fuente"]) == {"nutibara", "santafe"}
    assert set(cobertura["semana"]) == {"2026-S46"}
    salida = capsys.readouterr().out
    assert "cobertura_inmobiliaria" in salida and "2026-S46" in salida


def test_agregados_sin_columnas_privadas(tmp_path: Path) -> None:
    limpio = _limpio(tmp_path)
    cli.main(["compartidos", "--limpio", str(limpio), "--salida", str(tmp_path / "compartidos")])
    assert cli.main(_agregados(tmp_path)) == 0

    for nombre in TABLAS_AGREGADAS:
        columnas = leer_agregado(tmp_path / "agregados", nombre).columns
        base = {c.removesuffix("_a").removesuffix("_b") for c in columnas}
        assert not base & COLUMNAS_PRIVADAS, nombre


def test_agregados_sin_datos(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(_agregados(tmp_path)) == 1

    assert "no hay datos limpios en" in capsys.readouterr().err


def test_agregados_sin_compartidos(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _limpio(tmp_path)
    capsys.readouterr()

    assert cli.main(_agregados(tmp_path)) == 1

    error = capsys.readouterr().err
    assert "corre primero: observatorio compartidos" in error
    assert not (tmp_path / "agregados").exists()


# ---------------------------------------------------------------------- google


def test_google_buscar(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "clave")
    with respx.mock:
        respx.post(URL_BUSQUEDA).respond(
            json={
                "places": [
                    {
                        "id": "ChIJ1",
                        "displayName": {"text": "Alnago"},
                        "formattedAddress": "Calle 10, Medellín",
                    }
                ]
            }
        )
        assert cli.main(["google", "buscar", "Alnago Medellín"]) == 0

    salida = capsys.readouterr().out
    assert "ChIJ1" in salida and "Alnago" in salida and "Calle 10" in salida


def test_google_buscar_sin_clave(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("GOOGLE_PLACES_API_KEY", raising=False)
    assert cli.main(["google", "buscar", "Alnago"]) == 1
    assert "falta GOOGLE_PLACES_API_KEY" in capsys.readouterr().err


# ----------------------------------------------------------------------- sitio


def test_sitio_genera_index(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from observatorio_inmobiliario.tablero.datos import AGREGADOS

    codigo = cli.main(["sitio", "--agregados", str(AGREGADOS), "--salida", str(tmp_path / "sitio")])

    assert codigo == 0
    assert (tmp_path / "sitio" / "index.html").exists()
    assert "index.html" in capsys.readouterr().out


# ---------------------------------------------------------------------- semana


class FuenteSemana:
    """Fuente falsa con anuncios de Medellín completos (pasan la limpieza)."""

    def __init__(self, nombre: str, cantidad: int = 6, error: Exception | None = None) -> None:
        self.nombre, self._cantidad, self._error = nombre, cantidad, error

    def listar_anuncios(self) -> Iterator[AnuncioNormalizado]:
        if self._error is not None:
            raise self._error
        for i in range(self._cantidad):
            yield AnuncioNormalizado(
                fuente=self.nombre,
                id_fuente=f"{self.nombre}-{i}",
                fecha_observacion=date(2026, 11, 11),
                operacion=Operacion.ARRIENDO,
                tipo_inmueble="Apartamento",
                precio=2_000_000 + i * 10_000,
                area_m2=60.0 + i,
                habitaciones=2,
                banos=1,
                estrato=3,
                municipio="Medellín",
                latitud=6.2087,  # parque Lleras
                longitud=-75.5676,
            )


@pytest.fixture
def fuentes_semana(monkeypatch: pytest.MonkeyPatch) -> dict[str, Exception | None]:
    """Reemplaza ``crear_fuente``; el diccionario dice qué error lanza cada fuente."""
    errores: dict[str, Exception | None] = {"nutibara": None, "santafe": None}

    @contextmanager
    def crear(nombre: str, **_: Any) -> Iterator[FuenteSemana]:
        yield FuenteSemana(nombre, error=errores.get(nombre))

    monkeypatch.setattr(cli, "crear_fuente", crear)
    return errores


def _args_semana(tmp_path: Path, *extra: str) -> list[str]:
    return [
        "semana",
        "--fuentes",
        "nutibara",
        "santafe",
        "--crudo",
        str(tmp_path / "crudo"),
        "--limpio",
        str(tmp_path / "limpio"),
        "--compartidos",
        str(tmp_path / "compartidos"),
        "--agregados",
        str(tmp_path / "agregados"),
        *extra,
    ]


def test_semana_corre_todo(tmp_path: Path, fuentes_semana: dict[str, Any]) -> None:
    assert cli.main(_args_semana(tmp_path)) == 0

    assert sorted(p.name for p in (tmp_path / "crudo").iterdir()) == ["nutibara", "santafe"]
    assert [p.name for p in (tmp_path / "limpio").iterdir()] == ["2026-S46.parquet"]
    assert (tmp_path / "compartidos" / "parejas" / "2026-S46.parquet").exists()
    assert sorted(p.stem for p in (tmp_path / "agregados").iterdir()) == sorted(TABLAS_AGREGADAS)
    cobertura = leer_agregado(tmp_path / "agregados", "cobertura_inmobiliaria")
    assert set(cobertura["fuente"]) == {"nutibara", "santafe"}


def test_semana_falla_parcial(
    tmp_path: Path, fuentes_semana: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    fuentes_semana["nutibara"] = ErrorDeDescarga("sitio caído")
    resumen = tmp_path / "resumen.md"

    assert cli.main(_args_semana(tmp_path, "--resumen", str(resumen))) == 0

    cobertura = leer_agregado(tmp_path / "agregados", "cobertura_inmobiliaria")
    assert set(cobertura["fuente"]) == {"santafe"}
    texto = resumen.read_text(encoding="utf-8")
    assert "nutibara" in texto and "falló" in texto


def test_semana_falla_total(
    tmp_path: Path, fuentes_semana: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(_args_semana(tmp_path)) == 0
    antes = {p.name: p.stat().st_mtime_ns for p in (tmp_path / "agregados").iterdir()}
    fuentes_semana["nutibara"] = ErrorDeDescarga("caído")
    fuentes_semana["santafe"] = ErrorDeDescarga("caído")

    assert cli.main(_args_semana(tmp_path)) == 1

    assert "ninguna fuente trajo anuncios" in capsys.readouterr().err
    despues = {p.name: p.stat().st_mtime_ns for p in (tmp_path / "agregados").iterdir()}
    assert despues == antes


def test_semana_excepcion_inesperada(tmp_path: Path, fuentes_semana: dict[str, Any]) -> None:
    fuentes_semana["nutibara"] = RuntimeError("cambió el HTML")

    assert cli.main(_args_semana(tmp_path)) == 0

    assert [p.name for p in (tmp_path / "crudo").iterdir()] == ["santafe"]


def test_semana_repetida(tmp_path: Path, fuentes_semana: dict[str, Any]) -> None:
    assert cli.main(_args_semana(tmp_path)) == 0
    filas = len(leer_limpio(tmp_path / "limpio"))
    assert cli.main(_args_semana(tmp_path)) == 0

    assert [p.name for p in (tmp_path / "limpio").iterdir()] == ["2026-S46.parquet"]
    assert len(leer_limpio(tmp_path / "limpio")) == filas == 12


def test_semana_resumen_markdown(tmp_path: Path, fuentes_semana: dict[str, Any]) -> None:
    resumen = tmp_path / "resumen.md"
    assert cli.main(_args_semana(tmp_path, "--resumen", str(resumen))) == 0

    texto = resumen.read_text(encoding="utf-8")
    assert "2026-S46" in texto
    assert "| Fuente | Anuncios | Estado |" in texto
    assert "| santafe | 6 | ok |" in texto
    for nombre in TABLAS_AGREGADAS:
        assert nombre in texto


def test_semana_fuentes_elegidas(tmp_path: Path, fuentes_semana: dict[str, Any]) -> None:
    args = _args_semana(tmp_path)
    args[args.index("nutibara")] = "santafe"  # --fuentes santafe santafe → una sola vez
    assert cli.main(args) == 0
    assert [p.name for p in (tmp_path / "crudo").iterdir()] == ["santafe"]


def test_semana_fuente_desconocida(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        cli.main(["semana", "--fuentes", "no-existe"])
    assert "invalid choice" in capsys.readouterr().err
