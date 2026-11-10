"""Comando ``observatorio``: punto de entrada del scraper desde la terminal.

Uso::

    observatorio scrape santafe                     # corrida completa
    observatorio scrape santafe --max-paginas 2     # corrida corta de prueba
"""

import argparse
import logging
import sys
from collections.abc import Sequence
from pathlib import Path

from observatorio_inmobiliario.almacenamiento import guardar_observaciones
from observatorio_inmobiliario.fuentes import REGISTRO, crear_fuente
from observatorio_inmobiliario.http import ErrorDeDescarga, ErrorRutaBloqueadaPorRobots
from observatorio_inmobiliario.modelos import AnuncioNormalizado

logger = logging.getLogger(__name__)

SALIDA_POR_DEFECTO = Path("data/crudo")
CADA_CUANTOS_REPORTAR = 100
"""Cada cuántos anuncios se registra el avance, para seguir corridas largas."""


def _entero_positivo(texto: str) -> int:
    try:
        valor = int(texto)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{texto!r} no es un número entero") from None
    if valor < 1:
        raise argparse.ArgumentTypeError("debe ser 1 o más")
    return valor


def _crear_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="observatorio",
        description="Observatorio inmobiliario de Medellín.",
    )
    comandos = parser.add_subparsers(dest="comando", required=True, metavar="COMANDO")

    scrape = comandos.add_parser(
        "scrape",
        help="descarga los anuncios de una fuente y los guarda en Parquet",
        description="Descarga los anuncios de una inmobiliaria y los guarda en Parquet.",
    )
    scrape.add_argument("fuente", choices=sorted(REGISTRO), help="inmobiliaria a descargar")
    scrape.add_argument(
        "--salida",
        type=Path,
        default=SALIDA_POR_DEFECTO,
        help=f"carpeta de los datos crudos (por defecto: {SALIDA_POR_DEFECTO})",
    )
    scrape.add_argument(
        "--sin-detalle",
        action="store_true",
        help="no pide el detalle de cada anuncio: es más rápido, pero sin estrato ni parqueaderos",
    )
    scrape.add_argument(
        "--max-paginas",
        type=_entero_positivo,
        default=None,
        metavar="N",
        help="páginas por tipo de oferta como máximo; útil para pruebas",
    )
    return parser


def _scrape(fuente: str, salida: Path, *, con_detalle: bool, max_paginas: int | None) -> int:
    anuncios: list[AnuncioNormalizado] = []
    try:
        with crear_fuente(fuente, con_detalle=con_detalle, max_paginas=max_paginas) as origen:
            for anuncio in origen.listar_anuncios():
                anuncios.append(anuncio)
                if len(anuncios) % CADA_CUANTOS_REPORTAR == 0:
                    logger.info("%s: %d anuncios descargados...", fuente, len(anuncios))
    except (ErrorDeDescarga, ErrorRutaBloqueadaPorRobots) as error:
        # No se guarda una corrida incompleta: sobrescribiría el archivo bueno de la semana.
        print(f"{fuente}: la descarga falló y no se guardó nada ({error})", file=sys.stderr)
        return 1

    if not anuncios:
        print(f"{fuente}: 0 anuncios; puede que el sitio haya cambiado", file=sys.stderr)
        return 1

    rutas = guardar_observaciones(anuncios, salida)
    print(f"{fuente}: {len(anuncios)} anuncios guardados en {', '.join(map(str, rutas))}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Ejecuta el comando y devuelve el código de salida (0 = éxito)."""
    args = _crear_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    # httpx registra cada petición en INFO; en una corrida completa taparía el avance.
    logging.getLogger("httpx").setLevel(logging.WARNING)

    # Por ahora solo existe "scrape"; argparse ya rechazó cualquier otro comando.
    return _scrape(
        args.fuente,
        args.salida,
        con_detalle=not args.sin_detalle,
        max_paginas=args.max_paginas,
    )


if __name__ == "__main__":
    raise SystemExit(main())
