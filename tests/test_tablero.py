from pathlib import Path
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import pytest

from observatorio_inmobiliario.agregados import (
    MINIMO_PARES_PRECIO,
    MINIMO_PUBLICACION,
    RANGOS_AREA,
)
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
        graficas.oferta_por_tipo(tablas["oferta_zona"], "venta"),
        graficas.oferta_comunas(tablas["oferta_zona"], "arriendo", "vivienda"),
        graficas.oferta_barrios(tablas["oferta_zona"], "venta", "vivienda"),
        graficas.distribucion_precio(tablas["distribucion_oferta"], "venta", "vivienda"),
        graficas.distribucion_alcobas(tablas["distribucion_oferta"], "arriendo", "vivienda"),
        graficas.precio_y_alcobas(tablas["distribucion_oferta"], "venta", "vivienda"),
        graficas.nuevos_y_retirados(tablas["rotacion_inmobiliaria"]),
        graficas.cuota_total(tablas["cuota_zona"], "todas"),
        graficas.cuota_zonas(tablas["cuota_zona"], "barrio", "venta"),
        graficas.concentracion_hhi(tablas["cuota_zona"], "comuna", "todas"),
        graficas.perfil_tipos(tablas["perfil_inmobiliaria"], "venta"),
        graficas.perfil_operacion(tablas["perfil_inmobiliaria"]),
        graficas.calidad_datos(tablas["calidad_inmobiliaria"]),
        graficas.compartidas_por_inmobiliaria(tablas["compartidas_inmobiliaria"], "media"),
        graficas.matriz_compartidas(tablas["compartidas_inmobiliaria"], "alta"),
        graficas.precio_relativo(tablas["compartidas_inmobiliaria"], "media"),
        graficas.cobertura_estratos(tablas["cobertura_estrato"], "venta"),
        graficas.estratos_por_comuna(tablas["cobertura_estrato"], "venta"),
        graficas.desvio_zonas(tablas["desvio_precio"], "venta", "bajo"),
        graficas.desvio_inmobiliarias(tablas["desvio_precio"], "arriendo"),
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


def test_graficas_de_oferta_tienen_datos(reales: dict[str, pd.DataFrame]) -> None:
    oferta, distribucion = reales["oferta_zona"], reales["distribucion_oferta"]
    for operacion in ("venta", "arriendo"):
        for figura in (
            graficas.oferta_por_tipo(oferta, operacion),
            graficas.oferta_comunas(oferta, operacion, "vivienda"),
            graficas.oferta_barrios(oferta, operacion, "vivienda"),
            graficas.distribucion_precio(distribucion, operacion, "vivienda"),
            graficas.distribucion_alcobas(distribucion, operacion, "vivienda"),
            graficas.precio_y_alcobas(distribucion, operacion, "vivienda"),
        ):
            assert figura.data, figura.layout.title.text


def test_oferta_barrios_cuantos(reales: dict[str, pd.DataFrame]) -> None:
    figura = graficas.oferta_barrios(reales["oferta_zona"], "arriendo", "vivienda", cuantos=10)
    assert len(figura.data[0].y) == 10
    assert list(figura.data[0].x) == sorted(figura.data[0].x)


def test_tipos_oferta_empieza_por_todos(reales: dict[str, pd.DataFrame]) -> None:
    tipos = graficas.tipos_oferta(reales["oferta_zona"])
    assert tipos[:2] == ["todos", "vivienda"]
    assert tipos[2:] == sorted(tipos[2:])


def test_ubicacion_de_la_oferta(reales: dict[str, pd.DataFrame]) -> None:
    total, con_comuna, con_barrio = graficas.ubicacion_de_la_oferta(
        reales["oferta_zona"], "venta", "todos"
    )
    assert total >= con_comuna >= con_barrio > 0


def test_tabla_oferta_ordenada(reales: dict[str, pd.DataFrame]) -> None:
    tabla = graficas.tabla_oferta(reales["oferta_zona"], "barrio", "venta", "vivienda")
    assert list(tabla.columns) == ["Nombre", "Comuna", "Anuncios"]
    assert tabla["Anuncios"].is_monotonic_decreasing


