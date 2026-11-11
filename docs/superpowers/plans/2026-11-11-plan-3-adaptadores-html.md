# Plan 3: Adaptadores HTML (Puertabierta, Maxibienes, Activo Urbano, Panorama, Villacruz)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Agregar las cinco fuentes restantes, que no tienen una API JSON pública utilizable, de modo que `observatorio scrape puertabierta|maxibienes|activourbano|panorama|villacruz` funcione igual que las cuatro fuentes existentes.

**Architecture:** Igual que en el Plan 2. Cada sitio tiene un módulo en `fuentes/` con funciones puras de extracción (HTML → `dict` → `AnuncioNormalizado`) y una clase `Fuente<Sitio>` que recorre el sitio con `ClienteCortes`. Antes de los adaptadores se agregan dos piezas compartidas:

- `ClienteCortes.get_bytes`, porque dos sitios declaran mal su codificación;
- un módulo `html.py` con `decodificar` y el parser `selectolax`.

**Tech Stack:** Python 3.12+, httpx (vía `ClienteCortes`), **selectolax** (nuevo), pydantic, pytest + respx, ruff, mypy estricto.

**Spec:** `docs/superpowers/specs/2026-11-10-scraper-inmobiliario-medellin-design.md` (§6 fuentes, §7 arquitectura, §7.1 reglas legales).

## Revisión técnica de los sitios (2026-11-11)

La revisión se hizo con el User-Agent del proyecto, 2 s entre peticiones y menos de 40 peticiones por sitio. No se evadió ningún bloqueo. Las muestras crudas están en el scratchpad de la sesión (`scratchpad/recon/<sitio>/`) y de ahí salen los fixtures recortados. Esto es lo que el plan da por cierto:

| Sitio | Datos | robots.txt | Recorrido | Detalle | Corrida |
|---|---|---|---|---|---|
| Puertabierta | JSON de React Server Components dentro del HTML | permite todo (salvo `/sura`) | `/arriendos/<municipio>?page=N`, 36 por página | No | ~45 s, 14 peticiones |
| Maxibienes | HTML de tarjetas | permite `/resultados-de-la-busqueda-de-inmueble` | `/resultados-de-la-busqueda-de-inmueble/pagina/N?gestion=1\|2&ciudad=<DANE>`, 12 por página | No | ~19 min, ~280 peticiones |
| Activo Urbano | HTML de tarjetas Elementor | permite todo lo usado | `/inmuebles/?jsf=epro-loop-builder:products&pagenum=N`, 6 por página, 80 páginas | Sí: estrato y parqueadero | ~30 min, ~530 peticiones |
| Panorama | HTML ASP clásico en cp1252 | solo comentarios: sin reglas | `resumen_ciudad_<op>.asp?pCiudad=<c>&pTipoInmueble=<t>&offset=<n>`, 50 por página | Sí, **solo residenciales**: estrato | ~20–25 min |
| Villacruz | JSON embebido `let property= {...}` | permite `/detalle-propiedad/*` y `/sitemaps/*` | sitemap → detalle de cada anuncio **propio** | Sí, es la única fuente | ~18 min, ~700 peticiones |

**Decisiones del autor (2026-11-11):**

- **Villacruz:** solo el inventario propio (~700 anuncios). Las ~4.400 ventas MLS de otras agencias se excluyen: costarían ~2 h por corrida, no dicen qué agencia las publica e inflarían a Villacruz en los rankings.
- **Panorama:** se listan todos los tipos de inmueble, pero el detalle (estrato) se pide solo para apartamentos, apartaestudios y casas.

### Detalles por sitio que el código debe respetar

**Puertabierta**
- Solo tiene arriendo.
- Los datos van en `<script>self.__next_f.push([1,"..."])</script>`. Hay que unir los `[1]` de todos los `push` en orden, separar por `\n` (cada línea es `<id>:<json>`) y tomar la línea que contiene `"queries"` y `"hits"`. En `[3]["state"]["queries"]`, la consulta es la entrada cuyo `queryKey[:2] == ["properties", "search"]`, y los datos están en `.state.data = {hits, found, page, totalPages, perPage}`.
- Municipios con inventario: `medellin`, `envigado`, `sabaneta`, `itagui`, `la-estrella`.
- Una página después de la última responde **404**.
- Campos:
  - `id` (UUID)
  - `pricing.monthlyRent`
  - `pricing.monthlyAdministrationFee` (0 y `null` = no reportado)
  - `layout.areaM2`, `layout.numBedrooms`, `layout.numBathrooms` (puede ser `2.5`), `layout.numParkingLots`
  - `location.neighborhood` (`null` en 110 de 376) con `location.zone` como alterno
  - `location.latitude`, `location.longitude`
  - el tipo sale del `title` ("Apartaestudio en…", "Casa…", "Penthouse…", "Apartamento…")
