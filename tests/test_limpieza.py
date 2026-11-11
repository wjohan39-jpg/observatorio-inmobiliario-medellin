from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from observatorio_inmobiliario.almacenamiento import (
    ESQUEMA,
    guardar_observaciones,
    leer_observaciones,
)
from observatorio_inmobiliario.catalogo import Catalogo
from observatorio_inmobiliario.limpieza import limpiar
from observatorio_inmobiliario.modelos import AnuncioNormalizado, Operacion

MINI = Path(__file__).parent / "fixtures" / "catalogo" / "mini.geojson"
EN_LAURELES = {"latitud": 6.245, "longitud": -75.595}  # dentro de 1101 en el catálogo mini
EN_NARANJAL = {"latitud": 6.245, "longitud": -75.585}  # dentro de 1103


@pytest.fixture
def catalogo(tmp_path: Path) -> Catalogo:
    alias = tmp_path / "alias.csv"
    alias.write_text("alias,codigo\n", encoding="utf-8")
    return Catalogo.cargar(MINI, alias)


@pytest.fixture
def crudo(tmp_path: Path) -> Any:
    """Arma una tabla cruda con el mismo guardado y lectura del proyecto (tipos reales)."""

    def armar(*filas: dict[str, Any]) -> pd.DataFrame:
        anuncios = [
            AnuncioNormalizado(
                **{
                    "fuente": "prueba",
                    "id_fuente": f"P{i}",
                    "fecha_observacion": date(2026, 11, 11),
                    "operacion": Operacion.ARRIENDO,
                    "municipio": "Medellín",
                    **fila,
                }
            )
            for i, fila in enumerate(filas)
        ]
        directorio = tmp_path / "crudo"
        guardar_observaciones(anuncios, directorio)
        return leer_observaciones(directorio)

    return armar


def _una(df: pd.DataFrame) -> pd.Series:  # type: ignore[type-arg]
    assert len(df) == 1
    return df.iloc[0]


# --------------------------------------------------------------------- Ubicación


def test_coordenadas_ganan_al_nombre(crudo: Any, catalogo: Catalogo) -> None:
    fila = _una(limpiar(crudo({"barrio": "Naranjal", **EN_LAURELES}), catalogo))

    assert (fila["codigo_barrio"], fila["barrio_normalizado"]) == ("1101", "Laureles")
    assert (fila["comuna"], fila["nombre_comuna"]) == ("11", "LAURELES")
    assert fila["metodo_ubicacion"] == "coordenadas"


def test_sin_coordenadas_usa_el_nombre(crudo: Any, catalogo: Catalogo) -> None:
    fila = _una(limpiar(crudo({"barrio": "Naranjal"}), catalogo))

    assert (fila["codigo_barrio"], fila["metodo_ubicacion"]) == ("1103", "nombre")


def test_sin_ubicacion(crudo: Any, catalogo: Catalogo) -> None:
    fila = _una(limpiar(crudo({"barrio": "Torres del Campestre"}), catalogo))

    assert pd.isna(fila["codigo_barrio"]) and pd.isna(fila["comuna"])
    assert pd.isna(fila["metodo_ubicacion"])
    assert fila["es_medellin"]  # lo dice la fuente


def test_municipio_envigado_no_recibe_barrio_de_medellin(crudo: Any, catalogo: Catalogo) -> None:
    """Review Focus 5: en el borde con El Poblado manda el municipio de la fuente."""
    fila = _una(limpiar(crudo({"municipio": "Envigado", **EN_LAURELES}), catalogo))

    assert fila["municipio_normalizado"] == "Envigado"
    assert pd.isna(fila["codigo_barrio"])
    assert not fila["es_medellin"]


def test_envigado_tampoco_se_ubica_por_nombre(crudo: Any, catalogo: Catalogo) -> None:
    fila = _una(limpiar(crudo({"municipio": "ENVIGADO", "barrio": "Laureles"}), catalogo))

    assert pd.isna(fila["codigo_barrio"])


def test_barrio_que_es_municipio(crudo: Any, catalogo: Catalogo) -> None:
    """Villacruz pone a veces el municipio en el campo del barrio."""
    fila = _una(limpiar(crudo({"municipio": None, "barrio": "SABANETA"}), catalogo))

    assert fila["municipio_normalizado"] == "Sabaneta"
    assert pd.isna(fila["codigo_barrio"])
    assert fila["en_valle"] and not fila["es_medellin"]


