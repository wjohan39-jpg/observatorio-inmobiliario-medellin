# Plan 6: Análisis y agregados

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Responder las preguntas 1 a 8 del spec con tablas agregadas en `data/agregados/` y un notebook de análisis exploratorio que las presenta. Todo se genera con el comando `observatorio agregados`.
- Las tablas agregadas **sí van al repo público**: el dashboard (Plan 7) las lee de ahí.
- El notebook queda en `notebooks/`, con sus resultados guardados para que GitHub lo muestre.

**Architecture:** Es un paso aparte, igual que los anteriores:
- lee `data/limpio/` y `data/compartidos/`, y no los modifica;
- escribe `data/agregados/`.

Cada pregunta tiene una función pura que recibe DataFrames y devuelve una tabla. Están en dos módulos nuevos:
- `agregados.py`: la foto de la última semana (preguntas 1 a 4, 6 y 7);
- `evolucion.py`: las series entre semanas (pregunta 8).

El notebook lee **solo** `data/agregados/`, así que cualquiera que clone el repo público puede volver a correrlo.

**Tech Stack:** Python 3.12+, pandas, pyarrow, pytest, ruff, mypy estricto. Para el notebook se agrega un grupo de dependencias nuevo, `analisis`, con `ipykernel`, `nbconvert` y `matplotlib`.

**Spec:** `docs/superpowers/specs/2026-11-10-scraper-inmobiliario-medellin-design.md`. Las partes que aplican:
- §2: las preguntas 1 a 8;
- §3: la anti-meta "notebooks sueltos";
- §7: el repo público tiene solo tablas agregadas;
- §7.1: reglas legales y éticas;
- §7.2: Google Places no se guarda.

## Global Constraints

- **El repo público tiene solo agregados** (spec §7 y §7.1).
  - Ninguna tabla de `data/agregados/` tiene `id_fuente`, `url`, `latitud`, `longitud` ni texto de los anuncios.
  - La única excepción es `grupos_compartidos`, que tiene filas por anuncio, pero anónimas: barrio, área, estrato y precio por fuente, que es exactamente lo que el spec §7.1 permite.
- **Mínimo de publicación:** una fila con estadísticas de precio se publica solo si resume `MINIMO_PUBLICACION = 5` anuncios o más.
  - Con menos, una "mediana" es casi el precio de un anuncio y, además, no es representativa.
  - Las tablas que solo tienen conteos no aplican el mínimo.
- **Venta y arriendo nunca se mezclan** en una estadística (spec §2.3).
- **Precios de vivienda.** Las estadísticas de precio por zona y por inmobiliaria usan solo los tipos de vivienda (`apartamento`, `apartaestudio` y `casa`), por separado y juntos como `"vivienda"`. Mezclar un local con un apartamento no dice nada del precio de un barrio.
- **La base del análisis** son los anuncios de Medellín (`es_medellin`) que no son atípicos, una fila por clave `(fuente, id_fuente, operacion)`. La única excepción es la rotación (pregunta 8), que usa todos los de Medellín, porque la marca de atípico puede cambiar de una semana a otra.
- **Google Places no se guarda** (spec §7.2).
  - La pregunta 5 (reputación) se responde en vivo en el dashboard (Plan 7).
  - Para la pregunta 6 (reconocimiento), este plan publica dos de sus tres componentes: el volumen de anuncios y los barrios cubiertos. Las reseñas se suman en el Plan 7.
- Ningún archivo versionado puede pasar de 500 KB. Lo exige el hook `check-added-large-files`, y vale también para el notebook con sus resultados.
- El autor hace `git add`, `git commit` y `git push`. Los pasos de commit le dan los comandos (mensaje `tipo: descripción`, con espacio después de los dos puntos).

## Revisión de los datos (2026-11-12, semana 2026-S46)

- **Solo hay una semana de datos.**
  - La pregunta 8 se implementa y se prueba con semanas sintéticas.
  - Con los datos reales, sus tablas tendrán por ahora una sola semana, sin retiros ni cambios de precio.
  - El Plan 8, que corre el scraper cada semana, es el que las llena.
- **Base:** 5.634 anuncios de Medellín sin atípicos, de los cuales 1.640 son de venta y 3.994 de arriendo.
  - En venta, 87 barrios tienen 5 anuncios o más; en arriendo, 128. Las 20 comunas pasan el mínimo en las dos operaciones.
  - Con el mínimo de 5 se publica el precio de 999 de los 1.640 anuncios de venta. El resto queda en la tabla por comuna.
