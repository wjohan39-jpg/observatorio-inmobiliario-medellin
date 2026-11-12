from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from observatorio_inmobiliario.almacenamiento import (
    ESQUEMA,
    ESQUEMA_GRUPOS,
    ESQUEMA_LIMPIO,
    ESQUEMA_PAREJAS,
    guardar_compartidos,
    guardar_limpio,
    guardar_observaciones,
    leer_compartidos,
    leer_limpio,
    leer_observaciones,
    leer_semana,
    ruta_semana,
    semanas_disponibles,
    semanas_limpias,
)
from observatorio_inmobiliario.catalogo import Catalogo
from observatorio_inmobiliario.emparejamiento import agrupar, emparejar
from observatorio_inmobiliario.limpieza import limpiar
from observatorio_inmobiliario.modelos import AnuncioNormalizado, Operacion

SEMANA_46 = date(2026, 11, 10)
SEMANA_47 = date(2026, 11, 17)


def _anuncio(id_fuente: str, fecha: date = SEMANA_46, **campos: Any) -> AnuncioNormalizado:
    datos: dict[str, Any] = {
        "fuente": "santafe",
        "id_fuente": id_fuente,
        "fecha_observacion": fecha,
        "operacion": Operacion.ARRIENDO,
        **campos,
    }
    return AnuncioNormalizado.model_validate(datos)


@pytest.fixture
def anuncios() -> list[AnuncioNormalizado]:
    return [
        _anuncio(
            "A1",
            url="https://arrendamientossantafe.com/propiedad/A1",
            tipo_inmueble="Apartamento",
            precio=1_800_000,
            area_m2=45.5,
            habitaciones=1,
            banos=1,
            parqueaderos=0,
            estrato=3,
            barrio="Almerías",
            municipio="Medellín",
            latitud=6.245466,
            longitud=-75.6124142,
        ),
        _anuncio("V2", operacion=Operacion.VENTA, precio=750_000_000, estrato=4),
        _anuncio("A3"),  # casi todo vacío
    ]


# --------------------------------------------------------------------- Rutas


def test_ruta_semana() -> None:
    assert ruta_semana(Path("d"), "santafe", SEMANA_46) == Path("d/santafe/2026-S46.parquet")


def test_ruta_semana_usa_año_iso() -> None:
    # El 1 de enero de 2027 cae en la semana 53 del año ISO 2026, no en la semana 1 de 2027.
    assert ruta_semana(Path("d"), "santafe", date(2027, 1, 1)) == Path("d/santafe/2026-S53.parquet")


# --------------------------------------------------------------------- Guardar y leer


def test_esquema_coincide_con_el_modelo() -> None:
    assert ESQUEMA.names == list(AnuncioNormalizado.model_fields)


def test_guardar_y_leer_ida_y_vuelta(tmp_path: Path, anuncios: list[AnuncioNormalizado]) -> None:
    rutas = guardar_observaciones(anuncios, tmp_path)
    df = leer_observaciones(tmp_path)

    assert rutas == [tmp_path / "santafe" / "2026-S46.parquet"]
    assert list(df.columns) == list(AnuncioNormalizado.model_fields)
    assert len(df) == 3

    primera = df.iloc[0]
    assert primera["id_fuente"] == "A1"
    assert primera["operacion"] == "arriendo"
    assert primera["fecha_observacion"] == SEMANA_46
    assert primera["tipo_inmueble"] == "apartamento"
    assert primera["precio"] == 1_800_000
    assert primera["area_m2"] == 45.5
    assert primera["parqueaderos"] == 0
    assert primera["barrio"] == "Almerías"
    assert primera["latitud"] == pytest.approx(6.245466)
    assert df.iloc[1]["operacion"] == "venta"


def test_vacios_se_leen_como_nulos(tmp_path: Path, anuncios: list[AnuncioNormalizado]) -> None:
    guardar_observaciones(anuncios, tmp_path)
    vacia = leer_observaciones(tmp_path).iloc[2]

    for campo in ("url", "precio", "area_m2", "estrato", "barrio", "latitud"):
        assert pd.isna(vacia[campo]), campo


def test_enteros_conservan_su_tipo_con_nulos(
    tmp_path: Path, anuncios: list[AnuncioNormalizado]
) -> None:
    guardar_observaciones(anuncios, tmp_path)
    df = leer_observaciones(tmp_path)

    # Sin tipos enteros con nulos, pandas convertiría precio a float y 1.800.000 a 1800000.0.
    assert pd.api.types.is_integer_dtype(df["precio"])
    assert pd.api.types.is_integer_dtype(df["estrato"])


