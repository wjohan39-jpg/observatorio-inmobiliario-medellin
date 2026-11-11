# Plan 4: Limpieza y normalización

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convertir las observaciones crudas de las 9 fuentes en una tabla limpia por semana (`data/limpio/AAAA-SNN.parquet`). Cada anuncio queda con:
- municipio normalizado;
- barrio y comuna oficiales de Medellín;
- tipo de inmueble de un conjunto cerrado;
- precio por m²;
- marca de atípico.

Todo se hace con el comando `observatorio limpiar`.

**Architecture:** La limpieza es un paso aparte: lee `data/crudo/`, nunca lo modifica y escribe `data/limpio/`. Así se puede repetir cuantas veces haga falta sin volver a scrapear. Se divide en tres módulos de funciones puras:
- `normalizacion.py`: textos, municipios y tipos;
- `catalogo.py`: el catálogo oficial de barrios, que ubica por coordenadas y por nombre;
- `limpieza.py`: arma las columnas nuevas y marca los atípicos.

`almacenamiento.py` y `cli.py` solo se extienden.

**Tech Stack:** Python 3.12+, pandas, pyarrow, **shapely 2** (nuevo, para ubicar puntos en polígonos), pytest, ruff, mypy estricto.

**Spec:** `docs/superpowers/specs/2026-11-10-scraper-inmobiliario-medellin-design.md` (§2 preguntas, §3 anti-metas, §6 notas de fuentes, §7 arquitectura: "normalizar barrios (catálogo oficial de barrios y comunas de Medellín), precio/m², detección de outliers").

## Global Constraints

- **No se borra ningún anuncio** (spec §4: "No se eliminan duplicados"; §3: no presentar como seguro algo incierto). Los atípicos y los anuncios sin barrio **se marcan**, no se eliminan. El filtro de Medellín es una función aparte, que se aplica cuando hace falta.
- `data/crudo/` es de solo lectura para la limpieza.
- La tabla limpia conserva todas las columnas crudas, con su nombre y valor originales (spec §7: "barrio (original y normalizado)").
- Toda descarga pasa por `ClienteCortes` (robots.txt y límite de velocidad).
- Ningún archivo versionado puede pasar de 500 KB (lo exige el hook `check-added-large-files --maxkb=500`).
- Venta y arriendo nunca se mezclan en una estadística (spec §2.3). Los umbrales de atípicos son siempre por operación.
- El autor hace `git add`, `git commit` y `git push`. Los pasos de commit le dan los comandos (mensaje `tipo: descripción`, con espacio después de los dos puntos).

## Revisión de los datos y del catálogo (2026-11-11)

**Catálogo oficial.** La Alcaldía publica la capa "Limite Barrio_Vereda Catastral" en su servidor de mapas:

`https://www.medellin.gov.co/servidormapas/rest/services/ServiciosCatastro/Base_Catastral/MapServer/1`

- Tiene **349 polígonos**: los barrios urbanos (`indicador_ur = "U"`) y las veredas de los 5 corregimientos (`"R"`).
- Campos que se usan:
  - `codigo`: 4 dígitos; los dos primeros son la comuna;
  - `nombre_barrio`;
  - `comuna`: 2 dígitos; 01–16 urbanas, y 50, 60, 70, 80 y 90 los corregimientos;
  - `nombre_comuna`, en mayúsculas;
  - `indicador_ur`.
- El robots.txt de medellin.gov.co permite `/servidormapas`.
- La otra capa (`VA_ConsultaOperadorCatastral_geo`) responde 403 y **no se usa**.
- Una sola petición trae todo en GeoJSON, en WGS84 y simplificado a ~11 m. Pesa **396 KB**, por debajo del límite de 500 KB, así que el archivo se versiona en el repo. Parámetros:

```
where=1=1&outFields=codigo,nombre_barrio,comuna,nombre_comuna,indicador_ur
&outSR=4326&geometryPrecision=5&maxAllowableOffset=0.0001&f=geojson
```

- **Nombres repetidos** en el catálogo: Las Palmas, Naranjal, La Esperanza, La Florida, San Pablo, Las Playas, Suburbano El Llano y Pajarito. En casi todos hay uno urbano y uno rural.

**Lo que mostró un prototipo sobre los 8.589 anuncios crudos:**

| Fuente | Anuncios | Con coordenadas | Caen en un polígono de Medellín | Nombre exacto en el catálogo |
|---|---|---|---|---|
| alnago | 1.691 | 1.620 | 1.175 | 688 |
| maxibienes | 2.499 | 0 | — | 983 |
| panorama | 1.106 | 0 | — | 548 |
| nutibara | 982 | 982 | 770 | 431 |
| uribienes | 727 | 727 | 364 | 285 |
| villacruz | 682 | 682 | 599 | 342 |
| activourbano | 478 | 0 | — | 42 |
| puertabierta | 376 | 376 | 214 | 172 |
| santafe | 48 | 47 | 39 | 37 |

