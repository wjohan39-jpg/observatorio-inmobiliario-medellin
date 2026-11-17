from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import pytest

from observatorio_inmobiliario.agregados import MINIMO_PUBLICACION, RANGOS_AREA
from observatorio_inmobiliario.almacenamiento import TABLAS_AGREGADAS
from observatorio_inmobiliario.tablero import graficas, vista
from observatorio_inmobiliario.tablero.datos import (
    RAIZ,
    cargar_agregados,
    cargar_geojson,
    tablas_vacias,
)


@pytest.fixture(scope="module")
def reales() -> dict[str, pd.DataFrame]:
    return cargar_agregados()


@pytest.fixture(scope="module")
def vacias() -> dict[str, pd.DataFrame]:
    return tablas_vacias()


# ------------------------------------------------------------------ Datos


def test_raiz_es_el_repo() -> None:
    assert (RAIZ / "pyproject.toml").exists()


def test_cargar_agregados_reales(reales: dict[str, pd.DataFrame]) -> None:
    assert set(reales) == set(TABLAS_AGREGADAS)
    assert all(len(tabla) > 0 for tabla in reales.values())


def test_cargar_agregados_falta_archivo(tmp_path: Path, reales: dict[str, pd.DataFrame]) -> None:
    tablas = cargar_agregados(tmp_path)
    assert set(tablas) == set(TABLAS_AGREGADAS)
    for nombre, tabla in tablas.items():
        assert tabla.empty
        assert list(tabla.columns) == list(reales[nombre].columns), nombre


def test_cargar_geojson() -> None:
    geojson = cargar_geojson()
    assert len(geojson["features"]) == 349
    assert "codigo" in geojson["features"][0]["properties"]


def test_hay_datos(reales: dict[str, pd.DataFrame], vacias: dict[str, pd.DataFrame]) -> None:
    assert graficas.hay_datos(reales["precios_zona"])
    assert not graficas.hay_datos(vacias["precios_zona"])


# ---------------------------------------------------------------- Gráficas


