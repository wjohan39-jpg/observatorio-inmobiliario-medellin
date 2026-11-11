# Plan 2: Adaptadores JSON (Nutibara, Uribienes, Alnago)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Agregar tres fuentes nuevas que leen APIs JSON públicas, de modo que `observatorio scrape nutibara|uribienes|alnago` funcione igual que `santafe`.

**Architecture:** Cada sitio tiene un módulo en `fuentes/` con una función pura `mapear_anuncio(...)` (JSON → `AnuncioNormalizado`) y una clase `Fuente<Sitio>` que recorre la API con `ClienteCortes`. El registro de `fuentes/__init__.py` las expone a la CLI sin cambiarla. Dos conversiones nuevas y compartidas (coordenadas y estrato) van a `parseo.py`.

**Tech Stack:** Python 3.12+, httpx (vía `ClienteCortes`), pydantic, pytest + respx, ruff, mypy estricto.

**Spec:** `docs/superpowers/specs/2026-11-10-scraper-inmobiliario-medellin-design.md` (§6 fuentes, §7 arquitectura, §7.1 reglas legales).

## Revisión técnica de las APIs (2026-11-11)

Hecha con pocas peticiones, con el User-Agent del proyecto. Esto es lo que el plan da por cierto:

| Sitio | Host de la API | robots.txt del host | Endpoint | Paginación | Cobertura |
|---|---|---|---|---|---|
| Nutibara | `https://api.arrendamientosnutibara.com` | 404 → sin reglas | `GET /promotion/filter/nearest?latitude&longitude&page&priceStart=1&status=PROMOCION\|VENTAS` | 20 por página, `data.total` | **Radio de ~3 km** alrededor del punto (medido: el resultado más lejano está a 2,99 km). No hay parámetro para ampliarlo. |
| Uribienes | `https://uribienes.com` | permite `/api/properties`; prohíbe `/?*` | `GET /api/properties?city=<DANE>&biz=1\|2&page=N` | 12 por página fijos, `current_page`/`last_page` | Todo el país (incluye Bogotá y Santander) → se filtra por municipio. Medellín: 260 arriendo / 112 venta. |
| Alnago | `https://api.alnago.com` | solo comentarios de Cloudflare → sin reglas | `GET /property/map?for_rent=true&for_sale=false&id_city=<id Wasi>` (o al revés para venta) | Ninguna: una petición trae todo | Medellín: 816 arriendo / 437 venta. Sin estrato, sin administración, sin municipio en la respuesta. |

Detalles que el código debe respetar:

- **Nutibara.** `status=VENTAS` devuelve estados `"VENTAS"` y `"VENTAS - MLS"` (inventario compartido). `stratum` vale `0` cuando no hay dato. `facilities` es una lista; se identifica cada dato por `facility.id`: `112` área, `82` alcobas, `105` baños (el nombre llega con problemas de codificación, así que no se usa). `sellValue` y `rentValue` traen el mismo número; se usa `rentValue` en arriendo y `sellValue` en venta. URL pública: `https://anutibara.com/{tipo}-en-{arriendo|venta}/{barrio}-{ciudad}/{id}` en minúsculas y con espacios cambiados por `-`.
- **Uribienes.** Los inmuebles `"ARRIENDO/VENTA"` aparecen con `biz=1` y con `biz=2`; traen `rent` y `saleprice` por separado (`price` es `"1700000/250000000"` y no se usa). `latitude`/`longitude` son textos con signo (`"-75.17"`). `city` trae espacios al final. `administration`, `area_cons` y `stratum` usan `0` para "sin dato". URL pública: `https://uribienes.com/inmuebles/{codpro}` (no se pide nunca: su robots no quiere que se rastreen los detalles).
- **Alnago.** Con el filtro de operación, `price` es el precio correcto (sin él, 1.189 de 1.802 venían en 0). `zone` (el barrio) puede ser `null` o `""`. `id_property_type` es el tipo del CRM Wasi. URL pública: `https://alnago.com/es/inmueble/{id_property}`.

**Nota ética para el autor (decisión tomada: se usa la API).** `alnago.com/robots.txt` prohíbe `/api/` *en su propio dominio*. La API real está en otro host, `api.alnago.com`, cuyo robots.txt no tiene reglas, y es la que el navegador de cualquier visitante llama. El cliente aplica el robots.txt del host que consulta, como define RFC 9309. Además se hace una sola petición por municipio y operación (16 en total).

