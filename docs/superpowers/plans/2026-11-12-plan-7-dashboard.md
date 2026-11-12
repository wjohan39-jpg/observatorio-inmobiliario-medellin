# Plan 7: Dashboard

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Un dashboard web público en Streamlit, con las 6 páginas del spec §8. Lee las tablas de `data/agregados/` y consulta en vivo la reputación de cada inmobiliaria en Google Places. Se publica en Streamlit Community Cloud, con link en el README.

**Architecture:**
- **La lógica vive en el paquete y las páginas son delgadas.**
  - `observatorio_inmobiliario/tablero/` tiene funciones puras que reciben las tablas agregadas y devuelven DataFrames o figuras de plotly. Se prueban con pytest.
  - `app/` tiene los scripts de Streamlit: leen, llaman a esas funciones y muestran. Se prueban de punta a punta con `streamlit.testing.v1.AppTest`, sin navegador.
- **Google Places** queda en un módulo aparte, `reputacion.py`.
  - Usa `httpx` con timeout, una clave que se lee de los secrets y una caché de 24 horas (1.000 consultas gratis al mes).
  - Solo se guarda el `place_id` de cada sede, en `datos_referencia/sedes_google.csv` (spec §7.2).

**Tech Stack:** Python 3.12+, Streamlit, plotly, pandas, httpx, pytest y respx. Las dependencias nuevas son **streamlit** y **plotly**, y van en las dependencias principales: el CI prueba las páginas y Streamlit Cloud instala desde `uv.lock`.

**Spec:** `docs/superpowers/specs/2026-11-10-scraper-inmobiliario-medellin-design.md`. Las partes que aplican:
- §2: preguntas 5 y 6;
- §5: Streamlit, plotly y Streamlit Community Cloud;
- §7: el dashboard lee los agregados;
- §7.1: grupos anónimos;
- §7.2: Google Places;
- §8: páginas.

## Global Constraints

- **El dashboard lee solo `data/agregados/` y `datos_referencia/`.** No lee `data/limpio`, `data/crudo` ni `data/compartidos`, y no necesita el repo privado: el spec lo permitía "si hace falta detalle", y no hace falta.
- **Google Places** (spec §7.2):
  - Solo se piden `rating` y `userRatingCount` (nivel Enterprise, sin `reviews`).
  - Nada se guarda en disco. La caché vive en memoria 24 horas (`st.cache_data(ttl=24 h)`): con unas 15 sedes son unas 450 consultas al mes, dentro de las 1.000 gratis de Place Details Enterprise.
  - Si una inmobiliaria tiene varias sedes, se suman sus reseñas y la calificación es el promedio ponderado por número de reseñas.
  - La clave va en `st.secrets["GOOGLE_PLACES_API_KEY"]` o en la variable de entorno del mismo nombre, nunca en el código.
  - Sin clave, la página de reputación muestra un aviso y el resto funciona.
- **Pregunta 6, reconocimiento (decisión del diseñador):** el indicador es el promedio de tres componentes normalizados de 0 a 1 (cada uno dividido por el máximo entre las 9 inmobiliarias):
  - anuncios;
  - barrios cubiertos;
  - reseñas en Google.

  Si no hay reseñas, se calcula con los otros dos y se avisa.
- Venta y arriendo nunca se mezclan en una gráfica de precios: cada página tiene un selector de operación.
- Todo el texto del dashboard va en español. Cada gráfica tiene un título que dice qué muestra.
- La página de compartidos muestra grupos anónimos (barrio, área, estrato, precio por fuente), sin URL ni texto (spec §7.1).
- La página de metodología incluye el aviso del README: proyecto educativo, y cualquier inmobiliaria que pida retirar sus datos será atendida.
- El autor hace `git add`, `git commit` y `git push`. Los pasos de commit le dan los comandos (mensaje `tipo: descripción`).

## Estructura

```
app/
  Inicio.py                     # página 1: resumen del mercado (entrada de Streamlit)
  pages/
    2_Barrios.py
    3_Inmobiliarias.py          # cobertura, economía, estratos, reputación y reconocimiento
    4_Propiedades_compartidas.py
    5_Evolucion.py
    6_Metodologia.py
src/observatorio_inmobiliario/
  reputacion.py                 # cliente de Google Places y agregación por inmobiliaria
  tablero/
    __init__.py
    datos.py                    # carga de agregados y geojson (con caché de Streamlit)
    graficas.py                 # funciones que devuelven figuras de plotly
datos_referencia/sedes_google.csv   # fuente,sede,place_id
tests/test_reputacion.py, tests/test_tablero.py, tests/test_app.py
```

