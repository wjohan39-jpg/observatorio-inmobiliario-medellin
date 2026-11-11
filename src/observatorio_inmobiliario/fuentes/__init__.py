"""Adaptadores de cada inmobiliaria y registro para crearlos por nombre."""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from observatorio_inmobiliario.fuentes import (
    activourbano,
    alnago,
    maxibienes,
    nutibara,
    puertabierta,
    santafe,
    uribienes,
)
from observatorio_inmobiliario.fuentes.base import Fuente
from observatorio_inmobiliario.http import ClienteCortes

__all__ = ["REGISTRO", "Fuente", "RegistroFuente", "crear_fuente"]


@dataclass(frozen=True)
class RegistroFuente:
    """Lo necesario para crear una fuente: el sitio al que se conecta y su adaptador.

    ``timeout`` y ``max_intentos`` se ajustan por sitio: algunos servidores son lentos.
    """

    url_base: str
    crear: Callable[..., Fuente]
    timeout: float = 30.0
    max_intentos: int = 3


REGISTRO: dict[str, RegistroFuente] = {
    santafe.FuenteSantaFe.nombre: RegistroFuente(santafe.URL_BASE, santafe.FuenteSantaFe),
    nutibara.FuenteNutibara.nombre: RegistroFuente(nutibara.URL_BASE, nutibara.FuenteNutibara),
    uribienes.FuenteUribienes.nombre: RegistroFuente(uribienes.URL_BASE, uribienes.FuenteUribienes),
    alnago.FuenteAlnago.nombre: RegistroFuente(alnago.URL_BASE, alnago.FuenteAlnago),
    puertabierta.FuentePuertabierta.nombre: RegistroFuente(
        puertabierta.URL_BASE, puertabierta.FuentePuertabierta
    ),
    # El servidor de Maxibienes a veces tarda más de 30 s en una página.
    maxibienes.FuenteMaxibienes.nombre: RegistroFuente(
        maxibienes.URL_BASE, maxibienes.FuenteMaxibienes, timeout=90.0, max_intentos=5
    ),
    activourbano.FuenteActivoUrbano.nombre: RegistroFuente(
        activourbano.URL_BASE, activourbano.FuenteActivoUrbano
    ),
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
    with ClienteCortes(
        registro.url_base, timeout=registro.timeout, max_intentos=registro.max_intentos
    ) as cliente:
        yield registro.crear(cliente, **opciones)
