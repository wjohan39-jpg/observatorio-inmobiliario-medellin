"""Página 1: resumen del mercado inmobiliario de Medellín."""

import _ruta  # noqa: F401  (agrega src/ al path si el paquete no está instalado)
import streamlit as st

from observatorio_inmobiliario.tablero import graficas, vista

vista.configurar("Resumen del mercado")
t = vista.tablas()

st.title("Observatorio inmobiliario de Medellín")
st.markdown(
    "Precios de vivienda, cobertura y propiedades compartidas de **9 inmobiliarias** de "
    f"Medellín, a partir de sus anuncios públicos. Datos de la semana **{vista.semana()}**. "
    "Venta y arriendo se analizan siempre por separado."
)

cobertura = t["cobertura_inmobiliaria"]
precios = t["precios_zona"]
evolucion = t["evolucion_precios"]


def _mediana_ciudad(operacion: str) -> str:
    filas = evolucion[(evolucion["operacion"] == operacion) & (evolucion["tipo"] == "vivienda")]
    filas = filas.dropna(subset=["precio_m2_mediana"])
    if filas.empty:
        return "—"
    valor = float(filas.sort_values("semana")["precio_m2_mediana"].iloc[-1])
    return vista.pesos(valor)


todas = cobertura[cobertura["operacion"] == "todas"]
barrios_con_precio = precios.loc[precios["nivel"] == "barrio", "codigo"].nunique()
columnas = st.columns(5)
columnas[0].metric("Anuncios analizados", vista.entero(int(todas["anuncios"].sum())))
columnas[1].metric("Barrios con precio", str(barrios_con_precio))
columnas[2].metric("m² de vivienda en venta", _mediana_ciudad("venta"), help="Mediana")
columnas[3].metric(
    "m² de vivienda en arriendo", _mediana_ciudad("arriendo"), help="Mediana mensual"
)
columnas[4].metric("Inmobiliarias", str(todas["fuente"].nunique()))

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