- Cuando un anuncio tiene coordenadas y nombre, los dos dan **la misma comuna en el 80 %** de los casos, pero **el mismo barrio solo en el 43 %**. Las coordenadas son precisas: casi todas son únicas por anuncio. Los nombres son coloquiales: "Laureles" y "Belén" son zonas enteras en el habla, pero en el catálogo son barrios pequeños.
  - **Por eso se ubica primero por coordenadas.** El nombre se usa solo si no hay coordenadas, y los nombres de zona se resuelven solo hasta la comuna.
- De los 5.094 anuncios que la fuente dice que están en Medellín, 1.120 no se ubican con ninguno de los dos métodos. Los nombres más frecuentes entre ellos: poblado (133), ciudad del rio (89), estadio (39), belén san bernardo (38), av las palmas (34), manrique (33), manrique central 1 (31), conquistadores (30), belen parque (30), pilarica (27), centro (25), san antonio de prado (25), floresta (23), loma del indio (22), san cristóbal (21), milla de oro (20), los balsos (16), bomboná (15). Las reglas de la Tarea 2 y el archivo de alias están hechos para ellos.
- **Municipios:** la grafía es mixta ("Medellín" 4.370 / "MEDELLIN" 724; "Envigado" / "ENVIGADO"…). Villacruz deja 610 en `None` porque su campo trae un barrio ("LAURELES") o un municipio ("SABANETA"). Hay municipios fuera del valle ("EL RETIRO" 39).
- **Coordenadas fuera del valle:** 16 (Alnago 7, Uribienes 9).
- **Tipos de inmueble:** hay 30 variantes ("casa-local", "apto loft", "comercial (casa para comercio)", "casafinca"…).

## Review Focus

1. **Un punto justo en el borde entre dos barrios** (o sobre un vértice) debe quedar en uno de los dos, siempre el mismo (el de menor código), nunca en `None`.
2. **Variantes de escritura del mismo nombre** deben dar el mismo resultado. Por ejemplo: "BELÉN", "Belen" y "belén"; "Manrique Central No.1", "Manrique Central No. 1" y "manrique central 1"; "Conquistadores" y "Los Conquistadores".
3. **Nombres repetidos en el catálogo** ("Naranjal"): si hay exactamente un barrio urbano con ese nombre, se elige ese. Si no, el resultado es `None`. Nunca se elige uno al azar.
4. **Datos faltantes:** con `precio`, `area_m2` o las coordenadas en `None`, o con un área de 0, no se lanza ninguna excepción. `precio_m2` queda en `None` y la detección estadística de atípicos ignora esa fila.
5. **Contradicción entre el municipio y el polígono:** si la fuente dice "Envigado" pero el punto cae en un polígono de Medellín (algo común en el borde de El Poblado), se conserva Envigado y no se asigna un barrio de Medellín.

Cada punto tiene su prueba en la tarea correspondiente.

---

### Task 1: Normalización de textos, municipios y tipos

**Files:**
- Create: `src/observatorio_inmobiliario/normalizacion.py`
- Test: `tests/test_normalizacion.py`

**Interfaces:**
- Produces:
  - `normalizar_texto(texto: str) -> str`
  - `normalizar_municipio(texto: str | None) -> str | None`
  - `MUNICIPIOS_VALLE: Final[frozenset[str]]`
  - `normalizar_tipo(texto: str | None) -> str`
  - `TIPOS: Final[tuple[str, ...]]`

- [ ] **Step 1: Escribir las pruebas que fallan**