def test_oferta_vacia(vacias: dict[str, pd.DataFrame]) -> None:
    assert graficas.tipos_oferta(vacias["oferta_zona"]) == []
    assert graficas.ubicacion_de_la_oferta(vacias["oferta_zona"], "venta", "todos") == (0, 0, 0)
    assert graficas.tabla_oferta(vacias["oferta_zona"], "barrio", "venta", "todos").empty


def _rotacion() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "semana": ["2026-S46", "2026-S46", "2026-S47", "2026-S47", "2026-S47"],
            "fuente": ["a", "b", "a", "b", "c"],
            "operacion": ["arriendo"] * 5,
            "anuncios": [100, 50, 110, 40, 10],
            "nuevos": [None, None, 20, 5, None],
            "retirados": [0, 0, 10, 15, 0],
        }
    ).astype({"nuevos": "Int64", "anuncios": "Int64", "retirados": "Int64"})


def test_rotacion_semanal_suma_inmobiliarias_comparables() -> None:
    tabla = graficas.tabla_rotacion_semana(_rotacion())
    assert len(tabla) == 1  # la primera semana no tiene con qué comparar
    fila = tabla.iloc[0]
    assert fila["Semana"] == "2026-S47"
    assert fila["Inmobiliarias comparadas"] == 2  # «c» no tiene semana anterior
    assert fila["Nuevos"] == 25
    assert fila["Retirados"] == 25
    # había 150 - 25 + 25 = 150 anuncios la semana anterior
    assert fila["Tasa de retiro (%)"] == pytest.approx(25 / 150 * 100, abs=0.1)


def test_rotacion_sin_comparacion(vacias: dict[str, pd.DataFrame]) -> None:
    primera = _rotacion().iloc[:2]
    assert graficas.tabla_rotacion_semana(primera).empty
    assert graficas.nuevos_y_retirados(primera).layout.title.text
    assert graficas.tabla_rotacion_semana(vacias["rotacion_inmobiliaria"]).empty


def _cuota_sintetica() -> pd.DataFrame:
    """Cuatro zonas de ciudad con HHI conocidos: 5.000, 2.500, 1.000 y una con pocos anuncios."""
    zonas = {
        "Z1": {"a": 15, "b": 15},
        "Z2": {"a": 10, "b": 10, "c": 10, "d": 10},
        "Z3": {f"f{i}": 3 for i in range(10)},
        "Z4": {"a": 6, "b": 4},
    }
    filas = [
        {
            "nivel": "barrio",
            "codigo": zona,
            "nombre": zona.lower(),
            "comuna": "01",
            "operacion": "todas",
            "fuente": fuente,
            "anuncios": n,
        }
        for zona, fuentes in zonas.items()
        for fuente, n in fuentes.items()
    ]
    return pd.DataFrame(filas).astype({"anuncios": "Int64"})


def test_hhi_zonas_formula() -> None:
    tabla = graficas.hhi_zonas(_cuota_sintetica(), "barrio", "todas").set_index("codigo")
    assert tabla.loc["Z1", "hhi"] == 5_000
    assert tabla.loc["Z2", "hhi"] == 2_500
    assert tabla.loc["Z3", "hhi"] == 1_000
    assert "Z4" not in tabla.index  # menos anuncios que el mínimo para calcular el HHI
    assert tabla.loc["Z1", "lectura"] == "Muy concentrado"
    assert tabla.loc["Z2", "lectura"] == "Moderado"  # 2.500 no supera el límite
    assert tabla.loc["Z3", "lectura"] == "Poco concentrado"
    assert tabla.loc["Z1", "lider"] == "a"  # empate: gana la de nombre menor
    assert tabla.loc["Z1", "cuota_lider"] == 50
    assert tabla.loc["Z3", "inmobiliarias"] == 10
    assert list(tabla["hhi"]) == sorted(tabla["hhi"], reverse=True)