## Global Constraints

- Toda petición pasa por `ClienteCortes`: respeta robots.txt del host, 1,5 s entre peticiones (`SEGUNDOS_ENTRE_PETICIONES`) y reintentos con espera creciente.
- Solo datos de hecho: **no** se mapean fotos (`images`, `thumb`, `image1`…), descripciones, direcciones ni datos de contacto. `AnuncioNormalizado` ya rechaza campos extra.
- Los fixtures van al repo público: solo llevan los campos que el adaptador usa más uno o dos irrelevantes. Nunca `description`, `address`, imágenes ni teléfonos.
- No se piden páginas de detalle en ningún sitio de este plan.
- Un anuncio inválido se omite con `logger.warning` y no detiene la corrida (igual que Santa Fe).
- Código, nombres, docstrings y mensajes en español. `ruff`, `ruff format --check`, `mypy` estricto y `pytest` en verde antes de cada commit.
- Cada adaptador acepta las opciones que la CLI pasa a todas las fuentes: `con_detalle: bool = True` (sin efecto en estas tres; se documenta) y `max_paginas: int | None = None`, más `fecha: date | None = None`.
- Municipios: se guardan los del Valle de Aburrá con su nombre; el filtro a Medellín se hace en el Plan 4.

## Review Focus

1. **robots.txt real de Uribienes** (`Disallow: /?*`) no debe bloquear `/api/properties?city=…`. → prueba en la Tarea 3 con el texto real.
2. **Estrato `0` o fuera de 1-6** debe quedar nulo y no tumbar el anuncio entero (el modelo exige 1-6). → `parsear_estrato` (Tarea 1) y fixture de Nutibara con `stratum: 0` (Tarea 2).
3. **Coordenadas como texto con signo negativo** (`"-75.5812"`) deben conservar el signo; `parsear_decimal` lo pierde porque su regex ignora el `-`. → `parsear_coordenada` (Tarea 1).
4. **Círculos de Nutibara que se traslapan** devuelven el mismo anuncio varias veces; debe salir una sola vez por operación. → prueba de duplicados (Tarea 2).
5. **Respuestas vacías** (un punto de la cuadrícula sin inmuebles, `items: []`, `zone: null`) no deben fallar ni ciclar para siempre. → pruebas en las Tareas 2 y 4.

---

### Task 1: Conversiones compartidas de coordenadas y estrato

**Files:**
- Modify: `src/observatorio_inmobiliario/parseo.py`
- Modify: `src/observatorio_inmobiliario/fuentes/santafe.py` (quitar `_coordenada`, usar `parsear_coordenada`; usar `parsear_estrato`)
- Test: `tests/test_parseo.py`

**Interfaces:**
- Produces: `parsear_coordenada(valor: ValorCrudo) -> float | None` y `parsear_estrato(valor: ValorCrudo) -> int | None`, ambos en `observatorio_inmobiliario.parseo`. Nunca lanzan excepciones.

- [ ] **Step 1: Escribir las pruebas que fallan**

