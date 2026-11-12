"""Reputación de las inmobiliarias con la API oficial de Google Places (pregunta 5).

Reglas del spec §7.2:

* Solo se pide la calificación y el número de reseñas (``rating,userRatingCount``). Sin el
  texto de las reseñas, la consulta queda en el nivel de precio más barato de Place Details.
* **Nada se guarda en disco**: los términos de Google no lo permiten. El dashboard consulta en
  vivo y guarda la respuesta en memoria unas horas. Lo único que se guarda es el ``place_id``
  de cada sede, en ``datos_referencia/sedes_google.csv``.
* Si una inmobiliaria tiene varias sedes, se suman las reseñas y la calificación es el
  promedio ponderado por número de reseñas.
* La clave se lee de ``GOOGLE_PLACES_API_KEY`` y nunca aparece en registros ni mensajes.

También calcula el **indicador de reconocimiento** (pregunta 6): el promedio de anuncios,
barrios cubiertos y reseñas, cada uno dividido por el máximo entre las inmobiliarias.
"""

import logging
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import httpx
import pandas as pd

from observatorio_inmobiliario.tablero.datos import RAIZ

logger = logging.getLogger(__name__)

URL_DETALLE: Final = "https://places.googleapis.com/v1/places/{place_id}"
URL_BUSQUEDA: Final = "https://places.googleapis.com/v1/places:searchText"
CAMPOS: Final = "rating,userRatingCount"
CAMPOS_BUSQUEDA: Final = "places.id,places.displayName,places.formattedAddress"
TIEMPO_ESPERA_S: Final = 10.0
VARIABLE_CLAVE: Final = "GOOGLE_PLACES_API_KEY"
SEDES: Final = RAIZ / "datos_referencia" / "sedes_google.csv"
CENTRO_MEDELLIN: Final = {"latitude": 6.245, "longitude": -75.58}
RADIO_BUSQUEDA_M: Final = 20_000.0
"""Las búsquedas prefieren resultados a 20 km del centro: cubre el Valle de Aburrá."""
COLUMNAS_SEDES: Final = ["fuente", "sede", "place_id"]
COLUMNAS_REPUTACION: Final = ["fuente", "sedes", "resenas", "calificacion"]


@dataclass(frozen=True)
class Reseñas:
    """Calificación promedio (1 a 5) y número de reseñas de una sede en Google."""

    calificacion: float | None
    total: int


SIN_RESENAS: Final = Reseñas(None, 0)


def clave_api() -> str | None:
    """La clave de Google Places del entorno, o ``None`` si no está configurada."""
    clave = os.environ.get(VARIABLE_CLAVE, "").strip()
    return clave or None


def cargar_sedes(ruta: Path | None = None) -> pd.DataFrame:
    """Las sedes de cada inmobiliaria en Google: ``fuente, sede, place_id``."""
    sedes = pd.read_csv(ruta or SEDES, dtype="string")
    return sedes[COLUMNAS_SEDES]


def _cabeceras(clave: str, campos: str) -> dict[str, str]:
    return {"X-Goog-Api-Key": clave, "X-Goog-FieldMask": campos}


def consultar_sede(cliente: httpx.Client, place_id: str, clave: str) -> Reseñas:
    """Calificación y reseñas de una sede. Ante cualquier error devuelve "sin reseñas".

    Un error no detiene el dashboard: la sede cuenta como 0 reseñas y se registra un aviso
    con el ``place_id``, nunca con la clave.
    """
    try:
        respuesta = cliente.get(
            URL_DETALLE.format(place_id=place_id),
            headers=_cabeceras(clave, CAMPOS),
            timeout=TIEMPO_ESPERA_S,
        )
        respuesta.raise_for_status()
        datos: dict[str, Any] = respuesta.json()
    except httpx.HTTPStatusError as error:
        logger.warning("Google Places respondió %s para %s", error.response.status_code, place_id)
        return SIN_RESENAS
    except (httpx.HTTPError, ValueError) as error:
        logger.warning("Google Places falló para %s: %s", place_id, type(error).__name__)
        return SIN_RESENAS

    total = datos.get("userRatingCount")
    calificacion = datos.get("rating")
    if not isinstance(total, int) or total <= 0:
        return SIN_RESENAS
    return Reseñas(float(calificacion) if isinstance(calificacion, int | float) else None, total)


