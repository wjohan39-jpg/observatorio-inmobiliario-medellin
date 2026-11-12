# Plan 5: Propiedades compartidas

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Encontrar los anuncios de **distintas** inmobiliarias que publican el mismo inmueble (pregunta 7 del spec). Cada pareja recibe una confianza alta, media o baja, y las parejas se unen en grupos. Todo se genera con el comando `observatorio compartidos`, que escribe dos tablas por semana:
- `data/compartidos/parejas/AAAA-SNN.parquet`: una fila por pareja de anuncios, con su confianza y la diferencia de precio.
- `data/compartidos/grupos_inmueble/AAAA-SNN.parquet`: una fila por anuncio emparejado, con su grupo en cada nivel de confianza.

**Architecture:** Es un paso aparte, igual que la limpieza: lee `data/limpio/`, nunca lo modifica y escribe `data/compartidos/`. El módulo nuevo `emparejamiento.py` tiene dos funciones puras:
- `emparejar`: de la tabla limpia saca las parejas;
- `agrupar`: de las parejas saca los grupos.

`almacenamiento.py` y `cli.py` solo se extienden. No se borra ni se cambia ningún anuncio: la capa de grupos va aparte (spec §4).

**Tech Stack:** Python 3.12+, pandas, numpy, pyarrow, pytest, ruff, mypy estricto. No hay dependencias nuevas: la unión de grupos se escribe a mano (unión-búsqueda), para poder explicarla en una entrevista.

**Spec:** `docs/superpowers/specs/2026-11-10-scraper-inmobiliario-medellin-design.md`. Las partes que aplican:
- §2.7: qué inmobiliarias publican el mismo inmueble y cuánto difiere el precio;
- §3: anti-meta "presentar como seguro algo que es incierto";
- §7: "Agrupación de inmuebles compartidos";
- §7.1: datos completos solo en el repo privado.

## Global Constraints

- **No se borra ningún anuncio** (spec §4). Los grupos son una tabla aparte. `data/limpio/` es de solo lectura para este paso.
- Solo se emparejan anuncios de **distintas** inmobiliarias (spec §7: "anuncios de **distintas** inmobiliarias").
- Criterios del spec §7: cercanía de coordenadas, el mismo barrio normalizado, área similar (**±3 %**), las mismas habitaciones y baños y el mismo estrato.
- **El precio no es un criterio de emparejamiento.** La diferencia de precio es lo que se quiere medir, y usarla para emparejar sesgaría la respuesta a la pregunta 7.
- Venta y arriendo nunca se emparejan entre sí (spec §2.3).
- `data/compartidos/` se agrega a `.gitignore`: tiene ids y URL de anuncios, y esos datos van solo al repo privado (spec §7.1).
- El autor hace `git add`, `git commit` y `git push`. Los pasos de commit le dan los comandos (mensaje `tipo: descripción`, con espacio después de los dos puntos).

## Revisión de los datos (2026-11-12, semana 2026-S46)

Prototipo sobre la tabla limpia: 8.589 anuncios, de los cuales 5.634 son de Medellín y no son atípicos.

- **Bloques.** Se cruzan solo los anuncios con la misma operación, el mismo tipo normalizado y la misma comuna. Salen 334.492 pares de fuentes distintas.
  - Con área ±3 %: quedan 14.556.
  - Con habitaciones, baños y estrato compatibles (iguales, o nulos en alguno de los dos): quedan **3.719**.
- **La distancia separa las coincidencias reales del azar.** Entre los 817 pares de ese total que tienen coordenadas válidas en los dos anuncios:

| Distancia | Pares | Diferencia de precio mediana | Precio a menos de 15 % | Área idéntica |
|---|---|---|---|---|
| ≤ 100 m | 70 | 2,4 % | 80 % | 71 % |
| ≤ 300 m | 122 | 4,9 % | 73 % | 66 % |
| > 1 km | 507 | 25 % | 29 % | 47 % |

  - Hasta unos 300 m es el mismo inmueble.
  - Más lejos es una coincidencia de características. Por eso un par con coordenadas en los dos anuncios a más de 300 m **no** se empareja, aunque estén en el mismo barrio.
- **Sin coordenadas** (Maxibienes, Panorama y Activo Urbano no las publican), lo único que queda es el barrio oficial. Hay 158 pares en el mismo barrio, y solo 27 tienen habitaciones, baños y estrato conocidos e iguales en los dos lados.
- **Apartamentos gemelos.** En una torre hay varias unidades iguales. Cuando un anuncio tiene más de un candidato en la misma otra fuente, no se sabe cuál es su pareja. Pasa en 97 de 280 parejas. Esas parejas bajan un nivel de confianza.
  - Con eso, la diferencia de precio mediana de las parejas de confianza alta queda en 2 %.