- **Claves repetidas:** Alnago repite filas idénticas (un mismo id hasta 5 veces). Sin quitar las repeticiones, el conteo de anuncios de Alnago sale inflado.
- **Estrato.** Alnago y Puertabierta no lo publican.
  - En 88 barrios hay 5 anuncios o más con estrato declarado, y el estrato más frecuente reúne el 60 % o más de ellos.
  - Usando ese estrato más frecuente del barrio se cubre el 57 % de los anuncios de Alnago y el 67 % de los de Puertabierta.
  - Probada con los anuncios que sí declaran estrato, la regla acierta en el 76 %. Por eso el estrato inferido siempre va en una columna aparte del declarado (spec §6: "se infiere del barrio con su nivel de confianza indicado").
- **Índice de precio relativo.** Es el precio por m² de cada anuncio dividido por la mediana de su barrio, en la misma operación y el mismo tipo, contando solo barrios con 5 o más anuncios.
  - Con ese índice, la mediana de casi todas las fuentes queda entre 0,96 y 1,03. La excepción es Activo Urbano, que en arriendo queda en 1,14 (16 anuncios).
  - Responde "¿quién es más económico?" (pregunta 3) sin el sesgo de dónde trabaja cada inmobiliaria. Sin el índice, una inmobiliaria de El Poblado siempre parece "cara".

## Tablas de `data/agregados/`

Todas se escriben con `observatorio agregados`. Las de la foto usan la última semana limpia, que va en la columna `semana`. Los precios van en COP, como enteros (Int64), y los porcentajes de 0 a 100 con un decimal.

| Archivo | Pregunta | Una fila por | Columnas |
|---|---|---|---|
| `precios_zona` | 1 | nivel × zona × operación × tipo | `semana, nivel` ("barrio" o "comuna")`, codigo, nombre, comuna, operacion, tipo, anuncios, precio_mediana, precio_p25, precio_p75, precio_m2_mediana, precio_m2_p25, precio_m2_p75` |
| `cobertura_inmobiliaria` | 2, 6 | fuente × operación (y `"todas"`) | `semana, fuente, operacion, anuncios, barrios, comunas, comuna_principal, pct_comuna_principal` |
| `cobertura_comuna` | 2 | fuente × operación × comuna | `semana, fuente, operacion, comuna, nombre_comuna, anuncios, pct_de_la_fuente` |
| `economia_inmobiliaria` | 3 | fuente × operación × tipo | `semana, fuente, operacion, tipo, anuncios, precio_mediana, precio_m2_mediana, anuncios_indice, indice_relativo_mediana` |
| `estratos_inmobiliaria` | 4 | fuente × operación × estrato | `semana, fuente, operacion, estrato, declarados, inferidos` |
| `compartidos_fuentes` | 7 | par de fuentes × nivel | `semana, fuente_a, fuente_b, nivel, parejas, diferencia_precio_mediana_pct, pct_a_mas_barata, pct_mismo_precio` |
| `grupos_compartidos` | 7 | nivel × grupo × anuncio | `semana, nivel, grupo, operacion, tipo, comuna, nombre_comuna, barrio, area_m2, estrato, habitaciones, fuente, precio` |
| `evolucion_precios` | 8 | semana × operación × tipo | `semana, operacion, tipo, anuncios, precio_m2_mediana` |
| `rotacion_inmobiliaria` | 8 | semana × fuente × operación | `semana, fuente, operacion, anuncios, nuevos, retirados, tasa_retiro_pct, semanas_publicado_mediana, comparables, con_cambio_precio, cambio_precio_mediana_pct` |

Reglas de las columnas que no son evidentes:
- `tipo` puede ser `"apartamento"`, `"apartaestudio"`, `"casa"` o `"vivienda"` (los tres juntos).
- `nivel`, en las tablas de compartidos, es acumulado, igual que en el Plan 5. Por ejemplo, `"media"` incluye las parejas alta y media.
- `grupo` es un entero de 1 a n dentro de cada nivel. No tiene ids de la fuente.
- `pct_a_mas_barata` es el % de parejas en que `fuente_a` publica un precio menor. `pct_mismo_precio` es el % en que el precio es idéntico.
- Rotación:
  - `retirados`: anuncios de la semana anterior que no aparecen en esta.
  - `tasa_retiro_pct = retirados / anuncios de la semana anterior · 100`. Es nula en la primera semana.
  - `semanas_publicado_mediana`: entre los retirados, cuántas semanas estuvieron publicados. Se excluyen los que ya estaban en la primera semana del histórico, porque no se sabe cuándo empezaron.
  - `comparables`: anuncios presentes esta semana y la anterior, con precio en las dos.
  - `cambio_precio_mediana_pct`: la mediana del cambio, solo entre los que cambiaron.

## Review Focus

