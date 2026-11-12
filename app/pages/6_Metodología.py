"""Página 6: metodología, limitaciones y aviso legal."""

import streamlit as st

from observatorio_inmobiliario.tablero import vista

vista.configurar("Metodología")

st.title("Metodología")
st.markdown(
    f"Datos de la semana **{vista.semana()}**. El código completo, las pruebas y el notebook "
    "de análisis están en el repositorio de GitHub."
)

st.header("Fuentes")
st.markdown(
    "Los sitios web propios de **9 inmobiliarias** de Medellín: Alnago, Activo Urbano, "
    "Maxibienes, Nutibara, Panorama, Puertabierta, Santa Fe, Uribienes y Villacruz. Cada sitio "
    "tiene su propio adaptador: algunos leen una API JSON pública y otros leen el HTML.\n\n"
    "- Solo se extraen **datos de hecho**: precio, área, barrio, estrato, habitaciones, baños "
    "y coordenadas. No se guardan fotos, textos de los anuncios ni datos personales.\n"
    "- Se respeta `robots.txt`, se limita la velocidad de las peticiones y se usa un "
    "User-Agent que identifica el proyecto.\n"
    "- Una inmobiliaria más (Arango Tobón) se excluyó porque sus términos prohíben el scraping."
)

st.header("Limpieza")
st.markdown(
    "- **Ubicación:** cada anuncio se ubica en el barrio oficial del catálogo de la Alcaldía "
    "de Medellín. Primero por coordenadas; si no hay, por el nombre del barrio. Los nombres de "
    'zona ("Poblado", "Laureles") se ubican solo hasta la comuna.\n'
    "- **Atípicos:** se marcan los precios imposibles para su operación, las áreas imposibles "
    "para una vivienda y los precios por m² extremos frente a su grupo. Se excluyen del "
    "análisis, pero no se borran.\n"
    "- **Análisis:** solo anuncios de Medellín. Venta y arriendo siempre por separado, y los "
    "precios solo de vivienda (apartamento, apartaestudio y casa)."
)

st.header("Reglas de publicación")
st.markdown(
    "- **Mínimo de 5 anuncios:** cada estadística de precio se publica solo si resume 5 "
    "anuncios o más con ese dato. Con menos, la mediana es casi el precio de un anuncio.\n"
    "- **Índice de precio relativo:** el precio por m² de cada anuncio dividido por la mediana "
    "de su barrio. Así una inmobiliaria no parece cara solo por trabajar en El Poblado.\n"
    "- **Estrato inferido:** Alnago y Puertabierta no publican estrato. Se usa el más común de "
    "su barrio, que acierta en el 76 % de los casos comprobables, y se muestra aparte.\n"
    "- **Propiedades compartidas:** parejas con confianza alta, media o baja, según la "
    "distancia y los datos que coinciden. Nunca se presentan como seguras.\n"
    "- **Reputación:** el código consulta en vivo la API oficial de **Google Places**, cuyos "
    "términos no permiten guardar las calificaciones. Está desactivada en la versión publicada "
    "porque la API exige una cuenta de facturación; el indicador de reconocimiento usa entonces "
    "solo anuncios y barrios."
)

st.header("Limitaciones")
st.markdown(
    "- Son precios **publicados**, no precios de cierre, de 9 inmobiliarias, no de todo el "
    "mercado.\n"
    "- Maxibienes, Panorama y Activo Urbano no publican coordenadas: su barrio depende del "
    "nombre que escriben, y sus parejas compartidas nunca pasan de confianza media.\n"
    "- La evolución en el tiempo necesita varias semanas de datos."
)

st.header("Aviso")
st.markdown(
    "Proyecto **educativo y sin fines comerciales**. Si representas a una inmobiliaria y "
    "quieres retirar sus datos, abre un *issue* en el repositorio y será atendido."
)