```python
@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        (6.2442, 6.2442),
        (-75.5812, -75.5812),
        ("-75.170916308256", -75.170916308256),
        (" 6.24 ", 6.24),
        (0, None),
        ("0", None),
        ("", None),
        ("sin dato", None),
        (None, None),
        (True, None),
        (float("nan"), None),
        (181, None),
    ],
)
def test_parsear_coordenada(valor: ValorCrudo, esperado: float | None) -> None:
    assert parsear_coordenada(valor) == esperado


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [(3, 3), ("5", 5), ("Estrato 4", 4), (0, None), (7, None), (None, None), ("", None)],
)
def test_parsear_estrato(valor: ValorCrudo, esperado: int | None) -> None:
    assert parsear_estrato(valor) == esperado
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `uv run pytest tests/test_parseo.py -v`
Expected: FAIL con `ImportError` por `parsear_coordenada`.

- [ ] **Step 3: Implementar en `parseo.py`**

`parsear_coordenada`: `bool` → `None`; número → `float`; texto → `float(valor.strip())` dentro de `try` (no usar `_a_numero`, que pierde el signo). Devuelve `None` si es `0`, `NaN` o `abs(x) > 180`. `parsear_estrato`: `parsear_entero` y `None` si no está entre 1 y 6. Cada una con un doctest corto, como las existentes.

- [ ] **Step 4: Usarlas en Santa Fe**

En `santafe.py` borrar `_coordenada` y llamar `parsear_coordenada(...)` para latitud y longitud, y `parsear_estrato(d.get("estrato"))` para el estrato.

- [ ] **Step 5: Correr todo y ver que pasa**

Run: `uv run pytest && uv run ruff check . && uv run ruff format --check . && uv run mypy`
Expected: todo en verde; `tests/test_santafe.py` sin cambios y pasando.

- [ ] **Step 6: Commit**

```bash
git add src/observatorio_inmobiliario/parseo.py src/observatorio_inmobiliario/fuentes/santafe.py tests/test_parseo.py
git commit -m "feat(parseo): coordenadas con signo y estrato válido entre 1 y 6"
```

---

### Task 2: Adaptador de Arrendamientos Nutibara

**Files:**
- Create: `src/observatorio_inmobiliario/fuentes/nutibara.py`
- Modify: `src/observatorio_inmobiliario/fuentes/__init__.py` (agregar al `REGISTRO`)
- Create: `tests/fixtures/nutibara/arriendo_p1.json`, `tests/fixtures/nutibara/venta_p1.json`
- Test: `tests/test_nutibara.py`

**Interfaces:**
- Consumes: `ClienteCortes.get_json(ruta, params)`, `parsear_precio`, `parsear_decimal`, `parsear_entero`, `parsear_estrato`, `parsear_coordenada`.
- Produces:
  - `URL_BASE: Final = "https://api.arrendamientosnutibara.com"` (el host que consulta el cliente) y `URL_SITIO: Final = "https://anutibara.com"` (para armar la URL pública).
  - `RADIO_KM: Final = 2.9`, `TAMANO_PAGINA: Final = 20`.
  - `cuadricula(sur: float, norte: float, oeste: float, este: float, paso: float) -> tuple[tuple[float, float], ...]`: puntos `(lat, lon)` igualmente espaciados que incluyen los cuatro bordes; el espaciado real es ≤ `paso`.
  - `CENTROS: Final = cuadricula(6.09, 6.38, -75.66, -75.50, 0.035)` (Valle de Aburrá).
  - `mapear_anuncio(promocion: dict[str, Any], fecha: date) -> AnuncioNormalizado`.
  - `class FuenteNutibara` con `nombre = "nutibara"` y `__init__(self, cliente, *, con_detalle=True, max_paginas=None, fecha=None, centros=CENTROS)`.

**Fixtures** (forma real, recortada; sin `images`):

`arriendo_p1.json`:
```json
{"code": 200, "success": true, "data": {"total": 2, "promotions": [
  {"id": 68776, "sellValue": 3600000, "rentValue": 3600000, "status": "PROMOCION",
   "createdAt": "2023-11-30T11:58:01.000Z", "keys": false,
   "property": {"id": 37020, "type": "APARTAMENTO", "neighborhood": "CONQUISTADORES",
     "sector": "OCCIDENTE", "city": "MEDELLIN", "latitude": 6.2426, "longitude": -75.5828,
     "stratum": 5, "facilities": [
       {"id": 1, "value": "170", "facility": {"id": 112, "name": "Area"}},
       {"id": 2, "value": "3", "facility": {"id": 82, "name": "Alcobas"}},
       {"id": 3, "value": "2", "facility": {"id": 105, "name": "Baños"}}]}},
  {"id": 72012, "sellValue": 2300000, "rentValue": 2300000, "status": "PROMOCION",
   "createdAt": "2025-01-10T08:56:20.000Z", "keys": false,
   "property": {"id": 38148, "type": "LOCAL", "neighborhood": "CONQUISTADORES",
     "sector": "OCCIDENTE", "city": "MEDELLIN", "latitude": 6.24013, "longitude": -75.5845,
     "stratum": 0, "facilities": [{"id": 4, "value": "35", "facility": {"id": 112, "name": "Area"}}]}}
]}}
```

`venta_p1.json`: una promoción `id 70001`, `status "VENTAS - MLS"`, `sellValue 335000000`, `type "APARTAMENTO"`, `neighborhood "LAURELES"`, `city "MEDELLIN"`, `stratum 0`, `latitude 6.245`, `longitude -75.59`, facilities área `"80"`, alcobas `"2"`, baños `"2"`; `total: 1`.

- [ ] **Step 1: Escribir las pruebas que fallan**

Fixtures `sitio` (respx con `base_url=URL_BASE` y robots 404) y `cliente` (`ClienteCortes(URL_BASE, segundos_entre_peticiones=0)`), como en `test_santafe.py`. Pruebas:

```python
def test_mapear_arriendo_completo(arriendo: dict[str, Any]) -> None:
    a = mapear_anuncio(arriendo["data"]["promotions"][0], FECHA)
    assert a.fuente == "nutibara"
    assert a.id_fuente == "68776"
    assert a.operacion is Operacion.ARRIENDO
    assert a.url == "https://anutibara.com/apartamento-en-arriendo/conquistadores-medellin/68776"
    assert (a.tipo_inmueble, a.precio, a.area_m2) == ("apartamento", 3_600_000, 170.0)
    assert (a.habitaciones, a.banos, a.estrato) == (3, 2, 5)
    assert (a.barrio, a.municipio) == ("CONQUISTADORES", "MEDELLIN")
    assert (a.latitud, a.longitud) == (6.2426, -75.5828)