def reputacion(sedes: pd.DataFrame, consultar: Callable[[str], Reseñas]) -> pd.DataFrame:
    """Reseñas y calificación ponderada por inmobiliaria.

    ``consultar`` recibe un ``place_id``. Así se prueba sin red, y el dashboard le pasa una
    función con caché.
    """
    filas = []
    for fuente, de_la_fuente in sedes.groupby("fuente", sort=True):
        resenas = [consultar(str(p)) for p in de_la_fuente["place_id"]]
        total = sum(r.total for r in resenas)
        ponderada = sum(r.calificacion * r.total for r in resenas if r.calificacion is not None)
        con_calificacion = sum(r.total for r in resenas if r.calificacion is not None)
        filas.append(
            {
                "fuente": fuente,
                "sedes": len(resenas),
                "resenas": total,
                "calificacion": ponderada / con_calificacion if con_calificacion else None,
            }
        )
    tabla = pd.DataFrame(filas, columns=COLUMNAS_REPUTACION)
    return tabla.astype(
        {"fuente": "string", "sedes": "Int64", "resenas": "Int64", "calificacion": "float64"}
    )


def buscar_sedes(cliente: httpx.Client, texto: str, clave: str) -> list[dict[str, str]]:
    """Candidatos de Google para ``texto`` (Text Search), para elegir los ``place_id`` a mano."""
    cuerpo = {
        "textQuery": texto,
        "languageCode": "es",
        "locationBias": {"circle": {"center": CENTRO_MEDELLIN, "radius": RADIO_BUSQUEDA_M}},
    }
    respuesta = cliente.post(
        URL_BUSQUEDA,
        json=cuerpo,
        headers=_cabeceras(clave, CAMPOS_BUSQUEDA),
        timeout=TIEMPO_ESPERA_S,
    )
    respuesta.raise_for_status()
    lugares: list[dict[str, Any]] = respuesta.json().get("places", [])
    return [
        {
            "id": str(lugar.get("id", "")),
            "nombre": str(lugar.get("displayName", {}).get("text", "")),
            "direccion": str(lugar.get("formattedAddress", "")),
        }
        for lugar in lugares
    ]


def reconocimiento(cobertura: pd.DataFrame, reputacion: pd.DataFrame | None) -> pd.DataFrame:
    """Indicador de reconocimiento por inmobiliaria (pregunta 6), de 0 a 1.

    Promedio de anuncios, barrios cubiertos y reseñas en Google, cada uno dividido por el
    máximo entre las inmobiliarias. Sin datos de Google (``reputacion`` vacía o sin reseñas),
    se promedian solo los dos primeros y ``con_resenas`` queda en False.
    """
    tabla = cobertura.loc[cobertura["operacion"] == "todas", ["fuente", "anuncios", "barrios"]]
    resenas = (
        reputacion.set_index("fuente")["resenas"]
        if reputacion is not None and not reputacion.empty
        else pd.Series(dtype="Int64")
    )
    tabla = tabla.assign(resenas=tabla["fuente"].map(resenas).fillna(0).astype("Int64"))
    con_resenas = bool(tabla["resenas"].sum() > 0)
    componentes = ["anuncios", "barrios", *(["resenas"] if con_resenas else [])]
    normalizado = pd.DataFrame(
        {c: tabla[c].astype("float64") / max(float(tabla[c].max()), 1.0) for c in componentes}
    )
    tabla = tabla.assign(indice=normalizado.mean(axis=1).round(3), con_resenas=con_resenas)
    tabla = tabla.sort_values("indice", ascending=False)
    return tabla[["fuente", "anuncios", "barrios", "resenas", "indice", "con_resenas"]].reset_index(
        drop=True
    )