## Review Focus

1. **Sin clave de Google, o con Google caído** (timeout, 403, 429, JSON sin `rating`): la página de Inmobiliarias se muestra con un aviso, nunca con una traza de error. El reconocimiento se calcula sin reseñas.
2. **Tablas vacías o de una sola semana:** cada página muestra un mensaje ("todavía no hay datos de …") en vez de una gráfica rota. Esto aplica sobre todo a Evolución hoy, y a cualquier tabla si un clon todavía no tiene agregados.
3. **Medianas nulas** (el mínimo por estadística del Plan 6): las gráficas omiten esas barras o zonas, sin `TypeError` de `NA`, como pasó en el notebook.
4. **Un barrio del mapa sin datos** se pinta en gris ("sin datos"), no con el color del valor más bajo.
5. **Un `place_id` inválido o una sede sin reseñas** (`userRatingCount` ausente): esa sede cuenta como 0 reseñas, y la inmobiliaria sigue apareciendo si tiene otras sedes.

Cada punto tiene su prueba en la tarea correspondiente.

---

### Task 1: Datos y gráficas del tablero

**Files:**
- Modify: `pyproject.toml` y `uv.lock` (`uv add streamlit plotly`)
- Create: `src/observatorio_inmobiliario/tablero/__init__.py`, `tablero/datos.py`, `tablero/graficas.py`
- Test: `tests/test_tablero.py`

**Interfaces:**
- Consumes: `leer_agregado`, `TABLAS_AGREGADAS` (Plan 6) y `datos_referencia/barrios_medellin.geojson` (Plan 4).
- Produces:

```python
# tablero/datos.py
RAIZ: Final[Path]                                  # la raíz del repo, calculada desde __file__
def cargar_agregados(directorio: Path | None = None) -> dict[str, pd.DataFrame]   # las 9 tablas; vacías (con columnas) si falta un archivo
def cargar_geojson(ruta: Path | None = None) -> dict[str, Any]
# tablero/graficas.py
def mapa_barrios(precios: pd.DataFrame, geojson: dict[str, Any], operacion: str, tipo: str = "vivienda") -> go.Figure
def ranking_barrios(precios: pd.DataFrame, operacion: str, cuantos: int = 15) -> go.Figure
def comparacion_comunas(precios: pd.DataFrame) -> go.Figure          # venta vs. arriendo por comuna
def cobertura(cobertura: pd.DataFrame) -> go.Figure
def concentracion(cobertura_comuna: pd.DataFrame) -> go.Figure       # mapa de calor inmobiliaria × comuna
def indice_relativo(economia: pd.DataFrame, operacion: str) -> go.Figure
def estratos(estratos: pd.DataFrame) -> go.Figure                    # declarado e inferido distinguibles
def compartidos(compartidos_fuentes: pd.DataFrame, nivel: str) -> go.Figure
def evolucion(evolucion_precios: pd.DataFrame, operacion: str) -> go.Figure
def hay_datos(df: pd.DataFrame) -> bool
```

- `cargar_agregados` y `cargar_geojson` no dependen de Streamlit. Las páginas las envuelven con `st.cache_data`.
- Si falta el archivo de una tabla, `cargar_agregados` devuelve un DataFrame vacío con las columnas de esa tabla. Para conocerlas, cada tabla vacía se arma con su función del Plan 6, aplicada a `base_analisis` de una tabla limpia vacía.
- `mapa_barrios` usa `px.choropleth_map` con `featureidkey="properties.codigo"`. Los barrios sin dato o con la mediana nula quedan fuera de los datos, así se pintan en gris de fondo con un trazo del contorno.

- [ ] **Step 1: Escribir las pruebas que fallan**

```python
def test_cargar_agregados_reales()                 # las 9 tablas de data/agregados con filas
def test_cargar_agregados_falta_archivo(tmp_path)  # Review Focus 2: las 9 claves, vacías y con columnas
def test_cargar_geojson()                          # 349 features
def test_mapa_barrios_omite_nulos()                # Review Focus 3 y 4: una mediana nula no está en los datos de la figura
def test_ranking_barrios_cuantos()                 # 15 más caros, ordenados
def test_graficas_con_tablas_vacias()              # Review Focus 2: cada función con su tabla vacía → figura sin error
def test_estratos_distingue_inferidos()            # dos trazas por grupo (declarado, inferido)
def test_hay_datos()
```