```python
@pytest.mark.parametrize(("crudo", "esperado"), [
    ("BELÉN", "belen"),
    ("  Belén   Los  Alpes ", "belen los alpes"),
    ("Manrique Central No. 1", "manrique central 1"),
    ("Manrique Central No.1", "manrique central 1"),
    ("San José la Cima No.2", "san jose la cima 2"),
    ("El Nogal-Los Almendros", "el nogal los almendros"),
    ("B. Cerro  El Volador", "b cerro el volador"),
    ("Itagüí", "itagui"),
])
def test_normalizar_texto(crudo: str, esperado: str) -> None:
    assert normalizar_texto(crudo) == esperado


@pytest.mark.parametrize(("crudo", "esperado"), [
    ("MEDELLIN", "Medellín"), ("Medellín", "Medellín"), ("medellin ", "Medellín"),
    ("ITAGUI", "Itagüí"), ("La Estrella", "La Estrella"), ("SABANETA", "Sabaneta"),
    ("EL RETIRO", "El Retiro"),          # fuera del valle: se conserva con mayúsculas normales
    ("", None), (None, None),
])
def test_normalizar_municipio(crudo: str | None, esperado: str | None) -> None:
    assert normalizar_municipio(crudo) == esperado


def test_municipios_del_valle() -> None:
    assert MUNICIPIOS_VALLE == {
        "Medellín", "Bello", "Itagüí", "Envigado", "Sabaneta", "La Estrella",
        "Caldas", "Copacabana", "Girardota", "Barbosa",
    }


@pytest.mark.parametrize(("crudo", "esperado"), [
    ("apartamento", "apartamento"), ("apartamento amoblado", "apartamento"),
    ("penthouse", "apartamento"), ("apto loft", "apartaestudio"),
    ("apartaestudio", "apartaestudio"), ("casa", "casa"),
    ("casa - apartamento(s)", "casa"),
    ("casa-local", "local"), ("casa local", "local"),
    ("comercial (casa para comercio)", "local"), ("oficina-local", "local"),
    ("oficina", "oficina"), ("oficina-consultorio", "oficina"), ("consultorio", "consultorio"),
    ("bodega", "bodega"), ("lote", "lote"), ("terreno", "lote"), ("casalote", "lote"),
    ("finca", "finca"), ("casa-finca", "finca"), ("casafinca", "finca"),
    ("casa campestre", "finca"), ("finca de recreo", "finca"),
    ("parqueadero", "parqueadero"), ("garaje", "parqueadero"),
    ("edificio", "edificio"), ("hotel", "edificio"),
    ("inmueble residencial", "otro"), (None, "otro"), ("", "otro"),
])
def test_normalizar_tipo(crudo: str | None, esperado: str) -> None:
    assert normalizar_tipo(crudo) == esperado
    assert esperado in TIPOS
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `uv run pytest tests/test_normalizacion.py -q`
Expected: FAIL (`ModuleNotFoundError: observatorio_inmobiliario.normalizacion`)

- [ ] **Step 3: Implementar `normalizacion.py`**

- **`normalizar_texto`:**
  1. NFKD y quitar marcas diacríticas.
  2. Minúsculas.
  3. Convertir `no.` / `no ` seguido de un número en solo el número, con la regex `\bno\.?\s*(?=\d)`.
  4. Cualquier carácter que no sea `[a-z0-9]` pasa a espacio.
  5. Colapsar los espacios y hacer strip.
- **`normalizar_municipio`:** busca `normalizar_texto(texto)` en un dict normalizado → nombre oficial de los 10 municipios del valle. Si no está, devuelve `texto.strip().title()`. Un texto vacío o `None` da `None`.
- **`normalizar_tipo`:** sobre `normalizar_texto(texto)`, aplica la primera regla que coincide, **en este orden** (el orden define los casos mixtos):

| # | Si contiene | Resultado |
|---|---|---|
| 1 | `apartaestudio`, `loft` | apartaestudio |
| 2 | `local`, `comercial` | local |
| 3 | `oficina` | oficina |
| 4 | `consultorio` | consultorio |
| 5 | `finca`, `campestre` | finca |
| 6 | `lote`, `terreno` | lote |
| 7 | `casa` | casa |
| 8 | `apartamento`, `apto`, `penthouse` | apartamento |
| 9 | `bodega` | bodega |
| 10 | `parqueadero`, `garaje` | parqueadero |
| 11 | `edificio`, `hotel` | edificio |
| — | ninguna | otro |

`TIPOS` es la tupla de los 12 resultados posibles.

- [ ] **Step 4: Correr y ver que pasan**

Run: `uv run pytest tests/test_normalizacion.py -q && uv run mypy`
Expected: todas pasan; mypy `Success`.

- [ ] **Step 5: Commit** (lo hace el autor)

```bash
git add src/observatorio_inmobiliario/normalizacion.py tests/test_normalizacion.py
git commit -m "feat: normalización de textos, municipios y tipos de inmueble"
```

---

### Task 2: Catálogo oficial de barrios

**Files:**
- Create: `src/observatorio_inmobiliario/catalogo.py`
- Create: `datos_referencia/barrios_medellin.geojson` (descargado con el comando de esta tarea)
- Create: `datos_referencia/alias_barrios.csv`
- Create: `tests/fixtures/catalogo/mini.geojson` (3 polígonos sintéticos)
- Modify: `pyproject.toml` (`uv add shapely`; override de mypy si shapely no trae tipos completos)
- Test: `tests/test_catalogo.py`

**Interfaces:**
- Consumes: `normalizar_texto` (Task 1), `ClienteCortes.get_json` (Plan 1).
- Produces:

```python
URL_BASE_CATALOGO: Final = "https://www.medellin.gov.co"
RUTA_CATALOGO: Final = "/servidormapas/rest/services/ServiciosCatastro/Base_Catastral/MapServer/1/query"
RUTA_GEOJSON: Final = Path("datos_referencia/barrios_medellin.geojson")
RUTA_ALIAS: Final = Path("datos_referencia/alias_barrios.csv")

