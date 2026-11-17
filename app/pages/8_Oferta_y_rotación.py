"""Página 8: oferta activa, su distribución y la rotación semanal."""

import _ruta  # noqa: F401  (agrega src/ al path si el paquete no está instalado)
import streamlit as st

from observatorio_inmobiliario.tablero import graficas, vista

vista.configurar("Oferta y rotación")
tablas = vista.tablas()
oferta, distribucion = tablas["oferta_zona"], tablas["distribucion_oferta"]
rotacion = tablas["rotacion_inmobiliaria"]

st.title("Oferta y rotación")
st.markdown(
    "Cuántos inmuebles hay publicados, cómo se reparten por precio y alcobas, y cuántos "
    "entran y salen cada semana. Son los anuncios de **9 inmobiliarias**, no todo el mercado "
    "de Medellín, y un anuncio **activo** es uno que apareció en el último scraping."
)

if not graficas.hay_datos(oferta) or not graficas.hay_datos(distribucion):
    vista.sin_datos("oferta")
    st.stop()

st.header("Inmuebles activos por zona, tipo y operación")
columna_operacion, columna_tipo = st.columns(2)
operacion = columna_operacion.radio(
    "Operación", vista.OPERACIONES, horizontal=True, key="operacion_oferta"
)
tipo = columna_tipo.selectbox("Tipo", graficas.tipos_oferta(oferta), key="tipo_oferta")

total, con_comuna, con_barrio = graficas.ubicacion_de_la_oferta(oferta, operacion, tipo)
if total:
    a, b, c = st.columns(3)
    a.metric("Anuncios activos", vista.entero(total))
    b.metric("Con comuna", f"{con_comuna / total:.0%}")
    c.metric("Con barrio", f"{con_barrio / total:.0%}")
    st.caption(
        "Los anuncios que no traen coordenadas válidas no se pueden ubicar en un barrio, así "
        "que las cifras por zona son un mínimo. No incluye los anuncios con precio atípico "
        "(cerca del 1 %)."
    )
else:
    vista.sin_datos("anuncios de ese tipo")

st.plotly_chart(graficas.oferta_por_tipo(oferta, operacion), width="stretch")
st.plotly_chart(graficas.oferta_comunas(oferta, operacion, tipo), width="stretch")
st.plotly_chart(graficas.oferta_barrios(oferta, operacion, tipo), width="stretch")
nivel = st.radio("Detalle", ("barrio", "comuna"), horizontal=True, key="nivel_oferta")
st.dataframe(
    graficas.tabla_oferta(oferta, nivel, operacion, tipo), hide_index=True, width="stretch"
)

st.header("Distribución por rango de precio y alcobas")
tipo_vivienda = st.selectbox(
    "Tipo de vivienda",
    sorted(set(distribucion["tipo"].astype(str)), key=lambda t: (t != "vivienda", t)),
    key="tipo_distribucion",
)
izquierda, derecha = st.columns(2)
izquierda.plotly_chart(
    graficas.distribucion_precio(distribucion, operacion, tipo_vivienda), width="stretch"
)
derecha.plotly_chart(
    graficas.distribucion_alcobas(distribucion, operacion, tipo_vivienda), width="stretch"
)
st.plotly_chart(graficas.precio_y_alcobas(distribucion, operacion, tipo_vivienda), width="stretch")
st.caption(
    "El arriendo es el canon mensual y la venta es el precio total (M = millones de pesos), "
    "por eso los rangos son distintos. «Sin dato» son anuncios que no publican alcobas."
)

st.header("Rotación: anuncios nuevos y retirados por semana")
tabla_rotacion = graficas.tabla_rotacion_semana(rotacion)
if tabla_rotacion.empty:
    st.info(
        "Para medir la rotación hacen falta al menos dos semanas de datos. Se llena sola con "
        "la ejecución semanal automática."
    )
else:
    st.plotly_chart(graficas.nuevos_y_retirados(rotacion), width="stretch")
    st.dataframe(tabla_rotacion, hide_index=True, width="stretch")
    st.caption(
        "Cada inmobiliaria se compara con su propia semana anterior con datos, y solo cuentan "
        "las que se pudieron comparar. **Retirado** significa que el anuncio ya no apareció "
        "en el scraping: no necesariamente que se vendió o se arrendó. La tasa de retiro es "
        "retirados sobre los anuncios de la semana anterior. El detalle por inmobiliaria está "
        "en la página Evolución."
    )