1. **Claves repetidas.** Las filas idénticas de Alnago deben contarse una sola vez en todas las tablas, y el resultado no puede depender del orden de las filas. Esto corrige además un detalle que quedó pendiente del Plan 5 en `emparejamiento._anuncios`.
2. **Celdas pequeñas.** Un barrio con 4 anuncios no aparece en `precios_zona`, pero su comuna sí. Una inmobiliaria con 3 anuncios de venta no tiene fila de precios de venta, pero sí cuenta en cobertura.
3. **Semana sin datos de un tipo u operación.** Por ejemplo, Puertabierta no tiene ventas. No debe lanzar excepciones ni generar filas con `anuncios = 0`. Una tabla vacía conserva sus columnas y sus tipos.
4. **Histórico.**
   - Con una sola semana: `retirados` vale 0 y `tasa_retiro_pct` es nula.
   - Un anuncio que desaparece una semana y vuelve a la siguiente cuenta como retirado y luego como nuevo.
   - Un anuncio que ya estaba en la primera semana no entra en `semanas_publicado_mediana`.
5. **Privacidad.** Ninguna tabla publicada tiene las columnas `id_fuente`, `url`, `latitud`, `longitud` ni `anunciante_origen`. Una prueba lo verifica sobre la salida del comando, y otra verifica que el notebook no lea `data/limpio`, `data/crudo` ni `data/compartidos`.

Cada punto tiene su prueba en la tarea correspondiente.

---

### Task 1: Base del análisis y precios por zona (pregunta 1)

**Files:**
- Create: `src/observatorio_inmobiliario/agregados.py`
- Modify: `src/observatorio_inmobiliario/emparejamiento.py` (`_anuncios` usa `anuncios_unicos`)
- Modify: `src/observatorio_inmobiliario/almacenamiento.py` (`semana_de`; `ruta_semana` la usa)
- Test: `tests/test_agregados.py`, `tests/test_emparejamiento.py`, `tests/test_almacenamiento.py`

**Interfaces:**
- Consumes: las columnas de `ESQUEMA_LIMPIO` (Plan 4).
- Produces:

```python
# almacenamiento.py
def semana_de(fecha: date) -> str          # "2026-S46", con el año ISO

# agregados.py
MINIMO_PUBLICACION: Final = 5
TIPOS_VIVIENDA: Final = ("apartamento", "apartaestudio", "casa")
VIVIENDA: Final = "vivienda"
CLAVE: Final = ["fuente", "id_fuente", "operacion"]
def anuncios_unicos(df: pd.DataFrame) -> pd.DataFrame
def base_analisis(limpio: pd.DataFrame) -> pd.DataFrame
def con_vivienda(df: pd.DataFrame) -> pd.DataFrame
def precios_zona(base: pd.DataFrame, semana: str) -> pd.DataFrame
```

- `anuncios_unicos`: ordena por todas las columnas y se queda con la primera fila de cada `CLAVE`. Así el resultado no depende del orden de entrada.
- `base_analisis`: los anuncios únicos con `es_medellin` y sin `es_atipico`.
- `con_vivienda`: solo los tipos de vivienda, más una copia de esas mismas filas con `tipo = "vivienda"`. Agrega la columna `tipo`.
- `precios_zona`: devuelve las columnas de la tabla de arriba, en ese orden.
  - `nombre` es `barrio_normalizado` o `nombre_comuna`.
  - `comuna` es la comuna de la fila (en el nivel comuna, la misma `codigo`).
  - Los cuantiles se calculan sobre las filas que tienen el dato y se redondean a entero.
  - Las filas se ordenan por `nivel, codigo, operacion, tipo`.

- [ ] **Step 1: Escribir las pruebas que fallan.** Hace falta un constructor de filas limpias sintéticas, como en `test_emparejamiento.py`.

```python
def test_semana_de(): # date(2027, 1, 1) → "2026-S53"; ruta_semana sigue igual
def test_anuncios_unicos_quita_repetidas(): # 3 filas idénticas → 1; venta y arriendo con el mismo id → 2
def test_anuncios_unicos_no_depende_del_orden(): # misma clave, áreas 80 y 200 → la misma fila en cualquier orden
def test_base_analisis(): # fuera de Medellín y atípicos no entran
def test_con_vivienda(): # 2 apartamentos + 1 casa + 1 local → 3 filas por tipo y 3 "vivienda"
def test_precios_zona_mediana_y_cuantiles(): # 5 apartamentos en arriendo en 1101 a 1, 2, 3, 4, 5 millones → mediana 3_000_000, p25 2_000_000, p75 4_000_000
def test_minimo_de_publicacion(): # Review Focus 2: 4 anuncios en el barrio 1101 y 2 en el 1102 → sin filas de barrio; la comuna 11 (6) sí
def test_venta_y_arriendo_separados()
def test_sin_barrio_cuenta_en_comuna(): # codigo_barrio nulo, comuna 11 → solo en el nivel comuna
def test_precios_zona_vacia(): # Review Focus 3: base vacía → 0 filas con todas las columnas y tipos (Int64, string)
# test_emparejamiento.py
def test_emparejar_repetidas_distintas_no_dependen_del_orden(): # Review Focus 1: misma clave con áreas 80 y 200 + pareja de otra fuente; las dos órdenes dan el mismo resultado
```