- No publica estrato.
- **Nunca** se guardan `location.address`, `unitNumber`, `postalCode`, `googleMapsUri` ni `media`.
- URL: `https://puertabierta.com.co/propiedades/<id>`.

**Maxibienes**
- `gestion=1` es arriendo y `gestion=2` es venta. Ambas incluyen los anuncios duales.
- Con un parámetro desconocido el sitio devuelve **todo sin filtrar**. Por eso se verifica el eco `var gs = <op>` y `var ci = <ciudad>` en la primera página.
- Total: `var totalInmuebles = N`. Página: 12. Después de la última, la página viene sin tarjetas.
- Tarjeta `div.grid-style1 div.item`:
  - código y URL en el enlace `/descripcion-del-inmueble/codigo/(\d+)`
  - tipo en el `h3`, antes del `<br>`
  - estrato como `Estrato: N` (**7 = no aplica**)
  - barrio en `span.location` (`Barrio: …`)
  - precio en `div.price span`; en los duales es `$ X / $Y`: X para arriendo, Y para venta
  - área, baños, alcobas y parqueaderos con iconos `fa-compress`, `fa-bath`, `fa-bed`, `fa-warehouse`
- Sin coordenadas ni administración.
- **Codificación:** declara UTF-8 pero envía cp1252.
- **El token SIMI está en las páginas de detalle: nunca se piden ni se usan como fixture.**

**Activo Urbano**
- `/page/N/` no pagina; solo funciona la URL con `jsf=`.
- `"found_posts":N,"max_num_pages":M,"page":P` dentro de `JetSmartFilterSettings`. Después de la última página: `found_posts: 0` y sin tarjetas.
- Tarjeta `#products .elementor-loop-container > .e-loop-item.product`. Las clases de la tarjeta traen:
  - la operación: `product_cat-en-arriendo`, `-en-venta` o `-ambos`
  - el municipio y el barrio: `ubicacion-<slug>` (municipio si está en la lista blanca; el otro slug, sin sufijo `-\d+`, es el barrio)
  - el tipo: `tipo-de-propiedad-<slug>`
- Otros datos de la tarjeta:
  - código: `AU\s*-\s*(\d+)`
  - área, alcobas y baños junto a los iconos `gicon-full-screen`, `gicon-habitaciones`, `gicon-baths`
  - precio: `.woocommerce-Price-amount`
- Detalle `/propiedades/inmueble/<código>/`. Se emparejan etiqueta y valor **dentro del mismo contenedor `.e-con`**: "Estrato" (puede ser "Sin especificar") y "Parqueadero" (si no hay valor, el widget falta).
- **"Ambos" (13 anuncios) se guarda como arriendo**: su único precio está rotulado "Valor del arriendo".
- Puede haber códigos repetidos (reposts), así que se quitan duplicados por código.
- Sin coordenadas ni administración. No se toca `/wp-json/`, que responde 403.

**Panorama**
- `pTipoInmueble`:
  - 1 apartamento
  - 4 apartaestudio
  - 2 casa
  - 3 casa campestre
  - 12 finca de recreo
  - 6 bodega
  - 7 local
  - 8 oficina
  - 13 finca agroindustrial
  - 10 lote
- Municipios (`pCiudad`):
  - 10000 Medellín
  - 10041 San Antonio de Prado y 10037 San Cristóbal (corregimientos de Medellín)
  - 10001 Envigado
  - 10002 Itagüí
  - 10003 La Estrella
  - 10005 Sabaneta
  - 10006 Caldas
  - 10007 Bello
  - 10008 Copacabana
- Paginación: `offset` de 50 en 50. El total de páginas está en `Página N / M`. **Después de la última página el sitio repite la última**: se corta con M, nunca con "página vacía". Una combinación sin inventario muestra `Página 1 / 0`.
- Tarjeta: `Anuncio (\d+) - (BARRIO)`, precio `Precio $1,800,000` (coma de miles) e iconos `fa-bed`, `fa-bath`, `fa-car-side`, `fa-ruler-triangle`. Los locales no tienen `fa-bed`. Valores como `2 +1`.
- Detalle `Ficha.asp?xId=<id>`, en la tabla `table.table-striped`: `Estrato`, `Barrio / Sector`, `Valor Administracion` (`cop $0` = sin dato). Un anuncio retirado responde **500**.
- Sin coordenadas. Codificación **cp1252** sin charset en la cabecera. Los `href` traen un espacio al final.

