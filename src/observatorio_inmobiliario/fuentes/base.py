"""Contrato que debe cumplir el adaptador de cada inmobiliaria."""

from collections.abc import Iterator
from typing import Protocol, runtime_checkable

from observatorio_inmobiliario.modelos import AnuncioNormalizado


@runtime_checkable
class Fuente(Protocol):
    """Un sitio de una inmobiliaria del que se extraen anuncios.

    Cada adaptador sabe hablar con su sitio (API JSON o HTML) y entrega los anuncios ya
    convertidos en :class:`AnuncioNormalizado`. El resto del pipeline no necesita saber
    de qué sitio vienen.
    """

    nombre: str
    """Identificador corto de la fuente, p. ej. ``"santafe"``."""

    def listar_anuncios(self) -> Iterator[AnuncioNormalizado]:
        """Recorre el sitio y produce cada anuncio válido que encuentre."""
        ...