def test_estrato_cero_queda_nulo(arriendo: dict[str, Any]) -> None:
    a = mapear_anuncio(arriendo["data"]["promotions"][1], FECHA)
    assert a.estrato is None
    assert a.habitaciones is None and a.banos is None
    assert a.area_m2 == 35.0


def test_venta_mls_usa_precio_de_venta(venta: dict[str, Any]) -> None:
    a = mapear_anuncio(venta["data"]["promotions"][0], FECHA)
    assert a.operacion is Operacion.VENTA
    assert a.precio == 335_000_000


def test_cuadricula_incluye_bordes_y_respeta_paso() -> None:
    puntos = cuadricula(6.0, 6.1, -75.6, -75.5, 0.035)
    lats = sorted({p[0] for p in puntos})
    assert lats[0] == 6.0 and lats[-1] == pytest.approx(6.1)
    assert max(b - a for a, b in itertools.pairwise(lats)) <= 0.035


def test_centros_cubren_el_valle_de_aburra() -> None:
    """Todo punto del rectángulo queda a menos de RADIO_KM de algún centro."""
    for i in range(30):
        lat = 6.09 + i * (6.38 - 6.09) / 29
        for j in range(20):
            lon = -75.66 + j * (-75.50 + 75.66) / 19
            assert min(_km(lat, lon, c_lat, c_lon) for c_lat, c_lon in CENTROS) <= RADIO_KM