def test_misma_semana_sobrescribe(tmp_path: Path, anuncios: list[AnuncioNormalizado]) -> None:
    guardar_observaciones(anuncios, tmp_path)
    guardar_observaciones(anuncios, tmp_path)

    assert len(leer_observaciones(tmp_path)) == 3


def test_semanas_distintas_archivos_distintos(
    tmp_path: Path, anuncios: list[AnuncioNormalizado]
) -> None:
    siguiente = [a.model_copy(update={"fecha_observacion": SEMANA_47}) for a in anuncios]

    rutas = guardar_observaciones([*anuncios, *siguiente], tmp_path)

    assert [r.name for r in rutas] == ["2026-S46.parquet", "2026-S47.parquet"]
    assert len(leer_observaciones(tmp_path)) == 6


def test_leer_filtra_por_fuente(tmp_path: Path, anuncios: list[AnuncioNormalizado]) -> None:
    otra = [_anuncio("N1", fuente="nutibara")]
    guardar_observaciones([*anuncios, *otra], tmp_path)

    assert len(leer_observaciones(tmp_path)) == 4
    assert list(leer_observaciones(tmp_path, "nutibara")["id_fuente"]) == ["N1"]


def test_guardar_nada_no_escribe(tmp_path: Path) -> None:
    assert guardar_observaciones([], tmp_path) == []
    assert not any(tmp_path.iterdir())


def test_leer_directorio_vacio(tmp_path: Path) -> None:
    df = leer_observaciones(tmp_path / "no-existe")

    assert df.empty
    assert list(df.columns) == list(AnuncioNormalizado.model_fields)


# --------------------------------------------------------------------- Semanas y tabla limpia


@pytest.fixture
def catalogo(tmp_path: Path) -> Catalogo:
    alias = tmp_path / "alias.csv"
    alias.write_text("alias,codigo\n", encoding="utf-8")
    return Catalogo.cargar(Path(__file__).parent / "fixtures" / "catalogo" / "mini.geojson", alias)


def test_semanas_disponibles(tmp_path: Path) -> None:
    guardar_observaciones(
        [
            _anuncio("A1"),
            _anuncio("A2", SEMANA_47),
            _anuncio("A3", fuente="nutibara"),
        ],
        tmp_path,
    )

    assert semanas_disponibles(tmp_path) == ["2026-S46", "2026-S47"]


def test_semanas_disponibles_sin_datos(tmp_path: Path) -> None:
    assert semanas_disponibles(tmp_path / "no-existe") == []


def test_leer_semana_une_las_fuentes(tmp_path: Path) -> None:
    guardar_observaciones(
        [_anuncio("A1"), _anuncio("N1", fuente="nutibara"), _anuncio("A2", SEMANA_47)], tmp_path
    )

    df = leer_semana(tmp_path, "2026-S46")

    assert sorted(df["id_fuente"]) == ["A1", "N1"]


def test_esquema_limpio_coincide_con_limpiar(
    tmp_path: Path, anuncios: list[AnuncioNormalizado], catalogo: Catalogo
) -> None:
    guardar_observaciones(anuncios, tmp_path)

    limpio = limpiar(leer_observaciones(tmp_path), catalogo)

    assert ESQUEMA_LIMPIO.names == list(limpio.columns)
    assert ESQUEMA_LIMPIO.names[: len(ESQUEMA.names)] == ESQUEMA.names


def test_guardar_y_leer_limpio(
    tmp_path: Path, anuncios: list[AnuncioNormalizado], catalogo: Catalogo
) -> None:
    guardar_observaciones(anuncios, tmp_path / "crudo")
    limpio = limpiar(leer_observaciones(tmp_path / "crudo"), catalogo)

    ruta = guardar_limpio(limpio, tmp_path / "limpio", "2026-S46")
    leido = leer_limpio(tmp_path / "limpio")

    assert ruta == tmp_path / "limpio" / "2026-S46.parquet"
    pd.testing.assert_frame_equal(leido, limpio)


def test_guardar_limpio_sobrescribe(
    tmp_path: Path, anuncios: list[AnuncioNormalizado], catalogo: Catalogo
) -> None:
    guardar_observaciones(anuncios, tmp_path / "crudo")
    limpio = limpiar(leer_observaciones(tmp_path / "crudo"), catalogo)

    guardar_limpio(limpio, tmp_path / "limpio", "2026-S46")
    guardar_limpio(limpio.head(1), tmp_path / "limpio", "2026-S46")

    assert len(leer_limpio(tmp_path / "limpio", "2026-S46")) == 1
    assert list((tmp_path / "limpio").iterdir()) == [tmp_path / "limpio" / "2026-S46.parquet"]


