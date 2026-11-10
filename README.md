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
uv run observatorio scrape santafe                  # corrida completa (puede tardar más de 40 min)
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

Fuentes disponibles: `santafe` (Arrendamientos Santa Fe). Las demás se agregan en los siguientes planes de la [hoja de ruta](docs/superpowers/plans/2026-11-10-hoja-de-ruta.md).

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
