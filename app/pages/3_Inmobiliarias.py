"""Página 3: inmobiliarias (preguntas 2 a 6)."""

import streamlit as st

from observatorio_inmobiliario.reputacion import reconocimiento
from observatorio_inmobiliario.tablero import graficas, vista

vista.configurar("Inmobiliarias")
t = vista.tablas()

st.title("Inmobiliarias")
st.markdown(
    "Las 9 inmobiliarias comparadas por cobertura, precios, estratos y reputación. "
    f"Datos de la semana **{vista.semana()}**."
)

cobertura, economia, reputacion_tab, reconocimiento_tab, estratos = st.tabs(
    ["Cobertura", "Economía", "Reputación", "Reconocimiento", "Estratos"]
)

with cobertura:
    tabla = t["cobertura_inmobiliaria"]
    if not graficas.hay_datos(tabla):
        vista.sin_datos("cobertura")
    else:
        todas = tabla[tabla["operacion"] == "todas"]
        minimo = st.slider(
            "Mostrar inmobiliarias con más de N barrios",
            0,
            int(todas["barrios"].max()),
            0,
            key="minimo_barrios",
        )
        st.plotly_chart(graficas.cobertura(tabla[tabla["barrios"] > minimo]), width="stretch")
        st.plotly_chart(graficas.concentracion(t["cobertura_comuna"]), width="stretch")

with economia:
    st.markdown(
        "Una inmobiliaria que trabaja en El Poblado siempre parece cara. Por eso se compara "
        "cada anuncio con la **mediana de su propio barrio**: un índice de 0,95 es un 5 % por "
        "debajo de su barrio."
    )
    operacion = st.radio("Operación", vista.OPERACIONES, horizontal=True, key="operacion_economia")
    st.plotly_chart(
        graficas.indice_relativo(t["economia_inmobiliaria"], operacion), width="stretch"
    )

reputacion = vista.reputacion_en_vivo()

with reputacion_tab:
    if reputacion is None:
        st.info(
            "La reputación se consulta en vivo en Google Places y no hay clave configurada "
            "o sedes registradas. El resto del dashboard funciona sin ella."
        )
    else:
        st.dataframe(
            reputacion.sort_values("calificacion", ascending=False),
            hide_index=True,
            width="stretch",
            column_config={
                "fuente": "Inmobiliaria",
                "sedes": "Sedes",
                "resenas": "Reseñas",
                "calificacion": st.column_config.NumberColumn("Calificación", format="%.2f ⭐"),
            },
        )
        st.caption(
            "Calificaciones de Google, consultadas en vivo y guardadas en memoria 6 horas. "
            "Con varias sedes, se suman las reseñas y se pondera la calificación."
        )

with reconocimiento_tab:
    indice = reconocimiento(t["cobertura_inmobiliaria"], reputacion)
    st.markdown(
        "Indicador propio de 0 a 1: el promedio de **anuncios**, **barrios cubiertos** y "
        "**reseñas en Google**, cada uno dividido por el máximo entre las 9 inmobiliarias."
    )
    if not indice.empty and not bool(indice["con_resenas"].iloc[0]):
        st.info("Sin datos de Google: el indicador usa solo anuncios y barrios.")
    st.dataframe(indice, hide_index=True, width="stretch")

with estratos:
    st.markdown(
        "Alnago y Puertabierta no publican estrato. Para ellas se usa el estrato más común "
        "de su barrio (acierta en el 76 % de los casos comprobables), en tono claro."
    )
    st.plotly_chart(graficas.estratos(t["estratos_inmobiliaria"]), width="stretch")