```

`_km` es un haversine de 5 líneas en el archivo de prueba.

Pruebas de recorrido con respx (`centros` inyectados para no hacer 60 rutas):

- `test_recorre_ambas_operaciones`: un centro; la ruta responde `arriendo_p1.json` cuando `status=PROMOCION` y `venta_p1.json` cuando `status=VENTAS` (usar `params__contains`). Resultado: 3 anuncios, 2 de arriendo y 1 de venta; los parámetros enviados incluyen `priceStart=1` y la latitud como texto.
- `test_pagina_hasta_completar_total`: `total: 25`; página 1 con 20 promociones e ids distintos, página 2 con 5. Se piden exactamente 2 páginas por operación.
- `test_centro_sin_resultados_no_cicla`: respuesta `{"data": {"total": 0, "promotions": []}}` → 0 anuncios y 1 sola petición por operación.
- `test_duplicados_entre_centros_salen_una_vez`: dos centros que devuelven la misma promoción → 1 anuncio de arriendo.
- `test_max_paginas`: `total: 60`, `max_paginas=1` → 1 petición por centro y operación.
- `test_anuncio_invalido_se_omite`: una promoción con `"status": "PERMUTA"` entre dos válidas → salen las dos válidas y queda un `WARNING` en `caplog`.
- `test_registrada_en_cli`: `"nutibara" in REGISTRO` y `REGISTRO["nutibara"].url_base == URL_BASE`.

- [ ] **Step 2: Correr y ver que fallan**

Run: `uv run pytest tests/test_nutibara.py -v`
Expected: FAIL con `ModuleNotFoundError: observatorio_inmobiliario.fuentes.nutibara`.

- [ ] **Step 3: Implementar `nutibara.py`**

- `mapear_anuncio`: operación `ARRIENDO` si `status == "PROMOCION"`, `VENTA` si empieza por `"VENTAS"`; cualquier otro valor se pasa tal cual en minúsculas para que pydantic lo rechace. Facilities: diccionario `{facility.id: value}`. URL con el slug `texto.lower().replace(" ", "-")`; `None` si falta tipo, barrio o ciudad. `anunciante_origen` queda `None` (la API no dice qué agencia publicó en MLS).
- `_resultados(status, lat, lon)`: `params={"latitude": f"{lat:.5f}", "longitude": f"{lon:.5f}", "page": n, "priceStart": 1, "status": status}` (los `Parametros` del cliente solo aceptan `str | int`). Corta cuando la página viene vacía, cuando `n * TAMANO_PAGINA >= total` o al llegar a `max_paginas`.
- `listar_anuncios`: por cada `status` en `("PROMOCION", "VENTAS")`, un `set` de ids vistos y un recorrido de todos los centros; `ValidationError` → `logger.warning` y sigue.
- Docstring del módulo con lo de la tabla de revisión (endpoint, radio de 3 km, por qué la cuadrícula).

- [ ] **Step 4: Registrar la fuente**

En `fuentes/__init__.py`: `nutibara.FuenteNutibara.nombre: RegistroFuente(nutibara.URL_BASE, nutibara.FuenteNutibara)`.

- [ ] **Step 5: Correr todo y ver que pasa**

Run: `uv run pytest && uv run ruff check . && uv run ruff format --check . && uv run mypy`
Expected: todo en verde.

- [ ] **Step 6: Commit**

```bash
git add src/observatorio_inmobiliario/fuentes/nutibara.py src/observatorio_inmobiliario/fuentes/__init__.py tests/test_nutibara.py tests/fixtures/nutibara
git commit -m "feat: adaptador de Arrendamientos Nutibara con búsqueda por cuadrícula"
```

---

### Task 3: Adaptador de Uribienes

**Files:**
- Create: `src/observatorio_inmobiliario/fuentes/uribienes.py`
- Modify: `src/observatorio_inmobiliario/fuentes/__init__.py`
- Create: `tests/fixtures/uribienes/arriendo_p1.json`, `tests/fixtures/uribienes/robots.txt`
- Test: `tests/test_uribienes.py`

**Interfaces:**
- Consumes: lo mismo que la Tarea 2.
- Produces:
  - `URL_BASE: Final = "https://uribienes.com"`.
  - `MUNICIPIOS: Final[dict[int, str]]`, códigos DANE del Valle de Aburrá: `5001 "Medellín"`, `5088 "Bello"`, `5360 "Itagüí"`, `5266 "Envigado"`, `5631 "Sabaneta"`, `5380 "La Estrella"`, `5129 "Caldas"`, `5212 "Copacabana"`, `5308 "Girardota"`, `5079 "Barbosa"`.
  - `NEGOCIOS: Final = {1: Operacion.ARRIENDO, 2: Operacion.VENTA}` (valores del parámetro `biz`).
  - `mapear_anuncio(inmueble: dict[str, Any], operacion: Operacion, fecha: date) -> AnuncioNormalizado`.
  - `class FuenteUribienes` con `nombre = "uribienes"` y `__init__(self, cliente, *, con_detalle=True, max_paginas=None, fecha=None)`.

**Fixtures:** `arriendo_p1.json` con `{"total": 2, "per_page": 12, "current_page": 1, "last_page": 1, "from": 1, "to": 2, "data": [...]}` y dos inmuebles con solo estos campos:

1. `codpro 220400`, `idpro 3860800`, `biz "ARRIENDO"`, `type "APARTAMENTO"`, `city "Medellín "`, `neighborhood "Laureles"`, `rent 2500000`, `saleprice 0`, `price "2500000"`, `administration 350000`, `area_cons 85`, `bedrooms 3`, `bathrooms 2`, `parking 1`, `stratum 5`, `latitude "6.2441"`, `longitude "-75.5900"`.
2. `codpro 220401`, `biz "ARRIENDO/VENTA"`, `type "CASA"`, `city "Envigado "`, `neighborhood "Zuñiga"`, `rent 1700000`, `saleprice 250000000`, `price "1700000/250000000"`, `administration 0`, `area_cons 0`, `bedrooms 4`, `bathrooms 3`, `parking 0`, `stratum 0`, `latitude "0"`, `longitude "0"`.

`robots.txt`: copia literal del robots real de Uribienes (está arriba en la revisión; incluye `Disallow: /?*` y `Disallow: /inmuebles/[0-9]+`).

- [ ] **Step 1: Escribir las pruebas que fallan**

```python
def test_mapear_arriendo(listado: dict[str, Any]) -> None:
    a = mapear_anuncio(listado["data"][0], Operacion.ARRIENDO, FECHA)
    assert (a.fuente, a.id_fuente) == ("uribienes", "220400")
    assert a.url == "https://uribienes.com/inmuebles/220400"
    assert (a.precio, a.administracion, a.area_m2) == (2_500_000, 350_000, 85.0)
    assert (a.habitaciones, a.banos, a.parqueaderos, a.estrato) == (3, 2, 1, 5)
    assert (a.barrio, a.municipio) == ("Laureles", "Medellín")
    assert (a.latitud, a.longitud) == (6.2441, -75.59)