- [ ] **Step 2: Correr y ver que fallan.** Run: `uv run pytest tests/test_agregados.py tests/test_emparejamiento.py tests/test_almacenamiento.py -q`. Expected: FAIL con `ModuleNotFoundError: observatorio_inmobiliario.agregados` y la prueba nueva de emparejamiento en rojo.

- [ ] **Step 3: Implementar.**
  - `precios_zona` arma los dos niveles con un `groupby(...).agg` cada uno: una vez por `codigo_barrio` y una vez por `comuna`. Los une con `pd.concat` y filtra `anuncios >= MINIMO_PUBLICACION`.
  - `emparejamiento._anuncios` reemplaza su `drop_duplicates(CLAVE)` por `anuncios_unicos`.

- [ ] **Step 4: Correr y ver que pasan.** Run: `uv run pytest -q && uv run mypy`. Expected: toda la suite pasa.

- [ ] **Step 5: Commit** (lo hace el autor)

```bash
git add src/observatorio_inmobiliario/agregados.py src/observatorio_inmobiliario/almacenamiento.py src/observatorio_inmobiliario/emparejamiento.py tests/test_agregados.py tests/test_almacenamiento.py tests/test_emparejamiento.py
git commit -m "feat: base del análisis y precios por barrio y comuna"
```

---

### Task 2: Inmobiliarias: cobertura, economía y estratos (preguntas 2, 3, 4 y 6)

**Files:**
- Modify: `src/observatorio_inmobiliario/agregados.py`
- Test: `tests/test_agregados.py`

**Interfaces:**
- Consumes: `base_analisis`, `con_vivienda`, `MINIMO_PUBLICACION` (Task 1).
- Produces:

```python
TODAS: Final = "todas"
MINIMO_ESTRATO_BARRIO: Final = 5
CONSENSO_ESTRATO: Final = 0.6
def cobertura_inmobiliaria(base: pd.DataFrame, semana: str) -> pd.DataFrame
def cobertura_comuna(base: pd.DataFrame, semana: str) -> pd.DataFrame
def indice_relativo(base: pd.DataFrame) -> pd.Series        # float64; NaN si el grupo del barrio tiene < MINIMO_PUBLICACION
def economia_inmobiliaria(base: pd.DataFrame, semana: str) -> pd.DataFrame
def estrato_inferido(base: pd.DataFrame) -> pd.Series       # Int64 por codigo_barrio; solo barrios que cumplen la regla
def estratos_inmobiliaria(base: pd.DataFrame, semana: str) -> pd.DataFrame
```

- `cobertura_inmobiliaria`:
  - Tiene una fila por fuente y operación, y otra con `operacion = "todas"`.
  - `barrios` y `comunas` cuentan los valores distintos no nulos.
  - `comuna_principal` es la comuna con más anuncios de la fuente; si hay empate, la de menor código.
  - No aplica el mínimo de publicación, porque solo tiene conteos.
- `cobertura_comuna`: `pct_de_la_fuente` es el % de los anuncios de esa fuente y operación que caen en esa comuna. Los anuncios sin comuna no tienen fila.
- `indice_relativo`:
  - Es el `precio_m2` del anuncio dividido por la mediana de `precio_m2` del grupo `(operacion, tipo_normalizado, codigo_barrio)`.
  - Solo vale para tipos de vivienda y grupos con `MINIMO_PUBLICACION` anuncios o más.
  - El índice queda alineado con `base.index`.
- `economia_inmobiliaria`:
  - Usa `con_vivienda`.
  - Publica la fila si `anuncios >= MINIMO_PUBLICACION`.
  - `indice_relativo_mediana` es nulo si `anuncios_indice < MINIMO_PUBLICACION`.
- `estrato_inferido`: es el estrato declarado más frecuente del barrio, solo si hay `MINIMO_ESTRATO_BARRIO` anuncios o más con estrato y ese estrato reúne una proporción mayor o igual a `CONSENSO_ESTRATO`. Si hay empate, gana el menor estrato.
- `estratos_inmobiliaria`:
  - `declarados` cuenta los anuncios con estrato.
  - `inferidos` cuenta los anuncios sin estrato que reciben uno por su barrio.
  - Hay filas por estrato 1 a 6, solo si alguna de las dos cuentas es mayor que 0.