**Villacruz**
- El host es `https://www.arrendamientosvillacruz.com.co`.
- Sitemap `/sitemaps/villacruz/sitemap.xml`: ~6.900 `<loc>`, 1,5 MB. Los slugs propios se identifican con `^(?P<tipo>.+?)-(?P<op>enarriendo|enventa)-en-(?P<lugar>.+)-(?P<codigo>\d+)$`. Los MLS usan `-en-venta-en-` y **se descartan**.
- Detalle: `let property= {...};` se lee con `json.JSONDecoder().raw_decode`. Campos:
  - `code`, `price_new` (texto numérico), `property_type`
  - `management` (`Arriendo`, `Venta` o `Amoblado` = arriendo)
  - `area` (`"7.089"` = 7089)
  - `bedrooms`, `bathrooms`, `garage`, `stratum`
  - `neighborhood` (barrio o municipio, en mayúsculas)
  - `latitude`, `longitude` (texto)
- Un código inexistente redirige (302) al inicio, cuya página no tiene `let property=`.
- Se descartan los slugs de lugar que están fuera del valle: `rionegro`, `san-jeronimo`, `sopetran`, `retiro`, `el-retiro`, `amaga`, `san-pedro-de-los-milagros`, `cabaas`, `guarne`, `marinilla`, `peol`, `el-carmen-de-viboral`, `jardin`, `santa-fe-de-antioquia`, `la-ceja`.
- Municipio: si `neighborhood` es un municipio del valle, ese; si no, `None` (lo resuelve el Plan 4 con el catálogo de barrios y las coordenadas).

## Global Constraints

- Toda petición pasa por `ClienteCortes`: respeta robots.txt del host, 1,5 s entre peticiones y reintentos con espera creciente.
- Solo datos de hecho. **No** se guardan direcciones, número de apartamento, descripciones, fotos ni datos de asesores. Tampoco el token de Maxibienes: no se piden páginas de detalle de Maxibienes.
- Los fixtures van al repo público. Se recortan a las tarjetas o al JSON con los campos que el adaptador usa. Antes de cada commit se buscan en ellos `tel:`, `wa.me`, `Authorization`, `simi`, `address`, `description` e `<img` (ver Tarea 1).
- Ningún dato fuera de rango descarta el anuncio entero: se usan `parsear_area`, `parsear_conteo`, `parsear_estrato`, `parsear_precio` y `parsear_coordenada(..., limite=90)` para la latitud.
- Un anuncio inválido se omite con `logger.warning`, y una página de detalle que falla deja el anuncio solo con los datos del listado (igual que Santa Fe).
- Código, nombres y mensajes en español. `ruff`, `ruff format --check`, `mypy` estricto y `pytest` en verde antes de cada commit.
- Cada adaptador acepta `con_detalle: bool = True`, `max_paginas: int | None = None` y `fecha: date | None = None`, y su docstring dice qué significan en esa fuente.
- Los commits los hace Claude (con el mensaje `tipo: descripción` y los hooks); el autor solo hace `git push`.

## Review Focus

1. **Codificación cp1252 declarada como UTF-8, o sin declarar** (Maxibienes, Panorama). "Itagüí" o "Suramérica" no deben quedar con `�`. → `decodificar` (Tarea 1) y fixtures guardados en cp1252 (Tareas 3 y 5).
2. **Paginaciones engañosas.** Panorama repite la última página al pasarse; Maxibienes ignora en silencio un filtro mal escrito; Activo Urbano ignora `/page/N/`. Ninguna puede ciclar ni traer todo el país. → pruebas de corte por total (Tareas 3, 4 y 5) y verificación del eco de filtros (Tarea 3).
3. **Fugas de datos personales o del token en los fixtures.** → revisión automática de los fixtures (Tarea 1, aplicada en cada tarea).
4. **Anuncios repetidos** dentro de una misma corrida (reposts de Activo Urbano, duales de Maxibienes en la misma operación, reordenamiento por relevancia en Puertabierta). → `set` de códigos por operación en todos los adaptadores, con prueba.
5. **Un detalle que falla** (500 de Panorama, redirección de Villacruz, widget faltante en Activo Urbano) no debe tumbar la corrida ni inventar datos. → pruebas en las Tareas 4, 5 y 6.

---

