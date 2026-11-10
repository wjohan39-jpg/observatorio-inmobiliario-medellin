# Diseño: Observatorio inmobiliario de Medellín (scraper + análisis + dashboard)

Fecha: 2026-11-10
Estado: versión final, pendiente de aprobación del autor

## 1. Intención y porqué

Proyecto de portafolio en GitHub. Al abrir el repositorio, un reclutador debe pensar en los primeros 30 segundos que el autor es un profesional **tanto en desarrollo Python como en análisis de datos**. Por eso el proyecto recorre el ciclo completo de un análisis de datos (extracción, validación, limpieza, almacenamiento, análisis y visualización) sobre datos reales del mercado inmobiliario de Medellín. La calidad del código tiene que estar a la altura de la calidad del análisis.

No hay fecha límite. El proyecto se construye paso a paso, junto con el autor, para que entienda cada parte y pueda defenderla en una entrevista.

## 2. Preguntas que debe responder el análisis

1. **Precio por barrio:** precio de venta por barrio, en total y por m².
2. **Cobertura:** qué inmobiliarias tienen presencia en más barrios (en más de X o Y barrios) y dónde se concentra cada una.
3. **Economía:** qué inmobiliarias manejan las propiedades más económicas y cuáles los arriendos más económicos. Venta y arriendo se analizan siempre por separado.
4. **Estratos:** qué inmobiliarias trabajan estratos bajos (1-3) y cuáles estratos altos (4-6).
5. **Reputación:** qué inmobiliarias tienen mejor opinión. Se mide con calificación y número de reseñas obtenidos de la **API oficial de Google Places** (decisión del autor). No se hace scraping de Google Maps.
6. **Reconocimiento:** qué inmobiliarias son más reconocidas. *Decisión del diseñador:* se usa un indicador propio que combina volumen de anuncios, número de barrios cubiertos y número de reseñas en Google.
7. **Propiedades compartidas (decisión del autor):** qué inmobiliarias publican el mismo inmueble y cuánto difiere el precio entre ellas. **No se eliminan duplicados.** Todos los anuncios se guardan y una capa aparte los agrupa.
8. **Evolución en el tiempo:** con el histórico semanal, cuánto dura publicado un inmueble, cómo cambian los precios y quién rota inventario más rápido.

## 3. Metas, no-metas y anti-metas

**Metas**
- Pipeline reproducible: `scrape → validar → limpiar → guardar → analizar → dashboard`.
- Ejecución automática semanal con histórico acumulado.
- Dashboard web público con link en vivo en el README.
- Código con estructura profesional: paquete instalable, tipado, pruebas, linter y CI.

**No-metas (por ahora)**
- Predicción de precios con machine learning. Puede ser una fase posterior.
- Cubrir otras ciudades del Área Metropolitana más allá de lo que traigan los sitios. Medellín es el foco.
- Versión en inglés. Se deja preparada para traducir después.

**Anti-metas (sería un fracaso aunque funcione)**
- Saturar o violar las reglas de los sitios: ignorar `robots.txt`, no limitar la velocidad de peticiones o raspar páginas que el sitio pide no rastrear.
- Presentar como seguro algo que es incierto. Las coincidencias entre inmuebles llevan un nivel de confianza.
- Un repositorio desordenado: notebooks sueltos, código sin pruebas o README pobre.
- Publicar datos personales, como teléfonos o nombres de agentes.

## 4. Decisiones del autor

- Fuentes: sitios propios de inmobiliarias de Medellín, con URLs dadas por el autor (ver §6).
- Opiniones: API de Google Places.
- Presentación: dashboard web.
- Frecuencia: ejecución automática periódica con histórico.
- Duplicados: se conservan y se analizan las diferencias de precio entre inmobiliarias.
- Idioma: español (código, documentación y dashboard) por ahora.
- **Se descarta Arango Tobón** porque sus términos prohíben el scraping de forma explícita.
- **Se incluyen Puertabierta y Activo Urbano** con las precauciones de §7.1. El proyecto es académico.
- **"Inmobiliaria" = cada una de las 9 páginas scrapeadas.** Los rankings (preguntas 2 a 7) comparan esas 9 empresas. Cuando una página muestre la agencia de origen de un anuncio compartido (MLS), se guarda en un campo aparte `anunciante_origen` como dato complementario.
- **Google Places:** el autor creará un proyecto en Google Cloud con tarjeta registrada (el uso cabe en el nivel gratuito).
- Ritmo: sin afán, paso a paso y de forma guiada. El autor tiene cuenta de GitHub y aprenderá git durante el proyecto.

## 5. Decisiones del diseñador (el autor puede cambiarlas)

