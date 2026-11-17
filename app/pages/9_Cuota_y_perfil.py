"""Página 9: cuota de inventario, concentración, perfil y calidad de datos de cada inmobiliaria."""

import _ruta  # noqa: F401  (agrega src/ al path si el paquete no está instalado)
import streamlit as st

from observatorio_inmobiliario.tablero import graficas, vista

vista.configurar("Cuota y perfil")
tablas = vista.tablas()
cuota, perfil = tablas["cuota_zona"], tablas["perfil_inmobiliaria"]
calidad, estratos = tablas["calidad_inmobiliaria"], tablas["estratos_inmobiliaria"]

st.title("Cuota, perfil y calidad de las inmobiliarias")
st.markdown(
    "Qué parte del inventario tiene cada inmobiliaria, qué tan concentrado está, en qué se "
    "especializa y qué tan completos son sus datos. La cuota es la del **inventario "
    "observado en las 9 inmobiliarias**, no la del mercado: faltan otras inmobiliarias y los "
    "particulares. Una propiedad publicada por varias inmobiliarias cuenta en cada una."
)

if not graficas.hay_datos(cuota):
    vista.sin_datos("cuota por inmobiliaria")
    st.stop()

semanas = {str(t["semana"].iloc[0]) for t in (cuota, perfil, calidad, estratos) if not t.empty}
if len(semanas) > 1:
    st.info(
        "Las tablas de esta página vienen de semanas distintas "
        f"({', '.join(sorted(semanas))}). Se alinean con la próxima ejecución semanal completa."
    )

st.header("Cuota de inventario")
operacion = st.radio(
    "Operación", ("todas", "venta", "arriendo"), horizontal=True, key="operacion_cuota"
)
st.plotly_chart(graficas.cuota_total(cuota, operacion), width="stretch")
hhi = graficas.hhi_ciudad(cuota, operacion)
if hhi is not None:
    st.metric("HHI de toda la ciudad", vista.entero(hhi))

st.subheader("Cuota por zona")
nivel = st.radio("Zona", ("barrio", "comuna"), horizontal=True, key="nivel_cuota")
st.plotly_chart(graficas.cuota_zonas(cuota, nivel, operacion), width="stretch")
zonas = graficas.zonas_de_cuota(cuota, nivel, operacion)
if not zonas.empty:
    elegida = st.selectbox(
        "Ver una zona",
        zonas["codigo"].tolist(),
        format_func=lambda c: str(zonas.loc[zonas["codigo"] == c, "nombre"].iloc[0]).title(),
        key="zona_cuota",
    )
    st.dataframe(
        graficas.tabla_cuota(cuota, nivel, operacion, str(elegida)),
        hide_index=True,
        width="stretch",
    )
st.caption(
    "Solo los anuncios con coordenadas o barrio reconocido cuentan por zona (cerca del 50 % en "
    "barrios y del 64 % en comunas), y varía mucho por inmobiliaria: las que casi no traen "
    "ubicación aparecen subrepresentadas."
)

st.header("Concentración: índice HHI")
st.markdown(
    "El **HHI** es la suma de los cuadrados de las cuotas (en %), de 0 a 10.000: con 9 "
    "inmobiliarias parejas sería 1.111, y con una sola, 10.000. Como referencia, menos de "
    f"{vista.entero(graficas.UMBRALES_HHI[0])} es poco concentrado y más de "
    f"{vista.entero(graficas.UMBRALES_HHI[1])} "
    "es muy concentrado. Solo se calcula en zonas con "
    f"{graficas.MINIMO_HHI} anuncios o más."
)
st.plotly_chart(graficas.concentracion_hhi(cuota, nivel, operacion), width="stretch")
st.dataframe(graficas.tabla_hhi(cuota, nivel, operacion), hide_index=True, width="stretch")
st.caption(
    "Mide la concentración **dentro de estas 9 inmobiliarias**; no dice nada de las que no "
    "se scrapean."
)

st.header("Perfil: en qué se especializa cada inmobiliaria")
st.dataframe(graficas.tabla_perfil(perfil, estratos), hide_index=True, width="stretch")
st.plotly_chart(graficas.perfil_operacion(perfil), width="stretch")
venta, arriendo = st.columns(2)
venta.plotly_chart(graficas.perfil_tipos(perfil, "venta"), width="stretch")
arriendo.plotly_chart(graficas.perfil_tipos(perfil, "arriendo"), width="stretch")
st.plotly_chart(graficas.estratos(estratos), width="stretch")
st.caption(
    "Alnago y Puertabierta no publican estrato; en el gráfico, el estrato inferido va en tono "
    "claro. El precio de cada inmobiliaria frente a su barrio está en la página Inmobiliarias."
)

st.header("Calidad de los datos")
st.plotly_chart(graficas.calidad_datos(calidad), width="stretch")
st.dataframe(graficas.tabla_calidad(calidad), hide_index=True, width="stretch")
st.caption(
    "Porcentaje de los anuncios de vivienda que trae cada dato. «Coordenadas» son las válidas "
    "y «Estrato» el declarado: algunos sitios no publican coordenadas ni estrato, y entonces "
    "el barrio se deduce del nombre. Fotos y descripciones no se miden porque el proyecto no "
    "las guarda."
)