def test_hhi_zonas_reales(reales: dict[str, pd.DataFrame]) -> None:
    tabla = graficas.hhi_zonas(reales["cuota_zona"], "barrio", "todas")
    assert not tabla.empty
    assert (tabla["anuncios"] >= graficas.MINIMO_HHI).all()
    assert tabla["hhi"].between(0, 10_000).all()
    # El HHI mínimo posible con n inmobiliarias es 10.000 / n (todas con la misma cuota).
    assert (tabla["hhi"] >= 10_000 / tabla["inmobiliarias"] - 1).all()
    assert graficas.hhi_ciudad(reales["cuota_zona"], "todas") is not None


def test_hhi_vacio(vacias: dict[str, pd.DataFrame]) -> None:
    assert graficas.hhi_zonas(vacias["cuota_zona"], "barrio", "todas").empty
    assert graficas.tabla_hhi(vacias["cuota_zona"], "barrio", "todas").empty
    assert graficas.hhi_ciudad(vacias["cuota_zona"], "todas") is None


def test_cuota_suma_cien(reales: dict[str, pd.DataFrame]) -> None:
    cuota = reales["cuota_zona"]
    zonas = graficas.zonas_de_cuota(cuota, "barrio", "todas")
    tabla = graficas.tabla_cuota(cuota, "barrio", "todas", str(zonas["codigo"].iloc[0]))
    assert tabla["Cuota (%)"].sum() == pytest.approx(100, abs=0.5)
    assert tabla["Anuncios"].is_monotonic_decreasing
    figura = graficas.cuota_total(cuota, "venta")
    assert sum(v for traza in figura.data for v in traza.x) == pytest.approx(100)


def test_cuota_zonas_cuantos(reales: dict[str, pd.DataFrame]) -> None:
    figura = graficas.cuota_zonas(reales["cuota_zona"], "barrio", "todas", cuantos=10)
    nombres = {y for traza in figura.data for y in traza.y}
    assert len(nombres) == 10


def test_tabla_perfil_distingue_sin_datos_de_no_declara() -> None:
    perfil = pd.DataFrame(
        {
            "fuente": ["a", "a", "b", "c"],
            "operacion": ["venta", "arriendo", "arriendo", "venta"],
            "tipo": ["apartamento", "apartamento", "local", "casa"],
            "anuncios": [30, 10, 20, 5],
        }
    ).astype({"anuncios": "Int64"})
    estratos = pd.DataFrame(
        {
            "fuente": ["a", "a", "b"],
            "operacion": ["venta", "venta", "arriendo"],
            "estrato": ["3", "4", "3"],
            "declarados": [6, 2, 0],
            "inferidos": [0, 0, 20],
        }
    ).astype({"declarados": "Int64", "inferidos": "Int64"})
    tabla = graficas.tabla_perfil(perfil, estratos).set_index("Inmobiliaria")
    assert tabla.loc["a", "Anuncios"] == 40
    assert tabla.loc["a", "Venta (%)"] == 75
    assert tabla.loc["a", "Tipo principal"] == "apartamento (100%)"
    assert tabla.loc["a", "Estrato principal (declarado)"] == "3 (75%)"
    assert tabla.loc["b", "Estrato principal (declarado)"] == "No declara"
    assert tabla.loc["c", "Estrato principal (declarado)"] == "Sin datos"
    assert tabla.loc["b", "Tipo principal"] == "local (100%)"


def test_perfil_y_calidad_con_datos(reales: dict[str, pd.DataFrame]) -> None:
    perfil, calidad = reales["perfil_inmobiliaria"], reales["calidad_inmobiliaria"]
    for figura in (
        graficas.perfil_tipos(perfil, "venta"),
        graficas.perfil_tipos(perfil, "arriendo"),
        graficas.perfil_operacion(perfil),
        graficas.calidad_datos(calidad),
    ):
        assert figura.data
    tabla = graficas.tabla_calidad(calidad)
    assert tabla["Índice de completitud"].is_monotonic_decreasing
    assert tabla["Índice de completitud"].between(0, 100).all()
    assert len(graficas.tabla_perfil(perfil, reales["estratos_inmobiliaria"])) == len(
        set(perfil["fuente"])
    )


