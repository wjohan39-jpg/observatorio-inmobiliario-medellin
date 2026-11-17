"""Gráficas del dashboard: cada función recibe una tabla agregada y devuelve una figura.

Reglas comunes:

* Las filas con la mediana nula (menos de 5 anuncios con ese dato) se omiten, nunca se
  grafican como 0.
* Con una tabla vacía se devuelve una figura con el aviso "Sin datos", sin error.
* Cada inmobiliaria tiene el mismo color en todas las gráficas (:data:`COLORES_FUENTE`).
"""

from typing import Any, Final

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from observatorio_inmobiliario.agregados import (
    ANALISIS_AREA,
    ANALISIS_DISPERSION,
    ANALISIS_ESTRATO,
    ANALISIS_TIPO,
    RANGOS_AREA,
    TIPOS_COMPARADOS,
)

COLORES_FUENTE: Final = {
    "activourbano": "#1f77b4",
    "alnago": "#ff7f0e",
    "maxibienes": "#2ca02c",
    "nutibara": "#d62728",
    "panorama": "#9467bd",
    "puertabierta": "#8c564b",
    "santafe": "#e377c2",
    "uribienes": "#7f7f7f",
    "villacruz": "#bcbd22",
}
CENTRO_MEDELLIN: Final = {"lat": 6.245, "lon": -75.58}
VIVIENDA: Final = "vivienda"
_PLANTILLA: Final = "plotly_white"


def hay_datos(df: pd.DataFrame) -> bool:
    """Si la tabla tiene al menos una fila."""
    return not df.empty


def _sin_datos(titulo: str) -> go.Figure:
    figura = go.Figure()
    figura.add_annotation(text="Sin datos", showarrow=False, font={"size": 16})
    figura.update_layout(
        title=titulo, template=_PLANTILLA, xaxis_visible=False, yaxis_visible=False
    )
    return figura


def _barrios(precios: pd.DataFrame, operacion: str, tipo: str) -> pd.DataFrame:
    filas = precios[
        (precios["nivel"] == "barrio")
        & (precios["operacion"] == operacion)
        & (precios["tipo"] == tipo)
        & precios["precio_m2_mediana"].notna()
    ]
    return filas.assign(precio_m2_mediana=filas["precio_m2_mediana"].astype("float64"))


def mapa_barrios(
    precios: pd.DataFrame, geojson: dict[str, Any], operacion: str, tipo: str = VIVIENDA
) -> go.Figure:
    """Mapa de la mediana del precio por m² por barrio. Los barrios sin dato quedan en gris."""
    titulo = f"Precio por m² de {tipo} en {operacion}, por barrio (mediana)"
    datos = _barrios(precios, operacion, tipo)
    if datos.empty:
        return _sin_datos(titulo)
    figura = px.choropleth_map(
        datos,
        geojson=geojson,
        locations="codigo",
        featureidkey="properties.codigo",
        color="precio_m2_mediana",
        color_continuous_scale="Viridis",
        hover_name="nombre",
        hover_data={"codigo": False, "anuncios": True, "precio_m2_mediana": ":,.0f"},
        labels={"precio_m2_mediana": "COP por m²", "anuncios": "Anuncios"},
        center=CENTRO_MEDELLIN,
        zoom=10.5,
        opacity=0.75,
        map_style="carto-positron",
    )
    # Todos los barrios en gris de fondo: los que no tienen dato se ven, pero sin color.
    figura.update_layout(
        title=titulo,
        margin={"l": 0, "r": 0, "t": 40, "b": 0},
        map_layers=[
            {
                "source": geojson,
                "type": "fill",
                "color": "#d9d9d9",
                "opacity": 0.5,
                "below": "traces",
            }
        ],
    )
    return figura


