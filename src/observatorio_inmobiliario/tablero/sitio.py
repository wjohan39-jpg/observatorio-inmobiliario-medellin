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
from observatorio_inmobiliario.tablero.formato import entero, indicadores

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
    """Escribe ``salida/index.html`` con las 9 secciones del dashboard y devuelve su ruta."""
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
    mercado = tablas["mercado_precios"]
    analisis = _seccion(
        "precios",
        "Análisis de precios",
        [
            "<p>Seis preguntas sobre el precio de la vivienda. Todo usa la mediana y los "
            "cuartiles, y cada cifra resume 5 anuncios o más.</p>",
            "<h3>1. ¿Cuánto cuesta el m² y dónde es más caro o más barato?</h3>",
            figura(graficas.precio_comunas(precios, "venta")),
            figura(graficas.precio_comunas(precios, "arriendo")),
            figura(graficas.precio_estratos(mercado, "venta")),
            figura(graficas.precio_estratos(mercado, "arriendo")),
            "<p>El estrato solo está en los anuncios que lo declaran. Las barras de error "
            "van del cuartil 25 al 75.</p>",
            "<h3>2. ¿Qué tan parejo es el precio dentro de cada barrio?</h3>",
            figura(graficas.dispersion_barrios(mercado, "venta")),
            figura(graficas.dispersion_barrios(mercado, "arriendo")),
            "<p>La variación es la desviación estándar dividida por la media: con valores "
            "altos, el promedio del barrio no lo describe bien.</p>",
            "<h4>Venta</h4>",
            _tabla(graficas.tabla_dispersion(mercado, "venta")),
            "<h4>Arriendo</h4>",
            _tabla(graficas.tabla_dispersion(mercado, "arriendo")),
            "<h3>3. ¿Cuánto cambia el precio según el tipo de inmueble?</h3>",
            figura(graficas.tipos_por_comuna(mercado, "venta")),
            figura(graficas.tipos_por_comuna(mercado, "arriendo")),
            "<p>Solo aparecen las comunas con 5 anuncios o más de ese tipo.</p>",
            "<h3>4. ¿Cómo cambia el m² con la operación y el área?</h3>",
            figura(graficas.rangos_area(mercado, "venta")),
            figura(graficas.rangos_area(mercado, "arriendo")),
            "<h3>5. ¿Cuánto rinde un inmueble por barrio?</h3>",
            figura(graficas.rentabilidad_barrios(precios)),
            "<p>Rentabilidad bruta = arriendo de un año ÷ precio de venta del m². Compara "
            "medianas de anuncios distintos y no descuenta administración, impuestos ni "
            "vacancia.</p>",
            "<h3>6. ¿En qué barrios conviene más comprar que arrendar?</h3>",
            "<p>Los barrios se ordenan por rentabilidad y se dividen en tres grupos iguales: "
            "donde es alta, comprar sale relativamente barato frente a arrendar; donde es "
            "baja, arrendar. Es una comparación entre barrios, no una recomendación: no "
            "incluye crédito, valorización ni costo de oportunidad.</p>",
            _tabla(graficas.tabla_rentabilidad(precios)),
        ],
    )
    oferta, distribucion = tablas["oferta_zona"], tablas["distribucion_oferta"]
    rotacion = tablas["rotacion_inmobiliaria"]
    movimiento = _seccion(
        "oferta",
        "Oferta y rotación",
        [
            "<p>Anuncios de 9 inmobiliarias, no todo el mercado de Medellín. Un anuncio "
            "<b>activo</b> es uno que apareció en el último scraping, sin los de precio "
            "atípico (cerca del 1 %).</p>",
            "<h3>Inmuebles activos por zona, tipo y operación</h3>",
            figura(graficas.oferta_por_tipo(oferta, "venta")),
            figura(graficas.oferta_por_tipo(oferta, "arriendo")),
            figura(graficas.oferta_comunas(oferta, "venta", "vivienda")),
            figura(graficas.oferta_comunas(oferta, "arriendo", "vivienda")),
            figura(graficas.oferta_barrios(oferta, "venta", "vivienda")),
            figura(graficas.oferta_barrios(oferta, "arriendo", "vivienda")),
            "<p>Solo los anuncios con coordenadas válidas se pueden ubicar en un barrio: las "
            "cifras por zona son un mínimo.</p>",
            "<h4>Venta de vivienda por barrio</h4>",
            _tabla(graficas.tabla_oferta(oferta, "barrio", "venta", "vivienda")),
            "<h4>Arriendo de vivienda por barrio</h4>",
            _tabla(graficas.tabla_oferta(oferta, "barrio", "arriendo", "vivienda")),
            "<h3>Distribución por rango de precio y alcobas</h3>",
            figura(graficas.distribucion_precio(distribucion, "venta", "vivienda")),
            figura(graficas.distribucion_alcobas(distribucion, "venta", "vivienda")),
            figura(graficas.precio_y_alcobas(distribucion, "venta", "vivienda")),
            figura(graficas.distribucion_precio(distribucion, "arriendo", "vivienda")),
            figura(graficas.distribucion_alcobas(distribucion, "arriendo", "vivienda")),
            figura(graficas.precio_y_alcobas(distribucion, "arriendo", "vivienda")),
            "<p>El arriendo es el canon mensual y la venta es el precio total (M = millones "
            "de pesos). «Sin dato» son anuncios que no publican alcobas.</p>",
            "<h3>Rotación: anuncios nuevos y retirados por semana</h3>",
            figura(graficas.nuevos_y_retirados(rotacion)),
            _tabla(graficas.tabla_rotacion_semana(rotacion)),
            "<p>Cada inmobiliaria se compara con su propia semana anterior con datos. "
            "<b>Retirado</b> significa que el anuncio ya no apareció en el scraping, no "
            "necesariamente que se vendió o se arrendó.</p>",
        ],
    )
    cuota, perfil = tablas["cuota_zona"], tablas["perfil_inmobiliaria"]
    calidad, estratos = tablas["calidad_inmobiliaria"], tablas["estratos_inmobiliaria"]
    hhi_barrios = graficas.tabla_hhi(cuota, "barrio", "todas")
    cuota_agencias = _seccion(
        "cuota",
        "Cuota y perfil",
        [
            "<p>La cuota es la del <b>inventario observado en las 9 inmobiliarias</b>, no la "
            "del mercado: faltan otras inmobiliarias y los particulares. Una propiedad "
            "publicada por varias inmobiliarias cuenta en cada una.</p>",
            "<h3>Cuota de inventario</h3>",
            figura(graficas.cuota_total(cuota, "todas")),
            figura(graficas.cuota_total(cuota, "venta")),
            figura(graficas.cuota_total(cuota, "arriendo")),
            figura(graficas.cuota_zonas(cuota, "barrio", "todas")),
            figura(graficas.cuota_zonas(cuota, "comuna", "todas")),
            "<p>Solo los anuncios con barrio o comuna reconocidos cuentan por zona, y varía "
            "mucho por inmobiliaria: las que casi no traen ubicación aparecen "
            "subrepresentadas.</p>",
            "<h3>Concentración: índice HHI</h3>",
            "<p>Suma de los cuadrados de las cuotas (en %), de 0 a 10.000. Menos de "
            f"{entero(graficas.UMBRALES_HHI[0])} es poco concentrado y más de "
            f"{entero(graficas.UMBRALES_HHI[1])}, muy concentrado. Solo en zonas con "
            f"{graficas.MINIMO_HHI} anuncios o más.</p>",
            figura(graficas.concentracion_hhi(cuota, "barrio", "todas")),
            figura(graficas.concentracion_hhi(cuota, "comuna", "todas")),
            "<h4>Barrios</h4>",
            _tabla(hhi_barrios),
            "<h4>Comunas</h4>",
            _tabla(graficas.tabla_hhi(cuota, "comuna", "todas")),
            "<h3>Perfil: en qué se especializa cada inmobiliaria</h3>",
            _tabla(graficas.tabla_perfil(perfil, estratos)),
            figura(graficas.perfil_operacion(perfil)),
            figura(graficas.perfil_tipos(perfil, "venta")),
            figura(graficas.perfil_tipos(perfil, "arriendo")),
            "<h3>Calidad de los datos</h3>",
            figura(graficas.calidad_datos(calidad)),
            _tabla(graficas.tabla_calidad(calidad)),
            "<p>Porcentaje de los anuncios de vivienda que trae cada dato. Fotos y "
            "descripciones no se miden porque el proyecto no las guarda.</p>",
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
<a href="#resumen">Resumen</a><a href="#barrios">Barrios</a><a href="#precios">Precios</a>
<a href="#oferta">Oferta</a><a href="#cuota">Cuota</a>
<a href="#inmobiliarias">Inmobiliarias</a><a href="#compartidos">Compartidas</a>
<a href="#evolucion">Evolución</a><a href="#metodologia">Metodología</a>
</nav>
<main>
{resumen}{barrios}{analisis}{movimiento}{cuota_agencias}{inmobiliarias}{compartidos}{evolucion}{metodologia}
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