- [ ] **Step 1: Escribir las pruebas que fallan**

```python
def test_cobertura_inmobiliaria(): # santafe con 3 barrios de 2 comunas → barrios 3, comunas 2; fila "todas"
def test_comuna_principal_empate(): # 2 y 2 → la de menor código; pct 50,0
def test_cobertura_cuenta_celdas_pequenas(): # Review Focus 2: 1 anuncio de venta → aparece en cobertura
def test_cobertura_comuna_porcentajes(): # suma 100 por fuente y operación
def test_indice_relativo(): # 5 apartamentos del barrio: 4 a 40_000 $/m² y 1 a 60_000 → 1,5 para ese; mediana 40_000
def test_indice_relativo_grupo_pequeno(): # 4 en el barrio → NaN
def test_economia_minimo_y_vivienda(): # un local no entra; 4 anuncios de venta de una fuente → sin fila de venta
def test_economia_sin_operacion(): # Review Focus 3: puertabierta solo arriendo → sin filas de venta, sin anuncios = 0
def test_estrato_inferido_consenso(): # 5 con estrato 3 de 6 conocidos (83 %) → 3; 3 y 3 de 6 (50 %) → sin estrato
def test_estrato_inferido_pocos(): # 4 conocidos → sin estrato
def test_estratos_declarados_e_inferidos(): # alnago sin estrato en un barrio con consenso 4 → inferidos 1 en el estrato 4
def test_tablas_inmobiliaria_vacias(): # Review Focus 3: las 4 funciones con base vacía → columnas y tipos
```

- [ ] **Step 2: Correr y ver que fallan.** Run: `uv run pytest tests/test_agregados.py -q`. Expected: FAIL con `ImportError`.

- [ ] **Step 3: Implementar.** Todo vectorizado con `groupby`. Para los porcentajes se usa `transform("sum")`.

- [ ] **Step 4: Correr y ver que pasan.** Run: `uv run pytest -q && uv run mypy`. Expected: toda la suite pasa.

- [ ] **Step 5: Commit** (lo hace el autor)

```bash
git add src/observatorio_inmobiliario/agregados.py tests/test_agregados.py
git commit -m "feat: cobertura, economía y estratos por inmobiliaria"
```

---

### Task 3: Agregados de propiedades compartidas (pregunta 7)

**Files:**
- Modify: `src/observatorio_inmobiliario/agregados.py`
- Test: `tests/test_agregados.py`

**Interfaces:**
- Consumes: las tablas de `emparejar` y `agrupar` (Plan 5), `base_analisis` (Task 1) y `Confianza` (Plan 5).
- Produces:

```python
def compartidos_fuentes(parejas: pd.DataFrame, semana: str) -> pd.DataFrame
def grupos_compartidos(grupos: pd.DataFrame, base: pd.DataFrame, semana: str) -> pd.DataFrame
```

- `compartidos_fuentes`:
  - Por cada nivel acumulado (`"alta"`, `"media"`, `"baja"`), agrupa las parejas de ese nivel o mayor por `fuente_a, fuente_b`.
  - `pct_a_mas_barata` cuenta las parejas con `precio_a < precio_b`, sobre las que tienen los dos precios.
  - Ordena por `nivel` (alta, media, baja), `fuente_a` y `fuente_b`.
- `grupos_compartidos`:
  - Une `grupos` con `base` por `CLAVE` para traer los datos del anuncio.
  - Por cada nivel, numera los grupos de 1 a n en el orden de su id de grupo (orden de texto).
  - `barrio` es `barrio_normalizado`, y si es nulo, `nombre_comuna`.
  - `area_m2` se redondea a entero.
  - No incluye `id_fuente`, `url` ni coordenadas.

- [ ] **Step 1: Escribir las pruebas que fallan**

```python
def test_compartidos_fuentes_niveles_acumulados(): # 1 alta + 1 baja entre las mismas fuentes → "alta" 1, "media" 1, "baja" 2
def test_pct_a_mas_barata_y_mismo_precio(): # precios (1, 2), (2, 1), (3, 3) → 33,3 y 33,3
def test_grupos_compartidos_anonimos(): # Review Focus 5: sin id_fuente, url, latitud ni longitud; grupo 1..n por nivel
def test_grupos_compartidos_numeracion_estable(): # grupos en otro orden → la misma numeración
def test_compartidos_vacios(): # Review Focus 3: sin parejas → tablas vacías con columnas y tipos
```

- [ ] **Step 2: Correr y ver que fallan.** Run: `uv run pytest tests/test_agregados.py -q`. Expected: FAIL con `ImportError`.

