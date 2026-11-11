"""Adaptadores de cada inmobiliaria y registro para crearlos por nombre."""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from observatorio_inmobiliario.fuentes import alnago, nutibara, santafe, uribienes
from observatorio_inmobiliario.fuentes.base import Fuente
from observatorio_inmobiliario.http import ClienteCortes

__all__ = ["REGISTRO", "Fuente", "RegistroFuente", "crear_fuente"]


@dataclass(frozen=True)
class RegistroFuente:
    """Lo necesario para crear una fuente: el sitio al que se conecta y su adaptador."""

    url_base: str
    crear: Callable[..., Fuente]


REGISTRO: dict[str, RegistroFuente] = {
    santafe.FuenteSantaFe.nombre: RegistroFuente(santafe.URL_BASE, santafe.FuenteSantaFe),
    nutibara.FuenteNutibara.nombre: RegistroFuente(nutibara.URL_BASE, nutibara.FuenteNutibara),
    uribienes.FuenteUribienes.nombre: RegistroFuente(uribienes.URL_BASE, uribienes.FuenteUribienes),
    alnago.FuenteAlnago.nombre: RegistroFuente(alnago.URL_BASE, alnago.FuenteAlnago),
}


@contextmanager
def crear_fuente(nombre: str, **opciones: Any) -> Iterator[Fuente]:
    """Crea la fuente ``nombre`` con su propio cliente HTTP y lo cierra al terminar::

    with crear_fuente("santafe", max_paginas=1) as fuente:
        for anuncio in fuente.listar_anuncios():
            ...
    """
    registro = REGISTRO.get(nombre)
    if registro is None:
        disponibles = ", ".join(sorted(REGISTRO))
        raise ValueError(f"Fuente desconocida {nombre!r}. Disponibles: {disponibles}")
    with ClienteCortes(registro.url_base) as cliente:
        yield registro.crear(cliente, **opciones)
