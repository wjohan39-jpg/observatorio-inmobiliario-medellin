"""Autocorrelación espacial de los precios por barrio: Moran global y local (LISA).

Pregunta: ¿los barrios caros están juntos? Si sí, hay un patrón espacial (clústeres); si los
precios se reparten al azar entre barrios vecinos, el índice queda cerca de 0.

* **Vecindad:** dos barrios son vecinos si sus polígonos se tocan (contigüidad «reina»: basta
  con compartir un borde o un vértice). Los pesos se normalizan por fila, así el «rezago» de un
  barrio es el promedio de sus vecinos.
* **Moran global (I):** de −1 a 1 aproximadamente. Positivo, barrios parecidos juntos; negativo,
  barrios distintos juntos (tablero de ajedrez); cerca de 0, sin patrón.
* **Moran local (LISA):** clasifica cada barrio como alto-alto, bajo-bajo (clústeres) o
  alto-bajo, bajo-alto (atípicos espaciales), solo si es significativo.
* **Significancia:** por permutaciones (no supone una distribución), con semilla fija para
  que el resultado sea reproducible. No se corrige por comparaciones múltiples: con muchos
  barrios, algunos clústeres locales pueden salir significativos por azar.
"""

import math
from dataclasses import dataclass
from typing import Any, Final

import numpy as np
from numpy.typing import NDArray
from shapely.geometry import shape
from shapely.strtree import STRtree

PERMUTACIONES: Final = 999
SEMILLA: Final = 46
NIVEL_SIGNIFICANCIA: Final = 0.05
MINIMO_ZONAS: Final = 8
"""Con menos zonas con vecinos, un índice de Moran no tiene sentido."""
TOLERANCIA_BORDE: Final = 1e-5
"""Unos 1,1 m en grados: los bordes digitalizados no siempre coinciden exactamente."""

ALTO_ALTO: Final = "Alto-alto"
BAJO_BAJO: Final = "Bajo-bajo"
ALTO_BAJO: Final = "Alto-bajo"
BAJO_ALTO: Final = "Bajo-alto"
NO_SIGNIFICATIVO: Final = "No significativo"

Vector = NDArray[np.float64]


@dataclass(frozen=True)
class ResultadoMoran:
    """Moran global (``i``, ``esperado`` y ``p``) y local de cada zona."""

    i: float
    esperado: float
    p: float
    rezago: Vector
    local: Vector
    p_local: Vector
    cluster: list[str]


def vecinos_por_contiguidad(geometrias: list[Any]) -> list[list[int]]:
    """Para cada polígono, los índices de los que lo tocan (contigüidad reina)."""
    arbol = STRtree(geometrias)
    vecinos: list[list[int]] = []
    for i, geometria in enumerate(geometrias):
        cercanos = arbol.query(geometria.buffer(TOLERANCIA_BORDE), predicate="intersects")
        vecinos.append(sorted(int(j) for j in cercanos if int(j) != i))
    return vecinos


def geometrias_del_catalogo(geojson: dict[str, Any]) -> tuple[list[str], list[Any]]:
    """Códigos y polígonos válidos de un GeoJSON de barrios, en el mismo orden."""
    codigos: list[str] = []
    geometrias: list[Any] = []
    for elemento in geojson.get("features", []):
        geometria = shape(elemento["geometry"])
        if not geometria.is_valid:
            geometria = geometria.buffer(0)
        codigos.append(str(elemento["properties"]["codigo"]))
        geometrias.append(geometria)
    return codigos, geometrias


def _pesos(vecinos: list[list[int]]) -> NDArray[np.float64]:
    """Matriz de pesos normalizada por fila (cada fila suma 1; sin vecinos, ceros)."""
    n = len(vecinos)
    pesos = np.zeros((n, n))
    for i, lista in enumerate(vecinos):
        if lista:
            pesos[i, lista] = 1.0 / len(lista)
    return pesos


