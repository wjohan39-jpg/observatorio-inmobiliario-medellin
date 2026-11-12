# Plan 8: Automatización semanal

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que el pipeline completo corra solo cada semana en GitHub Actions:

`scrape → limpiar → compartidos → agregados → sitio`

- Los datos completos se guardan en el repo **privado** `observatorio-inmobiliario-datos`.
- Las tablas agregadas se publican en el repo público, y el sitio de GitHub Pages se actualiza con ellas.

**Architecture:**
- Un comando nuevo, `observatorio semana`, corre todo el pipeline con carpetas configurables. Si una fuente falla, sigue con las demás. Es Python y se prueba con pytest, igual que los otros comandos.
- El workflow `semanal.yml` es delgado: prepara los dos repos, llama a `observatorio semana` y sube los resultados.
- El repo privado se clona en `datos-privados/`, una carpeta ignorada por git, con esta estructura:
  - `crudo/<fuente>/AAAA-SNN.parquet`
  - `limpio/AAAA-SNN.parquet`
  - `compartidos/...`

**Tech Stack:** Python 3.12+, GitHub Actions, un token de acceso personal *fine-grained* de GitHub. No hay dependencias nuevas.

**Spec:** `docs/superpowers/specs/2026-11-10-scraper-inmobiliario-medellin-design.md`. Las partes que aplican:
- §3 metas: "ejecución automática semanal con histórico acumulado";
- §5: "GitHub Actions (cron semanal)";
- §7: el workflow "corre el pipeline, hace push de los datos crudos al repo privado y de los agregados al público";
- §7.1: los datos completos van solo al repo privado.

## Global Constraints

- **Los datos completos nunca llegan al repo público.** `crudo`, `limpio` y `compartidos` van solo a `observatorio-inmobiliario-datos`, que **debe ser privado**. Al público solo llega `data/agregados/`, que pasa por `guardar_agregado` y su control de columnas privadas.
- **Cortesía** (spec §7.1): se usa el mismo `ClienteCortes` de siempre (robots.txt, límite de velocidad y User-Agent del proyecto). Las fuentes corren **una tras otra**, nunca en paralelo.
- **Una fuente que falla no tumba la semana.** Se registra y se sigue con las demás. Su archivo de la semana no se escribe, y la rotación del Plan 6 ya compara cada fuente con su semana anterior con datos.
- **El token** del repo privado va en el secret `DATOS_TOKEN`, nunca en el código ni en los registros. Es *fine-grained*, con acceso solo a `observatorio-inmobiliario-datos` y permiso **Contents: Read and write**.
- **Sin tarjeta.** GitHub Actions es gratis e ilimitado en repos públicos, y los repos privados también son gratis.
- **Los commits automáticos** usan el bot `github-actions[bot]` con mensajes `chore(datos): semana AAAA-SNN`. El hook local de mensajes no corre en CI, pero se respeta el formato.
- El autor hace sus propios `git add`, `git commit` y `git push`. Los pasos de commit le dan los comandos.

## Review Focus

1. **Falla parcial:** si 3 fuentes fallan y 6 funcionan, el comando sale con 0, el resumen nombra las 3 que fallaron y los agregados se generan con las 6.
2. **Falla total:** si ninguna fuente trae anuncios, el comando sale con 1 y **no** sobrescribe la tabla limpia, los compartidos ni los agregados de la semana anterior.
3. **Semana repetida:** correr dos veces la misma semana (un reintento manual) sobrescribe los archivos de esa semana, sin duplicar filas ni semanas.
4. **Nada que publicar:** si los agregados no cambiaron, el workflow no crea un commit vacío.
5. **Sitio:** un push hecho con `GITHUB_TOKEN` no dispara otros workflows. El sitio se reconstruye porque `pages.yml` escucha `workflow_run` del semanal (solo si terminó bien), no por el push.

---

### Task 1: Comando `observatorio semana`

**Files:**
- Modify: `src/observatorio_inmobiliario/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `_scrape`, `_limpiar`, `_compartidos`, `_agregados` y `REGISTRO` (planes 1 a 6).
- Produces:

```
observatorio semana [--fuentes F ...] [--crudo DIR] [--limpio DIR] [--compartidos DIR]
                    [--agregados DIR] [--resumen ARCHIVO.md] [--max-paginas N]