@dataclass(frozen=True)
class Ubicacion:
    codigo_barrio: str | None   # "1418"; None si solo se conoce la comuna
    barrio: str | None          # nombre oficial: "El Poblado"
    comuna: str                 # "14"
    nombre_comuna: str          # "EL POBLADO"
    metodo: str                 # "coordenadas" | "nombre" | "alias"

def descargar_catalogo(cliente: ClienteCortes) -> dict[str, Any]   # GeoJSON; ValueError si < 300 polígonos
class Catalogo:
    @classmethod
    def cargar(cls, ruta_geojson: Path = RUTA_GEOJSON, ruta_alias: Path = RUTA_ALIAS) -> "Catalogo"
    def por_coordenadas(self, latitud: float, longitud: float) -> Ubicacion | None
    def por_nombre(self, texto: str | None) -> Ubicacion | None
```

`mini.geojson` tiene tres cuadrados de 0,01° de lado que comparten bordes:
- `"1101"` "Laureles", comuna "11" LAURELES, lon −75.60 a −75.59, lat 6.24 a 6.25;
- `"1103"` "Naranjal", comuna "11", lon −75.59 a −75.58, lat 6.24 a 6.25;
- `"6005"` "Naranjal", comuna "60" SAN CRISTOBAL, rural, lon −75.60 a −75.59, lat 6.25 a 6.26.

`alias_barrios.csv` tiene las columnas `alias,codigo`. El código es de 4 dígitos (un barrio) o de 2 dígitos (una comuna). Contenido inicial, con las claves ya escritas como las deja `normalizar_texto`:

```
alias,codigo
poblado,14
el poblado,14
ciudad del rio,14
av las palmas,14
avenida las palmas,14
milla de oro,14
los balsos,14
loma del indio,14
la loma del indio,14
laureles,11
estadio,11
belen,16
manrique,03
centro,10
robledo,07
castilla,05
san javier,13
buenos aires,09
guayabal,15
america,12
la america,12
aranjuez,04
san antonio de prado,80
san cristobal,60
barrio antioquia,1503
el nogal,1620
palenque 1 y 2,0716
```

- [ ] **Step 1: Escribir las pruebas que fallan** (con `mini.geojson` y un alias temporal en `tmp_path`, salvo la última)

```python
def test_punto_dentro(catalogo): assert catalogo.por_coordenadas(6.245, -75.595).codigo_barrio == "1101"
def test_metodo_coordenadas(catalogo): assert catalogo.por_coordenadas(6.245, -75.595).metodo == "coordenadas"
def test_punto_fuera(catalogo): assert catalogo.por_coordenadas(6.10, -75.60) is None
def test_punto_en_el_borde_es_el_de_menor_codigo(catalogo):      # Review Focus 1
    assert catalogo.por_coordenadas(6.245, -75.59).codigo_barrio == "1101"
def test_punto_en_el_vertice(catalogo):
    assert catalogo.por_coordenadas(6.25, -75.59).codigo_barrio == "1101"

@pytest.mark.parametrize("texto", ["Laureles", "LAURELES", "laureles "])
def test_alias_de_zona_da_solo_la_comuna(catalogo_con_alias, texto):   # alias "laureles,11"
    u = catalogo_con_alias.por_nombre(texto)
    assert (u.codigo_barrio, u.comuna, u.metodo) == (None, "11", "alias")

def test_nombre_exacto(catalogo): u = catalogo.por_nombre("LAURELES"); assert (u.codigo_barrio, u.metodo) == ("1101", "nombre")
def test_repetido_elige_el_unico_urbano(catalogo):                # Review Focus 3
    assert catalogo.por_nombre("Naranjal").codigo_barrio == "1103"
def test_repetido_sin_urbano_unico_es_none(catalogo_dos_urbanos): assert catalogo_dos_urbanos.por_nombre("Naranjal") is None
def test_articulo_opcional(catalogo_real): assert catalogo_real.por_nombre("Conquistadores").codigo_barrio == "1105"
def test_prefijo_barrio(catalogo_real): assert catalogo_real.por_nombre("Barrio Córdoba").barrio == "Córdoba"
def test_prefijo_de_comuna(catalogo_real):                        # "belén san bernardo"
    assert catalogo_real.por_nombre("Belén San Bernardo").codigo_barrio == "1605"
