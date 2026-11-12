"""Catálogo oficial de barrios y comunas de Medellín, para ubicar cada anuncio.

La fuente es la capa "Limite Barrio_Vereda Catastral" del servidor de mapas de la Alcaldía
de Medellín: 349 polígonos (barrios urbanos y veredas de los corregimientos), cada uno con
su código de 4 dígitos, cuyos dos primeros son la comuna. Se guarda en
``datos_referencia/barrios_medellin.geojson`` y se actualiza con ``observatorio catalogo``.

Hay dos formas de ubicar un anuncio:

* **Por coordenadas** (la más confiable): el barrio cuyo polígono contiene el punto.
* **Por nombre**: el texto del barrio que publica la inmobiliaria. Los nombres de zona
  ("Poblado", "Laureles", "Belén") son coloquiales y abarcan muchos barrios oficiales; el
  archivo de alias los lleva solo hasta la comuna, sin inventar un barrio.
"""

import csv
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Self

from shapely import STRtree
from shapely.geometry import Point, shape

from observatorio_inmobiliario.http import ClienteCortes
from observatorio_inmobiliario.normalizacion import normalizar_texto

URL_BASE_CATALOGO: Final = "https://www.medellin.gov.co"
RUTA_CATALOGO: Final = (
    "/servidormapas/rest/services/ServiciosCatastro/Base_Catastral/MapServer/1/query"
)
RUTA_GEOJSON: Final = Path("datos_referencia/barrios_medellin.geojson")
RUTA_ALIAS: Final = Path("datos_referencia/alias_barrios.csv")

PARAMETROS_CATALOGO: Final = {
    "where": "1=1",
    "outFields": "codigo,nombre_barrio,comuna,nombre_comuna,indicador_ur",
    "outSR": "4326",  # latitud y longitud (WGS84), como las de los anuncios
    "geometryPrecision": "5",  # ~1 m
    "maxAllowableOffset": "0.0001",  # simplifica los bordes a ~11 m: el archivo queda < 500 KB
    "f": "geojson",
}
MINIMO_POLIGONOS: Final = 300
"""Una descarga con menos polígonos se considera incompleta (el catálogo tiene 349)."""

_ARTICULO: Final = re.compile(r"^(el|la|los|las) ")
_PREFIJO: Final = re.compile(r"^(barrio|urbanizacion|urb|sector) ")


@dataclass(frozen=True)
class Ubicacion:
    """Dónde queda un anuncio dentro de Medellín."""

    codigo_barrio: str | None
    """Código oficial de 4 dígitos, p. ej. ``"1418"``; ``None`` si solo se conoce la comuna."""
    barrio: str | None
    """Nombre oficial, p. ej. ``"El Poblado"``."""
    comuna: str
    """Código de 2 dígitos: 01–16 urbanas; 50, 60, 70, 80 y 90 corregimientos."""
    nombre_comuna: str
    metodo: str
    """``"coordenadas"``, ``"nombre"`` o ``"alias"``."""


@dataclass(frozen=True)
class _Barrio:
    codigo: str
    nombre: str
    comuna: str
    nombre_comuna: str
    urbano: bool

    def ubicacion(self, metodo: str) -> Ubicacion:
        return Ubicacion(self.codigo, self.nombre, self.comuna, self.nombre_comuna, metodo)


def descargar_catalogo(cliente: ClienteCortes) -> dict[str, Any]:
    """Descarga el catálogo completo en GeoJSON con una sola petición.

    Lanza ``ValueError`` si la respuesta no es una colección con al menos
    :data:`MINIMO_POLIGONOS` polígonos.
    """
    geojson: dict[str, Any] = {}
    respuesta = cliente.get_json(RUTA_CATALOGO, params=PARAMETROS_CATALOGO)
    if isinstance(respuesta, dict):
        geojson = respuesta
    features = geojson.get("features")
    if geojson.get("type") != "FeatureCollection" or not isinstance(features, list):
        raise ValueError("La respuesta del catálogo no es una colección GeoJSON")
    if len(features) < MINIMO_POLIGONOS:
        raise ValueError(f"El catálogo trajo {len(features)} polígonos; se esperaban 349")
    return geojson


def _claves(nombre: str) -> set[str]:
    """El nombre normalizado, y también sin su artículo inicial si lo tiene."""
    clave = normalizar_texto(nombre)
    return {clave, _ARTICULO.sub("", clave)}