def test_leer_limpio_sin_datos(tmp_path: Path) -> None:
    df = leer_limpio(tmp_path)

    assert df.empty
    assert list(df.columns) == ESQUEMA_LIMPIO.names


# --------------------------------------------------------------------- Compartidos


def test_semanas_limpias(tmp_path: Path) -> None:
    for semana in ("2026-S47", "2026-S46"):
        (tmp_path / f"{semana}.parquet").touch()

    assert semanas_limpias(tmp_path) == ["2026-S46", "2026-S47"]
    assert semanas_limpias(tmp_path / "no-existe") == []


@pytest.fixture
def compartidos(tmp_path: Path, catalogo: Catalogo) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Parejas y grupos reales: el mismo apartamento en santafe y nutibara, y uno sin pareja."""
    comunes: dict[str, Any] = {
        "tipo_inmueble": "Apartamento",
        "area_m2": 80.0,
        "habitaciones": 3,
        "banos": 2,
        "municipio": "Medellín",
        "latitud": 6.245,
        "longitud": -75.595,
    }
    guardar_observaciones(
        [
            _anuncio("S1", precio=2_000_000, estrato=4, **comunes),
            _anuncio("N1", fuente="nutibara", precio=2_100_000, **comunes),
            _anuncio("S2", operacion=Operacion.VENTA, precio=400_000_000),
        ],
        tmp_path / "crudo",
    )
    parejas = emparejar(limpiar(leer_observaciones(tmp_path / "crudo"), catalogo))
    assert len(parejas) == 1
    return parejas, agrupar(parejas)


def test_esquemas_compartidos_coinciden(compartidos: tuple[pd.DataFrame, pd.DataFrame]) -> None:
    parejas, grupos = compartidos

    assert ESQUEMA_PAREJAS.names == list(parejas.columns)
    assert ESQUEMA_GRUPOS.names == list(grupos.columns)


def test_guardar_y_leer_compartidos(
    tmp_path: Path, compartidos: tuple[pd.DataFrame, pd.DataFrame]
) -> None:
    parejas, grupos = compartidos

    rutas = guardar_compartidos(parejas, grupos, tmp_path / "compartidos", "2026-S46")
    leidas, leidos = leer_compartidos(tmp_path / "compartidos")

    assert rutas == [
        tmp_path / "compartidos" / "parejas" / "2026-S46.parquet",
        tmp_path / "compartidos" / "grupos_inmueble" / "2026-S46.parquet",
    ]
    pd.testing.assert_frame_equal(leidas, parejas)
    pd.testing.assert_frame_equal(leidos, grupos)


def test_guardar_compartidos_sobrescribe(
    tmp_path: Path, compartidos: tuple[pd.DataFrame, pd.DataFrame]
) -> None:
    parejas, grupos = compartidos
    directorio = tmp_path / "compartidos"

    guardar_compartidos(parejas, grupos, directorio, "2026-S46")
    guardar_compartidos(parejas.head(0), grupos.head(0), directorio, "2026-S46")

    leidas, leidos = leer_compartidos(directorio, "2026-S46")
    assert leidas.empty and leidos.empty


def test_guardar_compartidos_vacios(tmp_path: Path, catalogo: Catalogo) -> None:
    parejas = emparejar(limpiar(leer_observaciones(tmp_path / "no-existe"), catalogo))
    directorio = tmp_path / "compartidos"

    guardar_compartidos(parejas, agrupar(parejas), directorio, "2026-S46")
    leidas, leidos = leer_compartidos(directorio, "2026-S46")

    assert list(leidas.columns) == ESQUEMA_PAREJAS.names
    assert list(leidos.columns) == ESQUEMA_GRUPOS.names
    assert leidas.empty and leidos.empty


def test_leer_compartidos_filtra_por_semana(
    tmp_path: Path, compartidos: tuple[pd.DataFrame, pd.DataFrame]
) -> None:
    parejas, grupos = compartidos
    guardar_compartidos(parejas, grupos, tmp_path, "2026-S46")
    guardar_compartidos(parejas, grupos, tmp_path, "2026-S47")

    assert len(leer_compartidos(tmp_path)[0]) == 2
    assert len(leer_compartidos(tmp_path, "2026-S47")[0]) == 1