### Task 1: Base compartida para HTML

**Files:**
- Modify: `pyproject.toml` (dependencia `selectolax`)
- Modify: `src/observatorio_inmobiliario/http.py` (`get_bytes`)
- Create: `src/observatorio_inmobiliario/html.py`
- Test: `tests/test_http.py`, `tests/test_html.py`, `tests/test_fixtures_publicos.py`

**Interfaces:**
- Produces:
  - `ClienteCortes.get_bytes(ruta: str, params: Parametros | None = None) -> bytes`.
  - `html.decodificar(contenido: bytes) -> str`: intenta UTF-8 estricto y, si falla, usa cp1252.
  - `html.analizar(texto: str) -> selectolax.lexbor.LexborHTMLParser`.
  - `html.texto(nodo: LexborNode | None) -> str | None`: el texto sin espacios sobrantes, o `None` si el nodo no existe o queda vacío.

- [ ] **Step 1: Agregar la dependencia**

Run: `uv add selectolax`
Expected: `pyproject.toml` y `uv.lock` actualizados; `uv run python -c "import selectolax"` funciona. Si mypy no encuentra tipos, verificar que selectolax trae `py.typed` (las versiones recientes lo traen); si no, agregar un override como el de pyarrow.

- [ ] **Step 2: Escribir las pruebas que fallan**

```python
# tests/test_html.py
def test_decodificar_utf8() -> None:
    assert decodificar("Itagüí".encode()) == "Itagüí"

def test_decodificar_cp1252() -> None:
    assert decodificar("Itagüí · 60 M²".encode("cp1252")) == "Itagüí · 60 M²"

def test_texto_quita_espacios_y_vacios() -> None:
    arbol = analizar("<p> 3 \r\n </p><p>  </p>")
    nodos = arbol.css("p")
    assert texto(nodos[0]) == "3"
    assert texto(nodos[1]) is None
    assert texto(None) is None

# tests/test_http.py
def test_get_bytes_devuelve_el_cuerpo_sin_decodificar(...) -> None:
    # respx: "/x" responde content="Itagüí".encode("cp1252") con Content-Type "text/html; charset=utf-8"
    assert cliente.get_bytes("/x") == "Itagüí".encode("cp1252")
```

`tests/test_fixtures_publicos.py` recorre `tests/fixtures/**/*` y falla si algún archivo contiene (sin distinguir mayúsculas) `tel:`, `wa.me`, `authorization`, `simi-api`, `"address"`, `"description"`, `"unitNumber"` o `<img`. Está parametrizado por archivo, para que el error diga cuál es.

- [ ] **Step 3: Correr y ver que fallan**

Run: `uv run pytest tests/test_html.py tests/test_http.py tests/test_fixtures_publicos.py -v`
Expected: FAIL por `ModuleNotFoundError: observatorio_inmobiliario.html` y `AttributeError: get_bytes`. `test_fixtures_publicos` pasa ya, porque los fixtures actuales están limpios.

- [ ] **Step 4: Implementar**

`get_bytes` reutiliza `_get_permitido` y devuelve `.content`. `html.py` envuelve selectolax (`LexborHTMLParser`) y tiene un docstring que explica por qué existe `decodificar`: dos sitios mienten sobre su codificación.

- [ ] **Step 5: Correr todo y ver que pasa**

