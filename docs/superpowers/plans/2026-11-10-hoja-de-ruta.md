# Hoja de ruta: Observatorio inmobiliario de Medellín

**Spec:** `docs/superpowers/specs/2026-11-10-scraper-inmobiliario-medellin-design.md`

El proyecto se divide en planes. Cada uno produce software que funciona y se puede probar por sí solo. Cada plan se escribe en detalle cuando termina el anterior, porque así aprovecha lo aprendido.

| # | Plan | Entrega | Fases del spec |
|---|---|---|---|
| 1 | **Fundación y primer scraper** | Repo con calidad profesional (CI, pruebas, linter), modelo `AnuncioNormalizado`, cliente HTTP cortés, adaptador Santa Fe y guardado en Parquet. Comando `observatorio scrape santafe` funcionando. | 1, 2, 3 (parcial) |
| 2 | Adaptadores JSON | Nutibara, Uribienes y Alnago. | 3 |
| 3 | Adaptadores HTML | Puertabierta, Panorama, Maxibienes, Villacruz y Activo Urbano. | 3 |
| 4 | Limpieza y normalización | Catálogo oficial de barrios y comunas de Medellín, normalización de barrios, precio/m², outliers y filtro Medellín. | 4 |
| 5 | Propiedades compartidas | Emparejamiento entre fuentes con confianza alta/media/baja y tabla `grupos_inmueble`. | 5 |
| 6 | Análisis y agregados | Notebook de análisis exploratorio y tablas agregadas en `data/agregados/` para las preguntas 1 a 8. | 7 |
| 7 | Dashboard | App Streamlit (6 páginas) + Google Places en vivo + despliegue en Streamlit Community Cloud. | 6, 8 |
| 8 | Automatización | GitHub Actions semanal: scraping, push de datos crudos al repo privado y de agregados al público. | 9 |
| 9 | Pulido de portafolio | README final con capturas, link en vivo, hallazgos, aviso legal y badges. | 10 |

Los planes 2 y 3 se pueden hacer en cualquier orden después del 1. Desde el plan 4 en adelante, cada uno depende del anterior.