@pytest.mark.parametrize("texto", ["Manrique Central No.1", "manrique central 1", "MANRIQUE CENTRAL NO. 1"])
def test_variantes_de_numero(catalogo_real, texto):              # Review Focus 2
    assert catalogo_real.por_nombre(texto).codigo_barrio == "0409"
def test_sin_coincidencia(catalogo_real): assert catalogo_real.por_nombre("Torres de Bomboná") is None
def test_vacio(catalogo_real): assert catalogo_real.por_nombre(None) is None and catalogo_real.por_nombre("") is None

def test_catalogo_real():                                         # archivo versionado
    c = Catalogo.cargar()
    assert len(c) == 349
    assert c.por_coordenadas(6.2566, -75.5904).comuna == "11"     # estadio Atanasio Girardot
    assert c.por_coordenadas(6.2087, -75.5676).comuna == "14"     # parque Lleras
    assert c.por_coordenadas(6.1700, -75.5900) is None            # Envigado

def test_alias_apuntan_a_codigos_existentes():
    c = Catalogo.cargar()      # cargar() lanza ValueError si un alias apunta a un código inexistente

def test_descargar_catalogo(respx_mock):    # GET con los parámetros de la revisión; devuelve el JSON
def test_descargar_catalogo_incompleto(respx_mock):   # 10 polígonos → ValueError
```

`catalogo_real` es un fixture de módulo que hace `Catalogo.cargar()` una sola vez.

- [ ] **Step 2: Correr y ver que fallan**

Run: `uv run pytest tests/test_catalogo.py -q`
Expected: FAIL (`ModuleNotFoundError: observatorio_inmobiliario.catalogo`)

- [ ] **Step 3: Agregar shapely y descargar el catálogo**

- `uv add shapely`. Si no instala para Python 3.14: `Ruling:` y reemplazarlo por un ray casting par-impar propio, con la misma interfaz y las mismas pruebas.
- Implementar `descargar_catalogo`: `cliente.get_json(RUTA_CATALOGO, params={...})` con los parámetros de la revisión. Valida `type == "FeatureCollection"` y al menos 300 features.
- Agregar en `cli.py` el subcomando `observatorio catalogo [--salida RUTA_GEOJSON]`:
  - abre `ClienteCortes(URL_BASE_CATALOGO)`;
  - escribe el JSON con `ensure_ascii=False` y `separators=(",", ":")`;
  - imprime cuántos polígonos guardó.
  - Prueba en `tests/test_cli.py` con `descargar_catalogo` simulado.
- Correr `uv run observatorio catalogo`.
  - Expected: `349 barrios y veredas guardados en datos_referencia/barrios_medellin.geojson`, archivo de menos de 500 KB.

- [ ] **Step 4: Implementar `Catalogo`**

**`cargar`:**
- Construye con `shapely.geometry.shape` un polígono por feature.
- Arma un `shapely.STRtree` con los polígonos en orden de `codigo`.
- Arma dos índices:
  - `nombre normalizado → [registros]`, con dos claves por registro: el nombre normalizado, y el mismo nombre sin el artículo inicial `el|la|los|las` si lo tiene;
  - `alias → código`, leído del CSV.
- Valida que cada código del alias exista (4 dígitos) o sea una comuna existente (2 dígitos). Si no, lanza `ValueError` con el alias.
- `__len__` devuelve el número de polígonos.

**`por_coordenadas`:**
- `arbol.query(Point(lon, lat), predicate="intersects")`. `intersects` incluye el borde.
- Toma el índice menor. Como el árbol se armó por código, es el de menor código.
- Ojo: shapely usa `(x, y) = (lon, lat)`.

**`por_nombre(texto)`:**
1. `t = normalizar_texto(texto)`. Si queda vacío → `None`.
2. Si `t` está en los alias → `Ubicacion` con `metodo="alias"`. Un código de 2 dígitos da `codigo_barrio=None` y `barrio=None`.
3. Quitar el prefijo `barrio ` / `urbanizacion ` / `urb ` / `sector `, si lo hay.
4. Buscar `t` en el índice de nombres:
   - un solo registro → ese;
   - varios → el único urbano si hay exactamente uno; si no, `None`.
   - `metodo="nombre"`.
5. Si no hubo resultado y `t` empieza con el nombre normalizado de una comuna urbana más un espacio ("belen san bernardo"), buscar el resto solo entre los barrios de esa comuna, con la misma regla del paso 4.
6. `None`.

- [ ] **Step 5: Correr y ver que pasan**

Run: `uv run pytest tests/test_catalogo.py tests/test_cli.py -q && uv run mypy`
Expected: todas pasan; mypy `Success`.

- [ ] **Step 6: Commit** (lo hace el autor)

```bash
git add pyproject.toml uv.lock src/observatorio_inmobiliario/catalogo.py src/observatorio_inmobiliario/cli.py datos_referencia tests/test_catalogo.py tests/test_cli.py tests/fixtures/catalogo
git commit -m "feat: catálogo oficial de barrios y comunas de Medellín"
```

---

### Task 3: Ubicación, municipio y precio por m²

**Files:**
- Create: `src/observatorio_inmobiliario/limpieza.py`
- Test: `tests/test_limpieza.py`

**Interfaces:**
- Consumes: `normalizar_municipio`, `MUNICIPIOS_VALLE`, `normalizar_tipo` (Task 1); `Catalogo`, `Ubicacion` (Task 2); el DataFrame de `leer_observaciones` (Plan 1).
- Produces:

```python
VALLE_LAT: Final = (6.00, 6.50)
VALLE_LON: Final = (-75.72, -75.30)
def limpiar(crudo: pd.DataFrame, catalogo: Catalogo) -> pd.DataFrame
```

Columnas que agrega, sin tocar las crudas:

| Columna | Tipo | Contenido |
|---|---|---|
| `municipio_normalizado` | string | ver reglas |
| `en_valle` | bool | `municipio_normalizado in MUNICIPIOS_VALLE` |
| `es_medellin` | bool | `municipio_normalizado == "Medellín"` |
| `coordenadas_validas` | bool | lat y lon no nulas y dentro de `VALLE_LAT` / `VALLE_LON` |
| `codigo_barrio`, `barrio_normalizado` | string | de la `Ubicacion` |
| `comuna`, `nombre_comuna` | string | de la `Ubicacion` |
| `metodo_ubicacion` | string | `"coordenadas"`, `"nombre"`, `"alias"` o nulo |
| `tipo_normalizado` | string | `normalizar_tipo(tipo_inmueble)` |
| `precio_m2` | float | `precio / area_m2` si los dos existen y el área es > 0; si no, nulo |

**Reglas, en orden, por fila:**
1. `m = normalizar_municipio(municipio)`.
2. Si `m` es nulo y `normalizar_municipio(barrio)` está en `MUNICIPIOS_VALLE`, ese es el municipio. Es el caso de Villacruz "SABANETA".
3. Si las coordenadas son válidas y `m` es nulo o "Medellín", se usa `catalogo.por_coordenadas`. Si cae en un polígono, el municipio pasa a "Medellín".
   - Si `m` es otro municipio, no se busca por coordenadas (Review Focus 5).
4. Si no se obtuvo ubicación y `m` es nulo o "Medellín", se usa `catalogo.por_nombre(barrio)`. Si da resultado y `m` era nulo, el municipio pasa a "Medellín".

- [ ] **Step 1: Escribir las pruebas que fallan** (con un catálogo pequeño del fixture `mini.geojson` y un DataFrame armado con `leer_observaciones` sobre filas sintéticas, o directamente con las columnas de `ESQUEMA`)

```python
def test_coordenadas_ganan_al_nombre(): # barrio "Naranjal", punto en 1101 → codigo 1101, metodo "coordenadas"
def test_sin_coordenadas_usa_el_nombre(): # barrio "Naranjal", sin lat/lon → 1103, "nombre"
def test_municipio_envigado_no_recibe_barrio_de_medellin(): # Review Focus 5
    # municipio "Envigado", punto dentro de 1101 → municipio_normalizado "Envigado", codigo_barrio nulo
