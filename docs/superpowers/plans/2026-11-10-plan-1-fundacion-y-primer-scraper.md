# Plan 1: Fundación y primer scraper (Santa Fe)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dejar un repositorio con estructura profesional donde `observatorio scrape santafe` descarga los anuncios de Arrendamientos Santa Fe, los valida y los guarda en Parquet semanal.

**Architecture:** Paquete Python en layout `src/`. Cada sitio es un adaptador que cumple el protocolo `Fuente` y entrega objetos `AnuncioNormalizado` (pydantic). Todas las peticiones pasan por `ClienteCortes`, que respeta `robots.txt`, limita la velocidad y reintenta. El almacenamiento escribe un Parquet por fuente y por semana ISO.

**Tech Stack:** Python ≥3.12, uv, httpx, pydantic v2, pandas, pyarrow, pytest, respx, ruff, mypy, pre-commit, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-11-10-scraper-inmobiliario-medellin-design.md`

**Hoja de ruta:** `docs/superpowers/plans/2026-11-10-hoja-de-ruta.md`

## Global Constraints

- Todo en español: nombres de módulos, funciones, variables, docstrings, mensajes de log, README y commits. Excepciones: palabras clave de Python y nombres de librerías.
- Python `>=3.12`.
- Se respeta `robots.txt` en todas las peticiones, con un mínimo de **1,5 s** entre peticiones al mismo sitio.
- User-Agent: `ObservatorioInmobiliarioMedellin/0.1 (+https://github.com/wjohan39-jpg/observatorio-inmobiliario-medellin)`, donde `wjohan39-jpg` es el usuario de GitHub del autor, en `config.py`.
- Solo se guardan datos de hecho. **Prohibido** guardar fotos, descripciones, nombres, teléfonos o correos de asesores.
- No se usan credenciales ajenas ni filtradas.
- Los datos crudos (`data/crudo/`) **nunca** se suben al repo público. Están en `.gitignore`.
- Los secretos (claves de API) solo van en variables de entorno o `.env`, que está en `.gitignore`.
- Mensajes de commit con el formato `tipo: descripción` (`feat`, `fix`, `test`, `chore`, `docs`).

## Review Focus

1. **Precios con formatos raros** (`"$ 2.500.000"`, `"Consultar"`, `0`, `""`): deben convertirse en entero o en `None`, nunca en un crash ni en un precio falso. Pruebas en la Tarea 2.
2. **Un anuncio inválido o un detalle que falla** no debe tumbar toda la corrida. Se registra una advertencia, se descarta o se completa con `None`, y la corrida sigue. Pruebas en la Tarea 5.
3. **Errores de red** (timeout, 429, 5xx): se reintentan con espera creciente. Después del último intento se lanza `ErrorDeDescarga`, y un 404 no se reintenta. Pruebas en la Tarea 4.
4. **Rutas bloqueadas por robots.txt**: el cliente se niega a pedirlas (`ErrorRutaBloqueadaPorRobots`). Pruebas en la Tarea 4.
5. **Correr dos veces la misma semana**: debe sobrescribir el mismo archivo, sin duplicar filas. Pruebas en la Tarea 6.

---

## Estructura de archivos

```
observatorio-inmobiliario-medellin/
├─ pyproject.toml
├─ README.md
├─ .gitignore
├─ .pre-commit-config.yaml
├─ .github/workflows/ci.yml
├─ docs/superpowers/{specs,plans}/...
├─ data/crudo/                      (ignorado por git)
├─ src/observatorio_inmobiliario/
│  ├─ __init__.py                   __version__
│  ├─ config.py                     USER_AGENT, constantes
│  ├─ parseo.py                     parsear_precio / parsear_entero / parsear_decimal
│  ├─ modelos.py                    Operacion, AnuncioNormalizado
│  ├─ http.py                       ClienteCortes y excepciones
│  ├─ almacenamiento.py             guardar/leer Parquet
│  ├─ cli.py                        comando `observatorio`
│  └─ fuentes/
│     ├─ __init__.py                REGISTRO de fuentes
│     ├─ base.py                    Protocol Fuente
│     └─ santafe.py                 FuenteSantaFe, mapear_anuncio
└─ tests/
   ├─ fixtures/santafe/{listado_arriendo_p1.json, detalle.json}
   ├─ test_parseo.py
   ├─ test_modelos.py
   ├─ test_http.py
   ├─ test_santafe.py
   ├─ test_almacenamiento.py
   └─ test_cli.py
```

---

### Tarea 0: Repositorios y git (guiada con el autor)

Esta tarea no tiene pruebas. Es el primer acercamiento del autor a git y se hace explicando cada comando.

- [ ] **Paso 1:** El autor crea en GitHub dos repos **vacíos** (sin README ni .gitignore):
  - `observatorio-inmobiliario-medellin`, **público**.
  - `observatorio-inmobiliario-datos`, **privado**. Se usa a partir del Plan 8.
- [ ] **Paso 2:** El autor configura su identidad, si no lo ha hecho:
  ```bash
  git config --global user.name "<Nombre>"
  git config --global user.email "<correo de GitHub>"
  ```
- [ ] **Paso 3:** En `C:\Users\Wesly Johan\Desktop\Scraper`, se inicializa el repo y se crea el primer commit con los documentos:
  ```bash
  git init -b main
  git add docs/
  git commit -m "docs: diseño y hoja de ruta del proyecto"
  git remote add origin https://github.com/wjohan39-jpg/observatorio-inmobiliario-medellin.git
  git push -u origin main
  ```
  Esperado: los documentos se ven en GitHub.

---

### Tarea 1: Esqueleto del proyecto, calidad y CI

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `.pre-commit-config.yaml`, `.github/workflows/ci.yml`, `README.md`, `src/observatorio_inmobiliario/__init__.py`, `src/observatorio_inmobiliario/config.py`
- Test: `tests/test_version.py`

**Interfaces:**
- Produces: `observatorio_inmobiliario.__version__: str = "0.1.0"`; `config.USER_AGENT: str`; `config.SEGUNDOS_ENTRE_PETICIONES: float = 1.5`.

- [ ] **Paso 1:** Instalar uv (`pip install uv`) y crear `pyproject.toml`:
  - nombre `observatorio-inmobiliario`, `requires-python = ">=3.12"`
  - dependencias: `httpx`, `pydantic>=2`, `pandas`, `pyarrow`
  - grupo dev: `pytest`, `pytest-cov`, `respx`, `ruff`, `mypy`, `pandas-stubs`, `pre-commit`
  - `[project.scripts] observatorio = "observatorio_inmobiliario.cli:main"`
  - ruff: `line-length = 100`, reglas `E,F,I,UP,B,SIM`
  - mypy: `strict = true`, `plugins = ["pydantic.mypy"]`
  - pytest: `testpaths = ["tests"]`
- [ ] **Paso 2:** `.gitignore` con la plantilla de Python, más `data/crudo/`, `.env` y `.venv/`.
- [ ] **Paso 3:** Escribir `tests/test_version.py`:
  ```python
  from observatorio_inmobiliario import __version__

  def test_version_definida():
      assert __version__ == "0.1.0"
  ```
- [ ] **Paso 4:** Correr `uv run pytest`. Esperado: FAIL (no existe el módulo).
- [ ] **Paso 5:** Crear `__init__.py` con `__version__` y `config.py` con `USER_AGENT` y `SEGUNDOS_ENTRE_PETICIONES`.
- [ ] **Paso 6:** Correr `uv sync` y luego `uv run pytest`. Esperado: 1 passed.
- [ ] **Paso 7:** `.pre-commit-config.yaml` con ruff (lint + format) y mypy. Correr `uv run pre-commit install` y `uv run pre-commit run --all-files`. Esperado: todo Passed.
- [ ] **Paso 8:** `.github/workflows/ci.yml`: en `push` y `pull_request`, configura uv, `uv sync`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy src` y `uv run pytest --cov`.
- [ ] **Paso 9:** `README.md` inicial: título, una línea de qué es el proyecto, la sección "Estado: en construcción", la línea `uv sync && uv run pytest` y el badge de CI.
- [ ] **Paso 10:** Commit y push. Esperado: CI en verde en GitHub.
  ```bash
  git add .
  git commit -m "chore: esqueleto del proyecto con pruebas, linter y CI"
  git push
  ```

---

### Tarea 2: Parseo de valores

**Files:**
- Create: `src/observatorio_inmobiliario/parseo.py`
- Test: `tests/test_parseo.py`

**Interfaces:**
- Produces:
  - `parsear_precio(valor: str | int | float | None) -> int | None`: pesos colombianos. Usa `.` como separador de miles y `,` como decimal. Devuelve `None` si el valor está vacío, no es numérico o es ≤ 0.
  - `parsear_entero(valor: str | int | float | None) -> int | None`: extrae el primer número entero (`"3 habitaciones"` → 3).
  - `parsear_decimal(valor: str | int | float | None) -> float | None`: áreas (`"85,5 m²"` → 85.5, `"120 m2"` → 120.0).

- [ ] **Paso 1:** Escribir las pruebas parametrizadas:
  ```python
  @pytest.mark.parametrize("entrada,esperado", [
      ("$ 2.500.000", 2_500_000), ("$1.200.000,50", 1_200_000), (2500000, 2_500_000),
      (2500000.0, 2_500_000), ("2500000", 2_500_000), ("Consultar", None),
      ("", None), (None, None), (0, None), ("$ 0", None), (-5, None),
  ])
  def test_parsear_precio(entrada, esperado): assert parsear_precio(entrada) == esperado

  @pytest.mark.parametrize("entrada,esperado", [
      ("3 habitaciones", 3), (2, 2), ("2.0", 2), ("", None), (None, None), ("N/A", None),
  ])
  def test_parsear_entero(entrada, esperado): ...

  @pytest.mark.parametrize("entrada,esperado", [
      ("85,5 m²", 85.5), ("120 m2", 120.0), (64, 64.0), ("1.250 m²", 1250.0),
      ("", None), (None, None), ("0", None),
  ])
  def test_parsear_decimal(entrada, esperado): ...
  ```
- [ ] **Paso 2:** Correr `uv run pytest tests/test_parseo.py -v`. Esperado: FAIL (ImportError).
- [ ] **Paso 3:** Implementar las tres funciones con `re`. En `parsear_decimal`, el `.` seguido de exactamente 3 dígitos se interpreta como separador de miles.
- [ ] **Paso 4:** Correr la prueba de nuevo. Esperado: todo PASS.
- [ ] **Paso 5:** Commit: `feat: funciones de parseo de precios, enteros y áreas`.

---

### Tarea 3: Modelo `AnuncioNormalizado`

**Files:**
- Create: `src/observatorio_inmobiliario/modelos.py`
- Test: `tests/test_modelos.py`

**Interfaces:**
- Produces:
  ```python
  class Operacion(StrEnum):
      VENTA = "venta"
      ARRIENDO = "arriendo"

  class AnuncioNormalizado(BaseModel):  # model_config = ConfigDict(frozen=True, extra="forbid")
      fuente: str                       # min_length=1, p. ej. "santafe"
      id_fuente: str                    # min_length=1
      url: str | None
      operacion: Operacion
      tipo_inmueble: str | None         # en minúsculas: "apartamento", "casa", ...
      precio: int | None                # COP, > 0
      administracion: int | None        # COP, >= 0
      area_m2: float | None             # 0 < x < 100_000
      habitaciones: int | None          # 0..50
      banos: int | None                 # 0..50
      parqueaderos: int | None          # 0..50
      estrato: int | None               # 1..6
      barrio: str | None                # tal como viene, sin espacios sobrantes
      municipio: str | None
      latitud: float | None             # -90..90
      longitud: float | None            # -180..180
      anunciante_origen: str | None
      fecha_observacion: date
  ```
  Todos los campos `| None` tienen `None` por defecto. Hay un validador que hace `strip()` a los strings y convierte `""` en `None`, y otro que pasa `tipo_inmueble` a minúsculas.

- [ ] **Paso 1:** Escribir las pruebas:
  - `test_anuncio_valido_minimo`: con solo `fuente`, `id_fuente`, `operacion` y `fecha_observacion` se crea el objeto, y el resto de campos queda en `None`.
  - `test_estrato_fuera_de_rango_falla`: `estrato=7` lanza `ValidationError`, y `estrato=0` también.
  - `test_precio_no_positivo_falla`: `precio=0` lanza `ValidationError`.
  - `test_strings_se_limpian`: `barrio="  Laureles "` → `"Laureles"`, `barrio=""` → `None`.
  - `test_tipo_en_minusculas`: `"APARTAMENTO"` → `"apartamento"`.
  - `test_campo_extra_prohibido`: `telefono="300..."` lanza `ValidationError`. Esto protege la regla de no guardar datos personales.
  - `test_es_inmutable`: asignar `a.precio = 1` lanza `ValidationError`.
- [ ] **Paso 2:** Correr las pruebas. Esperado: FAIL.
- [ ] **Paso 3:** Implementar `modelos.py` usando `Field(gt=0)`, `Field(ge=1, le=6)`, etc.
- [ ] **Paso 4:** Correr las pruebas. Esperado: PASS.
- [ ] **Paso 5:** Commit: `feat: modelo AnuncioNormalizado con validaciones`.

---

### Tarea 4: Cliente HTTP cortés

**Files:**
- Create: `src/observatorio_inmobiliario/http.py`
- Test: `tests/test_http.py`

**Interfaces:**
- Consumes: `config.USER_AGENT`, `config.SEGUNDOS_ENTRE_PETICIONES`.
- Produces:
  ```python
  class ErrorDeDescarga(Exception): ...
  class ErrorRutaBloqueadaPorRobots(Exception): ...

  class ClienteCortes:
      def __init__(
          self,
          url_base: str,
          *,
          segundos_entre_peticiones: float = SEGUNDOS_ENTRE_PETICIONES,
          max_intentos: int = 3,
          timeout: float = 30.0,
          dormir: Callable[[float], None] = time.sleep,
          reloj: Callable[[], float] = time.monotonic,
      ) -> None: ...
      def get_json(self, ruta: str, params: dict[str, str | int] | None = None) -> Any: ...
      def get_texto(self, ruta: str, params: dict[str, str | int] | None = None) -> str: ...
      def cerrar(self) -> None: ...   # también como context manager (__enter__/__exit__)
  ```
- Comportamiento:
  - La primera petición descarga `<url_base>/robots.txt` con `urllib.robotparser`. Si robots.txt da 404, todo queda permitido.
  - Antes de cada petición se verifica `can_fetch(USER_AGENT, url)`. Si la ruta no está permitida, se lanza `ErrorRutaBloqueadaPorRobots`.
  - Si desde la petición anterior pasó menos de `segundos_entre_peticiones`, se llama a `dormir(lo_que_falta)`.
  - Los errores 429, 5xx, `httpx.TimeoutException` y `httpx.TransportError` se reintentan con `dormir(2 ** intento)`, hasta `max_intentos` (intentos totales). Si se agotan, se lanza `ErrorDeDescarga`.
  - Otros errores 4xx lanzan `ErrorDeDescarga` de inmediato, sin reintentar.

- [ ] **Paso 1:** Escribir las pruebas con `respx`. Para el tiempo se usan un `dormir` falso que guarda las llamadas en una lista y un `reloj` controlado.
  - `test_envia_user_agent`: la petición lleva el header `User-Agent == USER_AGENT`.
  - `test_respeta_robots`: con robots `Disallow: /privado`, `get_json("/privado/x")` lanza `ErrorRutaBloqueadaPorRobots` y no hace la petición.
  - `test_robots_404_permite_todo`.
  - `test_espera_entre_peticiones`: dos `get_json` seguidos con el reloj sin avanzar. `dormir` recibe ≈1.5.
  - `test_reintenta_en_503_y_luego_funciona`: responde 503, 503 y luego 200 con `{"ok": true}`. El resultado es `{"ok": True}` y en `dormir` aparecen las esperas 2 y 4.
  - `test_falla_tras_agotar_intentos`: siempre 500, lanza `ErrorDeDescarga`.
  - `test_404_no_reintenta`: se lanza `ErrorDeDescarga` y la ruta se llamó una sola vez.
- [ ] **Paso 2:** Correr las pruebas. Esperado: FAIL.
- [ ] **Paso 3:** Implementar `ClienteCortes` sobre `httpx.Client(base_url=..., headers={"User-Agent": ...}, timeout=..., follow_redirects=True)`.
- [ ] **Paso 4:** Correr las pruebas. Esperado: PASS.
- [ ] **Paso 5:** Commit: `feat: cliente HTTP que respeta robots.txt, limita velocidad y reintenta`.

---

### Tarea 5: Protocolo `Fuente` y adaptador Santa Fe

**Files:**
- Create: `src/observatorio_inmobiliario/fuentes/__init__.py`, `fuentes/base.py`, `fuentes/santafe.py`, `tests/fixtures/santafe/listado_arriendo_p1.json`, `tests/fixtures/santafe/detalle.json`
- Test: `tests/test_santafe.py`

**Interfaces:**
- Consumes: `ClienteCortes`, `ErrorDeDescarga`, `AnuncioNormalizado`, `Operacion`, `parsear_*`.
- Produces:
  ```python
  # base.py
  class Fuente(Protocol):
      nombre: str
      def listar_anuncios(self) -> Iterator[AnuncioNormalizado]: ...

  # santafe.py
  URL_BASE = "https://arrendamientossantafe.com"
  def mapear_anuncio(resultado: dict[str, Any], detalle: dict[str, Any] | None, fecha: date) -> AnuncioNormalizado: ...
  class FuenteSantaFe:
      nombre = "santafe"
      def __init__(self, cliente: ClienteCortes, *, con_detalle: bool = True,
                   max_paginas: int | None = None, fecha: date | None = None) -> None: ...
      def listar_anuncios(self) -> Iterator[AnuncioNormalizado]: ...

  # fuentes/__init__.py
  REGISTRO: dict[str, Callable[..., Fuente]] = {"santafe": FuenteSantaFe}
  def crear_fuente(nombre: str, **opciones: Any) -> Fuente: ...  # crea su propio ClienteCortes(URL_BASE)
  ```
- Datos de la API (revisión del 2026-11-10):
  - Listado: `GET /apisf/properties?page=N&oferta=Arriendo|Venta` devuelve `{total, page, per_page: 12, has_more, results[]}`. Cada resultado trae `codigo`, `title`, `price_raw`, `location` (barrio), `ciudad`, `type`, `size`, `bedrooms`, `bathrooms`, `lat`, `lng`, `oferta` y `url`.
  - Detalle: `GET /apisf/property/{codigo}` devuelve, entre otros, `estrato`, `area`, `habitaciones`, `banos`, `parqueaderos`, `sector`, `direccion` y `tipo`.
  - **Los nombres exactos de las claves se confirman con el fixture del Paso 1.** Si alguno difiere, manda el fixture y se ajusta el mapeo.
- Reglas de mapeo:
  - `oferta` se pasa a `Operacion` sin importar mayúsculas.
  - El dato del detalle tiene prioridad sobre el del listado cuando ambos existen.
  - `fuente="santafe"`, `id_fuente=codigo` y `url` según la API.
  - **No se mapean** `title` (texto), `direccion`, fotos ni datos de asesores.
- Paginación: para cada `oferta` en `("Arriendo", "Venta")`, se recorren páginas desde 1 mientras `has_more` sea verdadero y no se supere `max_paginas`.
- Tolerancia a errores: si el detalle lanza `ErrorDeDescarga`, se registra un `logger.warning` y se mapea solo con el listado. Si `mapear_anuncio` lanza `ValidationError`, se registra un `logger.warning` con el código del anuncio y se omite.

- [ ] **Paso 1:** Capturar los fixtures con **una sola petición de cada tipo** y guardarlos recortados a 3 resultados:
  ```bash
  curl -s "https://arrendamientossantafe.com/apisf/properties?page=1&oferta=Arriendo" -A "<USER_AGENT>" > tests/fixtures/santafe/listado_arriendo_p1.json
  curl -s "https://arrendamientossantafe.com/apisf/property/<codigo del primer resultado>" -A "<USER_AGENT>" > tests/fixtures/santafe/detalle.json
  ```
  Abrir los dos archivos, borrar campos de fotos, textos o asesores, y anotar los nombres reales de las claves.
- [ ] **Paso 2:** Escribir las pruebas:
  - `test_mapear_anuncio_con_detalle`: con el resultado 0 del fixture y `detalle.json`, se obtiene `operacion == Operacion.ARRIENDO`, `estrato` y `area_m2` iguales a los valores del fixture, `fuente == "santafe"` e `id_fuente` igual al `codigo` del fixture.
  - `test_mapear_anuncio_sin_detalle`: `estrato is None` y el `precio` coincide con `price_raw` parseado.
  - `test_cumple_protocolo_fuente`: `isinstance(FuenteSantaFe(cliente), Fuente)`, con `Fuente` marcado `@runtime_checkable`.
  - `test_pagina_hasta_has_more_false` (respx): para arriendo, la página 1 tiene `has_more: true` y la página 2 `has_more: false`. Para venta, una sola página vacía. Con `con_detalle=False`, el número de anuncios es igual a la suma de resultados.
  - `test_max_paginas`: con `max_paginas=1` se pide solo `page=1` de cada oferta.
  - `test_detalle_falla_no_tumba_corrida`: el detalle responde 404 y el anuncio igual sale, con `estrato is None`.
  - `test_anuncio_invalido_se_omite`: un resultado con `oferta: "Permuta"` no sale, el resto sí, y `caplog` contiene una advertencia.
- [ ] **Paso 3:** Correr las pruebas. Esperado: FAIL.
- [ ] **Paso 4:** Implementar `base.py`, `santafe.py` y `fuentes/__init__.py`.
- [ ] **Paso 5:** Correr las pruebas. Esperado: PASS.
- [ ] **Paso 6:** Commit: `feat: protocolo Fuente y adaptador de Arrendamientos Santa Fe`.

---

### Tarea 6: Almacenamiento en Parquet

**Files:**
- Create: `src/observatorio_inmobiliario/almacenamiento.py`
- Test: `tests/test_almacenamiento.py`

**Interfaces:**
- Consumes: `AnuncioNormalizado`.
- Produces:
  ```python
  def ruta_semana(directorio: Path, fuente: str, fecha: date) -> Path:
      # directorio / fuente / f"{año_iso}-S{semana_iso:02d}.parquet"   p. ej. data/crudo/santafe/2026-S46.parquet
  def guardar_observaciones(anuncios: Iterable[AnuncioNormalizado], directorio: Path) -> list[Path]:
      # agrupa por (fuente, semana ISO de fecha_observacion); SOBRESCRIBE cada archivo; devuelve las rutas escritas
  def leer_observaciones(directorio: Path, fuente: str | None = None) -> pd.DataFrame:
      # concatena todos los Parquet (o los de una fuente); DataFrame vacío con las columnas del modelo si no hay archivos
  ```
  Columnas: los campos de `AnuncioNormalizado` en su orden. `operacion` se guarda como string y `fecha_observacion` como date.

- [ ] **Paso 1:** Escribir las pruebas (con `tmp_path`):
  - `test_ruta_semana`: `ruta_semana(Path("d"), "santafe", date(2026, 11, 10)) == Path("d/santafe/2026-S46.parquet")`.
  - `test_guardar_y_leer_ida_y_vuelta`: guardar 3 anuncios y leerlos da 3 filas, con valores y tipos iguales (`None` → `NaN`/`<NA>` aceptado).
  - `test_misma_semana_sobrescribe`: guardar los mismos 3 anuncios dos veces deja 3 filas, no 6.
  - `test_semanas_distintas_archivos_distintos`: con fechas en semanas 46 y 47 se escriben 2 archivos y se leen 6 filas.
  - `test_leer_directorio_vacio`: devuelve un DataFrame vacío con las columnas del modelo.
- [ ] **Paso 2:** Correr las pruebas. Esperado: FAIL.
- [ ] **Paso 3:** Implementar con `pandas.DataFrame([a.model_dump(mode="json") ...])` y `to_parquet(engine="pyarrow", index=False)`. Crear las carpetas con `mkdir(parents=True, exist_ok=True)`.
- [ ] **Paso 4:** Correr las pruebas. Esperado: PASS.
- [ ] **Paso 5:** Commit: `feat: almacenamiento semanal en Parquet`.

---

### Tarea 7: CLI y primera corrida real

**Files:**
- Create: `src/observatorio_inmobiliario/cli.py`
- Modify: `README.md` (sección "Uso")
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `crear_fuente`, `REGISTRO`, `guardar_observaciones`.
- Produces: `main(argv: list[str] | None = None) -> int`. Uso:
  ```
  observatorio scrape <fuente> [--salida data/crudo] [--sin-detalle] [--max-paginas N]
  ```
  Configura `logging` en nivel INFO. Al terminar imprime `"<fuente>: <n> anuncios guardados en <ruta>"` y devuelve 0. Con una fuente desconocida, argparse muestra un error con las fuentes válidas y devuelve código 2.

- [ ] **Paso 1:** Escribir las pruebas (se usa `monkeypatch` para que `crear_fuente` devuelva una fuente falsa con 2 anuncios):
  - `test_scrape_guarda_y_reporta`: `main(["scrape", "santafe", "--salida", str(tmp_path)]) == 0`, existe 1 archivo Parquet y la salida de `capsys` contiene `"2 anuncios"`.
  - `test_fuente_desconocida`: `main(["scrape", "noexiste"])` lanza `SystemExit` con código 2.
  - `test_opciones_se_pasan`: con `--sin-detalle --max-paginas 1`, `crear_fuente` recibe `con_detalle=False, max_paginas=1`.
- [ ] **Paso 2:** Correr las pruebas. Esperado: FAIL.
- [ ] **Paso 3:** Implementar `cli.py` con `argparse` y `choices=sorted(REGISTRO)`.
- [ ] **Paso 4:** Correr las pruebas. Esperado: PASS.
- [ ] **Paso 5:** Corrida real pequeña y cortés:
  ```bash
  uv run observatorio scrape santafe --max-paginas 2
  ```
  Esperado: unos 48 anuncios (2 páginas × 12 × 2 ofertas) guardados en `data/crudo/santafe/2026-SXX.parquet`. Se revisan con `uv run python -c "from observatorio_inmobiliario.almacenamiento import leer_observaciones; from pathlib import Path; print(leer_observaciones(Path('data/crudo')).describe(include='all'))"`. Precios, estratos y áreas deben verse razonables.
- [ ] **Paso 6:** Verificación completa: `uv run ruff check . && uv run mypy src && uv run pytest --cov`. Esperado: todo en verde.
- [ ] **Paso 7:** Agregar al README la sección "Uso" con el comando de scrape. Confirmar con `git status` que `data/crudo/` **no** aparece.
- [ ] **Paso 8:** Commit y push: `feat: comando observatorio scrape`. Esperado: CI en verde.