```

- Las carpetas por defecto son las de siempre (`data/crudo`, `data/limpio`, `data/compartidos` y `data/agregados`). Por defecto corre todas las fuentes de `REGISTRO`, en orden alfabético.
- Por cada fuente llama a `_scrape(...)`. Un código distinto de 0 o una excepción no prevista cuentan como falla, y se sigue con la siguiente.
- Si **al menos una** fuente funcionó: corre `_limpiar` y `_compartidos` sobre la semana actual y luego `_agregados`. Si alguno de esos pasos falla, sale con 1.
- Si **ninguna** funcionó: imprime `ninguna fuente trajo anuncios; no se actualizó nada` y sale con 1, sin tocar limpio, compartidos ni agregados.
- `--resumen` escribe un Markdown, que el workflow muestra en la página de la corrida. Contiene:
  - una tabla `| Fuente | Anuncios | Estado |`;
  - la semana;
  - las filas de cada tabla agregada.

- [ ] **Step 1: Escribir las pruebas que fallan.** Usan fuentes falsas con `monkeypatch` sobre `crear_fuente`, igual que las pruebas de `scrape`.

```python
def test_semana_corre_todo(tmp_path)                 # 2 fuentes falsas OK → crudo, limpio, compartidos y 9 agregados; exit 0
def test_semana_falla_parcial(tmp_path, capsys)      # Review Focus 1: una lanza ErrorDeDescarga → exit 0; el resumen la nombra; agregados con la otra
def test_semana_falla_total(tmp_path, capsys)        # Review Focus 2: todas fallan → exit 1; los agregados previos quedan intactos (misma mtime)
def test_semana_excepcion_inesperada(tmp_path)       # una fuente lanza RuntimeError → se registra y sigue
def test_semana_repetida(tmp_path)                   # Review Focus 3: dos corridas → una sola semana en limpio y la misma cantidad de filas
def test_semana_resumen_markdown(tmp_path)           # el archivo tiene la tabla de fuentes y las 9 tablas
def test_semana_fuentes_elegidas(tmp_path)           # --fuentes santafe → solo esa
```

- [ ] **Step 2: Correr y ver que fallan.** Run: `uv run pytest tests/test_cli.py -q -k semana`. Expected: FAIL (`invalid choice: 'semana'`).
- [ ] **Step 3: Implementar.** Las funciones `_scrape`, `_limpiar`, `_compartidos` y `_agregados` ya existen y devuelven un código de salida, así que `_semana` las orquesta sin duplicar su lógica.
- [ ] **Step 4: Correr y ver que pasan.** Run: `uv run pytest -q && uv run mypy`. Expected: toda la suite pasa.
- [ ] **Step 5: Commit** (lo hace el autor)

```bash
git add src/observatorio_inmobiliario/cli.py tests/test_cli.py
git commit -m "feat: comando semana que corre el pipeline completo"
```

---

### Task 2: Repo privado de datos y token (pasos del autor)

Todo esto se hace en github.com y en Git Bash. No hay código.

- [ ] **Step 1 (autor): volver privado el repo de datos.** Hoy `observatorio-inmobiliario-datos` es **público**; lo confirmó la API de GitHub el 2026-11-12, y está vacío. Ruta: *Settings → General → Danger Zone → Change repository visibility → Make private*.
- [ ] **Step 2 (autor): crear el token.** En *github.com → Settings (del perfil) → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token*:
  - nombre `observatorio-datos`;
  - vencimiento de 1 año;
  - *Repository access: Only select repositories* → `observatorio-inmobiliario-datos`;
  - *Permissions → Contents: Read and write*.

  Se copia el token **sin pegarlo en el chat**.
- [ ] **Step 3 (autor): guardar el token como secret** del repo público. En *observatorio-inmobiliario-medellin → Settings → Secrets and variables → Actions → New repository secret*:
  - nombre `DATOS_TOKEN`;
  - valor, el token.
- [ ] **Step 4 (autor): sembrar el repo privado** con los datos que ya existen (la semana 2026-S46). Comandos en Git Bash, desde `Desktop`:

```bash
git clone https://github.com/wjohan39-jpg/observatorio-inmobiliario-datos.git
cp -r Scraper/data/crudo Scraper/data/limpio Scraper/data/compartidos observatorio-inmobiliario-datos/
cd observatorio-inmobiliario-datos
git add .
git commit -m "chore(datos): semana 2026-S46"
git push
```

- [ ] **Step 5: Verificar.** Claude comprueba con la API pública que el repo **ya no responde sin autenticación** (404 = privado). El autor confirma en la web que tiene las carpetas `crudo/`, `limpio/` y `compartidos/`.

---

### Task 3: Workflow semanal y reconstrucción del sitio

**Files:**
- Create: `.github/workflows/semanal.yml`
- Modify: `.github/workflows/pages.yml` (agregar `workflow_run`), `.gitignore` (`datos-privados/`)
- Test: `tests/test_workflows.py` (se mueve aquí la prueba de `pages.yml` de `test_sitio.py`)

**Interfaces:**
- `semanal.yml`:
  - Se dispara con `schedule: cron "0 11 * * 1"` (lunes 6:00 a. m. en Colombia) y con `workflow_dispatch`. La corrida manual acepta la entrada opcional `fuentes`, para correr solo algunas.
  - `permissions: contents: write`, para el commit de los agregados al público.
  - `concurrency: semanal`. `timeout-minutes: 300`.
  - Pasos:
    1. `actions/checkout@v4` (público).
    2. `actions/checkout@v4` con `repository: wjohan39-jpg/observatorio-inmobiliario-datos`, `token: ${{ secrets.DATOS_TOKEN }}` y `path: datos-privados`.
    3. `setup-uv` y `uv sync --locked --python 3.12`.
    4. `uv run observatorio semana --crudo datos-privados/crudo --limpio datos-privados/limpio --compartidos datos-privados/compartidos --resumen resumen.md`.
    5. Publicar `resumen.md` en `$GITHUB_STEP_SUMMARY`, con `if: always()`.
    6. Commit y push en `datos-privados`, solo si hay cambios (`git diff --cached --quiet ||`).
    7. Commit y push de `data/agregados` en el público, solo si hay cambios.
  - La semana del mensaje del commit sale de `date +%G-S%V`, que es el mismo formato ISO de `semana_de`.
- `pages.yml`: agregar `workflow_run: {workflows: ["Actualización semanal"], types: [completed]}` y, en el job `construir`, `if: github.event_name != 'workflow_run' || github.event.workflow_run.conclusion == 'success'`.

- [ ] **Step 1: Escribir las pruebas que fallan**

```python
def test_semanal_es_yaml_valido()          # cron, workflow_dispatch con la entrada fuentes, permisos contents: write
def test_semanal_usa_el_secret()           # el checkout privado usa secrets.DATOS_TOKEN y path datos-privados; el token no aparece en ningún run
def test_semanal_no_hace_commits_vacios()  # Review Focus 4: cada commit está protegido con git diff --cached --quiet
def test_semanal_rutas_privadas()          # observatorio semana recibe --crudo/--limpio/--compartidos bajo datos-privados/
def test_pages_escucha_al_semanal()        # Review Focus 5: workflow_run del semanal y la condición de éxito
def test_workflow_pages_es_yaml_valido()   # (movida desde test_sitio.py)
```

- [ ] **Step 2: Correr y ver que fallan.** Run: `uv run pytest tests/test_workflows.py -q`. Expected: FAIL (falta `semanal.yml`).
- [ ] **Step 3: Implementar** los dos workflows.
- [ ] **Step 4: Correr y ver que pasan.** Run: `uv run pre-commit run --all-files && uv run pytest -q`. Expected: todo pasa, incluido `check-yaml`.
- [ ] **Step 5: Commit** (lo hace el autor)

```bash
git add .github/workflows/ .gitignore tests/test_workflows.py tests/test_sitio.py
git commit -m "feat: actualización semanal automática en GitHub Actions"
```

---

### Task 4: Primera corrida y README

- [ ] **Step 1 (autor): correr el workflow a mano.**
  - Ruta: *Actions → Actualización semanal → Run workflow*.
  - Primero con `fuentes: santafe`, que es la fuente más pequeña, para probar el circuito completo en pocos minutos.
  - Después, sin filtro.
- [ ] **Step 2: Revisar la corrida.** Claude revisa con la API pública los pasos y su duración, y el autor pega el resumen de la corrida. Hay que comprobar:
  - qué fuentes funcionaron desde los servidores de GitHub (algunas pueden bloquear IP de centros de datos; Cloudflare en Alnago y Santa Fe);
  - cuánto tardó cada una.

  Si una fuente falla siempre desde GitHub, se anota en el README como limitación. No se intenta evadir el bloqueo (spec §7.1).
- [ ] **Step 3: Verificar el resultado.**
  - El repo privado tiene la semana nueva (en `crudo/`, `limpio/` y `compartidos/`).
  - `data/agregados` del público tiene la semana nueva.
  - El sitio muestra la semana nueva.
  - Si es la segunda semana, Evolución ya muestra dos puntos.
- [ ] **Step 4: README.** Agregar:
  - una sección "Automatización" con el diagrama del flujo semanal;
  - dónde se ven las corridas;
  - cómo correrlo a mano;
  - cómo correr el pipeline en local con `observatorio semana`;
  - las fuentes que no funcionen desde GitHub, si las hay.
- [ ] **Step 5: Commit** (lo hace el autor)

```bash
git add README.md
git commit -m "docs: automatización semanal en el README"
```
