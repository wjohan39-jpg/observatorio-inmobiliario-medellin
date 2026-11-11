"""Herramientas comunes para leer páginas HTML.

Algunos sitios declaran una codificación y envían otra: Maxibienes dice UTF-8 y manda cp1252,
y Panorama no declara ninguna. Por eso las páginas se piden como bytes
(:meth:`ClienteCortes.get_bytes`) y se decodifican con :func:`decodificar`.
"""

from selectolax.lexbor import LexborHTMLParser, LexborNode


def decodificar(contenido: bytes) -> str:
    """Texto de una página: UTF-8 si es válido; si no, cp1252 (Windows, Latinoamérica).

    >>> decodificar("Itagüí".encode("cp1252"))
    'Itagüí'
    """
    try:
        return contenido.decode("utf-8")
    except UnicodeDecodeError:
        return contenido.decode("cp1252", errors="replace")


def analizar(html: str) -> LexborHTMLParser:
    """Árbol HTML para buscar con selectores CSS. Tolera HTML mal formado."""
    return LexborHTMLParser(html)


def texto(nodo: LexborNode | None) -> str | None:
    """Texto del nodo sin espacios sobrantes, o ``None`` si el nodo no existe o está vacío."""
    if nodo is None:
        return None
    return " ".join(nodo.text().split()) or None