def ranking_barrios(precios: pd.DataFrame, operacion: str, cuantos: int = 15) -> go.Figure:
    """Los ``cuantos`` barrios más baratos y los ``cuantos`` más caros por m² de vivienda."""
    titulo = f"{operacion.title()}: los barrios más baratos y más caros por m²"
    orden = _barrios(precios, operacion, VIVIENDA).sort_values("precio_m2_mediana")
    if orden.empty:
        return _sin_datos(titulo)
    mitad = min(cuantos, len(orden) // 2) or len(orden)
    baratos, caros = orden.head(mitad), orden.tail(mitad)
    figura = go.Figure()
    for nombre, filas, color in (
        ("Más baratos", baratos, "#2c7fb8"),
        ("Más caros", caros, "#d95f0e"),
    ):
        figura.add_bar(
            x=filas["precio_m2_mediana"],
            y=filas["nombre"],
            orientation="h",
            name=nombre,
            marker_color=color,
            customdata=filas[["anuncios"]],
            hovertemplate="%{y}: %{x:,.0f} COP/m² (%{customdata[0]} anuncios)<extra></extra>",
        )
    figura.update_layout(
        title=titulo,
        template=_PLANTILLA,
        xaxis_title="COP por m² (mediana)",
        height=max(400, 22 * 2 * mitad),
    )
    return figura


def comparacion_comunas(precios: pd.DataFrame) -> go.Figure:
    """Venta vs. arriendo por m² de vivienda por comuna, con la rentabilidad bruta anual."""
    titulo = "Venta vs. arriendo por comuna (vivienda, mediana por m²)"
    comunas = precios[(precios["nivel"] == "comuna") & (precios["tipo"] == VIVIENDA)]
    tabla = comunas.pivot_table(
        index="nombre", columns="operacion", values="precio_m2_mediana", aggfunc="first"
    )
    if not {"venta", "arriendo"} <= set(tabla.columns):
        return _sin_datos(titulo)
    tabla = tabla[["venta", "arriendo"]].astype("float64").dropna()
    if tabla.empty:
        return _sin_datos(titulo)
    tabla["rentabilidad"] = tabla["arriendo"] * 12 / tabla["venta"] * 100
    tabla = tabla.reset_index()
    figura = px.scatter(
        tabla,
        x="venta",
        y="rentabilidad",
        text=tabla["nombre"].str.title(),
        labels={"venta": "Venta: COP por m²", "rentabilidad": "Rentabilidad bruta anual (%)"},
        hover_data={"arriendo": ":,.0f", "venta": ":,.0f", "rentabilidad": ":.1f"},
        template=_PLANTILLA,
    )
    figura.update_traces(textposition="top center", textfont_size=9)
    figura.update_layout(title=titulo)
    return figura


def cobertura(cobertura: pd.DataFrame) -> go.Figure:
    """Barrios cubiertos por cada inmobiliaria (venta y arriendo juntos)."""
    titulo = "Barrios cubiertos por inmobiliaria"
    todas = cobertura[cobertura["operacion"] == "todas"].sort_values("barrios")
    if todas.empty:
        return _sin_datos(titulo)
    figura = px.bar(
        todas,
        x="barrios",
        y="fuente",
        orientation="h",
        color="fuente",
        color_discrete_map=COLORES_FUENTE,
        hover_data=["anuncios", "comunas", "pct_comuna_principal"],
        labels={"barrios": "Barrios", "fuente": "Inmobiliaria"},
        template=_PLANTILLA,
    )
    figura.update_layout(title=titulo, showlegend=False)
    return figura


def concentracion(cobertura_comuna: pd.DataFrame) -> go.Figure:
    """Mapa de calor: % de los anuncios de cada inmobiliaria en cada comuna."""
    titulo = "Dónde se concentra cada inmobiliaria (% de sus anuncios por comuna)"
    todas = cobertura_comuna[cobertura_comuna["operacion"] == "todas"]
    if todas.empty:
        return _sin_datos(titulo)
    tabla = todas.pivot_table(
        index="fuente", columns="nombre_comuna", values="pct_de_la_fuente", fill_value=0
    )
    tabla.columns = [str(c).title() for c in tabla.columns]
    figura = px.imshow(
        tabla,
        color_continuous_scale="Blues",
        aspect="auto",
        labels={"color": "% de sus anuncios", "x": "Comuna", "y": "Inmobiliaria"},
    )
    figura.update_layout(title=titulo, template=_PLANTILLA)
    return figura


def indice_relativo(economia: pd.DataFrame, operacion: str) -> go.Figure:
    """Índice de precio relativo a su barrio por inmobiliaria (1 = igual que su barrio)."""
    titulo = f"{operacion.title()}: precio relativo a su barrio (1 = igual que el barrio)"
    filas = economia[
        (economia["operacion"] == operacion)
        & (economia["tipo"] == VIVIENDA)
        & economia["indice_relativo_mediana"].notna()
    ].sort_values("indice_relativo_mediana")
    if filas.empty:
        return _sin_datos(titulo)
    figura = go.Figure(
        go.Bar(
            x=filas["indice_relativo_mediana"] - 1,
            base=1,
            y=filas["fuente"],
            orientation="h",
            marker_color=[COLORES_FUENTE.get(f, "#999999") for f in filas["fuente"]],
            customdata=filas[["indice_relativo_mediana", "anuncios_indice"]],
            hovertemplate="%{y}: %{customdata[0]:.3f} (%{customdata[1]} anuncios)<extra></extra>",
        )
    )
    figura.update_layout(template=_PLANTILLA)
    figura.add_vline(x=1, line_color="black", line_width=1)
    figura.update_layout(title=titulo, showlegend=False, xaxis_title="Índice relativo")
    return figura


def estratos(estratos: pd.DataFrame) -> go.Figure:
    """% de anuncios en estratos 1-3 y 4-6 por inmobiliaria, declarado e inferido aparte."""
    titulo = "Estratos por inmobiliaria (el inferido, en tono claro)"
    if estratos.empty:
        return _sin_datos(titulo)
    datos = estratos.assign(grupo=estratos["estrato"].map(lambda e: "1-3" if e <= 3 else "4-6"))
    suma = datos.groupby(["fuente", "grupo"])[["declarados", "inferidos"]].sum()
    total = suma.groupby("fuente").sum().sum(axis=1)
    figura = go.Figure()
    colores = {
        ("1-3", "declarado"): "#e6550d",
        ("1-3", "inferido"): "#fdd0a2",
        ("4-6", "declarado"): "#756bb1",
        ("4-6", "inferido"): "#dadaeb",
    }
    fuentes = sorted(total.index)
    for (grupo, origen), color in colores.items():
        columna = "declarados" if origen == "declarado" else "inferidos"
        valores = [
            float(suma[columna].get((f, grupo), 0)) / float(total[f]) * 100 if total[f] else 0.0
            for f in fuentes
        ]
        figura.add_bar(
            x=valores,
            y=fuentes,
            orientation="h",
            name=f"{grupo}, {origen}",
            marker_color=color,
            hovertemplate="%{y}: %{x:.1f} %<extra></extra>",
        )
    figura.update_layout(
        title=titulo,
        barmode="stack",
        template=_PLANTILLA,
        xaxis_title="% de los anuncios con estrato",
    )
    return figura


def compartidos(compartidos_fuentes: pd.DataFrame, nivel: str) -> go.Figure:
    """Parejas de inmuebles compartidos por par de inmobiliarias, con la diferencia de precio."""
    titulo = f"Inmuebles compartidos entre inmobiliarias (confianza {nivel} o mayor)"
    filas = compartidos_fuentes[compartidos_fuentes["nivel"] == nivel]
    if filas.empty:
        return _sin_datos(titulo)
    filas = filas.assign(par=filas["fuente_a"] + " – " + filas["fuente_b"]).sort_values("parejas")
    figura = px.bar(
        filas,
        x="parejas",
        y="par",
        orientation="h",
        color="diferencia_precio_mediana_pct",
        color_continuous_scale="OrRd",
        hover_data=["pct_mismo_precio", "pct_a_mas_barata"],
        labels={
            "parejas": "Parejas",
            "par": "Inmobiliarias",
            "diferencia_precio_mediana_pct": "Diferencia de precio (%)",
        },
        template=_PLANTILLA,
    )
    figura.update_layout(title=titulo, height=max(400, 22 * len(filas)))
    return figura


def evolucion(evolucion_precios: pd.DataFrame, operacion: str) -> go.Figure:
    """Mediana del precio por m² por semana, una línea por tipo de vivienda."""
    titulo = f"{operacion.title()}: precio por m² por semana (mediana)"
    filas = evolucion_precios[
        (evolucion_precios["operacion"] == operacion)
        & evolucion_precios["precio_m2_mediana"].notna()
    ]
    if filas.empty:
        return _sin_datos(titulo)
    filas = filas.assign(precio_m2_mediana=filas["precio_m2_mediana"].astype("float64"))
    figura = px.line(
        filas,
        x="semana",
        y="precio_m2_mediana",
        color="tipo",
        markers=True,
        labels={"precio_m2_mediana": "COP por m²", "semana": "Semana", "tipo": "Tipo"},
        template=_PLANTILLA,
    )
    figura.update_layout(title=titulo)
    return figura


def semanas(evolucion_precios: pd.DataFrame) -> list[str]:
    """Las semanas con datos de precios, ordenadas."""
    return sorted(str(s) for s in evolucion_precios["semana"].dropna().unique())


def rotacion(rotacion_inmobiliaria: pd.DataFrame) -> go.Figure:
    """Tasa de retiro semanal por inmobiliaria (qué tan rápido rota su inventario)."""
    titulo = "Tasa de retiro semanal por inmobiliaria (% de anuncios que salen)"
    filas = rotacion_inmobiliaria[rotacion_inmobiliaria["tasa_retiro_pct"].notna()]
    filas = filas[filas["operacion"].isin(["venta", "arriendo"])]
    if filas.empty:
        return _sin_datos(titulo)
    figura = px.line(
        filas,
        x="semana",
        y="tasa_retiro_pct",
        color="fuente",
        line_dash="operacion",
        markers=True,
        color_discrete_map=COLORES_FUENTE,
        labels={"tasa_retiro_pct": "Tasa de retiro (%)", "semana": "Semana"},
        template=_PLANTILLA,
    )
    figura.update_layout(title=titulo)
    return figura


def tabla_grupos(grupos_compartidos: pd.DataFrame, nivel: str) -> pd.DataFrame:
    """Los grupos anónimos en formato ancho: una fila por grupo, una columna de precio por fuente.

    Sin ids ni URL (spec §7.1). Si una fuente tiene dos unidades gemelas en el grupo, se
    muestra la más barata. ``Diferencia (%)`` es la del precio mayor frente al menor.
    """
    filas = grupos_compartidos[grupos_compartidos["nivel"] == nivel]
    if filas.empty:
        return pd.DataFrame()
    precios = filas.pivot_table(
        index="grupo", columns="fuente", values="precio", aggfunc="min"
    ).astype("float64")
    datos = filas.groupby("grupo").agg(
        operacion=("operacion", "first"),
        tipo=("tipo", "first"),
        barrio=("barrio", "first"),
        area=("area_m2", "median"),
        habitaciones=("habitaciones", "first"),
        estrato=("estrato", "max"),
    )
    diferencia = (precios.max(axis=1) / precios.min(axis=1) - 1) * 100
    tabla = datos.join(precios).assign(diferencia=diferencia.round(1)).reset_index()
    return tabla.rename(
        columns={
            "grupo": "Grupo",
            "operacion": "Operación",
            "tipo": "Tipo",
            "barrio": "Barrio",
            "area": "Área (m²)",
            "habitaciones": "Habitaciones",
            "estrato": "Estrato",
            "diferencia": "Diferencia (%)",
        }
    )


# ------------------------------------------------------------ Análisis de precios

UMBRAL_DISPERSION: Final = 40
"""Variación (%) desde la que un barrio se marca como disperso. Es orientativo: con más de
40 % la desviación estándar es casi la mitad de la media y el promedio deja de describir al
barrio."""
LECTURAS: Final = ("Favorece arrendar", "Intermedio", "Favorece comprar")
_COLUMNAS_NUMERICAS_MERCADO: Final = (
    "anuncios",
    "precio_m2_media",
    "precio_m2_mediana",
    "precio_m2_p25",
    "precio_m2_p75",
    "variacion_pct",
)
_COLUMNAS_ENTERAS_DISPERSION: Final = (
    "Anuncios",
    "Mediana (m²)",
    "Media (m²)",
    "Cuartil 25 (m²)",
    "Cuartil 75 (m²)",
    "Variación (%)",
)


def _mercado(mercado: pd.DataFrame, analisis: str, operacion: str) -> pd.DataFrame:
    """Las filas de un análisis y una operación, con las estadísticas como float."""
    filas = mercado[
        (mercado["analisis"] == analisis)
        & (mercado["operacion"] == operacion)
        & mercado["precio_m2_mediana"].notna()
    ]
    return filas.assign(
        **{
            c: filas[c].astype("Float64").to_numpy(dtype="float64", na_value=float("nan"))
            for c in _COLUMNAS_NUMERICAS_MERCADO
        }
    )


def dispersion_barrios(mercado: pd.DataFrame, operacion: str) -> go.Figure:
    """Precio por m² de cada barrio frente a su variación: arriba, el promedio engaña."""
    titulo = f"{operacion.title()}: ¿qué tan parejo es el precio dentro de cada barrio?"
    datos = _mercado(mercado, ANALISIS_DISPERSION, operacion)
    if datos.empty:
        return _sin_datos(titulo)
    figura = px.scatter(
        datos,
        x="precio_m2_mediana",
        y="variacion_pct",
        size="anuncios",
        hover_name="nombre",
        hover_data={
            "precio_m2_mediana": ":,.0f",
            "precio_m2_media": ":,.0f",
            "variacion_pct": ":.0f",
            "anuncios": True,
        },
        labels={
            "precio_m2_mediana": "Mediana, COP por m²",
            "precio_m2_media": "Media, COP por m²",
            "variacion_pct": "Variación (%)",
            "anuncios": "Anuncios",
        },
        template=_PLANTILLA,
    )
    figura.add_hline(
        y=UMBRAL_DISPERSION,
        line_dash="dot",
        annotation_text=f"Más de {UMBRAL_DISPERSION} %: el promedio engaña",
        annotation_position="top left",
    )
    figura.update_layout(title=titulo)
    return figura


def tabla_dispersion(mercado: pd.DataFrame, operacion: str) -> pd.DataFrame:
    """Los barrios del más al menos disperso, con la media y la mediana lado a lado."""
    datos = _mercado(mercado, ANALISIS_DISPERSION, operacion)
    if datos.empty:
        return pd.DataFrame()
    tabla = datos.sort_values("variacion_pct", ascending=False)[
        [
            "nombre",
            "comuna",
            "anuncios",
            "precio_m2_mediana",
            "precio_m2_media",
            "precio_m2_p25",
            "precio_m2_p75",
            "variacion_pct",
        ]
    ].rename(
        columns={
            "nombre": "Barrio",
            "comuna": "Comuna",
            "anuncios": "Anuncios",
            "precio_m2_mediana": "Mediana (m²)",
            "precio_m2_media": "Media (m²)",
            "precio_m2_p25": "Cuartil 25 (m²)",
            "precio_m2_p75": "Cuartil 75 (m²)",
            "variacion_pct": "Variación (%)",
        }
    )
    return tabla.round(0).astype({c: "int64" for c in _COLUMNAS_ENTERAS_DISPERSION})


def _barras(datos: pd.DataFrame, titulo: str, orden: list[str], etiqueta: str) -> go.Figure:
    """Barras de la mediana por categoría, con el rango entre los cuartiles 25 y 75."""
    figura = px.bar(
        datos.assign(
            arriba=datos["precio_m2_p75"] - datos["precio_m2_mediana"],
            abajo=datos["precio_m2_mediana"] - datos["precio_m2_p25"],
        ),
        x="categoria",
        y="precio_m2_mediana",
        error_y="arriba",
        error_y_minus="abajo",
        category_orders={"categoria": orden},
        hover_data={"anuncios": True, "precio_m2_mediana": ":,.0f", "categoria": False},
        labels={
            "categoria": etiqueta,
            "precio_m2_mediana": "COP por m² (mediana)",
            "anuncios": "Anuncios",
        },
        template=_PLANTILLA,
    )
    figura.update_layout(title=titulo)
    return figura


def rangos_area(mercado: pd.DataFrame, operacion: str) -> go.Figure:
    """Mediana del m² de vivienda por rango de área; las barras de error van de Q25 a Q75."""
    titulo = f"Vivienda en {operacion}: precio por m² según el área"
    datos = _mercado(mercado, ANALISIS_AREA, operacion)
    if datos.empty:
        return _sin_datos(titulo)
    return _barras(datos, titulo, list(RANGOS_AREA), "Área (m²)")


def precio_estratos(mercado: pd.DataFrame, operacion: str) -> go.Figure:
    """Mediana del m² de vivienda por estrato declarado; las barras de error van de Q25 a Q75."""
    titulo = f"Vivienda en {operacion}: precio por m² según el estrato"
    datos = _mercado(mercado, ANALISIS_ESTRATO, operacion)
    if datos.empty:
        return _sin_datos(titulo)
    orden = sorted(datos["categoria"].astype(str).unique())
    return _barras(datos, titulo, orden, "Estrato (solo anuncios que lo declaran)")


def tipos_por_comuna(mercado: pd.DataFrame, operacion: str) -> go.Figure:
    """Mediana del m² por tipo de inmueble en cada comuna (con 5 anuncios o más por celda)."""
    titulo = f"{operacion.title()}: precio por m² según el tipo de inmueble, por comuna"
    datos = _mercado(mercado, ANALISIS_TIPO, operacion)
    if datos.empty:
        return _sin_datos(titulo)
    datos = datos.assign(nombre=datos["nombre"].astype(str).str.title())
    figura = px.bar(
        datos.sort_values("nombre"),
        x="nombre",
        y="precio_m2_mediana",
        color="categoria",
        barmode="group",
        category_orders={"categoria": list(TIPOS_COMPARADOS)},
        hover_data={"anuncios": True, "precio_m2_mediana": ":,.0f"},
        labels={
            "nombre": "Comuna",
            "precio_m2_mediana": "COP por m² (mediana)",
            "categoria": "Tipo",
            "anuncios": "Anuncios",
        },
        template=_PLANTILLA,
    )
    figura.update_layout(title=titulo, xaxis_tickangle=-45)
    return figura


def precio_comunas(precios: pd.DataFrame, operacion: str) -> go.Figure:
    """Mediana del m² de vivienda en cada comuna, de la más barata a la más cara."""
    titulo = f"{operacion.title()}: precio por m² de vivienda en cada comuna (mediana)"
    comunas = precios[
        (precios["nivel"] == "comuna")
        & (precios["operacion"] == operacion)
        & (precios["tipo"] == VIVIENDA)
        & precios["precio_m2_mediana"].notna()
    ]
    if comunas.empty:
        return _sin_datos(titulo)
    orden = comunas.assign(
        precio_m2_mediana=comunas["precio_m2_mediana"].astype("float64"),
        nombre=comunas["nombre"].astype(str).str.title(),
    ).sort_values("precio_m2_mediana")
    figura = px.bar(
        orden,
        x="precio_m2_mediana",
        y="nombre",
        orientation="h",
        hover_data={"anuncios": True, "precio_m2_mediana": ":,.0f"},
        labels={
            "precio_m2_mediana": "COP por m² (mediana)",
            "nombre": "Comuna",
            "anuncios": "Anuncios",
        },
        template=_PLANTILLA,
    )
    figura.update_layout(title=titulo, height=max(400, 24 * len(orden)))
    return figura


def _lectura(rentabilidad: float, bajo: float, alto: float) -> str:
    if rentabilidad >= alto:
        return LECTURAS[2]
    return LECTURAS[0] if rentabilidad <= bajo else LECTURAS[1]


def _rentabilidad(precios: pd.DataFrame) -> pd.DataFrame:
    """Un barrio por fila con venta y arriendo del m², rentabilidad bruta anual y su lectura.

    Solo entran los barrios con mediana de venta **y** de arriendo de vivienda (cada una con
    5 anuncios o más). La lectura divide a los barrios en tres grupos iguales por rentabilidad.
    """
    vacia = pd.DataFrame(
        columns=["nombre", "comuna", "venta", "arriendo", "rentabilidad", "anios", "lectura"]
    )
    barrios = precios[
        (precios["nivel"] == "barrio")
        & (precios["tipo"] == VIVIENDA)
        & precios["precio_m2_mediana"].notna()
    ]
    if barrios.empty:
        return vacia
    medianas = barrios.pivot_table(
        index="codigo", columns="operacion", values="precio_m2_mediana", aggfunc="first"
    )
    if not {"venta", "arriendo"} <= set(medianas.columns):
        return vacia
    tabla = medianas[["venta", "arriendo"]].astype("float64").dropna().rename_axis(columns=None)
    if tabla.empty:
        return vacia
    nombres = barrios.drop_duplicates("codigo").set_index("codigo")
    tabla["nombre"] = nombres["nombre"].reindex(tabla.index)
    tabla["comuna"] = nombres["comuna"].reindex(tabla.index)
    tabla["rentabilidad"] = tabla["arriendo"] * 12 / tabla["venta"] * 100
    tabla["anios"] = 100 / tabla["rentabilidad"]
    bajo, alto = tabla["rentabilidad"].quantile([1 / 3, 2 / 3])
    tabla["lectura"] = tabla["rentabilidad"].map(lambda r: _lectura(r, bajo, alto))
    return tabla.sort_values("rentabilidad", ascending=False)


def rentabilidad_barrios(precios: pd.DataFrame, cuantos: int = 15) -> go.Figure:
    """Los barrios donde comprar rinde más y donde rinde menos (rentabilidad bruta anual)."""
    titulo = "Rentabilidad bruta anual por barrio: dónde favorece comprar y dónde arrendar"
    tabla = _rentabilidad(precios)
    if tabla.empty:
        return _sin_datos(titulo)
    mitad = min(cuantos, len(tabla) // 2) or len(tabla)
    figura = go.Figure()
    for nombre, filas, color in (
        (LECTURAS[0], tabla.tail(mitad), "#2c7fb8"),
        (LECTURAS[2], tabla.head(mitad), "#d95f0e"),
    ):
        figura.add_bar(
            x=filas["rentabilidad"],
            y=filas["nombre"],
            orientation="h",
            name=nombre,
            marker_color=color,
            customdata=filas[["anios"]],
            hovertemplate="%{y}: %{x:.1f} % al año (%{customdata[0]:.0f} años de arriendo "
            "para igualar la compra)<extra></extra>",
        )
    figura.update_layout(
        title=titulo,
        template=_PLANTILLA,
        xaxis_title="Rentabilidad bruta anual (%)",
        yaxis={"autorange": "reversed"},
        height=max(400, 22 * 2 * mitad),
    )
    return figura


def tabla_rentabilidad(precios: pd.DataFrame) -> pd.DataFrame:
    """Todos los barrios con venta y arriendo, de mayor a menor rentabilidad bruta."""
    tabla = _rentabilidad(precios)
    if tabla.empty:
        return pd.DataFrame()
    columnas = {
        "nombre": "Barrio",
        "comuna": "Comuna",
        "venta": "Venta (m²)",
        "arriendo": "Arriendo (m²)",
        "rentabilidad": "Rentabilidad bruta (%)",
        "anios": "Años de arriendo = compra",
        "lectura": "Lectura",
    }
    tabla = tabla.reset_index(drop=True)[list(columnas)].rename(columns=columnas)
    tabla = tabla.astype({"Venta (m²)": "int64", "Arriendo (m²)": "int64"})
    return tabla.round({"Rentabilidad bruta (%)": 1, "Años de arriendo = compra": 1})