- [ ] **Step 3: Implementar.** Los grupos se renumeran con `groupby("nivel")[...].rank(method="dense")` sobre el id de grupo, convertido a Int64.

- [ ] **Step 4: Correr y ver que pasan.** Run: `uv run pytest -q && uv run mypy`. Expected: toda la suite pasa.

- [ ] **Step 5: Commit** (lo hace el autor)

```bash
git add src/observatorio_inmobiliario/agregados.py tests/test_agregados.py
git commit -m "feat: agregados de propiedades compartidas sin datos de anuncios"
```

---

### Task 4: Evolución en el tiempo (pregunta 8)

**Files:**
- Create: `src/observatorio_inmobiliario/evolucion.py`
- Test: `tests/test_evolucion.py`

**Interfaces:**
- Consumes: `semana_de` (Task 1), y `anuncios_unicos`, `base_analisis`, `con_vivienda` y `MINIMO_PUBLICACION` (Task 1).
- Produces:

```python
def con_semana(limpio: pd.DataFrame) -> pd.DataFrame                 # agrega "semana" desde fecha_observacion
def evolucion_precios(limpio: pd.DataFrame) -> pd.DataFrame           # todas las semanas
def rotacion_inmobiliaria(limpio: pd.DataFrame) -> pd.DataFrame       # todas las semanas
```

- `limpio` es la unión de todas las semanas, tal como la devuelve `leer_limpio(directorio)`.
- `evolucion_precios`: por cada semana, aplica `base_analisis` y `con_vivienda`. Publica las filas con `anuncios >= MINIMO_PUBLICACION`.
- `rotacion_inmobiliaria`:
  - Usa los anuncios únicos con `es_medellin`, por semana.
  - Las semanas se ordenan y se comparan con la semana anterior **que tiene datos**: si falta una semana del calendario, no se inventa un retiro masivo.
  - `semanas_publicado` se cuenta con las apariciones consecutivas.
  - Un anuncio que vuelve después de desaparecer empieza a contar de nuevo.

- [ ] **Step 1: Escribir las pruebas que fallan.** Usan semanas sintéticas: filas con `fecha_observacion` en S45, S46 y S47.

```python
def test_con_semana(): # date(2026, 11, 11) → "2026-S46"
def test_evolucion_por_semana(): # 5 apartamentos en arriendo en S45 y 5 en S46 → 2 filas por tipo
def test_una_sola_semana(): # Review Focus 4: retirados 0, tasa nula, comparables 0
def test_retirados_y_tasa(): # S45: A, B, C, D; S46: A, B → retirados 2, tasa 50,0
def test_nuevos(): # S46 agrega E → nuevos 1
def test_semanas_publicado_excluye_primera_semana(): # Review Focus 4: B está en S45 y sale en S46 → no cuenta; E entra en S46 y sale en S48 → 2 semanas
def test_anuncio_que_vuelve(): # Review Focus 4: A en S45, falta en S46, vuelve en S47 → retirado en S46 y nuevo en S47
def test_cambio_de_precio(): # A: 2_000_000 → 2_100_000; B sin cambio → comparables 2, con_cambio 1, mediana 5,0
def test_semana_faltante_no_es_retiro(): # S45 y S47 sin S46 → se compara S47 con S45
def test_rotacion_cuenta_atipicos(): # un atípico de Medellín cuenta en anuncios
def test_evolucion_vacia(): # Review Focus 3: limpio vacío → columnas y tipos
```

- [ ] **Step 2: Correr y ver que fallan.** Run: `uv run pytest tests/test_evolucion.py -q`. Expected: FAIL con `ModuleNotFoundError: observatorio_inmobiliario.evolucion`.

- [ ] **Step 3: Implementar.**
  - Se arma una tabla de presencia: clave × semana → precio.
  - De ella salen los nuevos, los retirados y los cambios de precio, con `shift` sobre la lista ordenada de semanas con datos.
  - Las rachas de semanas consecutivas se numeran con un `cumsum` de los cortes.

- [ ] **Step 4: Correr y ver que pasan.** Run: `uv run pytest -q && uv run mypy`. Expected: toda la suite pasa.

- [ ] **Step 5: Commit** (lo hace el autor)

```bash
git add src/observatorio_inmobiliario/evolucion.py tests/test_evolucion.py
git commit -m "feat: evolución semanal de precios y rotación de inventario"
```

---

### Task 5: Comando `agregados`, corrida real y README

**Files:**
- Modify: `src/observatorio_inmobiliario/almacenamiento.py`, `src/observatorio_inmobiliario/cli.py`, `README.md`
- Create: `data/agregados/*.parquet` (salida de la corrida real; **se versionan**)
- Test: `tests/test_almacenamiento.py`, `tests/test_cli.py`