def _con_nulo(precios: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    """Copia de ``precios`` con la mediana del m² nula en un barrio de venta de vivienda."""
    filas = precios[
        (precios["nivel"] == "barrio")
        & (precios["operacion"] == "venta")
        & (precios["tipo"] == "vivienda")
    ]
    indice = filas.index[0]
    copia = precios.copy()
    copia.loc[indice, "precio_m2_mediana"] = pd.NA
    return copia, str(copia.loc[indice, "codigo"])


def test_mapa_barrios_omite_nulos(reales: dict[str, pd.DataFrame]) -> None:
    precios, codigo = _con_nulo(reales["precios_zona"])
    figura = graficas.mapa_barrios(precios, cargar_geojson(), "venta")
    ubicaciones = {
        str(u) for traza in figura.data if traza.locations is not None for u in traza.locations
    }
    assert ubicaciones
    assert codigo not in ubicaciones


def test_ranking_barrios_cuantos(reales: dict[str, pd.DataFrame]) -> None:
    figura = graficas.ranking_barrios(reales["precios_zona"], "venta", cuantos=15)
    valores = [v for traza in figura.data for v in traza.x]
    assert len(valores) == 30  # 15 más baratos y 15 más caros
    assert all(pd.notna(v) for v in valores)


def test_estratos_distingue_inferidos(reales: dict[str, pd.DataFrame]) -> None:
    figura = graficas.estratos(reales["estratos_inmobiliaria"])
    nombres = {traza.name for traza in figura.data}
    assert nombres == {
        "1-3, declarado",
        "1-3, inferido",
        "4-6, declarado",
        "4-6, inferido",
    }


def _llamadas(tablas: dict[str, pd.DataFrame]) -> list[go.Figure]:
    geojson = cargar_geojson()
    return [
        graficas.mapa_barrios(tablas["precios_zona"], geojson, "venta"),
        graficas.ranking_barrios(tablas["precios_zona"], "arriendo"),
        graficas.comparacion_comunas(tablas["precios_zona"]),
        graficas.cobertura(tablas["cobertura_inmobiliaria"]),
        graficas.concentracion(tablas["cobertura_comuna"]),
        graficas.indice_relativo(tablas["economia_inmobiliaria"], "arriendo"),
        graficas.estratos(tablas["estratos_inmobiliaria"]),
        graficas.compartidos(tablas["compartidos_fuentes"], "media"),
        graficas.evolucion(tablas["evolucion_precios"], "venta"),
        graficas.dispersion_barrios(tablas["mercado_precios"], "venta"),
        graficas.precio_estratos(tablas["mercado_precios"], "arriendo"),
        graficas.tipos_por_comuna(tablas["mercado_precios"], "venta"),
        graficas.rangos_area(tablas["mercado_precios"], "arriendo"),
        graficas.precio_comunas(tablas["precios_zona"], "venta"),
        graficas.rentabilidad_barrios(tablas["precios_zona"]),
    ]


def test_graficas_con_datos_reales(reales: dict[str, pd.DataFrame]) -> None:
    for figura in _llamadas(reales):
        assert isinstance(figura, go.Figure)
        assert figura.layout.title.text


def test_graficas_con_tablas_vacias(vacias: dict[str, pd.DataFrame]) -> None:
    for figura in _llamadas(vacias):
        assert isinstance(figura, go.Figure)


def test_colores_fijos_por_inmobiliaria(reales: dict[str, pd.DataFrame]) -> None:
    assert set(graficas.COLORES_FUENTE) >= set(reales["cobertura_inmobiliaria"]["fuente"])


def test_graficas_de_precios_tienen_datos(reales: dict[str, pd.DataFrame]) -> None:
    mercado, precios = reales["mercado_precios"], reales["precios_zona"]
    for operacion in ("venta", "arriendo"):
        for figura in (
            graficas.dispersion_barrios(mercado, operacion),
            graficas.precio_estratos(mercado, operacion),
            graficas.tipos_por_comuna(mercado, operacion),
            graficas.rangos_area(mercado, operacion),
            graficas.precio_comunas(precios, operacion),
        ):
            assert figura.data, figura.layout.title.text
    areas = graficas.rangos_area(mercado, "venta")
    assert set(areas.data[0].x) <= set(RANGOS_AREA)


def test_tabla_dispersion(reales: dict[str, pd.DataFrame]) -> None:
    tabla = graficas.tabla_dispersion(reales["mercado_precios"], "venta")
    assert not tabla.empty
    assert {"Barrio", "Mediana (m²)", "Media (m²)", "Variación (%)"} <= set(tabla.columns)
    assert tabla["Variación (%)"].is_monotonic_decreasing
    assert (tabla["Anuncios"] >= MINIMO_PUBLICACION).all()


def test_tabla_dispersion_vacia(vacias: dict[str, pd.DataFrame]) -> None:
    assert graficas.tabla_dispersion(vacias["mercado_precios"], "venta").empty


def test_rentabilidad_es_arriendo_anual_sobre_venta(reales: dict[str, pd.DataFrame]) -> None:
    tabla = graficas.tabla_rentabilidad(reales["precios_zona"])
    assert not tabla.empty
    esperada = tabla["Arriendo (m²)"] * 12 / tabla["Venta (m²)"] * 100
    assert ((tabla["Rentabilidad bruta (%)"] - esperada).abs() < 0.1).all()
    assert tabla["Rentabilidad bruta (%)"].is_monotonic_decreasing
    anios = 100 / tabla["Rentabilidad bruta (%)"]
    assert ((tabla["Años de arriendo = compra"] - anios).abs() < 0.2).all()


def test_rentabilidad_lecturas_en_tres_grupos(reales: dict[str, pd.DataFrame]) -> None:
    tabla = graficas.tabla_rentabilidad(reales["precios_zona"])
    assert set(tabla["Lectura"]) == set(graficas.LECTURAS)
    por_lectura = tabla.groupby("Lectura")["Rentabilidad bruta (%)"]
    assert por_lectura.min()["Favorece comprar"] >= por_lectura.max()["Intermedio"]
    assert por_lectura.min()["Intermedio"] >= por_lectura.max()["Favorece arrendar"]
    assert abs(tabla["Lectura"].value_counts().max() - tabla["Lectura"].value_counts().min()) <= 1


def test_rentabilidad_solo_barrios_con_venta_y_arriendo(
    reales: dict[str, pd.DataFrame],
) -> None:
    precios = reales["precios_zona"]
    solo_venta = precios[precios["operacion"] == "venta"]
    assert graficas.tabla_rentabilidad(solo_venta).empty
    assert graficas.rentabilidad_barrios(solo_venta).layout.title.text


def test_rentabilidad_vacia(vacias: dict[str, pd.DataFrame]) -> None:
    assert graficas.tabla_rentabilidad(vacias["precios_zona"]).empty


# ---------------------------------------------------------------- Formato


@pytest.mark.parametrize(
    ("valor", "texto"),
    [
        (5_079_208, "$5,08 M"),
        (42_553, "$42.553"),
        (999, "$999"),
        (1_234_567_890, "$1.234,57 M"),
    ],
)
def test_pesos_en_formato_colombiano(valor: float, texto: str) -> None:
    assert vista.pesos(valor) == texto


def test_entero_en_formato_colombiano() -> None:
    assert vista.entero(5630) == "5.630"


def test_tabla_grupos_ancha(reales: dict[str, pd.DataFrame]) -> None:
    grupos = reales["grupos_compartidos"]
    tabla = graficas.tabla_grupos(grupos, "alta")
    assert len(tabla) == grupos.loc[grupos["nivel"] == "alta", "grupo"].nunique()
    assert {"Grupo", "Barrio", "Área (m²)", "Diferencia (%)"} <= set(tabla.columns)
    fuentes = set(grupos.loc[grupos["nivel"] == "alta", "fuente"])
    assert fuentes <= set(tabla.columns)
    assert (tabla["Diferencia (%)"].dropna() >= 0).all()


def test_tabla_grupos_vacia(vacias: dict[str, pd.DataFrame]) -> None:
    assert graficas.tabla_grupos(vacias["grupos_compartidos"], "alta").empty


def test_rotacion(reales: dict[str, pd.DataFrame]) -> None:
    figura = graficas.rotacion(reales["rotacion_inmobiliaria"])
    assert figura.layout.title.text


def test_semanas(reales: dict[str, pd.DataFrame], vacias: dict[str, pd.DataFrame]) -> None:
    semanas = graficas.semanas(reales["evolucion_precios"])
    assert semanas  # las semanas crecen con cada actualización semanal
    assert semanas == sorted(semanas)
    assert all(len(semana) == 8 and semana[4:6] == "-S" for semana in semanas)
    assert graficas.semanas(vacias["evolucion_precios"]) == []


def test_cache_google_dentro_del_nivel_gratuito() -> None:
    # 1.000 consultas gratis al mes en Place Details Enterprise; margen para 20 sedes.
    consultas_al_mes = 20 * 30 * (24 * 60 * 60 / vista.CACHE_GOOGLE_S)
    assert consultas_al_mes <= 1_000


# ------------------------------------------------- Revisión final del plan 7


def test_tablas_se_recargan_si_cambian_los_archivos(tmp_path: Path) -> None:
    from observatorio_inmobiliario.almacenamiento import guardar_agregado

    vista.tablas.clear() if hasattr(vista.tablas, "clear") else None
    base = cargar_agregados()["cobertura_inmobiliaria"]
    guardar_agregado(base.head(3), tmp_path, "cobertura_inmobiliaria")
    assert len(vista.tablas(tmp_path)["cobertura_inmobiliaria"]) == 3

    ruta = guardar_agregado(base.head(5), tmp_path, "cobertura_inmobiliaria")
    import os

    os.utime(ruta, (ruta.stat().st_atime, ruta.stat().st_mtime + 10))
    assert len(vista.tablas(tmp_path)["cobertura_inmobiliaria"]) == 5


def test_evolucion_eje_y_en_espanol(reales: dict[str, pd.DataFrame]) -> None:
    figura = graficas.evolucion(reales["evolucion_precios"], "venta")
    assert figura.layout.yaxis.title.text == "COP por m²"


def test_ruta_agrega_src() -> None:
    import importlib.util
    import sys

    spec = importlib.util.spec_from_file_location("_ruta", RAIZ / "app" / "_ruta.py")
    assert spec and spec.loader
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    assert str(RAIZ / "src") in sys.path
