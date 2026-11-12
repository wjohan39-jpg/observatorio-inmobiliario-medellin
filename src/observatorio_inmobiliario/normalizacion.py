"""Normalización de textos, municipios y tipos de inmueble.

Cada inmobiliaria escribe a su manera: "MEDELLIN", "Medellín" o "medellin "; "apto loft",
"casa-local" o "comercial (casa para comercio)". Estas funciones llevan esas variantes a
una sola forma, para poder comparar y agrupar.

>>> normalizar_texto("Manrique Central No. 1")
'manrique central 1'
>>> normalizar_municipio("MEDELLIN")
'Medellín'
>>> normalizar_tipo("apto loft")
'apartaestudio'
"""

import re
import unicodedata
from typing import Final

MUNICIPIOS_VALLE: Final = frozenset(
    {
        "Medellín",
        "Bello",
        "Itagüí",
        "Envigado",
        "Sabaneta",
        "La Estrella",
        "Caldas",
        "Copacabana",
        "Girardota",
        "Barbosa",
    }
)
"""Los 10 municipios del Valle de Aburrá, con su nombre oficial."""

TIPOS: Final = (
    "apartamento",
    "apartaestudio",
    "casa",
    "local",
    "oficina",
    "consultorio",
    "bodega",
    "lote",
    "finca",
    "parqueadero",
    "edificio",
    "otro",
)
"""Conjunto cerrado de tipos de inmueble después de normalizar."""

_REGLAS_TIPO: Final = (
    (("apartaestudio", "loft"), "apartaestudio"),
    (("local", "comercial"), "local"),
    (("oficina",), "oficina"),
    (("consultorio",), "consultorio"),
    (("finca", "campestre"), "finca"),
    (("lote", "terreno"), "lote"),
    (("casa",), "casa"),
    (("apartamento", "apto", "penthouse"), "apartamento"),
    (("bodega",), "bodega"),
    (("parqueadero", "garaje"), "parqueadero"),
    (("edificio", "hotel"), "edificio"),
)
"""Se aplica la primera regla que coincide; el orden resuelve los tipos mixtos
("casa-local" es un local, "casa-finca" es una finca)."""

_NUMERO: Final = re.compile(r"\bno\.?\s*(?=\d)")
_NO_ALFANUMERICO: Final = re.compile(r"[^a-z0-9]+")


def normalizar_texto(texto: str) -> str:
    """Minúsculas, sin tildes ni puntuación, con espacios simples y "No. 1" → "1"."""
    sin_tildes = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    minusculas = _NUMERO.sub("", sin_tildes.lower())
    return _NO_ALFANUMERICO.sub(" ", minusculas).strip()


CORREGIMIENTOS_MEDELLIN: Final = frozenset(
    {"Santa Elena", "San Antonio de Prado", "San Cristóbal", "Altavista", "Palmitas"}
)
"""Zona rural de Medellín. Algunas fuentes los ponen como si fueran municipios."""

_MUNICIPIOS_POR_CLAVE: Final = {
    **{normalizar_texto(c): "Medellín" for c in CORREGIMIENTOS_MEDELLIN},
    **{normalizar_texto(m): m for m in MUNICIPIOS_VALLE},
}


def normalizar_municipio(texto: str | None) -> str | None:
    """Nombre oficial si es del valle; si no, el texto con mayúsculas normales.

    Un corregimiento de Medellín ("Santa Elena") devuelve "Medellín".
    """
    if texto is None or not texto.strip():
        return None
    return _MUNICIPIOS_POR_CLAVE.get(normalizar_texto(texto), texto.strip().title())


def normalizar_tipo(texto: str | None) -> str:
    """Uno de :data:`TIPOS`; ``"otro"`` si no se reconoce."""
    clave = normalizar_texto(texto or "")
    for palabras, tipo in _REGLAS_TIPO:
        if any(palabra in clave for palabra in palabras):
            return tipo
    return "otro"