- [ ] **Step 2: Correr y ver que fallan.** Run: `uv run pytest tests/test_tablero.py -q`. Expected: FAIL con `ModuleNotFoundError`.
- [ ] **Step 3: Implementar.** Los colores van en una paleta fija en `graficas.py`, la misma para la misma inmobiliaria en todas las páginas.
- [ ] **Step 4: Correr y ver que pasan.** Run: `uv run pytest -q && uv run mypy`. Expected: toda la suite pasa. Si plotly no trae tipos, va un `ignore_missing_imports` en `pyproject.toml`, como pyarrow.
- [ ] **Step 5: Commit** (lo hace el autor)

```bash
git add pyproject.toml uv.lock src/observatorio_inmobiliario/tablero/ tests/test_tablero.py
git commit -m "feat: datos y gráficas del dashboard"
```

---

### Task 2: Reputación con Google Places (pregunta 5) y reconocimiento (pregunta 6)

**Files:**
- Create: `src/observatorio_inmobiliario/reputacion.py`, `datos_referencia/sedes_google.csv` (solo el encabezado; los `place_id` se llenan en la Task 5)
- Modify: `src/observatorio_inmobiliario/cli.py` (comando `google buscar`)
- Test: `tests/test_reputacion.py`, `tests/test_cli.py`

**Interfaces:**
- Produces:

```python
URL_DETALLE: Final = "https://places.googleapis.com/v1/places/{place_id}"
URL_BUSQUEDA: Final = "https://places.googleapis.com/v1/places:searchText"
CAMPOS: Final = "rating,userRatingCount"
TIEMPO_ESPERA_S: Final = 10.0
@dataclass(frozen=True)
class Reseñas:
    calificacion: float | None
    total: int
def clave_api() -> str | None                               # GOOGLE_PLACES_API_KEY del entorno
def cargar_sedes(ruta: Path | None = None) -> pd.DataFrame   # fuente, sede, place_id
def consultar_sede(cliente: httpx.Client, place_id: str, clave: str) -> Reseñas
def reputacion(sedes: pd.DataFrame, consultar: Callable[[str], Reseñas]) -> pd.DataFrame
    # fuente, sedes, resenas, calificacion (ponderada por reseñas; NaN si 0 reseñas)
def buscar_sedes(cliente: httpx.Client, texto: str, clave: str) -> list[dict[str, str]]   # id, nombre, direccion
def reconocimiento(cobertura: pd.DataFrame, reputacion: pd.DataFrame | None) -> pd.DataFrame
    # fuente, anuncios, barrios, resenas, indice (0–1), con_resenas (bool)
```

- `consultar_sede` manda los headers `X-Goog-Api-Key` y `X-Goog-FieldMask: rating,userRatingCount`.
  - Ante un error HTTP, un timeout o un JSON sin los campos, devuelve `Reseñas(None, 0)` y registra el error con `logging.warning`, pero **sin la clave** en el mensaje.
- `reputacion` recibe la función de consulta, y así se prueba sin red. La página le pasa una función con caché.
- `buscar_sedes` usa Text Search (New) con `X-Goog-FieldMask: places.id,places.displayName,places.formattedAddress` y `locationBias` en Medellín.
- Comando: `observatorio google buscar "Arrendamientos Santa Fe Medellín"`. Imprime los candidatos (id, nombre y dirección) para copiarlos al CSV a mano. Sin clave, sale con 1 y el mensaje `falta GOOGLE_PLACES_API_KEY`.

- [ ] **Step 1: Escribir las pruebas que fallan** (con `respx`, igual que los adaptadores)

```python
def test_consultar_sede_ok()                    # headers con la clave y la máscara; Reseñas(4.6, 120)
def test_consultar_sede_sin_resenas()           # Review Focus 5: JSON {} → Reseñas(None, 0)
@pytest.mark.parametrize("estado", [403, 404, 429, 500])
def test_consultar_sede_error(estado, caplog)   # Review Focus 1: Reseñas(None, 0); la clave no aparece en caplog
def test_consultar_sede_timeout()
def test_reputacion_pondera_sedes()             # (4.0, 100) y (5.0, 300) → 4.75 y 400
def test_reputacion_sede_invalida()             # Review Focus 5: una sede con error y otra buena → la inmobiliaria sigue con la buena
def test_reconocimiento_con_y_sin_resenas()     # normalización 0–1; sin reputación → promedio de 2 componentes, con_resenas False
def test_cargar_sedes_vacio()                   # solo el encabezado → 0 filas, 3 columnas
def test_cli_google_buscar(monkeypatch, capsys) # respx + clave en el entorno → imprime id y nombre
def test_cli_google_buscar_sin_clave(capsys)    # exit 1
```

