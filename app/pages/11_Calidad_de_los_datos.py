"""Página 11: calidad de los datos de cada inmobiliaria y de la limpieza."""

import _ruta  # noqa: F401  (agrega src/ al path si el paquete no está instalado)
import streamlit as st

from observatorio_inmobiliario.agregados import UMBRAL_PAREJA_DIFERENTE
from observatorio_inmobiliario.tablero import graficas, vista

vista.configurar("Calidad de los datos")
calidad = vista.tablas()["calidad_pipeline"]

st.title("Calidad de los datos")
st.markdown(
    "Qué tan completos, consistentes y limpios son los datos de cada inmobiliaria. Se mide "
    "sobre **todos** los anuncios de la semana, también los de otros municipios y los "
    "atípicos, antes de excluir nada del análisis."
)

if not graficas.hay_datos(calidad):
    vista.sin_datos("calidad de los datos")
    st.stop()

st.header("Datos faltantes")
st.plotly_chart(graficas.faltantes(calidad), width="stretch")
st.caption(
    "«Barrio declarado» es lo que escribe la inmobiliaria; «barrio oficial» es el que logró "
    "asignar la limpieza. Alnago y Puertabierta no publican estrato."
)

st.header("Atípicos y errores")
st.plotly_chart(graficas.atipicos(calidad), width="stretch")
st.caption(
    "La limpieza marca (sin borrar) los precios fuera de rango, las áreas de vivienda fuera de "
    "10 a 2.000 m² y los precios por m² extremos dentro de su grupo (cercas de Tukey con 3 "
    "rangos intercuartiles, en grupos de 30 anuncios o más). Un dato faltante nunca se marca. "
    "Solo atrapa extremos: un área equivocada pero plausible pasa sin marcarse."
)

st.header("Ubicación y nomenclatura de barrios")
st.plotly_chart(graficas.metodo_de_ubicacion(calidad), width="stretch")
st.plotly_chart(graficas.desacuerdo_de_ubicacion(calidad), width="stretch")
st.caption(
    "Solo se compara cuando el anuncio tiene coordenadas y su barrio declarado se puede "
    "resolver a un barrio oficial. Muchas inmobiliarias escriben zonas coloquiales («Poblado», "
    "«Laureles») más amplias que el barrio oficial: parte del desacuerdo es nomenclatura. Un "
    "desacuerdo de **comuna** es una inconsistencia más seria. Las coordenadas que quedan "
    "fuera del Valle de Aburrá o son un punto por defecto del sitio se descartan."
)
st.plotly_chart(graficas.grafias_por_barrio(calidad), width="stretch")
st.caption(
    "Promedio de grafías distintas (sin tildes ni mayúsculas) con que se nombra un barrio "
    "oficial. La fila «todas» mezcla las inmobiliarias: si sube, es que no se nombran igual "
    "entre ellas."
)

st.header("Duplicados")
resumen = graficas.resumen_duplicados(calidad)
if resumen is not None:
    a, b, c, d = st.columns(4)
    a.metric("Duplicados exactos", vista.entero(resumen["duplicados_exactos"]))
    b.metric("Parejas entre inmobiliarias", vista.entero(resumen["parejas"]))
    c.metric("Parejas ambiguas", vista.entero(resumen["parejas_ambiguas"]))
    d.metric(
        f"Con más de {UMBRAL_PAREJA_DIFERENTE:.0f} % de diferencia",
        vista.entero(resumen["parejas_dif_20"]),
    )
st.markdown(
    "Un **duplicado exacto** es el mismo anuncio (inmobiliaria, código y operación) repetido: "
    "se cuenta una vez. Lo que **no** se mide es la repetición con pequeñas variaciones dentro "
    "de una misma inmobiliaria. Entre inmobiliarias sí se emparejan los anuncios, pero sin una "
    "muestra revisada a mano no hay forma de saber cuántas parejas son correctas. Las "
    "*ambiguas* (unidades iguales de una misma torre) y las de *más del 20 % de diferencia de "
    "precio* son señales de posibles errores de emparejamiento, no una medida de calidad."
)

st.header("Tabla completa")
st.dataframe(graficas.tabla_calidad_pipeline(calidad), hide_index=True, width="stretch")
