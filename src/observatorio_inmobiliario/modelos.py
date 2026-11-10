"""Modelo de datos común para los anuncios de todas las inmobiliarias.

Cada adaptador de fuente convierte lo que publica su sitio en un
:class:`AnuncioNormalizado`. Así, el resto del pipeline (limpieza, análisis,
dashboard) trabaja con una sola forma de dato, sin importar de dónde vino.
"""

from datetime import date
from enum import StrEnum
from typing import Annotated

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
)


class Operacion(StrEnum):
    """Tipo de negocio del anuncio."""

    VENTA = "venta"
    ARRIENDO = "arriendo"


def _texto_vacio_a_none(valor: object) -> object:
    """Quita espacios sobrantes y convierte un texto vacío en ``None``."""
    if isinstance(valor, str):
        return valor.strip() or None
    return valor


def _a_minusculas(valor: str | None) -> str | None:
    return None if valor is None else valor.lower()


type TextoObligatorio = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
type TextoOpcional = Annotated[str | None, BeforeValidator(_texto_vacio_a_none)]
type ConteoOpcional = Annotated[int | None, Field(ge=0, le=50)]


class AnuncioNormalizado(BaseModel):
    """Un anuncio inmobiliario observado en una fecha, con datos de hecho validados.

    Por diseño solo contiene datos de hecho. No incluye fotos, descripciones ni datos
    de contacto, y ``extra="forbid"`` rechaza cualquier campo que no esté definido aquí.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    # --- Identificación
    fuente: TextoObligatorio
    """Identificador corto de la inmobiliaria scrapeada, p. ej. ``"santafe"``."""
    id_fuente: TextoObligatorio
    """Código del anuncio dentro de su sitio."""
    url: TextoOpcional = None
    fecha_observacion: date
    """Día en que el scraper vio el anuncio."""

    # --- Negocio
    operacion: Operacion
    tipo_inmueble: Annotated[TextoOpcional, AfterValidator(_a_minusculas)] = None
    precio: Annotated[int | None, Field(gt=0)] = None
    """Pesos colombianos (COP). Es mensual en arriendo y total en venta."""
    administracion: Annotated[int | None, Field(ge=0)] = None
    """Cuota de administración mensual en COP."""

    # --- Características
    area_m2: Annotated[float | None, Field(gt=0, lt=100_000)] = None
    habitaciones: ConteoOpcional = None
    banos: ConteoOpcional = None
    parqueaderos: ConteoOpcional = None
    estrato: Annotated[int | None, Field(ge=1, le=6)] = None

    # --- Ubicación
    barrio: TextoOpcional = None
    """Barrio tal como lo publica la fuente. Se normaliza en una etapa posterior."""
    municipio: TextoOpcional = None
    latitud: Annotated[float | None, Field(ge=-90, le=90)] = None
    longitud: Annotated[float | None, Field(ge=-180, le=180)] = None

    # --- Inventario compartido
    anunciante_origen: TextoOpcional = None
    """Inmobiliaria que originó el anuncio, si la fuente lo publica (p. ej. inventario MLS)."""
