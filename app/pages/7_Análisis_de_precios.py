"""Página 7: análisis de precios (preguntas 1 a 6)."""

import _ruta  # noqa: F401  (agrega src/ al path si el paquete no está instalado)
import streamlit as st

from observatorio_inmobiliario.tablero import graficas, vista

vista.configurar("Análisis de precios")
tablas = vista.tablas()
precios, mercado = tablas["precios_zona"], tablas["mercado_precios"]

st.title("Análisis de precios")
st.markdown(
    "Seis preguntas sobre el precio de la vivienda en Medellín. Todo usa la **mediana** y "
    "los cuartiles, que no se mueven por unos pocos anuncios extremos, y cada cifra resume "
    "**5 anuncios o más**. Venta y arriendo nunca se mezclan."
)

if not graficas.hay_datos(precios) or not graficas.hay_datos(mercado):
    vista.sin_datos("análisis de precios")
    st.stop()

operacion = st.radio("Operación", vista.OPERACIONES, horizontal=True, key="operacion_precios")

st.header("1. ¿Cuánto cuesta el m² y dónde es más caro o más barato?")
st.plotly_chart(graficas.ranking_barrios(precios, operacion), width="stretch")
st.plotly_chart(graficas.precio_comunas(precios, operacion), width="stretch")
st.plotly_chart(graficas.precio_estratos(mercado, operacion), width="stretch")
st.caption(
    "El estrato solo está en los anuncios que lo declaran (cerca del 64 %). Las barras de "
    "error van del cuartil 25 al 75."
)

st.header("2. ¿Qué tan parejo es el precio dentro de cada barrio?")
st.plotly_chart(graficas.dispersion_barrios(mercado, operacion), width="stretch")
st.caption(
    "La variación es la desviación estándar dividida por la media. Un barrio muy por encima "
    "de la línea tiene anuncios muy distintos entre sí: su promedio no lo describe bien."
)
dispersion = graficas.tabla_dispersion(mercado, operacion)
st.dataframe(dispersion, hide_index=True, width="stretch")

st.header("3. ¿Cuánto cambia el precio según el tipo de inmueble?")
st.plotly_chart(graficas.tipos_por_comuna(mercado, operacion), width="stretch")
st.caption(
    "Solo aparecen las comunas con 5 anuncios o más de ese tipo. Los locales y las oficinas "
    "tienen pocos anuncios, así que faltan en muchas comunas."
)

st.header("4. ¿Cómo cambia el m² con la operación y el área?")
venta, arriendo = st.columns(2)
venta.plotly_chart(graficas.rangos_area(mercado, "venta"), width="stretch")
arriendo.plotly_chart(graficas.rangos_area(mercado, "arriendo"), width="stretch")
st.caption(
    "Vivienda de toda la ciudad, por el área que publica cada anuncio. Las barras de error "
    "van del cuartil 25 al 75; la venta se mide en millones y el arriendo en miles de pesos."
)

st.header("5. ¿Cuánto rinde un inmueble por barrio?")
st.plotly_chart(graficas.rentabilidad_barrios(precios), width="stretch")
st.plotly_chart(graficas.comparacion_comunas(precios), width="stretch")
st.caption(
    "Rentabilidad bruta = arriendo de un año ÷ precio de venta del m². Compara medianas de "
    "anuncios distintos y no descuenta administración, impuestos, vacancia ni mantenimiento."
)

st.header("6. ¿En qué barrios conviene más comprar que arrendar?")
st.markdown(
    "Se ordenan los barrios por rentabilidad y se dividen en tres grupos iguales. Donde la "
    "rentabilidad es alta, comprar sale relativamente barato frente a arrendar (**favorece "
    "comprar**); donde es baja, arrendar sale relativamente barato (**favorece arrendar**). "
    "Es una comparación **entre barrios**, no una recomendación: no incluye crédito, "
    "valorización ni costo de oportunidad."
)
rentabilidad = graficas.tabla_rentabilidad(precios)
if rentabilidad.empty:
    vista.sin_datos("rentabilidad por barrio")
else:
    lectura = st.selectbox("Lectura", ("Todas", *graficas.LECTURAS), key="lectura_precios")
    if lectura != "Todas":
        rentabilidad = rentabilidad[rentabilidad["Lectura"] == lectura]
    st.dataframe(rentabilidad, hide_index=True, width="stretch")
