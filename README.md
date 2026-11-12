# Observatorio inmobiliario de Medellín

[![CI](https://github.com/wjohan39-jpg/observatorio-inmobiliario-medellin/actions/workflows/ci.yml/badge.svg)](https://github.com/wjohan39-jpg/observatorio-inmobiliario-medellin/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.12%2B-blue)
[![Dashboard](https://img.shields.io/badge/dashboard-en%20vivo-2c7fb8)](https://wjohan39-jpg.github.io/observatorio-inmobiliario-medellin/)

Proyecto de análisis de datos de punta a punta: **extrae** anuncios de inmobiliarias de Medellín, los **valida y limpia**, los **guarda** con histórico semanal y los **analiza** en un dashboard web.

> **Estado:** en construcción. Ver la [hoja de ruta](docs/superpowers/plans/2026-11-10-hoja-de-ruta.md).

## Preguntas que responde

- ¿Cuánto cuesta el m² en cada barrio de Medellín?
- ¿Qué inmobiliarias cubren más barrios y en qué estratos trabajan?
- ¿Cuáles manejan las ventas y los arriendos más económicos?
- ¿Qué inmobiliarias publican el mismo inmueble y con qué diferencia de precio?
- ¿Cómo evolucionan los precios semana a semana?

## Uso

```bash
uv sync
uv run observatorio scrape puertabierta             # ~30 s
uv run observatorio scrape alnago                   # ~30 s
uv run observatorio scrape uribienes                # ~3 min
uv run observatorio scrape nutibara                 # ~5 min
uv run observatorio scrape maxibienes               # ~15 min
uv run observatorio scrape villacruz                # ~18 min
uv run observatorio scrape activourbano             # ~20 min
uv run observatorio scrape panorama                 # ~24 min
uv run observatorio scrape santafe                  # puede tardar más de 40 min (pide cada detalle)
uv run observatorio scrape santafe --max-paginas 2  # corrida corta de prueba (~1,5 min)
uv run observatorio scrape --help                   # todas las opciones
```

Los anuncios se guardan en `data/crudo/<fuente>/<año>-S<semana>.parquet`, un archivo por semana ISO. Si se corre dos veces en la misma semana, se sobrescribe el archivo, sin duplicar filas. Para leerlos:

```python
from pathlib import Path
from observatorio_inmobiliario.almacenamiento import leer_observaciones

df = leer_observaciones(Path("data/crudo"))  # todas las fuentes
df = leer_observaciones(Path("data/crudo"), "santafe")  # una sola fuente
```

Fuentes disponibles (corridas del 2026-11-11):

| Fuente | Inmobiliaria | Cómo se obtienen los datos | Anuncios | Tiempo |
|---|---|---|---|---|
| `santafe` | Arrendamientos Santa Fe | API JSON, con detalle de cada anuncio | — | > 40 min |
| `nutibara` | Arrendamientos Nutibara | API JSON que busca en un radio de ~3 km; se recorre una cuadrícula de 60 puntos | 982 | ~5 min |
| `uribienes` | Uribienes | API JSON, consultada municipio por municipio | 727 | ~3 min |
| `alnago` | Alnago | API JSON del mapa, una petición por municipio y operación (sin estrato) | 1.691 | ~30 s |
| `puertabierta` | Puertabierta | Datos de la página (Next.js), municipio por municipio; solo arriendo | 376 | ~30 s |
| `maxibienes` | Maxibienes | HTML del buscador, por operación y municipio (sin páginas de detalle) | 2.499 | ~15 min |
| `activourbano` | Activo Urbano | HTML del catálogo (WordPress), con detalle para estrato y parqueaderos | 478 | ~20 min |
| `panorama` | Arrendamientos Panorama | HTML (ASP), por operación, tipo y municipio; ficha solo para vivienda | 1.106 | ~24 min |
| `villacruz` | Arrendamientos Villacruz | Sitemap y página de detalle; solo inventario propio (sin ventas compartidas MLS) | 682 | ~18 min |

Todas cubren el Valle de Aburrá. Los tiempos dependen del límite de velocidad, que es deliberadamente conservador.

## Limpieza

```bash
uv run observatorio limpiar                    # limpia la última semana descargada
uv run observatorio limpiar --semana 2026-S46  # una semana en particular
uv run observatorio catalogo                   # actualiza el catálogo oficial de barrios
```

Une todas las fuentes de la semana en `data/limpio/<año>-S<semana>.parquet`. **No borra ningún anuncio ni cambia los datos crudos**: agrega columnas y marca lo dudoso, para que el análisis decida qué hacer con ello.

| Columnas | Qué agregan |
|---|---|
| `municipio_normalizado`, `en_valle`, `es_medellin` | Municipio con un solo nombre ("MEDELLIN" → "Medellín"); los corregimientos cuentan como Medellín |
| `codigo_barrio`, `barrio_normalizado`, `comuna`, `nombre_comuna`, `metodo_ubicacion` | Barrio y comuna **oficiales** de Medellín, y cómo se obtuvieron |
| `coordenadas_validas` | Falso si el punto cae fuera del valle o es un punto genérico (ver abajo) |
| `tipo_normalizado` | Uno de 12 tipos (apartamento, casa, local, oficina…) en lugar de las 30 variantes de los sitios |
| `precio_m2` | Precio por m², si hay precio y área |
| `es_atipico`, `motivo_atipico` | Precio imposible para la operación, área imposible para una vivienda, o precio por m² extremo frente a su grupo (operación y tipo) |

**Cómo se ubica cada anuncio.** El catálogo es el *límite barrio-vereda catastral* de la Alcaldía de Medellín: 349 barrios y veredas, con su comuna. Se tomó de su servidor de mapas el 2026-11-11 y está en `datos_referencia/`.

1. **Por coordenadas**, si las hay: el barrio cuyo polígono contiene el punto. Es lo más confiable.
2. **Por el nombre** que publica la inmobiliaria, si no hay coordenadas. Los nombres de zona ("Poblado", "Laureles", "Belén Parque") abarcan varios barrios oficiales, así que se ubican **solo hasta la comuna** (`datos_referencia/alias_barrios.csv`).

Un anuncio de otro municipio nunca recibe un barrio de Medellín, aunque su punto caiga dentro de la ciudad.

**Puntos genéricos.** Algunos sitios ponen un punto por defecto cuando no saben la dirección. En una semana hubo 58 anuncios en el mismo punto del centro, con 48 barrios distintos. Por eso un punto con 5 o más anuncios que nombran 5 o más barrios distintos no se usa para ubicar. Un edificio también repite su punto, pero con un solo barrio, y ese sí se usa.

Resultado de la semana 2026-S46: 8.589 anuncios; 5.700 de Medellín; el 96,5 % con comuna y el 75,9 % con barrio oficial; 1,3 % marcados como atípicos.

**Limitaciones:**
- Cuando un anuncio tiene coordenadas y nombre, los dos dan comunas distintas en el 14,5 % de los casos. Casi siempre son zonas en el borde entre dos comunas. Se usan las coordenadas.
- Maxibienes, Panorama y Activo Urbano no publican coordenadas, así que su barrio depende del nombre. Activo Urbano casi siempre da solo la zona.

## Propiedades compartidas

```bash
uv run observatorio compartidos                    # la última semana limpia
uv run observatorio compartidos --semana 2026-S46  # una semana en particular
```

Busca el mismo inmueble publicado por **distintas** inmobiliarias. Escribe dos tablas por semana; ninguna borra ni cambia anuncios:

- `data/compartidos/parejas/<semana>.parquet`: una fila por pareja, con la distancia, la diferencia de precio y un nivel de confianza.
- `data/compartidos/grupos_inmueble/<semana>.parquet`: una fila por anuncio emparejado, con su grupo en cada nivel (`grupo_alta`, `grupo_media`, `grupo_baja`).

**Qué se compara.** Entran los anuncios de Medellín que no son atípicos. Dos anuncios son candidatos si cumplen todo esto:
- son de fuentes distintas;
- tienen la misma operación, el mismo tipo y la misma comuna;
- su área difiere un 3 % o menos;
- tienen las mismas habitaciones, baños y estrato. Un dato que falta en un lado no descarta la pareja.

**El precio no se usa para emparejar.** La diferencia de precio es lo que se quiere medir, y usarla para emparejar sesgaría la respuesta.

| Confianza | Cuándo |
|---|---|
| Alta | Los dos tienen coordenadas y están a 100 m o menos |
| Media | Los dos tienen coordenadas y están a 300 m o menos; o a alguno le faltan, pero están en el mismo barrio oficial con habitaciones, baños y estrato conocidos e iguales |
| Baja | A alguno le faltan coordenadas, y están en el mismo barrio oficial pero falta alguno de esos datos |

Los umbrales salen de los datos. En la semana 2026-S46, los pares a 100 m o menos difieren 2,4 % en precio (mediana); a más de 1 km difieren 25 %, y ya son coincidencias de características.

**Apartamentos gemelos.** En una torre hay varias unidades iguales. Si un anuncio tiene más de una pareja en la misma otra fuente, no se sabe cuál es la buena: esas parejas se marcan como `ambigua` y bajan un nivel. Una baja ambigua se descarta.

**Grupos por nivel.** Cada nivel tiene sus propios grupos, armados solo con las parejas de ese nivel o uno mayor. Por ejemplo, `grupo_media` usa las parejas alta y media. Así, una cadena de parejas débiles no une grupos fuertes. El id del grupo es la clave del menor de sus anuncios (`fuente:id:operación`).

Resultado de la semana 2026-S46:

| Confianza | Parejas | Grupos (ese nivel o mayor) | Diferencia de precio mediana |
|---|---|---|---|
| Alta | 53 | 49 | 2,0 % |
| Media | 83 | 107 | 6,4 % |
| Baja | 94 | 155 | 11,6 % |

En una revisión a mano de 15 parejas alta al azar, 13 se ven como el mismo inmueble (mismo precio o casi, área idéntica, a menos de 80 m). En las parejas baja es frecuente que un precio sea el doble del otro: deben leerse como "posible" y no como "seguro".

**Limitaciones:**
- Sin coordenadas (Maxibienes, Panorama y Activo Urbano), el emparejamiento depende del barrio oficial y nunca pasa de confianza media.
- Los grupos media y baja pueden juntar varias unidades gemelas de una misma torre. El mayor grupo baja de la semana tiene 13 anuncios de 3 fuentes.

## Agregados

```bash
uv run observatorio agregados   # después de limpiar y compartidos
```

Resume la última semana limpia y todo el histórico en `data/agregados/`. **Son los únicos datos que se publican en este repositorio.** No tienen ids, URL, coordenadas ni textos de anuncios, y el guardado rechaza cualquier tabla que traiga esas columnas.

| Archivo | Pregunta | Qué tiene |
|---|---|---|
| `precios_zona` | 1. Precio por barrio | Mediana y cuartiles del precio y del precio por m², por barrio y comuna |
| `cobertura_inmobiliaria` | 2 y 6. Cobertura y reconocimiento | Anuncios, barrios y comunas de cada inmobiliaria, y su comuna principal |
| `cobertura_comuna` | 2. Dónde se concentra | % de los anuncios de cada inmobiliaria en cada comuna |
| `economia_inmobiliaria` | 3. Economía | Medianas de precio e índice de precio relativo a su barrio |
| `estratos_inmobiliaria` | 4. Estratos | Anuncios por estrato, declarados e inferidos por separado |
| `compartidos_fuentes` | 7. Propiedades compartidas | Parejas y diferencia de precio por par de inmobiliarias |
| `grupos_compartidos` | 7. Propiedades compartidas | Grupos anónimos: barrio, área, estrato y precio de cada inmobiliaria |
| `evolucion_precios` | 8. Evolución | Precio por m² por semana |
| `rotacion_inmobiliaria` | 8. Evolución | Nuevos, retirados, semanas publicado y cambios de precio por semana |

**Reglas del análisis:**
- **Base:** anuncios de Medellín que no son atípicos, uno por anuncio. Las filas repetidas por una fuente se cuentan una vez.
- **Solo vivienda en los precios:** apartamento, apartaestudio, casa y los tres juntos. Mezclar un local con un apartamento no dice nada del precio de un barrio.
- **Mínimo de publicación:** cada estadística de precio se publica solo si resume 5 anuncios o más **que tienen ese dato**. Por ejemplo, la mediana del m² exige 5 anuncios con área. Con menos, la mediana es casi el precio de un anuncio puntual. El barrio sigue contando en su comuna.
- **Índice de precio relativo:** es el precio por m² de cada anuncio dividido por la mediana de su barrio, en la misma operación y tipo. Así una inmobiliaria no parece cara solo por trabajar en El Poblado. Un índice de 1,10 significa un 10 % por encima de su barrio.
- **Estrato inferido:** Alnago y Puertabierta no publican estrato. Si en un barrio 5 anuncios o más declaran estrato y el más frecuente reúne el 60 % o más, ese estrato se asigna a los anuncios del barrio que no lo traen.
  - Probada con los anuncios que sí lo declaran, la regla acierta en el 76 %. Por eso el inferido va siempre en su propia columna.
- **Reputación (pregunta 5):** el módulo `reputacion.py` consulta en vivo la API oficial de Google Places (sus términos no permiten guardar calificaciones). Está **desactivada en la versión publicada**, porque la API exige una cuenta de facturación; se activa con una clave en `GOOGLE_PLACES_API_KEY`. Sin ella, el indicador de reconocimiento (pregunta 6) usa solo anuncios y barrios.

**Evolución:** la rotación se mide por inmobiliaria. Cada una se compara con su propia semana anterior con datos, así un scraping que falló, o una fuente que se agregó tarde, no parece un retiro masivo ni un inventario nuevo. La duración publicada excluye los anuncios que ya estaban en la primera semana de su inmobiliaria, porque no se sabe cuándo empezaron. Con una sola semana (2026-S46), estas tablas todavía no muestran retiros ni cambios.

## Hallazgos

Del [notebook de análisis exploratorio](notebooks/01_analisis_exploratorio.ipynb), con los datos de la semana 2026-S46 (vivienda en Medellín):

1. **El m² de vivienda en venta más caro cuesta 3,4 veces el más barato:** Villa Carlota (El Poblado) tiene una mediana de 10,4 millones por m², y Barrio Caicedo (comuna 9), 3,1 millones.
2. **Las comunas más caras rinden menos en arriendo.** La rentabilidad bruta anual es 7,6 % en El Poblado y llega a 9,9 % en Villa Hermosa y San Javier (11,8 % en Guayabal).
3. **Nutibara y Alnago son las de mayor cobertura** (183 y 179 barrios). Activo Urbano y Puertabierta son especialistas: el 88 % y el 78 % de sus anuncios están en El Poblado.
4. **Frente a su propio barrio, la mayoría cobra casi lo mismo** (índice entre 0,99 y 1,03). Activo Urbano en arriendo queda un 14 % por encima, y Nutibara un 4 % por debajo (Santa Fe, un 10 % por debajo, pero con solo 5 anuncios comparables).
5. **Nutibara y Panorama son las que más trabajan estratos 1 a 3** según el estrato que declaran (44 % y 40 %; Santa Fe llega al 76 %, pero con solo 38 anuncios). Activo Urbano casi no tiene (4 %). Alnago y Puertabierta no publican estrato: con el inferido de su barrio, Puertabierta queda en 2 %.
6. **Hay 53 parejas de alta confianza entre inmobiliarias, con una diferencia de precio mediana de solo 2 %.** Nutibara y Villacruz publican el mismo precio exacto en dos de cada tres inmuebles que comparten, lo que encaja con inventario compartido por MLS.

El notebook lee solo `data/agregados/`, así que se puede volver a correr desde un clon del repositorio:

```bash
uv sync --group analisis
uv run --group analisis jupyter nbconvert --to notebook --execute --inplace notebooks/01_analisis_exploratorio.ipynb
```

## Dashboard

**En vivo:** https://wjohan39-jpg.github.io/observatorio-inmobiliario-medellin/

El dashboard tiene dos versiones con la misma información. Las dos leen solo `data/agregados/`, así que nunca muestran ids, enlaces ni coordenadas de anuncios.

- **Sitio estático en GitHub Pages:** es el link de arriba. GitHub Actions (`.github/workflows/pages.yml`) lo genera con `observatorio sitio` y lo publica cada vez que cambian los datos agregados. Las gráficas son interactivas: zoom y detalle al pasar el mouse.
- **App de Streamlit** (`app/`): 6 páginas con selectores. Se corre en local:

  ```bash
  uv run streamlit run app/Inicio.py
  ```

| Página | Qué muestra |
|---|---|
| Inicio | Indicadores del mercado y mapa del precio por m² por barrio |
| Barrios | Barrios más caros y más baratos, y venta vs. arriendo por comuna |
| Inmobiliarias | Cobertura, concentración por comuna, precio relativo a su barrio, estratos y reconocimiento |
| Propiedades compartidas | Parejas por confianza y grupos anónimos con el precio de cada inmobiliaria |
| Evolución | Precios por semana y rotación de inventario |
| Metodología | Fuentes, limpieza, reglas de publicación, limitaciones y aviso |

## Desarrollo

Requiere [uv](https://docs.astral.sh/uv/).

```bash
uv sync                 # instala dependencias
uv run pytest           # corre las pruebas
uv run ruff check .     # linter
uv run mypy             # verificación de tipos
```

## Aviso

Proyecto educativo y sin fines comerciales. Solo se recolectan datos de hecho que están publicados (precio, área, barrio, estrato), respetando `robots.txt` y con un límite de velocidad en las peticiones. No se guardan fotos, textos de los anuncios ni datos personales. Si representas a una inmobiliaria y quieres que retiremos tus datos, abre un *issue*.