| Tema | Elección | Por qué |
|---|---|---|
| Lenguaje | Python 3.12+ (el equipo tiene 3.14) | El autor ya lo usa |
| Peticiones HTTP | `httpx` | Moderno, con timeouts y reintentos |
| Parseo HTML | `selectolax` o `BeautifulSoup` | Para sitios sin API JSON |
| Navegador | `Playwright`, solo si algún sitio lo exige | Evitarlo mientras se pueda |
| Validación | `pydantic` | Esquema único de "anuncio" para todas las fuentes |
| Datos | `pandas` (el autor lo domina) | Más adelante se puede usar `polars` |
| Almacenamiento | Archivos **Parquet por semana** en un **repo privado de datos**, consultados con DuckDB/pandas; en el repo público solo tablas agregadas | Respeta los términos de las fuentes, el repo no crece sin límite y sigue sin servidores ni costos |
| Gráficas | `plotly` | Interactivas y se integran con Streamlit |
| Dashboard | Streamlit, publicado en Streamlit Community Cloud | Python puro y gratis, con link en vivo |
| Automatización | GitHub Actions (cron semanal) | Gratis y visible en el repo |
| Calidad | `pytest`, `ruff`, `mypy`, `pre-commit` y CI en Actions | Señales de profesionalismo |
| Paquetes | `uv` con `pyproject.toml` | Estándar moderno |

## 6. Fuentes de datos (revisión técnica del 2026-11-10)

Revisión hecha con pocas peticiones por sitio y sin rastrear.

| Sitio | Tecnología | Cómo se obtienen los datos | Arriendo / Venta | Medellín aprox. | Estrato | Bloqueos | Dificultad |
|---|---|---|---|---|---|---|---|
| anutibara.com | Nuxt + API propia | API JSON pública | ✔ / ✔ | 384 / 351 | ✔ | ninguno | Fácil |
| uribienes.com | Next.js + CRM Domus | `/api/properties` JSON | ✔ / ✔ | 258 / 111 | ✔ | ninguno | Fácil |
| puertabierta.com.co | Next.js SSR | JSON embebido en el HTML | ✔ / ✘ | 207 | ✘ | ninguno | Fácil (solo arriendo) |
| arrendamientospanorama.com | ASP clásico | HTML estático, paginación `offset` | ✔ / ✔ | ≥100 (aptos arriendo) | ✔ (detalle) | Cloudflare sin reto | Fácil-Media |
| arrendamientosvillacruz.com.co | Laravel + Livewire | HTML + JSON-LD + sitemap | ✔ / ✔ | 535 / 6.314 (todas las ciudades) | ✔ (detalle) | ninguno | Media |
| alnago.com | Next.js + CRM Wasi | API JSON `api.alnago.com/property/map` + JSON de detalle | ✔ / ✔ | 810 arriendo (todas las ciudades) | ✘ | Cloudflare pasivo | Fácil |
| arrendamientossantafe.com | Next.js propio | API JSON `/apisf/properties`, permitida explícitamente en robots | ✔ / ✔ | ~953 / 868 | ✔ (detalle) | Cloudflare pasivo | Fácil |
| maxibienes.com | PHP + CRM SIMI | HTML del servidor | ✔ / ✔ | ~952 arriendo | ✔ | ninguno (servidor lento) | Fácil-Media |
| activourbano.com.co | WordPress + WooCommerce | Solo HTML (las API responden 403) | ✔ / ✔ | 392 arriendo (todas las ciudades) | ✔ (detalle) | 403 en las API | Media |
| ~~arangotobon.com~~ | WordPress | — | — | 112 / 62 | — | — | **Excluido**: sus términos prohíben el scraping de forma explícita |

**Quedan 9 fuentes.** Cada sitio tiene un front-end distinto, así que se necesita un adaptador por sitio. Hay de dos tipos: los que leen una API JSON (Nutibara, Uribienes, Alnago, Santa Fe) y los que parsean HTML (Panorama, Villacruz, Maxibienes, Activo Urbano, Puertabierta con JSON embebido). Esa mezcla también muestra las dos habilidades en el portafolio.

Notas:
- **Maxibienes:** su JavaScript público trae a la vista un token de la API de SIMI. **No se usa**, porque sería usar una credencial filtrada. Se parsea el HTML público.
- **Activo Urbano**, igual que Puertabierta, tiene una cláusula general de propiedad intelectual. Se publican solo agregados.
- **Alnago** no publica el estrato. Se deja nulo, o se infiere del barrio con su nivel de confianza indicado.
- Varias fuentes cubren otros municipios del Valle de Aburrá (Envigado, Sabaneta, Bello, Itagüí). Se guardan todos los anuncios con su municipio, y el análisis principal filtra Medellín.
- **Uribienes:** su `robots.txt` muestra que no quiere que se rastreen las páginas de detalle. Se usa solo el listado de la API.
- **Puertabierta:** sus términos prohíben reproducir contenido sin autorización. En el repositorio y el dashboard se publican solo agregados y métricas, sin textos ni fotos.
- Nutibara ("VENTAS - MLS") y Villacruz incluyen inventario compartido. Eso alimenta directamente la pregunta 7.

## 7. Arquitectura