def test_villacruz_barrio_que_es_municipio(): # municipio None, barrio "SABANETA" → "Sabaneta", sin barrio de Medellín
def test_municipio_nulo_con_punto_en_medellin(): # municipio None, punto en 1103 → "Medellín", es_medellin True
def test_coordenadas_fuera_del_valle(): # lat 4.6 (Bogotá) → coordenadas_validas False; se ubica por nombre
def test_mayusculas_del_municipio(): # "MEDELLIN" → "Medellín"
def test_fuera_del_valle(): # "EL RETIRO" → en_valle False, es_medellin False
def test_precio_m2(): # 2_000_000 / 50.0 → 40_000.0
@pytest.mark.parametrize(("precio", "area"), [(None, 50.0), (2_000_000, None), (None, None)])
def test_precio_m2_nulo(precio, area): # Review Focus 4 → nulo, sin excepción
def test_no_modifica_las_columnas_crudas(): # df_limpio[columnas crudas].equals(df_crudo)
def test_no_borra_filas(): # len(limpio) == len(crudo)
def test_tabla_vacia(): # DataFrame vacío de ESQUEMA → vacío, con las columnas nuevas
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `uv run pytest tests/test_limpieza.py -q`
Expected: FAIL (`ModuleNotFoundError: observatorio_inmobiliario.limpieza`)