Run: `uv run pytest && uv run ruff check . && uv run ruff format --check . && uv run mypy`
Expected: todo en verde.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock src/observatorio_inmobiliario/http.py src/observatorio_inmobiliario/html.py tests/test_http.py tests/test_html.py tests/test_fixtures_publicos.py
git commit -m "feat: base para fuentes HTML (selectolax, get_bytes y decodificación)"
```

---

### Task 2: Adaptador de Puertabierta

**Files:**
- Create: `src/observatorio_inmobiliario/fuentes/puertabierta.py`
- Modify: `src/observatorio_inmobiliario/fuentes/__init__.py`
- Create: `tests/fixtures/puertabierta/arriendos_medellin_p1.html` (a partir de `scratchpad/recon/puertabierta/fixture_candidate_arriendos_medellin_p1_trimmed.html`), `tests/fixtures/puertabierta/arriendos_itagui.html` (recortado a 1 hit con `"Itagüi"`)
- Test: `tests/test_puertabierta.py`

**Interfaces:**
- Produces:
  - `URL_BASE: Final = "https://puertabierta.com.co"`.
  - `MUNICIPIOS: Final[dict[str, str]] = {"medellin": "Medellín", "envigado": "Envigado", "sabaneta": "Sabaneta", "itagui": "Itagüí", "la-estrella": "La Estrella"}`.
  - `extraer_busqueda(html: str) -> dict[str, Any] | None`: devuelve `{hits, found, page, totalPages, perPage}`, o `None` si la página no trae la consulta.
  - `tipo_desde_titulo(titulo: str | None) -> str | None`: devuelve `apartaestudio`, `penthouse`, `casa`, `apartamento` o `None` (se revisa en ese orden).
  - `mapear_anuncio(hit: dict[str, Any], municipio: str, fecha: date) -> AnuncioNormalizado`.
  - `class FuentePuertabierta` con `nombre = "puertabierta"`. `max_paginas` limita las páginas por municipio y `con_detalle` no tiene efecto.

- [ ] **Step 1: Pruebas que fallan**

- `test_extraer_busqueda`: con el fixture, `found == 217`, `totalPages == 7` y `len(hits) == 3`. La prueba también arma un HTML que parte la misma línea RSC en **dos** `push` y espera el mismo resultado.
- `test_mapear_hit`: verifica `id_fuente` (el UUID), la URL `https://puertabierta.com.co/propiedades/<id>`, el arriendo, el precio, el área, las habitaciones, la latitud y la longitud contra los valores del primer hit del fixture, y que `estrato is None`.
- `test_administracion_cero_es_nula`: con `monthlyAdministrationFee` 0 y con `null`, el resultado es `None`.
- `test_banos_fraccionarios`: con `numBathrooms: 2.5`, `banos == 2`.
- `test_barrio_usa_zone_si_falta_neighborhood`.
- `test_tipo_desde_titulo`: parametrizada con `"Apartaestudio en Laureles" → "apartaestudio"`, `"Hermosa Casa en…" → "casa"`, `"Apartamento de 3 habitaciones en…" → "apartamento"` y `"Penthouse…" → "penthouse"`.
- `test_municipio_sale_del_slug_consultado`: un hit con `city: "Itagüi"` consultado desde `itagui` da `municipio == "Itagüí"`.
- `test_recorre_hasta_total_pages`, con respx: 2 páginas para `medellin` y 404 para los demás municipios. Salen 2 páginas de anuncios y no se pide `page=3`.
- `test_404_de_municipio_no_tumba_la_corrida`.
- `test_duplicados_por_id_salen_una_vez`.
- `test_registrada_en_cli`.

- [ ] **Step 2: Correr y ver que fallan** (`ModuleNotFoundError`).
- [ ] **Step 3: Implementar.** Se buscan los `push` con `str.find`, sin regex sobre la página completa (pesa 1,5 MB). Un 404 en `?page=N` se trata como fin de ese municipio, con la misma regla `_es_404` que Nutibara: moverla a `http.py` como `es_404(error: ErrorDeDescarga) -> bool` y usarla en ambos.
- [ ] **Step 4: Registrar la fuente.**
- [ ] **Step 5: Correr todo y ver que pasa.**
- [ ] **Step 6: Commit** — `feat: adaptador de Puertabierta`.

---

### Task 3: Adaptador de Maxibienes

**Files:**
- Create: `src/observatorio_inmobiliario/fuentes/maxibienes.py`
- Modify: `src/observatorio_inmobiliario/fuentes/__init__.py`
- Create: `tests/fixtures/maxibienes/arriendo_medellin_p80.html` (a partir de `arr_med_p80.html`), `tests/fixtures/maxibienes/duales.html` (a partir de `q10.html`) y `tests/fixtures/maxibienes/caldas.html` (a partir de `cities/arr_5129.html`, con estrato 7 y ceros). Se recortan al bloque `div.grid-style1` más los `<script>` de una línea con `var gs`, `var ci` y `var totalInmuebles`. **Se guardan en cp1252, tal como los envía el sitio.**
- Test: `tests/test_maxibienes.py`

