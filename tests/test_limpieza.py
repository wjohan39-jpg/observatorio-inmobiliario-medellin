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
from observatorio_inmobiliario.limpieza import filtrar_medellin, limpiar, marcar_atipicos
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


# --------------------------------------------------------------------- Atípicos


def _apartamentos(n: int, operacion: Operacion = Operacion.ARRIENDO) -> list[dict[str, Any]]:
    """``n`` apartamentos normales de 50 m² (~40.000 $/m² en arriendo, ~8 M$/m² en venta)."""
    base = 2_000_000 if operacion is Operacion.ARRIENDO else 400_000_000
    return [
        {
            "operacion": operacion,
            "tipo_inmueble": "apartamento",
            "area_m2": 50.0,
            "precio": base + i * base // 100,
        }
        for i in range(n)
    ]


def _motivos(df: pd.DataFrame) -> list[str | None]:
    return [None if pd.isna(m) else m for m in df["motivo_atipico"]]


def test_arriendo_con_precio_de_venta(crudo: Any, catalogo: Catalogo) -> None:
    fila = _una(limpiar(crudo({"precio": 450_000_000}), catalogo))

    assert fila["es_atipico"]
    assert fila["motivo_atipico"] == "precio_fuera_de_rango"


def test_venta_barata(crudo: Any, catalogo: Catalogo) -> None:
    fila = _una(limpiar(crudo({"operacion": Operacion.VENTA, "precio": 5_000_000}), catalogo))

    assert fila["motivo_atipico"] == "precio_fuera_de_rango"


def test_precio_normal(crudo: Any, catalogo: Catalogo) -> None:
    fila = _una(limpiar(crudo({"precio": 2_500_000, "area_m2": 60.0}), catalogo))

    assert not fila["es_atipico"]
    assert pd.isna(fila["motivo_atipico"])


def test_apartamento_de_3_m2(crudo: Any, catalogo: Catalogo) -> None:
    df = limpiar(
        crudo(
            {"tipo_inmueble": "apartamento", "area_m2": 3.0, "precio": 1_000_000},
            {"tipo_inmueble": "lote", "area_m2": 5_000.0, "precio": 3_000_000},
        ),
        catalogo,
    )

    assert _motivos(df) == ["area_fuera_de_rango", None]


def test_precio_m2_extremo(crudo: Any, catalogo: Catalogo) -> None:
    filas = _apartamentos(40)
    filas.append({"tipo_inmueble": "apartamento", "area_m2": 25.0, "precio": 100_000_000})

    df = limpiar(crudo(*filas), catalogo)

    assert _motivos(df) == [None] * 40 + ["precio_m2_extremo"]


def test_grupo_pequeno_no_usa_iqr(crudo: Any, catalogo: Catalogo) -> None:
    filas = _apartamentos(10)
    filas.append({"tipo_inmueble": "apartamento", "area_m2": 25.0, "precio": 100_000_000})

    df = limpiar(crudo(*filas), catalogo)

    assert not df["es_atipico"].any()


def test_venta_y_arriendo_no_se_mezclan(crudo: Any, catalogo: Catalogo) -> None:
    """Una venta normal, al lado de 40 arriendos, no es extrema: su grupo es otro."""
    filas = [*_apartamentos(40), *_apartamentos(1, Operacion.VENTA)]

    df = limpiar(crudo(*filas), catalogo)

    assert not df["es_atipico"].any()


def test_tipos_no_se_mezclan(crudo: Any, catalogo: Catalogo) -> None:
    filas = _apartamentos(40)
    filas.append({"tipo_inmueble": "bodega", "area_m2": 1_000.0, "precio": 2_000_000})

    df = limpiar(crudo(*filas), catalogo)

    assert not df["es_atipico"].any()


def test_nulos_no_marcan(crudo: Any, catalogo: Catalogo) -> None:
    """Review Focus 4."""
    filas = [*_apartamentos(40), {"tipo_inmueble": "apartamento"}]

    df = limpiar(crudo(*filas), catalogo)

    assert not df["es_atipico"].any()


def test_varios_motivos(crudo: Any, catalogo: Catalogo) -> None:
    fila = _una(
        limpiar(crudo({"tipo_inmueble": "casa", "area_m2": 5.0, "precio": 450_000_000}), catalogo)
    )

    assert fila["motivo_atipico"] == "precio_fuera_de_rango; area_fuera_de_rango"


def test_marcar_no_borra_filas(crudo: Any, catalogo: Catalogo) -> None:
    filas = [*_apartamentos(40), {"precio": 450_000_000}]

    assert len(marcar_atipicos(limpiar(crudo(*filas), catalogo))) == 41


def test_marcar_tabla_vacia(catalogo: Catalogo) -> None:
    limpio = limpiar(leer_observaciones(Path("no-existe")), catalogo)

    assert {"es_atipico", "motivo_atipico"} <= set(limpio.columns)


# --------------------------------------------------------------------- Filtro de Medellín


def test_filtrar_medellin(crudo: Any, catalogo: Catalogo) -> None:
    df = limpiar(
        crudo({"municipio": "MEDELLIN"}, {"municipio": "Envigado"}, {"municipio": None}),
        catalogo,
    )

    assert filtrar_medellin(df)["id_fuente"].tolist() == ["P0"]