def test_arriendo_venta_toma_el_precio_de_la_operacion(listado: dict[str, Any]) -> None:
    inmueble = listado["data"][1]
    assert mapear_anuncio(inmueble, Operacion.ARRIENDO, FECHA).precio == 1_700_000
    assert mapear_anuncio(inmueble, Operacion.VENTA, FECHA).precio == 250_000_000


def test_ceros_quedan_nulos(listado: dict[str, Any]) -> None:
    a = mapear_anuncio(listado["data"][1], Operacion.ARRIENDO, FECHA)
    assert a.administracion is None and a.area_m2 is None and a.estrato is None
    assert a.latitud is None and a.longitud is None
    assert a.parqueaderos == 0


def test_robots_real_permite_la_api() -> None:
    """El robots de Uribienes prohíbe '/?*'; eso no debe bloquear /api/properties."""
    # respx: /robots.txt responde el fixture; /api/properties responde una página vacía.
    # cliente.get_json("/api/properties", params={"city": 5001, "biz": 1, "page": 1}) no lanza.
```

Pruebas de recorrido con respx:

- `test_recorre_municipios_y_negocios`: `/api/properties` responde una página vacía (`"data": [], "last_page": 1`) salvo para `city=5001&biz=1`, que responde el fixture. Resultado: 2 anuncios de arriendo; se hicieron `len(MUNICIPIOS) * 2` peticiones.
- `test_pagina_hasta_last_page`: `last_page: 3` → 3 peticiones para ese municipio y negocio, con `page` 1, 2 y 3.
- `test_max_paginas`: `last_page: 3`, `max_paginas=1` → 1 petición por municipio y negocio.
- `test_anuncio_invalido_se_omite`: un inmueble sin `codpro` → se omite con `WARNING` y el otro sale.
- `test_registrada_en_cli`.

- [ ] **Step 2: Correr y ver que fallan**

Run: `uv run pytest tests/test_uribienes.py -v`
Expected: FAIL con `ModuleNotFoundError`.

- [ ] **Step 3: Implementar `uribienes.py`**

- `mapear_anuncio`: precio `rent` en arriendo y `saleprice` en venta, con `parsear_precio` (así `0` → `None`); `administracion=parsear_precio(administration)`; `area_m2=parsear_decimal(area_cons)`; `parqueaderos=parsear_entero(parking)`; `estrato=parsear_estrato(stratum)`; coordenadas con `parsear_coordenada`; `id_fuente=str(codpro)` o `None` si falta (pydantic lo rechaza). El modelo ya quita los espacios sobrantes de `city`.
- `_resultados(codigo, biz)`: `params={"city": codigo, "biz": biz, "page": n}`; corta cuando `current_page >= last_page` o al llegar a `max_paginas`.
- `listar_anuncios`: `for biz, operacion in NEGOCIOS.items(): for codigo in MUNICIPIOS: ...`. Un inmueble "ARRIENDO/VENTA" sale una vez por operación, y eso es correcto: son dos ofertas.
- Docstring del módulo: endpoint, filtros y por qué no se piden detalles (robots).

- [ ] **Step 4: Registrar la fuente** (igual que en la Tarea 2).

- [ ] **Step 5: Correr todo y ver que pasa**

Run: `uv run pytest && uv run ruff check . && uv run ruff format --check . && uv run mypy`
Expected: todo en verde.

- [ ] **Step 6: Commit**

```bash
git add src/observatorio_inmobiliario/fuentes/uribienes.py src/observatorio_inmobiliario/fuentes/__init__.py tests/test_uribienes.py tests/fixtures/uribienes
git commit -m "feat: adaptador de Uribienes filtrado al Valle de Aburrá"
```

---

### Task 4: Adaptador de Alnago

**Files:**
- Create: `src/observatorio_inmobiliario/fuentes/alnago.py`
- Modify: `src/observatorio_inmobiliario/fuentes/__init__.py`
- Create: `tests/fixtures/alnago/mapa_arriendo.json`
- Test: `tests/test_alnago.py`

**Interfaces:**
- Consumes: lo mismo que la Tarea 2.
- Produces:
  - `URL_BASE: Final = "https://api.alnago.com"`, `URL_SITIO: Final = "https://alnago.com"`.
  - `MUNICIPIOS: Final[dict[int, str]]` (ids de ciudad del CRM Wasi, sacados de la página `/es/categorias`): `496 "Medellín"`, `89 "Bello"`, `389 "Itagüí"`, `291 "Envigado"`, `698 "Sabaneta"`, `416 "La Estrella"`, `130 "Caldas"`, `219 "Copacabana"`.
  - `FILTROS_OPERACION: Final = {Operacion.ARRIENDO: {"for_rent": "true", "for_sale": "false"}, Operacion.VENTA: {"for_rent": "false", "for_sale": "true"}}`.
  - `TIPOS: Final[dict[int, str]]`, igual al que usa el sitio: `1 casa`, `2 apartamento`, `3 local`, `4 oficina`, `15 oficina`, `5 lote`, `6 lote`, `32 lote`, `7 finca`, `11 finca`, `28 finca`, `8 bodega`, `16 bodega`, `14 apartaestudio`, `26 garaje`. Un id desconocido → `None`.
  - `mapear_anuncio(item: dict[str, Any], operacion: Operacion, municipio: str, fecha: date) -> AnuncioNormalizado`.
  - `class FuenteAlnago` con `nombre = "alnago"` y `__init__(self, cliente, *, con_detalle=True, max_paginas=None, fecha=None)`. `max_paginas` no tiene efecto: la API no pagina (se documenta).

**Fixture** `mapa_arriendo.json`: `{"total": 2, "items": [...]}` con
1. `id_property 10569564`, `lat 6.1512`, `lng -75.6169`, `price 1950000`, `beds 3`, `baths 2`, `area 72.5`, `garages 1`, `zone "María Auxiliadora"`, `id_property_type 2`.
2. `id_property 4283268`, `lat 6.2389`, `lng -75.6004`, `price 0`, `beds 0`, `baths 1`, `area 37.69`, `garages 0`, `zone null`, `id_property_type 99`.

Sin `thumb`.

- [ ] **Step 1: Escribir las pruebas que fallan**

```python
def test_mapear_item(mapa: dict[str, Any]) -> None:
    a = mapear_anuncio(mapa["items"][0], Operacion.ARRIENDO, "Sabaneta", FECHA)
    assert (a.fuente, a.id_fuente) == ("alnago", "10569564")
    assert a.url == "https://alnago.com/es/inmueble/10569564"
    assert (a.tipo_inmueble, a.precio, a.area_m2) == ("apartamento", 1_950_000, 72.5)
    assert (a.habitaciones, a.banos, a.parqueaderos) == (3, 2, 1)
    assert (a.barrio, a.municipio) == ("María Auxiliadora", "Sabaneta")
    assert a.estrato is None and a.administracion is None