**Interfaces:**
- Produces:
  - `URL_BASE: Final = "https://www.maxibienes.com"`.
  - `MUNICIPIOS: Final[dict[int, str]]`, los mismos 10 códigos DANE de Uribienes. Se importan de `uribienes.MUNICIPIOS` para no duplicarlos.
  - `GESTIONES: Final = {1: Operacion.ARRIENDO, 2: Operacion.VENTA}`.
  - `TAMANO_PAGINA: Final = 12`.
  - `extraer_tarjetas(html: str) -> list[dict[str, str | None]]`: claves `codigo`, `tipo`, `estrato`, `barrio`, `precio`, `area`, `banos`, `alcobas`, `parqueaderos`.
  - `extraer_filtros(html: str) -> tuple[int | None, int | None, int | None]`: devuelve `(gs, ci, totalInmuebles)`.
  - `mapear_anuncio(tarjeta: dict[str, str | None], operacion: Operacion, municipio: str, fecha: date) -> AnuncioNormalizado`.
  - `class FuenteMaxibienes` con `nombre = "maxibienes"`. `max_paginas` limita las páginas por municipio y operación; `con_detalle` no tiene efecto (las páginas de detalle no se piden: llevan el token).
  - `class ErrorFiltroIgnorado(ErrorDeDescarga)`: se lanza si el eco no coincide con el filtro pedido.

- [ ] **Step 1: Pruebas que fallan**

- `test_extraer_tarjetas`: con el fixture de la página 80, salen 8 tarjetas, y la primera tiene los valores reales del recon. La prueba también verifica que el barrio con tilde se decodifica bien después de `decodificar`.
- `test_precio_dual_toma_el_de_la_operacion`: `"$ $ 3.100.000 / $610.000.000"` da 3.100.000 en arriendo y 610.000.000 en venta.
- `test_venta_con_precio_repetido`: `"$ $ 830.000.000 / $830.000.000"` da 830.000.000.
- `test_estrato_siete_es_nulo` (fixture de Caldas).
- `test_filtro_ignorado_detiene_la_fuente`: si la primera página trae `var ci = 0` cuando se pidió 5001, se lanza `ErrorFiltroIgnorado`.
- `test_pagina_hasta_el_total`: con `totalInmuebles = 20` se piden exactamente 2 páginas, y la URL usa la ruta `/pagina/2`.
- `test_duales_salen_una_vez_por_operacion`.
- `test_registrada_en_cli`.

- [ ] **Step 2–6:** igual que en la Tarea 2. Commit: `feat: adaptador de Maxibienes`.

---

### Task 4: Adaptador de Activo Urbano

**Files:**
- Create: `src/observatorio_inmobiliario/fuentes/activourbano.py`
- Modify: `src/observatorio_inmobiliario/fuentes/__init__.py`
- Create: `tests/fixtures/activourbano/` a partir de `scratchpad/recon/activourbano/fixtures_trimmed/`:
  - `listado_p40.html`
  - `listado_vacio.html`
  - `detalle_6752.html` (completo)
  - `detalle_6754.html` (sin parqueadero)
  - `detalle_6163.html` (estrato "Sin especificar")
- Test: `tests/test_activourbano.py`

**Interfaces:**
- Produces:
  - `URL_BASE: Final = "https://activourbano.com.co"`.
  - `MUNICIPIOS: Final[dict[str, str]]`: slug → nombre, para los 10 municipios del valle (`medellin` → `Medellín`, `itagui` → `Itagüí`, …).
  - `extraer_paginacion(html: str) -> tuple[int, int]`: devuelve `(found_posts, max_num_pages)`.
  - `extraer_tarjetas(html: str) -> list[dict[str, str | None]]`: claves `codigo`, `operacion` (`en-arriendo`, `en-venta` o `ambos`), `municipio_slug`, `barrio_slug`, `tipo_slug`, `precio`, `area`, `alcobas`, `banos`.
  - `extraer_detalle(html: str) -> dict[str, str | None]`: claves `estrato` y `parqueaderos`.
  - `mapear_anuncio(tarjeta, detalle: dict[str, str | None] | None, fecha: date) -> AnuncioNormalizado`.
  - `class FuenteActivoUrbano` con `nombre = "activourbano"`. Con `con_detalle=False` no pide detalles; `max_paginas` limita las páginas del listado.

- [ ] **Step 1: Pruebas que fallan**

- `test_extraer_tarjetas`: con el fixture salen 6 tarjetas y ninguna es del pie de página (blog). Las operaciones, municipios y barrios coinciden con los del recon.
- `test_ambos_se_guarda_como_arriendo`.
- `test_barrio_sin_sufijo_numerico`: `ciudad-del-rio-3` da `"ciudad del rio"`.
- `test_detalle_sin_parqueadero_es_nulo` (fixture 6754): no se debe tomar "Baños" por error.
- `test_estrato_sin_especificar_es_nulo`.
- `test_banos_decimales`: "2.5" da 2.
- `test_fuera_del_valle_se_omite`: una tarjeta con solo `ubicacion-rionegro` no sale.
- `test_pagina_hasta_max_num_pages` y `test_pagina_vacia_corta`.
- `test_codigo_repetido_sale_una_vez`.
- `test_detalle_que_falla_deja_datos_del_listado`.
- `test_registrada_en_cli`.

