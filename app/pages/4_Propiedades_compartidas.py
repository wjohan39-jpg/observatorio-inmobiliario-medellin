"""Página 4: propiedades compartidas entre inmobiliarias (pregunta 7)."""

import _ruta  # noqa: F401  (agrega src/ al path si el paquete no está instalado)
import streamlit as st

from observatorio_inmobiliario.agregados import MINIMO_PARES_PRECIO
from observatorio_inmobiliario.tablero import graficas, vista

vista.configurar("Propiedades compartidas")
t = vista.tablas()
fuentes, grupos = t["compartidos_fuentes"], t["grupos_compartidos"]
compartidas = t["compartidas_inmobiliaria"]

st.title("Propiedades compartidas")
st.markdown(
    "El mismo inmueble publicado por **dos o más inmobiliarias**. Se emparejan anuncios por "
    "cercanía (si tienen coordenadas), barrio oficial, área (±3 %), habitaciones, baños y "
    "estrato. **El precio no se usa para emparejar**: es lo que se quiere comparar."
)

with st.expander("¿Qué significa cada nivel de confianza?"):
    st.markdown(
        "- **Alta:** los dos anuncios tienen coordenadas y están a 100 m o menos.\n"
        "- **Media:** están a 300 m o menos, o les faltan coordenadas pero están en el mismo "
        "barrio con habitaciones, baños y estrato iguales.\n"
        "- **Baja:** les faltan coordenadas y están en el mismo barrio, pero falta algún dato.\n\n"
        "Cuando una inmobiliaria tiene dos unidades gemelas de la misma torre, no se sabe cuál "
        "es la pareja: la confianza baja un nivel. Los niveles son acumulados: *media* incluye "
        "las parejas *alta*."
    )

if not graficas.hay_datos(fuentes):
    vista.sin_datos("propiedades compartidas")
    st.stop()

nivel = st.radio(
    "Confianza mínima", ("alta", "media", "baja"), horizontal=True, key="nivel_compartidos"
)
del_nivel = fuentes[fuentes["nivel"] == nivel]
columnas = st.columns(3)
columnas[0].metric("Parejas", vista.entero(int(del_nivel["parejas"].sum())))
columnas[1].metric("Grupos", vista.entero(grupos.loc[grupos["nivel"] == nivel, "grupo"].nunique()))
columnas[2].metric("Pares de inmobiliarias", str(len(del_nivel)))

st.plotly_chart(graficas.compartidos(fuentes, nivel), width="stretch")
st.caption(
    "El color es la diferencia de precio mediana entre las dos inmobiliarias. Con pocas "
    "parejas, esa mediana es poco estable: mira la columna de parejas."
)

st.subheader("Cuánto inventario comparte cada inmobiliaria")
semanas = {str(x["semana"].iloc[0]) for x in (fuentes, grupos, compartidas) if not x.empty}
if len(semanas) > 1:
    st.info(
        "Las tablas de esta página vienen de semanas distintas "
        f"({', '.join(sorted(semanas))}). Se alinean con la próxima ejecución semanal completa."
    )
resumen = graficas.resumen_compartidas(compartidas, nivel)
if resumen is None:
    vista.sin_datos("inventario compartido por inmobiliaria")
else:
    a, b, c = st.columns(3)
    a.metric("Inmuebles en más de una inmobiliaria", vista.entero(resumen["inmuebles"]))
    b.metric("Anuncios compartidos", vista.entero(resumen["compartidos"]))
    c.metric("Parte del inventario", f"{resumen['pct']:.1f} %".replace(".", ","))
    st.plotly_chart(graficas.compartidas_por_inmobiliaria(compartidas, nivel), width="stretch")
    st.plotly_chart(graficas.matriz_compartidas(compartidas, nivel), width="stretch")
    st.caption(
        "Es probablemente un mínimo: para emparejar se exigen comuna, tipo, área, alcobas y "
        "baños iguales, y las inmobiliarias que casi no publican coordenadas se emparejan "
        "menos. Villacruz muestra solo su inventario propio."
    )

st.subheader("¿Quién publica más caro o más barato el mismo inmueble?")
st.plotly_chart(graficas.precio_relativo(compartidas, nivel), width="stretch")
st.dataframe(graficas.tabla_compartidas(compartidas, nivel), hide_index=True, width="stretch")
st.caption(
    "Positivo: publica por encima de la otra inmobiliaria. Solo aparecen las que tienen "
    f"{MINIMO_PARES_PRECIO} parejas con precio o más. El número entre paréntesis son las "
    "parejas: con pocas, un par de casos decide. Una diferencia grande puede ser un "
    "emparejamiento equivocado (otra unidad del mismo edificio) o un precio desactualizado, "
    "y la media se mueve mucho más que la mediana por esos casos."
)

st.subheader("Grupos")
st.markdown(
    "Cada fila es un inmueble con el precio que publica cada inmobiliaria. Los grupos son "
    "anónimos: no se muestran enlaces ni textos de los anuncios."
)
st.dataframe(graficas.tabla_grupos(grupos, nivel), hide_index=True, width="stretch")