**Interfaces:**
- Consumes: todas las funciones de las Tasks 1-4, más `leer_limpio`, `leer_compartidos` y `semanas_limpias`.
- Produces:

```python
TABLAS_AGREGADAS: Final = ("precios_zona", "cobertura_inmobiliaria", "cobertura_comuna",
    "economia_inmobiliaria", "estratos_inmobiliaria", "compartidos_fuentes",
    "grupos_compartidos", "evolucion_precios", "rotacion_inmobiliaria")
COLUMNAS_PRIVADAS: Final = frozenset({"id_fuente", "url", "latitud", "longitud", "anunciante_origen"})
def guardar_agregado(df: pd.DataFrame, directorio: Path, nombre: str) -> Path   # directorio/<nombre>.parquet, escritura atómica
def leer_agregado(directorio: Path, nombre: str) -> pd.DataFrame
```

- `guardar_agregado`:
  - Lanza `ValueError` si `nombre` no está en `TABLAS_AGREGADAS`, o si el DataFrame tiene alguna columna de `COLUMNAS_PRIVADAS` (incluidas las variantes con sufijo `_a` o `_b`).
  - Es la última barrera antes del repo público.
- Comando: `observatorio agregados [--limpio data/limpio] [--compartidos data/compartidos] [--salida data/agregados]`.
  - La foto usa la última semana limpia.
  - La evolución usa todas las semanas.
  - Si no hay datos limpios: imprime `no hay datos limpios en …` por stderr y devuelve 1.
  - Si faltan las parejas de esa semana, avisa por stderr (`corre primero: observatorio compartidos`) y devuelve 1.
  - Al terminar imprime cada archivo con su número de filas.

- [ ] **Step 1: Escribir las pruebas que fallan**

```python
def test_guardar_y_leer_agregado(tmp_path)               # ida y vuelta conserva dtypes
def test_guardar_agregado_nombre_desconocido(tmp_path)    # ValueError
def test_guardar_agregado_rechaza_columnas_privadas(tmp_path)  # Review Focus 5: id_fuente, url_a → ValueError
def test_cli_agregados(tmp_path, capsys)                  # limpiar + compartidos + agregados sobre crudo sintético → 9 archivos; exit 0
def test_cli_agregados_sin_columnas_privadas(tmp_path)    # Review Focus 5: ningún archivo tiene COLUMNAS_PRIVADAS
def test_cli_agregados_sin_datos(tmp_path)                # exit 1
def test_cli_agregados_sin_compartidos(tmp_path, capsys)  # exit 1 y el aviso
```

- [ ] **Step 2: Correr y ver que fallan.** Run: `uv run pytest tests/test_almacenamiento.py tests/test_cli.py -q`. Expected: FAIL con `ImportError`.

- [ ] **Step 3: Implementar.** `guardar_agregado` usa `pa.Table.from_pandas(df, preserve_index=False)` y `_escribir`. Las tablas ya llegan con tipos fijos desde las Tasks 1-4, así que no hace falta declarar un esquema por tabla.

- [ ] **Step 4: Correr y ver que pasan.** Run: `uv run pytest -q && uv run mypy`. Expected: toda la suite pasa.

- [ ] **Step 5: Corrida real.** Run: `uv run observatorio agregados && du -k data/agregados/*`

Expected, con los datos de 2026-S46:
- 9 archivos, y ninguno pasa de 500 KB.
- `precios_zona`: en venta y tipo `"vivienda"`, 87 barrios o menos (porque se filtra por vivienda) y las 20 comunas.
- `cobertura_inmobiliaria`: 9 fuentes × (2 operaciones o 1) + `"todas"`.
- `estratos_inmobiliaria`: Alnago y Puertabierta tienen `inferidos > 0`.
- `compartidos_fuentes`, en el nivel `"baja"`: la suma de `parejas` es 230.
- `evolucion_precios` y `rotacion_inmobiliaria`: solo la semana 2026-S46, con 0 retirados.

Revisar a mano:
- los 10 barrios con mayor y menor precio por m² de venta, para ver que sean razonables (El Poblado arriba);
- la comuna principal de cada inmobiliaria.

Si algo no tiene sentido, se aplica superpowers:systematic-debugging antes de seguir.

- [ ] **Step 6: README.** Agregar una sección "Agregados" con:
  - el comando;
  - la tabla de archivos (qué pregunta responde cada uno);
  - el mínimo de publicación y por qué;
  - el estrato inferido y su tasa de acierto;
  - el índice relativo;
  - una nota: la reputación (pregunta 5) se consulta en vivo en el dashboard.