def test_perfil_y_calidad_vacios(vacias: dict[str, pd.DataFrame]) -> None:
    assert graficas.tabla_perfil(
        vacias["perfil_inmobiliaria"], vacias["estratos_inmobiliaria"]
    ).empty
    assert graficas.tabla_calidad(vacias["calidad_inmobiliaria"]).empty


def test_resumen_compartidas_es_coherente(reales: dict[str, pd.DataFrame]) -> None:
    for nivel in ("alta", "media", "baja"):
        resumen = graficas.resumen_compartidas(reales["compartidas_inmobiliaria"], nivel)
        assert resumen is not None
        assert 0 < resumen["inmuebles"] <= resumen["compartidos"] <= resumen["anuncios"]
        assert resumen["pct"] == pytest.approx(
            resumen["compartidos"] / resumen["anuncios"] * 100, abs=0.1
        )


def test_compartidas_niveles_acumulados_reales(reales: dict[str, pd.DataFrame]) -> None:
    compartidas = reales["compartidas_inmobiliaria"]
    inmuebles = [
        graficas.resumen_compartidas(compartidas, n)["inmuebles"]  # type: ignore[index]
        for n in ("alta", "media", "baja")
    ]
    assert inmuebles == sorted(inmuebles)


def test_compartidas_parejas_son_simetricas(reales: dict[str, pd.DataFrame]) -> None:
    cruces = reales["compartidas_inmobiliaria"]
    cruces = cruces[(cruces["fuente"] != "todas") & (cruces["otra"] != "todas")]
    cruces = cruces[cruces["nivel"] == "media"]
    parejas = {
        (f, o): int(n)
        for f, o, n in zip(cruces["fuente"], cruces["otra"], cruces["parejas"], strict=True)
    }
    assert parejas
    for (fuente, otra), n in parejas.items():
        assert parejas[(otra, fuente)] == n


def test_matriz_compartidas_sin_diagonal(reales: dict[str, pd.DataFrame]) -> None:
    figura = graficas.matriz_compartidas(reales["compartidas_inmobiliaria"], "media")
    matriz = pd.DataFrame(figura.data[0].z)
    assert matriz.shape[0] == matriz.shape[1]
    assert all(pd.isna(matriz.iloc[i, i]) for i in range(len(matriz)))


def test_precio_relativo_solo_con_minimo(reales: dict[str, pd.DataFrame]) -> None:
    compartidas = reales["compartidas_inmobiliaria"]
    figura = graficas.precio_relativo(compartidas, "media")
    etiquetas = list(figura.data[0].y)
    assert etiquetas
    for etiqueta in etiquetas:
        pares = int(etiqueta.rsplit("(", 1)[1].rstrip(")"))
        assert pares >= MINIMO_PARES_PRECIO


def test_tabla_compartidas(reales: dict[str, pd.DataFrame]) -> None:
    tabla = graficas.tabla_compartidas(reales["compartidas_inmobiliaria"], "media")
    assert {"Inmobiliaria", "Compartido (%)", "Diferencia media (%)"} <= set(tabla.columns)
    assert tabla["Compartido (%)"].is_monotonic_decreasing
    assert "todas" not in set(tabla["Inmobiliaria"])


def test_compartidas_vacias(vacias: dict[str, pd.DataFrame]) -> None:
    assert graficas.resumen_compartidas(vacias["compartidas_inmobiliaria"], "alta") is None
    assert graficas.tabla_compartidas(vacias["compartidas_inmobiliaria"], "alta").empty


def _geojson_corto() -> dict[str, Any]:
    barrios = [
        ("0101", "Uno", "U"),
        ("0102", "Dos", "U"),
        ("0103", "Tres", "U"),
        ("9001", "Vereda", "R"),
    ]
    return {
        "features": [
            {"properties": {"codigo": c, "nombre_barrio": n, "comuna": "01", "indicador_ur": z}}
            for c, n, z in barrios
        ]
    }


