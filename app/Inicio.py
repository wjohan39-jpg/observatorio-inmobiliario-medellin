"""Página 1: resumen del mercado inmobiliario de Medellín."""

import _ruta  # noqa: F401  (agrega src/ al path si el paquete no está instalado)
import streamlit as st

from observatorio_inmobiliario.tablero import graficas, vista
from observatorio_inmobiliario.tablero.formato import indicadores

vista.configurar("Resumen del mercado")
t = vista.tablas()

st.title("Observatorio inmobiliario de Medellín")
st.markdown(
    "Precios de vivienda, cobertura y propiedades compartidas de **9 inmobiliarias** de "
    f"Medellín, a partir de sus anuncios públicos. Datos de la semana **{vista.semana()}**. "
    "Venta y arriendo se analizan siempre por separado."
)

precios = t["precios_zona"]
ayudas = {"m² de vivienda en venta": "Mediana", "m² de vivienda en arriendo": "Mediana mensual"}
for columna, (etiqueta, valor) in zip(st.columns(5), indicadores(t), strict=True):
    columna.metric(etiqueta, valor, help=ayudas.get(etiqueta))

st.subheader("Precio por m² por barrio")
operacion = st.radio("Operación", vista.OPERACIONES, horizontal=True, key="operacion_inicio")
if graficas.hay_datos(precios):
    st.plotly_chart(graficas.mapa_barrios(precios, vista.geojson(), operacion), width="stretch")
    st.caption(
        "Mediana por barrio oficial, con al menos 5 anuncios con área. "
        "En gris, los barrios sin datos suficientes."
    )
else:
    vista.sin_datos("precios por barrio")
