# Observatorio inmobiliario de Medellín

[![CI](https://github.com/wjohan39-jpg/observatorio-inmobiliario-medellin/actions/workflows/ci.yml/badge.svg)](https://github.com/wjohan39-jpg/observatorio-inmobiliario-medellin/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.12%2B-blue)

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