def _cuota_corta() -> pd.DataFrame:
    filas = [
        ("0101", "a", 4),
        ("0101", "b", 2),  # dos inmobiliarias
        ("0102", "a", 3),  # una sola
    ]
    return pd.DataFrame(
        [
            {
                "nivel": "barrio",
                "codigo": c,
                "nombre": c,
                "comuna": "01",
                "operacion": "venta",
                "fuente": f,
                "anuncios": n,
            }
            for c, f, n in filas
        ]
    ).astype({"anuncios": "Int64"})


def test_cobertura_barrios_incluye_los_sin_anuncios() -> None:
    cobertura = graficas.cobertura_barrios(_cuota_corta(), _geojson_corto(), "venta")
    assert len(cobertura) == 4
    por_codigo = cobertura.set_index("codigo")
    assert por_codigo.loc["0101", "inmobiliarias"] == 2
    assert por_codigo.loc["0101", "anuncios"] == 6
    assert por_codigo.loc["0103", "inmobiliarias"] == 0
    resumen = graficas.resumen_cobertura(cobertura)
    assert resumen == {"urbanos": 3, "sin_anuncios": 1, "una": 1, "dos": 1, "tres_o_mas": 0}


def test_tabla_nichos_solo_urbanos_y_menos_cubiertos_primero() -> None:
    tabla = graficas.tabla_nichos(_cuota_corta(), _geojson_corto(), "venta", 1)
    assert list(tabla["Barrio"]) == ["Tres", "Dos"]  # la vereda rural no cuenta
    assert list(tabla["Inmobiliarias"]) == [0, 1]
    assert graficas.tabla_nichos(_cuota_corta(), _geojson_corto(), "arriendo", 0).shape[0] == 3


def test_nichos_con_datos_reales(reales: dict[str, pd.DataFrame]) -> None:
    geojson = cargar_geojson()
    cuota, estratos = reales["cuota_zona"], reales["cobertura_estrato"]
    cobertura = graficas.cobertura_barrios(cuota, geojson, "venta")
    assert len(cobertura) == 349
    resumen = graficas.resumen_cobertura(cobertura)
    assert (
        resumen["sin_anuncios"] + resumen["una"] + resumen["dos"] + resumen["tres_o_mas"]
        == (resumen["urbanos"])
    )
    assert graficas.mapa_cobertura(cuota, geojson, "venta").data
    assert graficas.cobertura_estratos(estratos, "venta").data
    assert graficas.estratos_por_comuna(estratos, "arriendo").data


def test_desvio_con_datos_reales(reales: dict[str, pd.DataFrame]) -> None:
    desvio = reales["desvio_precio"]
    for operacion in ("venta", "arriendo"):
        resumen = graficas.resumen_desvio(desvio, operacion)
        assert resumen is not None
        assert 0 < resumen["pct_bajo"] < 100 and 0 < resumen["pct_alto"] < 100
        assert graficas.desvio_zonas(desvio, operacion, "bajo").data
        assert graficas.desvio_zonas(desvio, operacion, "alto").data
        assert graficas.desvio_inmobiliarias(desvio, operacion).data
    tabla = graficas.tabla_desvio(desvio, "venta")
    assert tabla["Bajo (%)"].is_monotonic_decreasing
    assert (tabla["Bajo"] <= tabla["Anuncios comparables"]).all()
    assert (tabla["Anuncios comparables"] >= MINIMO_PUBLICACION).all()


def test_nichos_vacios(vacias: dict[str, pd.DataFrame]) -> None:
    assert graficas.resumen_desvio(vacias["desvio_precio"], "venta") is None
    assert graficas.tabla_desvio(vacias["desvio_precio"], "venta").empty
    assert graficas.desvio_zonas(vacias["desvio_precio"], "venta", "bajo").layout.title.text
    assert graficas.cobertura_estratos(vacias["cobertura_estrato"], "venta").layout.title.text
    assert graficas.tabla_nichos(vacias["cuota_zona"], _geojson_corto(), "venta", 1).shape[0] == 3


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
