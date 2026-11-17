"""Página 12: geografía de los precios: clústeres, distancia a los centros y municipios."""

import _ruta  # noqa: F401  (agrega src/ al path si el paquete no está instalado)
import streamlit as st

from observatorio_inmobiliario.tablero import graficas, vista

vista.configurar("Geografía")
tablas = vista.tablas()
precios, clusteres = tablas["precios_zona"], tablas["clusteres_espaciales"]
zonas = tablas["precios_municipio"]

st.title("Geografía de los precios")
st.markdown(
    "Cómo se reparten los precios en el espacio: dónde se agrupan los barrios caros o baratos, "
    "qué pasa al alejarse de los centros y cómo se compara Medellín con El Poblado, Laureles y "
    "los municipios vecinos. Se usa la **mediana** del precio por m² de vivienda, con 5 "
    "anuncios o más por cifra."
)

if not graficas.hay_datos(precios) or not graficas.hay_datos(zonas):
    vista.sin_datos("geografía de los precios")
    st.stop()

operacion = st.radio("Operación", vista.OPERACIONES, horizontal=True, key="operacion_geo")

st.header("Mapa de precios por barrio")
st.plotly_chart(graficas.mapa_barrios(precios, vista.geojson(), operacion), width="stretch")
st.caption(
    "Por barrio oficial y no por punto: solo el 50 % de los anuncios tiene coordenadas, y las "
    "coordenadas de anuncios individuales no se publican. En gris, barrios sin datos suficientes."
)

st.header("¿Hay clústeres espaciales? Autocorrelación (Moran)")
resumen = graficas.resumen_moran(clusteres, operacion)
if resumen is None:
    vista.sin_datos("autocorrelación espacial")
else:
    a, b, c = st.columns(3)
    a.metric("Moran's I", f"{resumen['i']:.2f}".replace(".", ","))
    b.metric("p (permutaciones)", f"{resumen['p']:.3f}".replace(".", ","))
    c.metric("Barrios analizados", vista.entero(resumen["barrios"]))
    st.markdown(
        "El **índice de Moran** va aproximadamente de −1 a 1: positivo significa que los "
        "barrios con precios parecidos están **juntos**, cerca de 0 que no hay patrón y "
        "negativo que se alternan. La significancia se calcula por permutaciones. El mapa "
        "muestra los clústeres locales: **alto-alto** son barrios caros rodeados de barrios "
        "caros, **bajo-bajo** baratos entre baratos; **alto-bajo** y **bajo-alto** son barrios "
        "que contrastan con su entorno."
    )
    st.plotly_chart(graficas.mapa_clusteres(clusteres, vista.geojson(), operacion), width="stretch")
    st.dataframe(graficas.tabla_clusteres(clusteres, operacion), hide_index=True, width="stretch")
    st.caption(
        "Vecinos son los barrios con los que comparte borde o vértice, solo entre los que "
        "tienen datos. No se corrige por comparaciones múltiples: con muchos barrios, algún "
        "clúster local puede salir significativo por azar, y el resultado depende de cómo se "
        "defina «vecino»."
    )

st.header("Distancia a los centros")
centro = st.selectbox("Centro de referencia", list(graficas.CENTROS), key="centro_geo")
st.plotly_chart(
    graficas.distancia_al_centro(precios, vista.geojson(), operacion, centro), width="stretch"
)
st.dataframe(
    graficas.correlacion_distancia(precios, vista.geojson()), hide_index=True, width="stretch"
)
st.caption(
    "Spearman entre la distancia en línea recta (centroide del barrio) y el precio por m²: "
    "**negativo** si el precio baja al alejarse, **positivo** si sube. Medellín tiene varios "
    "centros, por eso se mide contra tres; los puntos de referencia son aproximados. Es una "
    "asociación entre barrios, no un efecto: la distancia se mezcla con el estrato y la zona. "
    "No hay medida de ejes viales porque el proyecto no tiene datos de vías."
)

st.header("Poblado, Laureles y los municipios")
col_tipo, col_estrato = st.columns(2)
tipo = col_tipo.selectbox("Tipo", graficas.TIPOS_ZONA, key="tipo_zona")
estrato = col_estrato.selectbox("Estrato declarado", graficas.ESTRATOS_ZONA, key="estrato_zona")
st.plotly_chart(graficas.comparacion_zonas(zonas, operacion, tipo, estrato), width="stretch")
st.dataframe(
    graficas.tabla_zonas(zonas, operacion, tipo, estrato), hide_index=True, width="stretch"
)
st.caption(
    "Las barras de error van del cuartil 25 al 75. Medellín entero incluye a El Poblado y a "
    "Laureles, que son comunas, no municipios. Cada inmobiliaria cubre distinto cada "
    "municipio, así que con pocos anuncios la mediana es poco estable: mira la columna de "
    "anuncios y compara dentro del mismo estrato. Rionegro y otros municipios del Oriente no "
    "son del Valle de Aburrá."
)