class Catalogo:
    """Barrios oficiales indexados por polígono y por nombre."""

    def __init__(self, barrios: list[_Barrio], poligonos: list[Any], alias: dict[str, str]):
        orden = sorted(range(len(barrios)), key=lambda i: barrios[i].codigo)
        self._barrios = [barrios[i] for i in orden]
        # El árbol devuelve índices; al ordenar por código, el menor índice es el menor código.
        self._arbol = STRtree([poligonos[i] for i in orden])
        self._por_codigo = {b.codigo: b for b in self._barrios}
        self._comunas = {b.comuna: b.nombre_comuna for b in self._barrios}
        self._por_nombre: dict[str, list[_Barrio]] = {}
        for barrio in self._barrios:
            for clave in _claves(barrio.nombre):
                self._por_nombre.setdefault(clave, []).append(barrio)
        self._comunas_por_nombre = {
            clave: comuna
            for comuna, nombre in self._comunas.items()
            if comuna <= "16"  # solo las comunas urbanas
            for clave in _claves(nombre)
        }
        self._alias: dict[str, Ubicacion] = {}
        for texto, codigo in alias.items():
            self._alias[normalizar_texto(texto)] = self._ubicacion_alias(texto, codigo)

    @classmethod
    def cargar(cls, ruta_geojson: Path = RUTA_GEOJSON, ruta_alias: Path = RUTA_ALIAS) -> Self:
        """Lee el GeoJSON y el CSV de alias (columnas ``alias,codigo``).

        Lanza ``ValueError`` si un alias apunta a un barrio o comuna que no existe.
        """
        geojson = json.loads(ruta_geojson.read_text(encoding="utf-8"))
        barrios: list[_Barrio] = []
        poligonos: list[Any] = []
        for feature in geojson["features"]:
            p = feature["properties"]
            barrios.append(
                _Barrio(
                    codigo=p["codigo"],
                    nombre=p["nombre_barrio"],
                    comuna=p["comuna"],
                    nombre_comuna=p["nombre_comuna"],
                    urbano=p["indicador_ur"] == "U",
                )
            )
            poligonos.append(shape(feature["geometry"]))
        with ruta_alias.open(encoding="utf-8", newline="") as archivo:
            alias = {fila["alias"]: fila["codigo"] for fila in csv.DictReader(archivo)}
        return cls(barrios, poligonos, alias)

    def __len__(self) -> int:
        return len(self._barrios)

    def _ubicacion_alias(self, texto: str, codigo: str) -> Ubicacion:
        if codigo in self._por_codigo:
            return self._por_codigo[codigo].ubicacion("alias")
        if codigo in self._comunas:
            return Ubicacion(None, None, codigo, self._comunas[codigo], "alias")
        raise ValueError(f"El alias {texto!r} apunta a {codigo!r}, que no está en el catálogo")

    def por_coordenadas(self, latitud: float, longitud: float) -> Ubicacion | None:
        """El barrio que contiene el punto (el de menor código si cae en un borde)."""
        # shapely usa (x, y) = (longitud, latitud). "intersects" incluye los bordes.
        indices = self._arbol.query(Point(longitud, latitud), predicate="intersects")
        if len(indices) == 0:
            return None
        return self._barrios[int(min(indices))].ubicacion("coordenadas")

    def por_nombre(self, texto: str | None) -> Ubicacion | None:
        """Ubica por el nombre que publica la inmobiliaria; ``None`` si no hay certeza."""
        clave = normalizar_texto(texto or "")
        if not clave:
            return None
        if clave in self._alias:
            return self._alias[clave]
        barrio = self._unico(clave) or self._unico(_PREFIJO.sub("", clave))
        if barrio is None:
            barrio = self._con_prefijo_de_comuna(clave)
        if barrio is not None:
            return barrio.ubicacion("nombre")
        return self._comuna_del_prefijo(clave)

    def _unico(self, clave: str, comuna: str | None = None) -> _Barrio | None:
        """El barrio con ese nombre; si hay varios, el único urbano. Si no, ``None``."""
        candidatos = [
            b for b in self._por_nombre.get(clave, []) if comuna is None or b.comuna == comuna
        ]
        if len(candidatos) > 1:
            candidatos = [b for b in candidatos if b.urbano]
        return candidatos[0] if len(candidatos) == 1 else None

    def _comuna_del_prefijo(self, clave: str) -> Ubicacion | None:
        """Un sector que empieza con el nombre de una comuna ("belen parque") da solo esa comuna."""
        for nombre, comuna in self._comunas_por_nombre.items():
            if clave.startswith(nombre + " "):
                return Ubicacion(None, None, comuna, self._comunas[comuna], "alias")
        return None

    def _con_prefijo_de_comuna(self, clave: str) -> _Barrio | None:
        """Busca "belen san bernardo" como San Bernardo, solo dentro de la comuna Belén."""
        for nombre, comuna in self._comunas_por_nombre.items():
            if clave.startswith(nombre + " "):
                barrio = self._unico(clave.removeprefix(nombre + " "), comuna)
                if barrio is not None:
                    return barrio
        return None