```
REPO PÚBLICO (código + portafolio)          REPO PRIVADO (datos completos)
fuentes (1 adaptador por sitio)
   └─► AnuncioCrudo ──► pydantic: AnuncioNormalizado
                          └─────────────────────────► observaciones/AAAA-SS.parquet
                                                      (una fila por anuncio por semana)
limpieza / enriquecimiento  ◄──── lee Parquet
   ├─ normalizar barrios (catálogo oficial de barrios y comunas de Medellín)
   ├─ precio/m², detección de outliers
   └─ agrupación de inmuebles compartidos ──────────► grupos_inmueble.parquet
análisis ──► tablas AGREGADAS (data/agregados/*.parquet, en el repo público)
dashboard (Streamlit) ◄── lee agregados; si hace falta detalle, lee el repo privado con un token secreto
GitHub Actions (cron semanal, en el repo público) ──► corre el pipeline, hace push de los datos crudos
                                                      al repo privado y de los agregados al público
Google Places API ──► se consulta en vivo desde el dashboard (con caché de horas); solo se guarda el `place_id`
```

### 7.1 Reglas legales y éticas (obligatorias)

- Solo se extraen **datos de hecho** (precio, área, barrio, estrato, habitaciones, etc.). **No se descargan ni publican fotos ni textos descriptivos.**
- No se guardan datos personales (nombres, teléfonos o correos de asesores), en cumplimiento de la Ley 1581 de 2012.
- No se evade ninguna medida de seguridad (contraseñas, captchas, bloqueos) ni se usan credenciales filtradas, en cumplimiento de la Ley 1273 de 2009. El token SIMI de Maxibienes **no se usa**.
- Se respeta `robots.txt` y se limita la velocidad de peticiones.
- Los datos completos van solo al repo privado. El repo público y el dashboard muestran **agregados**. En la página de propiedades compartidas se muestran grupos anónimos (barrio, área, estrato, precio por fuente), sin la URL ni el texto del anuncio.
- El README incluye un aviso: proyecto educativo, sin fines comerciales, y cualquier inmobiliaria que pida retirar sus datos será atendida.

### 7.2 Google Places

- Sus términos no permiten guardar a largo plazo la calificación ni el número de reseñas. Por eso **no hay histórico de reputación**: el dashboard consulta en vivo y guarda en caché unas horas.
- Solo se guarda el `place_id` de cada sede, en un archivo de configuración.
- Para las inmobiliarias con varias sedes: se suman las reseñas de todas y la calificación es el promedio ponderado por número de reseñas (*decisión del diseñador*).
- La clave de la API va en los *secrets* de Streamlit y GitHub, nunca en el código.

**Patrón de adaptadores:** cada sitio implementa la misma interfaz (`listar_anuncios() -> Iterable[AnuncioCrudo]`). Si se agrega un sitio nuevo, no hay que tocar el resto del pipeline. Este patrón es la principal señal de diseño para quien lea el código.

**Esquema mínimo de anuncio:** fuente, id en la fuente, URL, inmobiliaria, operación (venta/arriendo), tipo de inmueble, precio, administración, área (m²), habitaciones, baños, parqueaderos, estrato, barrio (original y normalizado), comuna, municipio, lat/lon (si existen) y fecha de observación.

**Agrupación de inmuebles compartidos:** se emparejan anuncios de **distintas** inmobiliarias por cercanía de coordenadas (si existen), el mismo barrio normalizado, área similar (±3 %), las mismas habitaciones y baños y el mismo estrato. Cada pareja recibe una confianza alta, media o baja. El dashboard permite filtrar por nivel de confianza.

**Cortesía:** se respeta `robots.txt`, se limita la velocidad (por ejemplo 1 petición cada 1-2 s por sitio), se usa un User-Agent identificable del proyecto, y se reintenta con espera creciente.

## 8. Dashboard (páginas propuestas)

1. Resumen del mercado: KPIs, mapa por barrio y precio/m².
2. Barrios: comparación de venta y arriendo, y ranking por m².
3. Inmobiliarias: cobertura, estratos, precios y reputación (Google).
4. Propiedades compartidas: grupos y diferencias de precio.
5. Evolución: series semanales y días en el mercado.
6. Metodología: fuentes, limpieza y limitaciones.

## 9. Fases sugeridas

1. Crear los dos repos (público y privado), estructura del proyecto, herramientas de calidad y primer commit guiado de git.
2. Esquema `pydantic` y primer adaptador (el más fácil: Santa Fe o Nutibara), con pruebas.
3. Almacenamiento en Parquet y resto de adaptadores, uno por uno.
4. Limpieza y normalización de barrios.
5. Agrupación de inmuebles compartidos.
6. Google Places.
7. Análisis exploratorio (notebook documentado).
8. Dashboard Streamlit y despliegue.
9. GitHub Actions semanal.
10. README final con capturas, link en vivo y hallazgos.

## 10. Se deja al constructor

- Selectores y endpoints exactos por sitio.
- Umbrales finos de la agrupación y de los outliers.
- Diseño visual del dashboard dentro de las páginas propuestas.