- [ ] **Step 3: Implementar `limpiar`.** Se recorre fila por fila con `itertuples`: son ~10.000 filas y la búsqueda en el STRtree es rápida. Las columnas nuevas se arman en listas y se asignan con los dtypes `string`, `boolean` y `Float64` de pandas.

- [ ] **Step 4: Correr y ver que pasan**

Run: `uv run pytest tests/test_limpieza.py -q && uv run mypy`
Expected: todas pasan; mypy `Success`.

- [ ] **Step 5: Commit** (lo hace el autor)

```bash
git add src/observatorio_inmobiliario/limpieza.py tests/test_limpieza.py
git commit -m "feat: ubicación en barrios oficiales, municipio y precio por m2"
```

---

### Task 4: Atípicos y filtro de Medellín

**Files:**
- Modify: `src/observatorio_inmobiliario/limpieza.py`
- Test: `tests/test_limpieza.py`

**Interfaces:**
- Produces:

```python
RANGOS_PRECIO: Final = {Operacion.ARRIENDO: (200_000, 200_000_000), Operacion.VENTA: (20_000_000, 50_000_000_000)}
RANGO_AREA_VIVIENDA: Final = (10.0, 2_000.0)       # para apartamento, apartaestudio y casa
MINIMO_GRUPO: Final = 30
FACTOR_IQR: Final = 3.0
def marcar_atipicos(df: pd.DataFrame) -> pd.DataFrame     # agrega es_atipico (bool) y motivo_atipico (string)
def filtrar_medellin(df: pd.DataFrame) -> pd.DataFrame    # filas con es_medellin
```

`limpiar` llama a `marcar_atipicos` al final.

Motivos posibles. Si hay varios, se unen con `"; "` en este orden:
- `precio_fuera_de_rango`: el precio está fuera de `RANGOS_PRECIO[operacion]`.
- `area_fuera_de_rango`: el tipo es de vivienda y el área está fuera de `RANGO_AREA_VIVIENDA`.
- `precio_m2_extremo`: en el grupo (`operacion`, `tipo_normalizado`), si tiene al menos `MINIMO_GRUPO` filas con `precio_m2`, el `log10(precio_m2)` queda fuera de `[Q1 − 3·IQR, Q3 + 3·IQR]`.

Los nulos no marcan nada.

- [ ] **Step 1: Escribir las pruebas que fallan**

```python
def test_arriendo_con_precio_de_venta(): # arriendo 450_000_000 → "precio_fuera_de_rango"
def test_venta_barata(): # venta 5_000_000 → "precio_fuera_de_rango"
def test_apartamento_de_3_m2(): # → "area_fuera_de_rango"; un lote de 5_000 m² no se marca
def test_precio_m2_extremo(): # 40 apartamentos en arriendo a ~40.000 $/m² y uno a 4.000.000 $/m² → solo ese
def test_grupo_pequeno_no_usa_iqr(): # 10 filas, una extrema → no "precio_m2_extremo"
def test_venta_y_arriendo_no_se_mezclan(): # 40 arriendos y 40 ventas normales → ninguna marcada
def test_nulos_no_marcan(): # Review Focus 4: precio y área nulos → es_atipico False
def test_varios_motivos(): # "precio_fuera_de_rango; area_fuera_de_rango"
def test_filtrar_medellin(): # 3 filas, 1 de Medellín → 1
def test_marcar_no_borra_filas()
```

- [ ] **Step 2: Correr y ver que fallan** — Run: `uv run pytest tests/test_limpieza.py -q` — Expected: FAIL en las pruebas nuevas (`ImportError: marcar_atipicos`).

- [ ] **Step 3: Implementar** con operaciones vectorizadas de pandas: `groupby(...).transform("quantile")` para Q1 y Q3.

- [ ] **Step 4: Correr y ver que pasan** — Run: `uv run pytest -q && uv run mypy` — Expected: toda la suite pasa.

- [ ] **Step 5: Commit** (lo hace el autor)

```bash
git add src/observatorio_inmobiliario/limpieza.py tests/test_limpieza.py
git commit -m "feat: marca de atípicos y filtro de Medellín"
```

---

### Task 5: Guardado limpio, comando `limpiar`, corrida real y README