- [ ] **Step 2: Correr y ver que fallan.** Run: `uv run pytest tests/test_reputacion.py -q`. Expected: FAIL con `ModuleNotFoundError`.
- [ ] **Step 3: Implementar.**
- [ ] **Step 4: Correr y ver que pasan.** Run: `uv run pytest -q && uv run mypy`. Expected: toda la suite pasa.
- [ ] **Step 5: Commit** (lo hace el autor)

```bash
git add src/observatorio_inmobiliario/reputacion.py src/observatorio_inmobiliario/cli.py datos_referencia/sedes_google.csv tests/test_reputacion.py tests/test_cli.py
git commit -m "feat: reputación en vivo con Google Places e indicador de reconocimiento"
```

---

### Task 3: Páginas de mercado, barrios e inmobiliarias

**Files:**
- Create: `app/Inicio.py`, `app/pages/2_Barrios.py`, `app/pages/3_Inmobiliarias.py`, `.streamlit/config.toml` (tema)
- Test: `tests/test_app.py`

**Interfaces:**
- Consumes: Tasks 1 y 2.

**Contenido de cada página:**
1. **Inicio (resumen del mercado):**
   - KPIs: anuncios analizados, barrios con precio, mediana del m² en venta y en arriendo, e inmobiliarias;
   - el mapa de barrios con un selector de operación;
   - un texto corto de qué es el proyecto, con la semana de los datos.
2. **Barrios:**
   - selectores de operación y tipo;
   - el ranking de barrios más caros y más baratos por m²;
   - la comparación de venta y arriendo por comuna;
   - una tabla filtrable.
3. **Inmobiliarias:** pestañas de cobertura (con un deslizador de "más de N barrios", pregunta 2), economía, estratos, reputación y reconocimiento.
   - **Reputación:** la tabla de calificación y reseñas, más una nota de atribución ("Calificaciones de Google, consultadas en vivo").
   - **Reconocimiento:** el indicador, con su fórmula explicada.

- [ ] **Step 1: Escribir las pruebas que fallan** (con `AppTest.from_file`, sin red: se hace `monkeypatch` a `reputacion.consultar_sede`)

```python
@pytest.mark.parametrize("pagina", ["app/Inicio.py", "app/pages/2_Barrios.py", "app/pages/3_Inmobiliarias.py"])
def test_pagina_corre_sin_errores(pagina)       # at.run(); not at.exception
def test_inicio_muestra_kpis()                  # 5 st.metric
def test_barrios_cambia_operacion()             # seleccionar "arriendo" y volver a correr sin errores
def test_inmobiliarias_sin_clave()              # Review Focus 1: sin GOOGLE_PLACES_API_KEY → st.info con el aviso; sin excepción
def test_inmobiliarias_con_reputacion_falsa()   # consultar_sede falso → la tabla de reputación tiene filas
```

- [ ] **Step 2: Correr y ver que fallan.** Run: `uv run pytest tests/test_app.py -q`. Expected: FAIL (los archivos no existen).
- [ ] **Step 3: Implementar.** Cada página arranca con `st.set_page_config(page_title=..., layout="wide")` y lee los datos con las funciones cacheadas de la Task 1.
- [ ] **Step 4: Correr y ver que pasan.** Run: `uv run pytest -q && uv run mypy`. Expected: toda la suite pasa.
- [ ] **Step 5: Revisión visual.** Run: `uv run streamlit run app/Inicio.py`. Recorrer las 3 páginas en el navegador y tomar una captura de cada una para el Plan 9.
- [ ] **Step 6: Commit** (lo hace el autor)

```bash
git add app/ .streamlit/config.toml tests/test_app.py
git commit -m "feat: dashboard con mercado, barrios e inmobiliarias"
```

---

### Task 4: Páginas de compartidos, evolución y metodología