- [ ] **Step 7: Verificación completa.** Run: `uv run pre-commit run --all-files && uv run pytest`. Expected: todo pasa.

- [ ] **Step 8: Commit** (lo hace el autor)

```bash
git add README.md src/observatorio_inmobiliario/almacenamiento.py src/observatorio_inmobiliario/cli.py tests/test_almacenamiento.py tests/test_cli.py data/agregados/
git commit -m "feat: comando agregados con las tablas públicas del análisis"
```

---

### Task 6: Notebook de análisis exploratorio y hallazgos

**Files:**
- Modify: `pyproject.toml` (grupo `analisis`: `ipykernel`, `nbconvert`, `matplotlib`), `uv.lock`, `README.md`
- Create: `notebooks/01_analisis_exploratorio.ipynb`
- Test: `tests/test_notebook.py`

**Interfaces:**
- Consumes: `leer_agregado` y `TABLAS_AGREGADAS` (Task 5).

**Decisión del diseñador** (el autor puede cambiarla): el notebook grafica con **matplotlib** y no con plotly.
- GitHub muestra las imágenes PNG de un notebook, pero no las gráficas de plotly.
- Las imágenes PNG pesan poco y caben en el límite de 500 KB.
- El dashboard (Plan 7) sí usa plotly, como dice el spec.

**Estructura del notebook** (en español, con texto que explica antes de cada gráfica):
1. **Introducción.** Fuentes, semana y advertencias. Lee las tablas con `leer_agregado(Path("../data/agregados"), ...)`.
2. **Precio por barrio.** Los 15 barrios más caros y los 15 más baratos por m² de venta de vivienda, y la comparación venta vs. arriendo por comuna (pregunta 1).
3. **Cobertura.** Barrios cubiertos por inmobiliaria y un mapa de calor de inmobiliaria × comuna (pregunta 2).
4. **Economía.** Índice relativo por inmobiliaria, en venta y en arriendo por separado (pregunta 3).
5. **Estratos.** Barras apiladas de estratos 1-3 vs. 4-6 por inmobiliaria, distinguiendo declarado e inferido (pregunta 4).
6. **Reputación y reconocimiento.** Un texto que explica que la reputación se consulta en vivo en el dashboard, y los componentes de volumen y barrios (preguntas 5 y 6).
7. **Propiedades compartidas.** Parejas por combinación de fuentes y diferencia de precio por nivel (pregunta 7).
8. **Evolución.** Qué se mide y la nota de que hoy hay una sola semana (pregunta 8).
9. **Hallazgos.** Entre 5 y 8 frases con cifras, y las limitaciones.

- [ ] **Step 1: Escribir las pruebas que fallan**

```python
RUTA = Path("notebooks/01_analisis_exploratorio.ipynb")
def test_notebook_existe_y_tiene_resultados(): # json válido; todas las celdas de código tienen execution_count
def test_notebook_solo_lee_agregados(): # Review Focus 5: ninguna celda menciona "data/limpio", "data/crudo", "data/compartidos" ni leer_limpio, leer_compartidos ni leer_observaciones
def test_notebook_pesa_menos_de_500_kb()
def test_notebook_responde_las_preguntas(): # hay una celda markdown con un encabezado por cada pregunta 1-8 y un "Hallazgos"
```

- [ ] **Step 2: Correr y ver que fallan.** Run: `uv run pytest tests/test_notebook.py -q`. Expected: FAIL (el archivo no existe).

- [ ] **Step 3: Agregar las dependencias.** Run: `uv add --group analisis ipykernel nbconvert matplotlib`.

- [ ] **Step 4: Escribir el notebook y ejecutarlo.** Run: `uv run --group analisis jupyter nbconvert --to notebook --execute --inplace notebooks/01_analisis_exploratorio.ipynb`. Expected: termina sin errores.

- [ ] **Step 5: Correr y ver que pasan.** Run: `uv run pytest -q && uv run ruff check notebooks && uv run ruff format --check notebooks`. Expected: todo pasa.

- [ ] **Step 6: README.** Agregar:
  - una sección "Hallazgos" con las frases del notebook;
  - un enlace al notebook;
  - cómo correrlo: `uv sync --group analisis`, más el comando de nbconvert.

- [ ] **Step 7: Verificación completa.** Run: `uv run pre-commit run --all-files && uv run pytest`. Expected: todo pasa.

- [ ] **Step 8: Commit** (lo hace el autor)

```bash
git add pyproject.toml uv.lock README.md notebooks/01_analisis_exploratorio.ipynb tests/test_notebook.py
git commit -m "feat: notebook de análisis exploratorio con los hallazgos"
```
