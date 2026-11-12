"""Sitio estático del dashboard para GitHub Pages: un solo ``index.html``.

Tiene la misma información que las páginas de Streamlit, pero sin servidor: las gráficas de
plotly siguen siendo interactivas (zoom y detalle al pasar el mouse). Como no hay selectores,
venta y arriendo van una debajo de la otra. Lee solo las tablas agregadas, así que nunca
muestra ids, URL ni coordenadas de anuncios.
"""

from html import escape
from pathlib import Path
from typing import Any, Final

import pandas as pd
import plotly.graph_objects as go

from observatorio_inmobiliario.reputacion import reconocimiento
from observatorio_inmobiliario.tablero import graficas
from observatorio_inmobiliario.tablero.formato import indicadores

REPOSITORIO: Final = "https://github.com/wjohan39-jpg/observatorio-inmobiliario-medellin"
_ESTILO: Final = """
body{font-family:system-ui,-apple-system,"Segoe UI",sans-serif;margin:0;color:#1f2933;
background:#fff}
header{background:#2c7fb8;color:#fff;padding:24px 32px}
header h1{margin:0 0 6px}
nav{position:sticky;top:0;background:#f5f7fa;border-bottom:1px solid #d9e2ec;padding:10px 32px;
z-index:10}
nav a{margin-right:18px;color:#2c7fb8;text-decoration:none;font-weight:600}
main{max-width:1200px;margin:0 auto;padding:8px 32px 48px}
section{padding-top:24px;border-bottom:1px solid #eef2f6}
.kpis{display:flex;flex-wrap:wrap;gap:16px;margin:16px 0}
.kpi{flex:1 1 180px;background:#f5f7fa;border-radius:8px;padding:12px 16px}
.kpi span{display:block;font-size:13px;color:#52606d}
.kpi strong{font-size:28px}
.aviso{background:#e8f4fd;border-left:4px solid #2c7fb8;padding:10px 14px;margin:12px 0}
table{border-collapse:collapse;font-size:13px;margin:12px 0;width:100%}
th,td{border-bottom:1px solid #e4e7eb;padding:4px 8px;text-align:right}
th:first-child,td:first-child{text-align:left}
.tabla{max-height:420px;overflow:auto}
footer{color:#7b8794;font-size:13px;padding:24px 32px}
"""


class _Graficas:
    """Convierte figuras a HTML; solo la primera incluye plotly.js (desde su CDN)."""

    def __init__(self) -> None:
        self._primera = True

    def __call__(self, figura: go.Figure) -> str:
        incluir = "cdn" if self._primera else False
        self._primera = False
        html: str = figura.to_html(
            full_html=False, include_plotlyjs=incluir, config={"displaylogo": False}
        )
        return html


def _aviso(texto: str) -> str:
    return f'<p class="aviso">{escape(texto)}</p>'


def _tabla(df: pd.DataFrame) -> str:
    if df.empty:
        return _aviso("Todavía no hay datos para esta tabla.")
    return '<div class="tabla">' + df.to_html(index=False, na_rep="—", border=0) + "</div>"


def _seccion(id_: str, titulo: str, contenido: list[str]) -> str:
    return f'<section id="{id_}"><h2>{escape(titulo)}</h2>{"".join(contenido)}</section>'