- [ ] **Step 2–6:** igual que en la Tarea 2. Commit: `feat: adaptador de Activo Urbano`.

---

### Task 5: Adaptador de Panorama

**Files:**
- Create: `src/observatorio_inmobiliario/fuentes/panorama.py`
- Modify: `src/observatorio_inmobiliario/fuentes/__init__.py`
- Create: `tests/fixtures/panorama/` (todos en **cp1252**):
  - `descubrir_apto_arriendo.html`, a partir de `arr_apto_p1.html`, recortado a los enlaces `Resumen_Ciudad_*`
  - `apto_medellin_ultima.html`, a partir de `arr_apto_med_off300.html`, con 3 tarjetas y "7 / 7"
  - `locales_medellin.html`, a partir de `arr_tipo7_med_p1.html`, con 2 tarjetas sin `fa-bed`
  - `vacia.html`, a partir de `test_nociudad.html`
  - `ficha_arriendo.html`, a partir de `ficha_1820710.html`, recortada a la tabla
  - `ficha_venta.html`, a partir de `ficha_1820376.html`, recortada a la tabla
- Test: `tests/test_panorama.py`

**Interfaces:**
- Produces:
  - `URL_BASE: Final = "https://arrendamientospanorama.com"`.
  - `TIPOS: Final[dict[int, str]]`: el código de `pTipoInmueble` → tipo, con los 10 de la tabla.
  - `TIPOS_RESIDENCIALES: Final = frozenset({1, 2, 4})`.
  - `MUNICIPIOS: Final[dict[int, str]]`: `pCiudad` → municipio. Los corregimientos 10041 y 10037 van a `"Medellín"`.
  - `OPERACIONES: Final = {Operacion.ARRIENDO: ("listado_arriendos.asp", "resumen_ciudad_arriendos.asp"), Operacion.VENTA: ("listado_ventas.asp", "resumen_ciudad_ventas.asp")}`.
  - `extraer_ciudades(html: str) -> set[int]`: los `pCiudad` con inventario. Ignora el bloque "TOP 10".
  - `extraer_paginas(html: str) -> int`: el M de `Página N / M`.
  - `extraer_tarjetas(html: str) -> list[dict[str, str | None]]`: claves `codigo`, `barrio`, `precio`, `alcobas`, `banos`, `parqueaderos`, `area`.
  - `extraer_ficha(html: str) -> dict[str, str]`: etiqueta → valor, con las entidades HTML ya convertidas.
  - `mapear_anuncio(tarjeta, ficha: dict[str, str] | None, operacion: Operacion, tipo: str, municipio: str, fecha: date) -> AnuncioNormalizado`.
  - `class FuentePanorama` con `nombre = "panorama"`. Pide la ficha solo si `con_detalle` está activo y el tipo está en `TIPOS_RESIDENCIALES`. `max_paginas` limita las páginas por combinación.

- [ ] **Step 1: Pruebas que fallan**

- `test_extraer_ciudades`: el fixture de descubrimiento devuelve un conjunto que incluye 10000 y no incluye ningún código del "TOP 10".
- `test_extraer_tarjetas`: 3 tarjetas con barrio en mayúsculas y precio `1,800,000`, que se convierte en 1.800.000.
- `test_local_sin_alcobas`: `alcobas is None`, y lo demás presente.
- `test_valores_como_dos_mas_uno`: "2 +1" da 2.
- `test_ficha_estrato_y_barrio`: el estrato de la ficha y el barrio de la ficha (con mayúsculas normales) tienen prioridad sobre los de la tarjeta.
- `test_administracion_cero_es_nula` (`cop $0`).
- `test_corta_con_el_total_aunque_el_sitio_repita_la_ultima`: si la ruta con `offset` responde siempre la misma página con "7 / 7", se piden exactamente 7 páginas.
- `test_combinacion_vacia`: "Página 1 / 0" da 0 anuncios y 1 sola petición.
- `test_ficha_solo_para_residenciales`: un local no pide la ficha.
- `test_ficha_500_deja_datos_del_listado`.
- `test_codificacion_cp1252`: el barrio "BELÉN" sale bien escrito.
- `test_registrada_en_cli`.

- [ ] **Step 2–6:** igual que en la Tarea 2. La página se obtiene con `cliente.get_bytes` y luego `decodificar`. Commit: `feat: adaptador de Arrendamientos Panorama`.

