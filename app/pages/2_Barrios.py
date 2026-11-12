"""Página 2: barrios y comunas (pregunta 1)."""

import streamlit as st

from observatorio_inmobiliario.tablero import graficas, vista

vista.configurar("Barrios")
precios = vista.tablas()["precios_zona"]

st.title("Barrios")
st.markdown(
    "¿Cuánto cuesta el m² de vivienda en cada barrio? Se usa la **mediana**, que no se mueve "
    "por unos pocos anuncios extremos, y solo se publica con 5 anuncios o más."
)

if not graficas.hay_datos(precios):
    vista.sin_datos("precios por barrio")
    st.stop()

operacion = st.radio("Operación", vista.OPERACIONES, horizontal=True, key="operacion_barrios")
st.plotly_chart(graficas.ranking_barrios(precios, operacion), width="stretch")

st.subheader("Venta y arriendo por comuna")
st.plotly_chart(graficas.comparacion_comunas(precios), width="stretch")
st.caption(
    "Rentabilidad bruta = arriendo de un año ÷ precio de venta del m². Es una orientación: "
    "compara medianas de anuncios distintos y no descuenta gastos ni vacancia."
)

st.subheader("Todos los barrios")
tipo = st.selectbox("Tipo", vista.TIPOS, key="tipo_barrios")
nivel = st.radio("Nivel", ("barrio", "comuna"), horizontal=True, key="nivel_barrios")
tabla = precios[
    (precios["nivel"] == nivel) & (precios["operacion"] == operacion) & (precios["tipo"] == tipo)
]
st.dataframe(
    tabla[["nombre", "comuna", "anuncios", "precio_mediana", "precio_m2_mediana"]]
    .sort_values("precio_m2_mediana", ascending=False)
    .rename(
        columns={
            "nombre": "Nombre",
            "comuna": "Comuna",
            "anuncios": "Anuncios",
            "precio_mediana": "Precio (mediana)",
            "precio_m2_mediana": "Precio por m² (mediana)",
        }
    ),
    hide_index=True,
    width="stretch",
)