def generar_sitio(tablas: dict[str, pd.DataFrame], geojson: dict[str, Any], salida: Path) -> Path:
    """Escribe ``salida/index.html`` con las 6 secciones del dashboard y devuelve su ruta."""
    figura = _Graficas()
    cobertura = tablas["cobertura_inmobiliaria"]
    semana = str(cobertura["semana"].iloc[0]) if not cobertura.empty else "sin datos"
    precios = tablas["precios_zona"]
    kpis = "".join(
        f'<div class="kpi"><span>{escape(etiqueta)}</span><strong>{escape(valor)}</strong></div>'
        for etiqueta, valor in indicadores(tablas)
    )

    resumen = _seccion(
        "resumen",
        "Resumen del mercado",
        [
            f'<div class="kpis">{kpis}</div>',
            figura(graficas.mapa_barrios(precios, geojson, "venta")),
            figura(graficas.mapa_barrios(precios, geojson, "arriendo")),
            "<p>Mediana por barrio oficial, con al menos 5 anuncios con área. En gris, los "
            "barrios sin datos suficientes.</p>",
        ],
    )
    barrios = _seccion(
        "barrios",
        "Barrios",
        [
            figura(graficas.ranking_barrios(precios, "venta")),
            figura(graficas.ranking_barrios(precios, "arriendo")),
            figura(graficas.comparacion_comunas(precios)),
            "<p>Rentabilidad bruta = arriendo de un año ÷ precio de venta del m². Es una "
            "orientación: compara medianas de anuncios distintos y no descuenta gastos.</p>",
        ],
    )
    indice = reconocimiento(cobertura, None)
    inmobiliarias = _seccion(
        "inmobiliarias",
        "Inmobiliarias",
        [
            figura(graficas.cobertura(cobertura)),
            figura(graficas.concentracion(tablas["cobertura_comuna"])),
            "<p>El índice compara cada anuncio con la mediana de su propio barrio: 0,95 es un "
            "5 % por debajo de su barrio.</p>",
            figura(graficas.indice_relativo(tablas["economia_inmobiliaria"], "arriendo")),
            figura(graficas.indice_relativo(tablas["economia_inmobiliaria"], "venta")),
            figura(graficas.estratos(tablas["estratos_inmobiliaria"])),
            "<h3>Reconocimiento</h3>",
            "<p>Promedio de anuncios y barrios cubiertos, cada uno dividido por el máximo. La "
            "reputación de Google está desactivada en la versión publicada (la API exige una "
            "cuenta de facturación).</p>",
            _tabla(indice.drop(columns=["resenas", "con_resenas"], errors="ignore")),
        ],
    )
    fuentes, grupos = tablas["compartidos_fuentes"], tablas["grupos_compartidos"]
    compartidos = _seccion(
        "compartidos",
        "Propiedades compartidas",
        [
            "<p>El mismo inmueble publicado por dos o más inmobiliarias. El precio no se usa "
            "para emparejar: es lo que se compara. Confianza <b>media o mayor</b>.</p>",
            figura(graficas.compartidos(fuentes, "media")),
            "<h3>Grupos de confianza alta</h3>",
            "<p>Una fila por inmueble, con el precio de cada inmobiliaria. Sin enlaces ni "
            "textos de los anuncios.</p>",
            _tabla(graficas.tabla_grupos(grupos, "alta")),
        ],
    )
    semanas = graficas.semanas(tablas["evolucion_precios"])
    evolucion = _seccion(
        "evolucion",
        "Evolución",
        [
            _aviso(
                f"Por ahora hay una sola semana de datos ({', '.join(semanas) or 'ninguna'}). "
                "La evolución se llena con la ejecución semanal automática."
            )
            if len(semanas) < 2
            else "",
            figura(graficas.evolucion(tablas["evolucion_precios"], "venta")),
            figura(graficas.evolucion(tablas["evolucion_precios"], "arriendo")),
            figura(graficas.rotacion(tablas["rotacion_inmobiliaria"])),
        ],
    )
    metodologia = _seccion(
        "metodologia",
        "Metodología",
        [
            "<p>Datos de hecho (precio, área, barrio, estrato) de los anuncios públicos de 9 "
            "inmobiliarias de Medellín, respetando <code>robots.txt</code> y con límite de "
            "velocidad. Cada anuncio se ubica en el barrio oficial de la Alcaldía; los "
            "atípicos se marcan y se excluyen; venta y arriendo van siempre por separado; "
            "cada precio publicado resume al menos 5 anuncios.</p>",
            f'<p>El detalle está en el <a href="{REPOSITORIO}#readme">README del '
            "repositorio</a>, junto con el código, las pruebas y el notebook de análisis.</p>",
            "<p><b>Aviso:</b> proyecto educativo y sin fines comerciales. Si representas a una "
            "inmobiliaria y quieres retirar sus datos, abre un <i>issue</i> en el "
            "repositorio.</p>",
        ],
    )

    html = f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Observatorio inmobiliario de Medellín</title>
<style>{_ESTILO}</style>
</head>
<body>
<header>
<h1>Observatorio inmobiliario de Medellín</h1>
<div>Precios de vivienda, cobertura y propiedades compartidas de 9 inmobiliarias.
Datos de la semana <b>{escape(semana)}</b>.</div>
</header>
<nav>
<a href="#resumen">Resumen</a><a href="#barrios">Barrios</a>
<a href="#inmobiliarias">Inmobiliarias</a><a href="#compartidos">Compartidas</a>
<a href="#evolucion">Evolución</a><a href="#metodologia">Metodología</a>
</nav>
<main>
{resumen}{barrios}{inmobiliarias}{compartidos}{evolucion}{metodologia}
</main>
<footer>Generado a partir de <code>data/agregados/</code> ·
<a href="{REPOSITORIO}">Código en GitHub</a></footer>
</body>
</html>
"""
    salida.mkdir(parents=True, exist_ok=True)
    ruta = salida / "index.html"
    ruta.write_text(html, encoding="utf-8")
    return ruta
