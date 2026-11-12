"""Comando ``observatorio``: punto de entrada del scraper desde la terminal.

Uso::

    observatorio scrape santafe                     # corrida completa
    observatorio scrape santafe --max-paginas 2     # corrida corta de prueba
    observatorio catalogo                           # actualiza el catálogo oficial de barrios
    observatorio limpiar                            # limpia la última semana descargada
"""

import argparse
import json
import logging
import re
import sys
from collections.abc import Sequence
from pathlib import Path

import pandas as pd

from observatorio_inmobiliario.almacenamiento import (
    guardar_limpio,
    guardar_observaciones,
    leer_semana,
    semanas_disponibles,
)
from observatorio_inmobiliario.catalogo import (
    RUTA_GEOJSON,
    URL_BASE_CATALOGO,
    Catalogo,
    descargar_catalogo,
)
from observatorio_inmobiliario.fuentes import REGISTRO, crear_fuente
from observatorio_inmobiliario.http import (
    ClienteCortes,
    ErrorDeDescarga,
    ErrorRutaBloqueadaPorRobots,
)
from observatorio_inmobiliario.limpieza import limpiar
from observatorio_inmobiliario.modelos import AnuncioNormalizado

logger = logging.getLogger(__name__)

SALIDA_POR_DEFECTO = Path("data/crudo")
LIMPIO_POR_DEFECTO = Path("data/limpio")
_SEMANA = re.compile(r"\d{4}-S\d{2}")
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


def _semana(texto: str) -> str:
    if not _SEMANA.fullmatch(texto):
        raise argparse.ArgumentTypeError(f"{texto!r} no tiene la forma AAAA-SNN, p. ej. 2026-S46")
    return texto


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

    catalogo = comandos.add_parser(
        "catalogo",
        help="descarga el catálogo oficial de barrios de Medellín",
        description="Descarga de la Alcaldía de Medellín los límites de barrios y veredas.",
    )
    catalogo.add_argument(
        "--salida",
        type=Path,
        default=RUTA_GEOJSON,
        help=f"archivo GeoJSON de salida (por defecto: {RUTA_GEOJSON})",
    )

    limpieza = comandos.add_parser(
        "limpiar",
        help="limpia una semana de datos crudos y guarda la tabla limpia",
        description="Ubica cada anuncio en los barrios oficiales, normaliza y marca atípicos.",
    )
    limpieza.add_argument(
        "--semana",
        type=_semana,
        default=None,
        metavar="AAAA-SNN",
        help="semana ISO a limpiar (por defecto: la última con datos crudos)",
    )
    limpieza.add_argument(
        "--crudo",
        type=Path,
        default=SALIDA_POR_DEFECTO,
        help=f"carpeta de los datos crudos (por defecto: {SALIDA_POR_DEFECTO})",
    )
    limpieza.add_argument(
        "--salida",
        type=Path,
        default=LIMPIO_POR_DEFECTO,
        help=f"carpeta de la tabla limpia (por defecto: {LIMPIO_POR_DEFECTO})",
    )
    return parser


def _catalogo(salida: Path) -> int:
    try:
        with ClienteCortes(URL_BASE_CATALOGO) as cliente:
            geojson = descargar_catalogo(cliente)
    except (ErrorDeDescarga, ErrorRutaBloqueadaPorRobots, ValueError) as error:
        print(f"catálogo: la descarga falló y no se guardó nada ({error})", file=sys.stderr)
        return 1
    salida.parent.mkdir(parents=True, exist_ok=True)
    texto = json.dumps(geojson, ensure_ascii=False, separators=(",", ":"))
    salida.write_text(texto + "\n", encoding="utf-8")
    print(f"{len(geojson['features'])} barrios y veredas guardados en {salida}")
    return 0


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


def _resumen(limpio: pd.DataFrame) -> pd.DataFrame:
    """Por fuente: anuncios, de Medellín, % con comuna y barrio (en Medellín) y % atípicos."""
    medellin = limpio[limpio["es_medellin"]]
    por_fuente = limpio.groupby("fuente")
    en_medellin = medellin.groupby("fuente")
    resumen = pd.DataFrame(
        {
            "anuncios": por_fuente.size(),
            "medellin": en_medellin.size(),
            "% comuna": en_medellin["comuna"].count() / en_medellin.size() * 100,
            "% barrio": en_medellin["codigo_barrio"].count() / en_medellin.size() * 100,
            "% atipicos": por_fuente["es_atipico"].mean() * 100,
        }
    )
    resumen.loc["TOTAL"] = [
        len(limpio),
        len(medellin),
        medellin["comuna"].count() / max(len(medellin), 1) * 100,
        medellin["codigo_barrio"].count() / max(len(medellin), 1) * 100,
        limpio["es_atipico"].mean() * 100,
    ]
    return resumen.fillna(0).round(1).astype({"anuncios": int, "medellin": int})


def _limpiar(semana: str | None, crudo: Path, salida: Path) -> int:
    semanas = semanas_disponibles(crudo)
    if not semanas:
        print(f"no hay datos crudos en {crudo}", file=sys.stderr)
        return 1
    semana = semana or semanas[-1]
    if semana not in semanas:
        print(f"no hay datos de la semana {semana} en {crudo}", file=sys.stderr)
        return 1

    limpio = limpiar(leer_semana(crudo, semana), Catalogo.cargar())
    ruta = guardar_limpio(limpio, salida, semana)
    print(f"{semana}: {len(limpio)} anuncios limpios guardados en {ruta}")
    print()
    print(_resumen(limpio).to_string())
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Ejecuta el comando y devuelve el código de salida (0 = éxito)."""
    args = _crear_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    # httpx registra cada petición en INFO; en una corrida completa taparía el avance.
    logging.getLogger("httpx").setLevel(logging.WARNING)

    if args.comando == "catalogo":
        return _catalogo(args.salida)
    if args.comando == "limpiar":
        return _limpiar(args.semana, args.crudo, args.salida)
    return _scrape(
        args.fuente,
        args.salida,
        con_detalle=not args.sin_detalle,
        max_paginas=args.max_paginas,
    )


if __name__ == "__main__":
    raise SystemExit(main())