- **Clave de un anuncio.** `(fuente, id_fuente)` no es única en una semana:
  - Maxibienes usa el mismo id para el arriendo y la venta del mismo inmueble (116 filas).
  - Alnago repite filas idénticas (por ejemplo, 5 veces el id 9037878).

  La clave es `(fuente, id_fuente, operacion)`. Las filas repetidas con la misma clave se toman una sola vez.
- **Grupos.** Si se unen por transitividad todas las parejas, sale un grupo de 13 anuncios: es una cadena de coincidencias débiles. Por eso cada nivel de confianza tiene sus propios grupos. Por ejemplo, el grupo "alta" usa solo parejas de confianza alta. Así, el dashboard filtra por confianza sin que una pareja débil contamine los grupos fuertes.
  - Resultado del prototipo:

| Nivel | Grupos | Tamaño máximo |
|---|---|---|
| Alta | 49 | 3 |
| Media o más | 107 | 6 |
| Cualquiera | 155 | 13 |

## Reglas de confianza

**Qué filas entran.** Solo las de Medellín (`es_medellin`) que no son atípicas, con `comuna`, `tipo_normalizado` y `area_m2 > 0`. Una fila sin alguno de esos datos no se empareja; no hay error.

**Cuándo dos filas son candidatas.** Tienen que cumplir todo esto:
- son de fuentes distintas;
- tienen la misma `operacion`, el mismo `tipo_normalizado` y la misma `comuna`;
- `|área_a − área_b| / max(área_a, área_b) ≤ TOLERANCIA_AREA`;
- `habitaciones`, `banos` y `estrato` son iguales, o nulos en alguno de los dos lados.

**Confianza de una candidata:**

| Caso | Condición | Confianza |
|---|---|---|
| Las dos tienen `coordenadas_validas` | distancia ≤ `DISTANCIA_ALTA_M` (100 m) | alta |
| | distancia ≤ `DISTANCIA_MEDIA_M` (300 m) | media |
| | más lejos | no es pareja |
| Al menos una no tiene `coordenadas_validas` | el mismo `codigo_barrio` (no nulo), y `habitaciones`, `banos` y `estrato` conocidos e iguales en las dos | media |
| | el mismo `codigo_barrio` (no nulo), con algún nulo en esos tres campos | baja |
| | otro barrio, o barrio nulo | no es pareja |

**Ambigüedad.** Una pareja es `ambigua` si alguno de sus dos anuncios tiene más de una pareja (de las aceptadas arriba) en la fuente del otro. Una pareja ambigua baja un nivel:
- alta pasa a media;
- media pasa a baja;
- baja se descarta.

## Review Focus

1. **Claves repetidas.** El mismo `id_fuente` puede aparecer en venta y en arriendo, y hay filas idénticas repetidas. Se deben tratar como dos anuncios distintos en el primer caso y como uno solo en el segundo. Un anuncio nunca se empareja consigo mismo.
2. **Gemelos en la misma torre.** Si dos unidades iguales de una fuente quedan a 0 m de un anuncio de otra fuente, ninguna de las dos parejas puede quedar en confianza alta.
3. **Nulos.** Con `habitaciones`, `banos`, `estrato`, `latitud` o `codigo_barrio` en `None` no se lanza ninguna excepción. Una pareja sin coordenadas válidas en las dos filas nunca es alta.
4. **Entradas vacías o degeneradas.** Con una tabla limpia vacía, o sin ninguna pareja, `emparejar` y `agrupar` devuelven tablas vacías con todas sus columnas. Con un área 0 o nula no hay división por cero.
5. **Determinismo.** Con las filas de entrada en otro orden, las parejas y los ids de grupo salen idénticos. Es lo que permite comparar semanas.

Cada punto tiene su prueba en la tarea correspondiente.

---

### Task 1: Parejas con confianza

**Files:**
- Create: `src/observatorio_inmobiliario/emparejamiento.py`
- Test: `tests/test_emparejamiento.py`

**Interfaces:**
- Consumes: las columnas de `ESQUEMA_LIMPIO` (Plan 4): `fuente`, `id_fuente`, `operacion`, `tipo_normalizado`, `comuna`, `codigo_barrio`, `area_m2`, `habitaciones`, `banos`, `estrato`, `latitud`, `longitud`, `coordenadas_validas`, `precio`, `es_medellin` y `es_atipico`.
- Produces:

```python
class Confianza(StrEnum):  # en orden de mayor a menor
    ALTA = "alta"
    MEDIA = "media"
    BAJA = "baja"

TOLERANCIA_AREA: Final = 0.03
DISTANCIA_ALTA_M: Final = 100.0
DISTANCIA_MEDIA_M: Final = 300.0

def distancia_m(lat_a: np.ndarray, lon_a: np.ndarray, lat_b: np.ndarray, lon_b: np.ndarray) -> np.ndarray
def emparejar(limpio: pd.DataFrame) -> pd.DataFrame
```

`distancia_m` usa la aproximación equirectangular con R = 6.371.000 m. A menos de 1 km el error es menor de 1 m.

`emparejar` devuelve una fila por pareja. El lado `a` es el de menor `(fuente, id_fuente)`. Las filas se ordenan por `fuente_a, id_fuente_a, fuente_b, id_fuente_b`, y el índice va de 0 a n−1. Columnas, en este orden:
- `fuente_a`, `id_fuente_a`, `fuente_b`, `id_fuente_b`, `operacion`, `tipo_normalizado`, `comuna`, `codigo_barrio_a`, `codigo_barrio_b`: string;
- `area_m2_a`, `area_m2_b`: float64;
- `precio_a`, `precio_b`: Int64;
- `distancia_m`: float64, NaN si a alguna le faltan coordenadas válidas;
- `diferencia_precio_pct`: float64. Vale `(max/min − 1)·100` y es NaN si falta un precio;
- `ambigua`: bool;
- `confianza`: string, con un valor de `Confianza`.

- [ ] **Step 1: Escribir las pruebas que fallan.** Hacen falta un constructor de filas limpias sintéticas (`_fila(**cambios)`) con valores por defecto válidos y estas pruebas:

```python
def test_distancia_m(): # 0,001° de latitud ≈ 111 m (±1 m); el mismo punto → 0
def test_mismo_punto_es_alta(): # santafe y nutibara, a 0 m, área 80 y 81,5 → una pareja "alta"
def test_entre_100_y_300_m_es_media()
def test_mas_de_300_m_no_es_pareja(): # aunque el codigo_barrio sea el mismo
def test_area_fuera_de_tolerancia(): # 80 y 83 m² → sin pareja (3,6 %)
def test_misma_fuente_no_se_empareja()
def test_venta_y_arriendo_no_se_emparejan()
def test_habitaciones_distintas_no_se_emparejan()
def test_nulo_es_compatible(): # estrato None en un lado → hay pareja
def test_sin_coordenadas_mismo_barrio_completo_es_media(): # maxibienes sin coordenadas
def test_sin_coordenadas_con_nulos_es_baja()
def test_sin_coordenadas_otro_barrio_no_es_pareja()
def test_sin_coordenadas_nunca_es_alta(): # Review Focus 3: con todo igual y barrio igual → media
def test_gemelos_bajan_un_nivel(): # Review Focus 2: dos de villacruz a 0 m de uno de nutibara → 2 parejas "media", ambigua True
def test_gemelos_baja_se_descarta(): # dos candidatas "baja" en la misma fuente → ninguna pareja
def test_atipicos_y_fuera_de_medellin_no_entran()
def test_clave_incluye_operacion(): # Review Focus 1: mismo id en venta y arriendo → dos anuncios distintos
def test_filas_repetidas_cuentan_una_vez(): # Review Focus 1: la misma fila 3 veces → 1 pareja, no ambigua
def test_area_cero_o_nula_no_falla(): # Review Focus 4
def test_vacio_devuelve_columnas(): # Review Focus 4: list(resultado.columns) == las 17 columnas
def test_orden_de_entrada_no_cambia_resultado(): # Review Focus 5: df.sample(frac=1, random_state=0) → assert_frame_equal
def test_diferencia_precio_pct(): # 100 y 110 millones → 10,0
```

- [ ] **Step 2: Correr y ver que fallan.** Run: `uv run pytest tests/test_emparejamiento.py -q`. Expected: FAIL con `ModuleNotFoundError: observatorio_inmobiliario.emparejamiento`.