---

### Task 6: Adaptador de Villacruz

**Files:**
- Create: `src/observatorio_inmobiliario/fuentes/villacruz.py`
- Modify: `src/observatorio_inmobiliario/fuentes/__init__.py`
- Create: `tests/fixtures/villacruz/`:
  - `sitemap.xml`, recortado a ~8 `<url>`: propios de arriendo y de venta, un MLS, uno fuera del valle y uno con fecha 1900
  - `detalle_arriendo_bello.html`, `detalle_amoblado.html` y `detalle_lote.html`, recortados al `<script>` con `let property=`, sin las claves `description`, `gallery`, `image`, `video`, `attributes` ni `sites`
- Test: `tests/test_villacruz.py`

**Interfaces:**
- Produces:
  - `URL_BASE: Final = "https://www.arrendamientosvillacruz.com.co"`.
  - `RUTA_SITEMAP: Final = "/sitemaps/villacruz/sitemap.xml"`.
  - `LUGARES_FUERA_DEL_VALLE: Final[frozenset[str]]`: la lista de la revisión.
  - `MUNICIPIOS: Final[dict[str, str]]`: el texto de `neighborhood` normalizado (minúsculas, sin tildes) → municipio, para los 10 municipios del valle.
  - `slugs_propios(sitemap: str) -> list[str]`: los slugs de inventario propio dentro del valle, sin MLS.
  - `extraer_propiedad(html: str) -> dict[str, Any] | None`.
  - `mapear_anuncio(propiedad: dict[str, Any], slug: str, fecha: date) -> AnuncioNormalizado`.
  - `class FuenteVillacruz` con `nombre = "villacruz"`. `con_detalle` no tiene efecto (el detalle es la fuente). `max_paginas=N` limita a `N * 12` páginas de detalle, para corridas de prueba.

- [ ] **Step 1: Pruebas que fallan**

- `test_slugs_propios`: del sitemap recortado salen solo los propios dentro del valle. Sin MLS y sin `rionegro`.
- `test_mapear_arriendo_bello`: código, precio (`price_new`), estrato 3, `parqueaderos == 0`, `municipio == "Bello"`, latitud y longitud con signo, URL `/detalle-propiedad/<slug>`.
- `test_amoblado_es_arriendo`.
- `test_area_con_punto_de_miles`: `"7.089"` da 7089.0.
- `test_barrio_que_no_es_municipio`: `neighborhood "LAURELES"` da barrio `"LAURELES"` y municipio `None`.
- `test_redireccion_al_inicio_se_omite`: si la página no trae `let property=`, el anuncio se omite con `WARNING` y la corrida sigue.
- `test_max_paginas_limita_detalles`.
- `test_registrada_en_cli`.

- [ ] **Step 2–6:** igual que en la Tarea 2. Commit: `feat: adaptador de Arrendamientos Villacruz (inventario propio)`.

---

### Task 7: Corridas reales y README

**Files:**
- Modify: `README.md` (tabla de fuentes y tiempos)

- [ ] **Step 1: Corrida real de cada fuente**, de la más corta a la más larga:

```bash
uv run observatorio scrape puertabierta
uv run observatorio scrape maxibienes
uv run observatorio scrape villacruz
uv run observatorio scrape panorama
uv run observatorio scrape activourbano
```

Expected (cifras del 2026-11-11, con variaciones de unos pocos por ciento):

| Fuente | Esperado |
|---|---|
| puertabierta | ≈ 376 arriendos |
| maxibienes | ≈ 1.787 arriendos + las ventas del valle (Medellín ≈ 351) |
| villacruz | ≈ 700 |
| panorama | > 410 apartamentos en arriendo, más los demás tipos |
| activourbano | ≈ 450 del valle |

Si una corrida falla o descarta muchos anuncios, se aplica superpowers:systematic-debugging: se reproduce con un fixture y se corrige con una prueba que falle primero, como con el 404 de Nutibara.

- [ ] **Step 2: Revisar los Parquet**: la misma revisión del Plan 2 (conteos por fuente y operación, campos no nulos, municipios, medianas de precio y coordenadas fuera del valle) más una búsqueda de `�` en `barrio` y `municipio`.

- [ ] **Step 3: README**: la tabla de fuentes con las 9 inmobiliarias y los tiempos medidos.

- [ ] **Step 4: Verificación completa**: `uv run pre-commit run --all-files && uv run pytest`.

- [ ] **Step 5: Commit** — `docs: las 9 fuentes en el README`. El autor hace `git push`.