def _cluster(z: float, rezago: float, p: float) -> str:
    if p >= NIVEL_SIGNIFICANCIA:
        return NO_SIGNIFICATIVO
    if z > 0:
        return ALTO_ALTO if rezago > 0 else ALTO_BAJO
    return BAJO_ALTO if rezago > 0 else BAJO_BAJO


def moran(
    valores: Vector,
    vecinos: list[list[int]],
    permutaciones: int = PERMUTACIONES,
    semilla: int = SEMILLA,
) -> ResultadoMoran:
    """Moran global y local de ``valores``, con ``vecinos`` ya restringidos a las mismas zonas.

    Todas las zonas deben tener al menos un vecino (quita antes las islas).
    """
    n = len(valores)
    z = valores - valores.mean()
    suma_cuadrados = float(z @ z)
    pesos = _pesos(vecinos)
    rezago = pesos @ z
    esperado = -1.0 / (n - 1)
    if suma_cuadrados == 0.0:
        return ResultadoMoran(
            0.0, esperado, 1.0, rezago, np.zeros(n), np.ones(n), [NO_SIGNIFICATIVO] * n
        )
    azar = np.random.default_rng(semilla)

    global_i = float(z @ rezago) / suma_cuadrados
    permutados = np.array([azar.permutation(z) for _ in range(permutaciones)])
    simulados = ((permutados @ pesos.T) * permutados).sum(axis=1) / suma_cuadrados
    extremos = int((np.abs(simulados - esperado) >= abs(global_i - esperado)).sum())
    p_global = (extremos + 1) / (permutaciones + 1)

    m2 = suma_cuadrados / n
    local = z * rezago / m2
    p_local = np.ones(n)
    for i in range(n):
        otros = np.delete(z, i)
        k = len(vecinos[i])
        elegidos = azar.random((permutaciones, n - 1)).argsort(axis=1)[:, :k]
        simulado = z[i] * otros[elegidos].mean(axis=1) / m2
        p_local[i] = ((np.abs(simulado) >= abs(local[i])).sum() + 1) / (permutaciones + 1)
    clusteres = [_cluster(float(z[i]), float(rezago[i]), float(p_local[i])) for i in range(n)]
    return ResultadoMoran(global_i, esperado, p_global, rezago, local, p_local, clusteres)


def sin_islas(vecinos: list[list[int]], activas: list[int]) -> tuple[list[int], list[list[int]]]:
    """Restringe la vecindad a las zonas ``activas`` y quita las que quedan sin vecinos.

    Devuelve los índices que se conservan y la lista de vecinos con índices relativos a ellos.
    """
    conjunto = set(activas)
    restringidos = {i: [j for j in vecinos[i] if j in conjunto] for i in activas}
    conservadas = [i for i in activas if restringidos[i]]
    posicion = {indice: orden for orden, indice in enumerate(conservadas)}
    nuevos = [[posicion[j] for j in restringidos[i] if j in posicion] for i in conservadas]
    return conservadas, nuevos


RADIO_TIERRA_KM: Final = 6371.0088


def centroides(geojson: dict[str, Any]) -> dict[str, tuple[float, float]]:
    """``codigo -> (latitud, longitud)`` del centroide de cada polígono."""
    codigos, geometrias = geometrias_del_catalogo(geojson)
    return {
        codigo: (float(g.centroid.y), float(g.centroid.x))
        for codigo, g in zip(codigos, geometrias, strict=True)
    }


def distancia_km(lat_a: float, lon_a: float, lat_b: float, lon_b: float) -> float:
    """Distancia en línea recta (haversine) entre dos puntos, en kilómetros."""
    fi_a, fi_b = math.radians(lat_a), math.radians(lat_b)
    delta_fi = fi_b - fi_a
    delta_lambda = math.radians(lon_b - lon_a)
    h = (
        math.sin(delta_fi / 2) ** 2
        + math.cos(fi_a) * math.cos(fi_b) * math.sin(delta_lambda / 2) ** 2
    )
    return 2 * RADIO_TIERRA_KM * math.asin(math.sqrt(h))