- [ ] **Step 3: Implementar.** Pasos, todos vectorizados:
  1. Filtrar las filas que entran y quitar las claves repetidas con `drop_duplicates(["fuente", "id_fuente", "operacion"])`.
  2. Cruzar con `merge` por `["operacion", "tipo_normalizado", "comuna"]` y quedarse con `fuente_a < fuente_b`. Eso elimina a la vez la misma fuente y el par repetido al revés.
  3. Aplicar los filtros de área y de compatibilidad, y luego la tabla de confianza.
  4. Calcular la ambigüedad con `groupby([lado, fuente del otro lado]).transform("size") > 1` en cada lado.
  5. Bajar un nivel a las ambiguas y descartar las que queden sin nivel.

  La comparación "iguales o nulo" sobre columnas Int64 debe quedar en `bool`, sin `<NA>`. Usar `(x.isna() | y.isna() | (x == y)).fillna(False).astype(bool)`.

- [ ] **Step 4: Correr y ver que pasan.** Run: `uv run pytest -q && uv run mypy`. Expected: toda la suite pasa.

- [ ] **Step 5: Commit** (lo hace el autor)

```bash
git add src/observatorio_inmobiliario/emparejamiento.py tests/test_emparejamiento.py
git commit -m "feat: parejas de anuncios compartidos con nivel de confianza"
```

---

### Task 2: Grupos por nivel de confianza

**Files:**
- Modify: `src/observatorio_inmobiliario/emparejamiento.py`
- Test: `tests/test_emparejamiento.py`

**Interfaces:**
- Consumes: `emparejar(...)` y `Confianza` (Task 1).
- Produces:

```python
def clave_anuncio(fuente: str, id_fuente: str, operacion: str) -> str   # "nutibara:123:venta"
def agrupar(parejas: pd.DataFrame) -> pd.DataFrame
```

`agrupar` devuelve una fila por anuncio que aparece en al menos una pareja, ordenada por `fuente, id_fuente, operacion`, con índice de 0 a n−1. Columnas, todas string:
- `fuente`, `id_fuente`, `operacion`;
- `grupo_alta`, `grupo_media`, `grupo_baja`.

`grupo_<nivel>` es el grupo del anuncio cuando solo se usan las parejas de confianza mayor o igual a ese nivel. Por ejemplo, `grupo_media` usa las parejas alta y media. Si el anuncio no tiene ninguna pareja de ese nivel o mayor, el valor es nulo.

El id de un grupo es la menor `clave_anuncio` de sus miembros (orden de texto). Así no depende del orden de entrada y se puede leer: dice de qué anuncio salió.

- [ ] **Step 1: Escribir las pruebas que fallan**

```python
def test_clave_anuncio()
def test_pareja_alta_forma_un_grupo_en_los_tres_niveles(): # grupo_alta == grupo_media == grupo_baja
def test_pareja_baja_solo_en_grupo_baja(): # grupo_alta y grupo_media nulos
def test_transitividad(): # A-B alta y B-C alta → un grupo de 3, id = menor clave
def test_cadena_debil_no_contamina(): # A-B alta, B-C baja → grupo_alta {A,B}; grupo_baja {A,B,C}; C sin grupo_alta
def test_agrupar_vacio_devuelve_columnas(): # Review Focus 4
def test_agrupar_orden_de_entrada(): # Review Focus 5: parejas en otro orden → assert_frame_equal
def test_emparejar_y_agrupar_extremo_a_extremo(): # tabla limpia sintética de 6 filas → 2 grupos esperados
```

- [ ] **Step 2: Correr y ver que fallan.** Run: `uv run pytest tests/test_emparejamiento.py -q`. Expected: FAIL con `ImportError: agrupar`.

- [ ] **Step 3: Implementar.** Una función privada `_componentes(aristas: Iterable[tuple[str, str]]) -> dict[str, str]` hace la unión-búsqueda con compresión de caminos y devuelve, para cada clave, el id de su grupo (su menor clave). `agrupar` la llama una vez por nivel.

- [ ] **Step 4: Correr y ver que pasan.** Run: `uv run pytest -q && uv run mypy`. Expected: toda la suite pasa.

- [ ] **Step 5: Commit** (lo hace el autor)

```bash
git add src/observatorio_inmobiliario/emparejamiento.py tests/test_emparejamiento.py
git commit -m "feat: grupos de inmuebles compartidos por nivel de confianza"
```

---

### Task 3: Guardado, comando `compartidos`, corrida real y README

**Files:**
- Modify: `src/observatorio_inmobiliario/almacenamiento.py`, `src/observatorio_inmobiliario/cli.py`, `README.md`, `.gitignore` (agregar `data/compartidos/`)
- Test: `tests/test_almacenamiento.py`, `tests/test_cli.py`

**Interfaces:**
- Consumes: `emparejar` y `agrupar` (Tasks 1-2), `leer_limpio` (Plan 4).
- Produces:

```python
ESQUEMA_PAREJAS: Final   # las 17 columnas de emparejar, en su orden
ESQUEMA_GRUPOS: Final    # las 6 columnas de agrupar, en su orden
def semanas_limpias(directorio: Path) -> list[str]   # ["2026-S46", ...], de data/limpio/*.parquet
def guardar_compartidos(parejas: pd.DataFrame, grupos: pd.DataFrame, directorio: Path, semana: str) -> list[Path]
def leer_compartidos(directorio: Path, semana: str | None = None) -> tuple[pd.DataFrame, pd.DataFrame]   # (parejas, grupos)
```

`guardar_compartidos` escribe `directorio/parejas/<semana>.parquet` y `directorio/grupos_inmueble/<semana>.parquet`. Usa `_escribir`, que hace la escritura atómica, y sobrescribe si la semana ya existe.

Comando: `observatorio compartidos [--semana AAAA-SNN] [--limpio data/limpio] [--salida data/compartidos]`.
- Por defecto toma la última semana limpia.
- Si no hay tablas limpias, imprime `no hay datos limpios en …` por stderr y devuelve 1.
- Si la semana no existe, imprime `no hay datos limpios de la semana …` y devuelve 1.
- Al terminar imprime:
  - las parejas por confianza;
  - los grupos por nivel;
  - las parejas de confianza media o alta por combinación de fuentes;
  - la diferencia de precio mediana por confianza.

- [ ] **Step 1: Escribir las pruebas que fallan**

```python
def test_semanas_limpias(tmp_path)
def test_guardar_y_leer_compartidos(tmp_path)          # ida y vuelta conserva dtypes (bool, string, Int64, float64)
def test_guardar_compartidos_sobrescribe(tmp_path)
def test_guardar_compartidos_vacios(tmp_path)          # Review Focus 4: tablas vacías → archivos válidos
def test_cli_compartidos(tmp_path, capsys)             # tabla limpia sintética con una pareja → 2 archivos + resumen; exit 0
def test_cli_compartidos_sin_datos(tmp_path)           # exit 1
def test_cli_compartidos_semana_inexistente(tmp_path)  # exit 1
```

- [ ] **Step 2: Correr y ver que fallan.** Run: `uv run pytest tests/test_almacenamiento.py tests/test_cli.py -q`. Expected: FAIL con `ImportError`.

- [ ] **Step 3: Implementar.** Los esquemas se declaran con `pa.schema([...])`, igual que `ESQUEMA_LIMPIO`. Agregar el comando al docstring de `cli.py`.

- [ ] **Step 4: Correr y ver que pasan.** Run: `uv run pytest -q && uv run mypy`. Expected: toda la suite pasa.

- [ ] **Step 5: Corrida real.** Run: `uv run observatorio compartidos`

Expected, con los datos de 2026-S46. Si una cifra se sale por más del 15 %, se aplica superpowers:systematic-debugging antes de seguir.

| Medida | Prototipo |
|---|---|
| Parejas alta / media / baja | 53 / 83 / 94 |
| Grupos alta / media o más / cualquiera | 49 / 107 / 155 |
| Diferencia de precio mediana en las parejas alta | ≈ 2 % |
| Tiempo | menos de 5 s |

Revisar a mano:
- 15 parejas de confianza alta y 15 de confianza baja: abrir las dos URL de cada pareja y anotar si es el mismo inmueble;
- el grupo más grande de cada nivel.

Si la proporción de aciertos en las parejas alta queda por debajo del 80 %, se ajustan los umbrales y se anota el porqué en el docstring de la constante.

- [ ] **Step 6: README.** Agregar una sección "Propiedades compartidas" con:
  - el comando y las dos tablas que escribe;
  - las reglas de confianza en una tabla corta;
  - por qué el precio no es un criterio;
  - el tratamiento de los gemelos;
  - las cifras de la corrida y el resultado de la revisión a mano;
  - una limitación: sin coordenadas, el emparejamiento depende del barrio y es más débil.

- [ ] **Step 7: Verificación completa.** Run: `uv run pre-commit run --all-files && uv run pytest`. Expected: todo pasa.

- [ ] **Step 8: Commit** (lo hace el autor)

```bash
git add .gitignore README.md src/observatorio_inmobiliario/almacenamiento.py src/observatorio_inmobiliario/cli.py tests/test_almacenamiento.py tests/test_cli.py
git commit -m "feat: comando compartidos con parejas y grupos por semana"
```
