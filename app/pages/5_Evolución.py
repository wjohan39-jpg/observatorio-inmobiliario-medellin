"""Página 5: evolución en el tiempo (pregunta 8)."""

import streamlit as st

from observatorio_inmobiliario.tablero import graficas, vista

vista.configurar("Evolución")
t = vista.tablas()
evolucion, rotacion = t["evolucion_precios"], t["rotacion_inmobiliaria"]

st.title("Evolución")
st.markdown(
    "Con el histórico semanal se mide cómo cambian los precios, cuánto dura publicado un "
    "inmueble y qué inmobiliaria rota su inventario más rápido. Cada inmobiliaria se compara "
    "con su propia semana anterior con datos, así un scraping fallido no parece un retiro."
)

semanas = graficas.semanas(evolucion)
if len(semanas) < 2:
    st.info(
        f"Por ahora hay una sola semana de datos ({', '.join(semanas) or 'ninguna'}). "
        "La evolución se llena sola con la ejecución semanal automática."
    )

operacion = st.radio("Operación", vista.OPERACIONES, horizontal=True, key="operacion_evolucion")
st.plotly_chart(graficas.evolucion(evolucion, operacion), width="stretch")
st.plotly_chart(graficas.rotacion(rotacion), width="stretch")

if graficas.hay_datos(rotacion):
    st.subheader("Rotación por inmobiliaria")
    st.dataframe(
        rotacion.rename(
            columns={
                "semana": "Semana",
                "fuente": "Inmobiliaria",
                "operacion": "Operación",
                "anuncios": "Anuncios",
                "nuevos": "Nuevos",
                "retirados": "Retirados",
                "tasa_retiro_pct": "Tasa de retiro (%)",
                "semanas_publicado_mediana": "Semanas publicado (mediana)",
                "comparables": "Comparables",
                "con_cambio_precio": "Cambiaron de precio",
                "cambio_precio_mediana_pct": "Cambio de precio (%)",
            }
        ),
        hide_index=True,
        width="stretch",
    )
