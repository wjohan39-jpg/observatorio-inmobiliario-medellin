"""Página 10: nichos sin cobertura, anuncios bajo o sobre el mercado y barrios para invertir."""

import _ruta  # noqa: F401  (agrega src/ al path si el paquete no está instalado)
import streamlit as st

from observatorio_inmobiliario.agregados import UMBRAL_ALTO, UMBRAL_BAJO
from observatorio_inmobiliario.tablero import graficas, vista

vista.configurar("Oportunidades y nichos")
tablas = vista.tablas()
cuota, cobertura_est = tablas["cuota_zona"], tablas["cobertura_estrato"]
desvio, precios = tablas["desvio_precio"], tablas["precios_zona"]

st.title("Oportunidades y nichos")
st.markdown(
    "Dónde hay poca cobertura de inmobiliarias, qué parte de los anuncios está lejos del "
    "precio de su barrio y qué barrios combinan precio y rentabilidad. Todo es sobre el "
    "**inventario de las 9 inmobiliarias que se scrapean**, no sobre todo el mercado, y es una "
    "orientación para investigar, no una recomendación de compra."
)

if not graficas.hay_datos(cuota) or not graficas.hay_datos(desvio):
    vista.sin_datos("oportunidades y nichos")
    st.stop()

operacion = st.radio("Operación", vista.OPERACIONES, horizontal=True, key="operacion_nichos")

st.header("Nichos: barrios con poca cobertura")
cobertura = graficas.cobertura_barrios(cuota, vista.geojson(), operacion)
resumen = graficas.resumen_cobertura(cobertura)
a, b, c, d = st.columns(4)
a.metric("Barrios urbanos", vista.entero(resumen["urbanos"]))
b.metric("Sin anuncios", vista.entero(resumen["sin_anuncios"]))
c.metric("Con 1 inmobiliaria", vista.entero(resumen["una"]))
d.metric("Con 3 o más", vista.entero(resumen["tres_o_mas"]))
st.plotly_chart(graficas.mapa_cobertura(cuota, vista.geojson(), operacion), width="stretch")
maximo = st.selectbox("Cubiertos por como máximo", (0, 1, 2), index=1, key="maximo_nichos")
st.dataframe(
    graficas.tabla_nichos(cuota, vista.geojson(), operacion, int(maximo)),
    hide_index=True,
    width="stretch",
)
st.caption(
    "«Sin cobertura» significa sin anuncios de estas 9 inmobiliarias: puede ser un barrio poco "
    "residencial, o que su oferta la publican particulares u otras inmobiliarias. Solo los "
    "anuncios con coordenadas válidas se ubican en un barrio (cerca del 50 %), así que los "
    "barrios con poca cobertura pueden estar subestimados."
)

st.subheader("Estratos")
st.plotly_chart(graficas.cobertura_estratos(cobertura_est, operacion), width="stretch")
st.plotly_chart(graficas.estratos_por_comuna(cobertura_est, operacion), width="stretch")
st.caption(
    "Solo cuentan los anuncios que declaran estrato (cerca del 64 %). Un 0 no prueba que ese "
    "estrato exista en esa comuna: el proyecto no tiene el estrato oficial de cada zona. "
    "El color del primer gráfico es el número de inmobiliarias que publican ese estrato."
)

st.header("Anuncios bajo o sobre el mercado de su barrio")
ciudad = graficas.resumen_desvio(desvio, operacion)
if ciudad is not None:
    x, y = st.columns(2)
    x.metric(f"Bajo el mercado (≤ {UMBRAL_BAJO:.0%})", f"{ciudad['pct_bajo']:.1f} %")
    y.metric(f"Sobre el mercado (≥ {UMBRAL_ALTO:.0%})", f"{ciudad['pct_alto']:.1f} %")
st.markdown(
    "Se compara el precio por m² de cada anuncio con la **mediana de su barrio**, en la misma "
    "operación y tipo (apartamento, apartaestudio o casa), con 5 comparables o más. Los "
    "resultados son **conteos**: no se publica ningún anuncio concreto."
)
st.plotly_chart(graficas.desvio_zonas(desvio, operacion, "bajo"), width="stretch")
st.plotly_chart(graficas.desvio_zonas(desvio, operacion, "alto"), width="stretch")
st.plotly_chart(graficas.desvio_inmobiliarias(desvio, operacion), width="stretch")
st.dataframe(graficas.tabla_desvio(desvio, operacion), hide_index=True, width="stretch")
st.warning(
    "Un precio bajo **no prueba una ganga** ni uno alto una sobrevaloración: la comparación "
    "no conoce el estado, el piso, la antigüedad ni las alcobas, y muchos anuncios están "
    "desactualizados. Con un 20 % de margen, cerca de 1 de cada 5 anuncios queda por cada "
    "lado solo por la dispersión normal de los precios. Sirve para saber dónde mirar."
)

st.header("Inversión: precio y rentabilidad por barrio")
st.plotly_chart(graficas.rentabilidad_barrios(precios), width="stretch")
st.dataframe(graficas.tabla_rentabilidad(precios), hide_index=True, width="stretch")
st.caption(
    "Rentabilidad bruta = arriendo de un año ÷ precio de venta del m², sin administración, "
    "impuestos ni vacancia. **Falta la liquidez** (cuánto tarda en salir un anuncio): necesita "
    "varias semanas de datos y se sumará cuando existan."
)