def test_precio_cero_barrio_nulo_y_tipo_desconocido(mapa: dict[str, Any]) -> None:
    a = mapear_anuncio(mapa["items"][1], Operacion.VENTA, "Medellín", FECHA)
    assert a.precio is None and a.barrio is None and a.tipo_inmueble is None
```

Pruebas de recorrido con respx:

- `test_una_peticion_por_municipio_y_operacion`: `/property/map` responde `{"total": 0, "items": []}` salvo para `id_city=496&for_rent=true`, que responde el fixture. Resultado: 2 anuncios de arriendo con `municipio == "Medellín"`; `len(MUNICIPIOS) * 2` peticiones, cada una con `for_rent` y `for_sale` opuestos.
- `test_respuesta_sin_items_no_falla`: respuesta `{}` → 0 anuncios, sin excepción.
- `test_anuncio_invalido_se_omite`: un item con `area: -5` → `WARNING` y el otro sale.
- `test_registrada_en_cli`.

- [ ] **Step 2: Correr y ver que fallan**

Run: `uv run pytest tests/test_alnago.py -v`
Expected: FAIL con `ModuleNotFoundError`.

- [ ] **Step 3: Implementar `alnago.py`**

`listar_anuncios`: `for operacion, filtros in FILTROS_OPERACION.items(): for id_ciudad, municipio in MUNICIPIOS.items():` una petición a `/property/map` con `{**filtros, "id_city": id_ciudad}`, y recorre `datos.get("items", [])`. Docstring del módulo con el endpoint, la nota sobre el robots de `alnago.com` frente a `api.alnago.com`, y que no hay estrato.

- [ ] **Step 4: Registrar la fuente** (igual que en la Tarea 2).

- [ ] **Step 5: Correr todo y ver que pasa**

Run: `uv run pytest && uv run ruff check . && uv run ruff format --check . && uv run mypy`
Expected: todo en verde.

- [ ] **Step 6: Commit**

```bash
git add src/observatorio_inmobiliario/fuentes/alnago.py src/observatorio_inmobiliario/fuentes/__init__.py tests/test_alnago.py tests/fixtures/alnago
git commit -m "feat: adaptador de Alnago"
```

---

### Task 5: Corridas reales y README

**Files:**
- Modify: `README.md` (líneas 22-24 y 37)

- [ ] **Step 1: Corrida real de cada fuente**

```bash
uv run observatorio scrape uribienes
uv run observatorio scrape alnago
uv run observatorio scrape nutibara
```

Expected (cifras del 2026-11-11; se aceptan variaciones de unos pocos por ciento):
- `alnago`: 16 peticiones; Medellín ≈ 816 arriendo + 437 venta, más el resto del valle.
- `uribienes`: Medellín ≈ 260 arriendo + 112 venta, más el resto del valle.
- `nutibara`: unos cientos de anuncios, casi todos de Medellín, Envigado, Itagüí, Sabaneta y Bello.

- [ ] **Step 2: Revisar los Parquet**

```python
from pathlib import Path
from observatorio_inmobiliario.almacenamiento import leer_observaciones
df = leer_observaciones(Path("data/crudo"))
print(df.groupby(["fuente", "operacion"]).size())
print(df.groupby("fuente")[["precio", "area_m2", "estrato", "latitud", "barrio"]].count())
print(df[df.fuente == "nutibara"].municipio.value_counts().head(10))
```

Expected: cada fuente con arriendo y venta; Nutibara y Uribienes con estrato en la mayoría de filas; Alnago con estrato en 0 filas; ninguna longitud positiva (sería señal de que se perdió el signo). Si Nutibara tiene inmuebles en un municipio fuera del rectángulo de la cuadrícula, anotarlo para el Plan 4 (no ampliar la cuadrícula sin medirlo).

- [ ] **Step 3: Actualizar el README**

Ejemplos de uso con las cuatro fuentes y la línea "Fuentes disponibles" con `santafe`, `nutibara`, `uribienes` y `alnago` y el nombre de cada inmobiliaria. Las duraciones aproximadas salen de la corrida del Step 1.

- [ ] **Step 4: Verificación completa**

Run: `uv run pre-commit run --all-files && uv run pytest`
Expected: todo en verde.

- [ ] **Step 5: Commit y push**

```bash
git add README.md
git commit -m "docs: fuentes Nutibara, Uribienes y Alnago en el README"
git push
```

Después del push, confirmar que el CI quedó en verde con la API pública de GitHub (`gh` no está instalado).