**Files:**
- Create: `app/pages/4_Propiedades_compartidas.py`, `app/pages/5_Evolucion.py`, `app/pages/6_Metodologia.py`
- Test: `tests/test_app.py`

**Contenido de cada página:**
4. **Propiedades compartidas:**
   - un selector de confianza mínima (alta / media / baja);
   - las parejas por par de inmobiliarias, con la diferencia de precio y el % de mismo precio;
   - una tabla de grupos anónimos (`grupos_compartidos`): una fila por grupo y una columna de precio por inmobiliaria.
5. **Evolución:**
   - la serie del precio por m² por semana;
   - la rotación por inmobiliaria.
   - Con una sola semana, un `st.info` lo explica en vez de graficar.
6. **Metodología:**
   - las fuentes (las 9 inmobiliarias) y qué se extrae;
   - limpieza, ubicación, atípicos, mínimo de publicación, estrato inferido, índice relativo, emparejamiento y su confianza;
   - limitaciones y aviso legal.
   - El texto sale del README, resumido.

- [ ] **Step 1: Escribir las pruebas que fallan**

```python
@pytest.mark.parametrize("pagina", ["app/pages/4_Propiedades_compartidas.py", "app/pages/5_Evolucion.py", "app/pages/6_Metodologia.py"])
def test_pagina_corre_sin_errores(pagina)
def test_compartidos_sin_columnas_privadas()     # ningún dataframe mostrado tiene id_fuente ni url
def test_evolucion_una_semana_muestra_aviso()    # Review Focus 2
def test_metodologia_tiene_aviso_legal()         # el texto "retirar sus datos" está en la página
```

- [ ] **Step 2: Correr y ver que fallan.** Run: `uv run pytest tests/test_app.py -q`. Expected: FAIL.
- [ ] **Step 3: Implementar.**
- [ ] **Step 4: Correr y ver que pasan.** Run: `uv run pytest -q && uv run mypy`. Expected: toda la suite pasa.
- [ ] **Step 5: Revisión visual** de las 3 páginas con `uv run streamlit run app/Inicio.py`.
- [ ] **Step 6: Commit** (lo hace el autor)

```bash
git add app/pages/ tests/test_app.py
git commit -m "feat: páginas de compartidos, evolución y metodología"
```

---

### Task 5: Sedes de Google, despliegue y README

Esta tarea necesita acciones del autor fuera del repo: crear la clave de Google y la cuenta de Streamlit. Las cuentas son suyas, y las claves nunca pasan por el chat.

- [ ] **Step 1 (autor): clave de Google Places.** En Google Cloud Console:
  1. crear un proyecto;
  2. activar **Places API (New)**;
  3. crear una clave de API restringida a esa API;
  4. guardarla en un archivo `.env` local (ya está en `.gitignore`) como `GOOGLE_PLACES_API_KEY=...`.
- [ ] **Step 2: Buscar las sedes.** Para cada una de las 9 inmobiliarias, run: `uv run --env-file .env observatorio google buscar "<nombre> Medellín"`. Se copian al CSV los `place_id` de las sedes de Medellín y el Valle de Aburrá. El autor confirma cada sede, porque hay homónimos.
- [ ] **Step 3: Probar en local** con la clave. Run: `uv run --env-file .env streamlit run app/Inicio.py`. Expected: la pestaña de reputación muestra las 9 inmobiliarias, o las que tengan sede.
- [ ] **Step 4 (autor): desplegar.** En share.streamlit.io, entrar con GitHub y crear la app:
  - repo `observatorio-inmobiliario-medellin`, rama `main`, archivo `app/Inicio.py`;
  - Python 3.12;
  - en *Secrets*: `GOOGLE_PLACES_API_KEY = "..."`.
- [ ] **Step 5: Verificar la app publicada.** Abrir el link, recorrer las 6 páginas y revisar los logs.
- [ ] **Step 6: README.** Agregar:
  - un badge y el link en vivo arriba del todo;
  - una sección "Dashboard" con las 6 páginas y cómo correrlo en local (`uv run streamlit run app/Inicio.py`, con la clave opcional).
- [ ] **Step 7: Verificación completa.** Run: `uv run pre-commit run --all-files && uv run pytest`. Expected: todo pasa.
- [ ] **Step 8: Commit** (lo hace el autor)

```bash
git add datos_referencia/sedes_google.csv README.md
git commit -m "feat: sedes de Google Places y dashboard publicado"
```
