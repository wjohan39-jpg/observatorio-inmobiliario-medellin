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