**Files:**
- Modify: `src/observatorio_inmobiliario/almacenamiento.py`, `src/observatorio_inmobiliario/cli.py`, `README.md`, `.gitignore` (agregar `data/limpio/`: los datos completos van solo al repo privado, spec §7.1)
- Test: `tests/test_almacenamiento.py`, `tests/test_cli.py`

**Interfaces:**
- Produces:

```python
ESQUEMA_LIMPIO: Final   # ESQUEMA + las 14 columnas nuevas (string, bool, float64)
def semanas_disponibles(directorio: Path) -> list[str]                  # ["2026-S46", ...] ordenadas, de data/crudo/*/
def leer_semana(directorio: Path, semana: str) -> pd.DataFrame          # todas las fuentes de esa semana
def guardar_limpio(df: pd.DataFrame, directorio: Path, semana: str) -> Path   # data/limpio/2026-S46.parquet, escritura atómica
def leer_limpio(directorio: Path, semana: str | None = None) -> pd.DataFrame
```

Comando: `observatorio limpiar [--semana AAAA-SNN] [--crudo data/crudo] [--salida data/limpio]`.
- Por defecto toma la última semana con datos.
- Si no hay datos, imprime `no hay datos crudos en …` por stderr y devuelve 1.
- Si la semana no existe, imprime `no hay datos de la semana …` y devuelve 1.
- Al terminar imprime un resumen por fuente: anuncios, % con barrio oficial, % atípicos y anuncios en Medellín.

- [ ] **Step 1: Escribir las pruebas que fallan**

```python
def test_semanas_disponibles(tmp_path)          # dos fuentes, semanas S45 y S46 → ["2026-S45", "2026-S46"]
def test_leer_semana_une_las_fuentes(tmp_path)
def test_guardar_y_leer_limpio(tmp_path)        # ida y vuelta conserva dtypes (bool, string, Float64)
def test_guardar_limpio_sobrescribe(tmp_path)   # dos veces la misma semana → una sola versión
def test_cli_limpiar(tmp_path, capsys)          # crudo sintético → archivo limpio + resumen; exit 0
def test_cli_limpiar_sin_datos(tmp_path)        # exit 1
def test_cli_limpiar_semana_inexistente(tmp_path)  # exit 1
```

- [ ] **Step 2: Correr y ver que fallan** — Run: `uv run pytest tests/test_almacenamiento.py tests/test_cli.py -q` — Expected: FAIL (`ImportError`).

- [ ] **Step 3: Implementar.** `ESQUEMA_LIMPIO` se arma con `ESQUEMA.append(...)`, igual que el esquema crudo, para que los tipos no dependan de los datos.

- [ ] **Step 4: Correr y ver que pasan** — Run: `uv run pytest -q && uv run mypy` — Expected: toda la suite pasa.

- [ ] **Step 5: Corrida real** — Run: `uv run observatorio limpiar`

Expected (datos del 2026-11-11; si un porcentaje queda muy por debajo, se aplica superpowers:systematic-debugging antes de seguir):

| Medida | Esperado |
|---|---|
| Filas | 8.589, las mismas que en crudo |
| Medellín | ≥ 5.100 (los 5.094 que traían municipio, más los de Villacruz ubicados por coordenadas) |
| Medellín con comuna | ≥ 90 % |
| Medellín con barrio oficial | ≥ 70 % |
| Atípicos | entre 1 % y 5 % |
| Coordenadas no válidas | 16 |

Revisar a mano:
- 20 filas de Medellín al azar: que el barrio oficial sea razonable frente al texto original;
- los 30 atípicos de mayor precio por m².

Los 15 nombres más frecuentes que sigan sin ubicarse se agregan al alias si su zona es inequívoca. Cada uno lleva su prueba en `test_catalogo.py`.

- [ ] **Step 6: README.** Agregar:
- una sección "Limpieza" con el comando y qué columnas agrega;
- el método de ubicación (coordenadas primero; el nombre, solo hasta la comuna cuando es una zona);
- las cifras de la corrida;
- la atribución del catálogo: "Límite barrio-vereda catastral, Alcaldía de Medellín (servidor de mapas, consultado el 2026-11-11)".

- [ ] **Step 7: Verificación completa** — Run: `uv run pre-commit run --all-files && uv run pytest` — Expected: todo pasa.

- [ ] **Step 8: Commit** (lo hace el autor)

```bash
git add .gitignore src/observatorio_inmobiliario/almacenamiento.py src/observatorio_inmobiliario/cli.py README.md tests/test_almacenamiento.py tests/test_cli.py datos_referencia/alias_barrios.csv tests/test_catalogo.py
git commit -m "feat: comando limpiar con guardado semanal de la tabla limpia"
```