def test_municipio_nulo_con_punto_en_medellin(crudo: Any, catalogo: Catalogo) -> None:
    fila = _una(limpiar(crudo({"municipio": None, **EN_NARANJAL}), catalogo))

    assert fila["municipio_normalizado"] == "Medellín"
    assert fila["codigo_barrio"] == "1103"
    assert fila["es_medellin"]


def test_municipio_nulo_ubicado_por_nombre(crudo: Any, catalogo: Catalogo) -> None:
    fila = _una(limpiar(crudo({"municipio": None, "barrio": "LAURELES"}), catalogo))

    assert fila["municipio_normalizado"] == "Medellín"
    assert fila["codigo_barrio"] == "1101"


def test_municipio_nulo_sin_ubicacion(crudo: Any, catalogo: Catalogo) -> None:
    fila = _una(limpiar(crudo({"municipio": None, "barrio": "Torres"}), catalogo))

    assert pd.isna(fila["municipio_normalizado"])
    assert not fila["en_valle"] and not fila["es_medellin"]


def test_coordenadas_fuera_del_valle(crudo: Any, catalogo: Catalogo) -> None:
    fila = _una(
        limpiar(crudo({"barrio": "Naranjal", "latitud": 4.6, "longitud": -74.08}), catalogo)
    )

    assert not fila["coordenadas_validas"]
    assert (fila["codigo_barrio"], fila["metodo_ubicacion"]) == ("1103", "nombre")


def test_sin_coordenadas_no_son_validas(crudo: Any, catalogo: Catalogo) -> None:
    assert not _una(limpiar(crudo({}), catalogo))["coordenadas_validas"]


def test_mayusculas_del_municipio(crudo: Any, catalogo: Catalogo) -> None:
    fila = _una(limpiar(crudo({"municipio": "MEDELLIN"}), catalogo))

    assert fila["municipio_normalizado"] == "Medellín"
    assert fila["es_medellin"]


def test_fuera_del_valle(crudo: Any, catalogo: Catalogo) -> None:
    fila = _una(limpiar(crudo({"municipio": "EL RETIRO", **EN_LAURELES}), catalogo))

    assert fila["municipio_normalizado"] == "El Retiro"
    assert not fila["en_valle"] and not fila["es_medellin"]
    assert pd.isna(fila["codigo_barrio"])


# --------------------------------------------------------------------- Tipo y precio por m²


def test_tipo_normalizado(crudo: Any, catalogo: Catalogo) -> None:
    fila = _una(limpiar(crudo({"tipo_inmueble": "Apto Loft"}), catalogo))

    assert fila["tipo_normalizado"] == "apartaestudio"
    assert fila["tipo_inmueble"] == "apto loft"  # la columna cruda no cambia


def test_precio_m2(crudo: Any, catalogo: Catalogo) -> None:
    fila = _una(limpiar(crudo({"precio": 2_000_000, "area_m2": 50.0}), catalogo))

    assert fila["precio_m2"] == 40_000.0


@pytest.mark.parametrize(("precio", "area"), [(None, 50.0), (2_000_000, None), (None, None)])
def test_precio_m2_nulo(
    crudo: Any, catalogo: Catalogo, precio: int | None, area: float | None
) -> None:
    """Review Focus 4: sin dato no hay precio por m², y no se lanza ninguna excepción."""
    fila = _una(limpiar(crudo({"precio": precio, "area_m2": area}), catalogo))

    assert pd.isna(fila["precio_m2"])


# --------------------------------------------------------------------- Forma de la tabla


def test_no_modifica_las_columnas_crudas(crudo: Any, catalogo: Catalogo) -> None:
    df = crudo({"barrio": "Naranjal", **EN_LAURELES}, {"municipio": "ENVIGADO"})
    copia = df.copy()

    limpio = limpiar(df, catalogo)

    pd.testing.assert_frame_equal(limpio[ESQUEMA.names], copia)
    pd.testing.assert_frame_equal(df, copia)  # tampoco cambia la tabla de entrada


def test_no_borra_filas(crudo: Any, catalogo: Catalogo) -> None:
    df = crudo({}, {"municipio": "EL RETIRO"}, {"precio": None})

    assert len(limpiar(df, catalogo)) == 3


def test_tabla_vacia(catalogo: Catalogo) -> None:
    vacio = leer_observaciones(Path("no-existe"))

    limpio = limpiar(vacio, catalogo)

    assert limpio.empty
    assert {"codigo_barrio", "precio_m2", "es_medellin"} <= set(limpio.columns)
