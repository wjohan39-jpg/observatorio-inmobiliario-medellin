"""Configuración global del proyecto."""

from typing import Final

from observatorio_inmobiliario import __version__

URL_REPOSITORIO: Final = "https://github.com/wjohan39-jpg/observatorio-inmobiliario-medellin"

USER_AGENT: Final = f"ObservatorioInmobiliarioMedellin/{__version__} (+{URL_REPOSITORIO})"
"""Identifica al scraper ante los sitios y les da un enlace para contactar al proyecto."""

SEGUNDOS_ENTRE_PETICIONES: Final = 1.5
"""Pausa mínima entre dos peticiones al mismo sitio, por cortesía."""
