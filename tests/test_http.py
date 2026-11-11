from collections.abc import Iterator

import httpx
import pytest
import respx

from observatorio_inmobiliario.config import USER_AGENT
from observatorio_inmobiliario.http import (
    ClienteCortes,
    ErrorDeDescarga,
    ErrorRutaBloqueadaPorRobots,
)

URL_BASE = "https://inmobiliaria.example"


class RelojFalso:
    """Reloj controlado: ``dormir`` avanza el tiempo sin esperar y registra cada pausa."""

    def __init__(self) -> None:
        self.ahora = 1000.0
        self.pausas: list[float] = []

    def reloj(self) -> float:
        return self.ahora

    def dormir(self, segundos: float) -> None:
        self.pausas.append(segundos)
        self.ahora += segundos


@pytest.fixture
def reloj() -> RelojFalso:
    return RelojFalso()


@pytest.fixture
def sitio() -> Iterator[respx.MockRouter]:
    """Simula el sitio web. Por defecto, su robots.txt permite todo."""
    with respx.mock(base_url=URL_BASE, assert_all_called=False) as router:
        router.get("/robots.txt").respond(200, text="User-agent: *\nAllow: /\n")
        yield router


@pytest.fixture
def cliente(reloj: RelojFalso) -> Iterator[ClienteCortes]:
    with ClienteCortes(URL_BASE, dormir=reloj.dormir, reloj=reloj.reloj) as c:
        yield c


def test_max_intentos_debe_ser_positivo() -> None:
    with pytest.raises(ValueError, match="max_intentos"):
        ClienteCortes(URL_BASE, max_intentos=0)


def test_get_json_devuelve_datos(sitio: respx.MockRouter, cliente: ClienteCortes) -> None:
    sitio.get("/api/items").respond(200, json={"ok": True})
    assert cliente.get_json("/api/items") == {"ok": True}


def test_get_texto_devuelve_html(sitio: respx.MockRouter, cliente: ClienteCortes) -> None:
    sitio.get("/listado").respond(200, text="<html>hola</html>")
    assert cliente.get_texto("/listado") == "<html>hola</html>"


def test_get_bytes_devuelve_el_cuerpo_sin_decodificar(
    sitio: respx.MockRouter, cliente: ClienteCortes
) -> None:
    """Algunos sitios declaran UTF-8 pero envían cp1252: se decodifica aparte, a mano."""
    cuerpo = "Itagüí".encode("cp1252")
    sitio.get("/x").respond(
        200, content=cuerpo, headers={"Content-Type": "text/html; charset=utf-8"}
    )

    assert cliente.get_bytes("/x") == cuerpo


def test_envia_params(sitio: respx.MockRouter, cliente: ClienteCortes) -> None:
    ruta = sitio.get("/api/items", params={"page": "2"}).respond(200, json=[])
    cliente.get_json("/api/items", params={"page": 2})
    assert ruta.called


def test_envia_user_agent(sitio: respx.MockRouter, cliente: ClienteCortes) -> None:
    ruta = sitio.get("/api/items").respond(200, json={})
    cliente.get_json("/api/items")
    assert ruta.calls.last.request.headers["User-Agent"] == USER_AGENT


def test_respeta_robots(sitio: respx.MockRouter, cliente: ClienteCortes) -> None:
    sitio.get("/robots.txt").respond(200, text="User-agent: *\nDisallow: /privado\n")
    ruta = sitio.get("/privado/x").respond(200, json={})
    with pytest.raises(ErrorRutaBloqueadaPorRobots):
        cliente.get_json("/privado/x")
    assert not ruta.called


ROBOTS_SANTA_FE = """User-Agent: *
Allow: /
Allow: /apisf/property/
Allow: /apisf/properties
Disallow: /admin
Disallow: /api/
Disallow: /apisf/
"""


@pytest.mark.parametrize(
    ("ruta", "permitida"),
    [
        ("/apisf/properties", True),
        ("/apisf/property/A22843", True),
        ("/propiedades", True),
        ("/admin", False),
        ("/api/secreto", False),
        ("/apisf/otra", False),
    ],
)
def test_robots_usa_la_regla_mas_especifica(
    sitio: respx.MockRouter, cliente: ClienteCortes, ruta: str, permitida: bool
) -> None:
    """RFC 9309: gana la regla más larga, no la primera.

    Regresión: en Python 3.12, ``urllib.robotparser`` aplicaba la primera regla que
    coincidía, así que ``Allow: /`` al inicio permitía también ``/admin``.
    """
    sitio.get("/robots.txt").respond(200, text=ROBOTS_SANTA_FE)
    sitio.get(ruta).respond(200, json={})
    if permitida:
        assert cliente.get_json(ruta) == {}
    else:
        with pytest.raises(ErrorRutaBloqueadaPorRobots):
            cliente.get_json(ruta)


def test_robots_se_descarga_una_sola_vez(sitio: respx.MockRouter, cliente: ClienteCortes) -> None:
    sitio.get("/api/items").respond(200, json={})
    cliente.get_json("/api/items")
    cliente.get_json("/api/items")
    assert sum(1 for c in sitio.calls if c.request.url.path == "/robots.txt") == 1


def test_robots_404_permite_todo(sitio: respx.MockRouter, cliente: ClienteCortes) -> None:
    sitio.get("/robots.txt").respond(404)
    sitio.get("/cualquier/ruta").respond(200, json={"ok": True})
    assert cliente.get_json("/cualquier/ruta") == {"ok": True}


def test_espera_entre_peticiones(
    sitio: respx.MockRouter, cliente: ClienteCortes, reloj: RelojFalso
) -> None:
    sitio.get("/api/items").respond(200, json={})
    cliente.get_json("/api/items")  # robots.txt + 1.ª petición
    cliente.get_json("/api/items")  # 2.ª petición
    # Tres peticiones seguidas sin que pase el tiempo → dos pausas de 1,5 s.
    assert reloj.pausas == [1.5, 1.5]


def test_no_espera_si_ya_paso_el_tiempo(
    sitio: respx.MockRouter, cliente: ClienteCortes, reloj: RelojFalso
) -> None:
    sitio.get("/api/items").respond(200, json={})
    cliente.get_json("/api/items")
    reloj.ahora += 10
    cliente.get_json("/api/items")
    assert reloj.pausas == [1.5]  # solo la pausa entre robots.txt y la 1.ª petición


def test_reintenta_en_503_y_luego_funciona(
    sitio: respx.MockRouter, cliente: ClienteCortes, reloj: RelojFalso
) -> None:
    sitio.get("/api/items").mock(
        side_effect=[httpx.Response(503), httpx.Response(503), httpx.Response(200, json={"ok": 1})]
    )
    assert cliente.get_json("/api/items") == {"ok": 1}
    # 1,5 s de cortesía tras robots.txt, luego espera creciente: 2 s y 4 s.
    assert reloj.pausas == [1.5, 2, 4]


def test_reintenta_en_429(sitio: respx.MockRouter, cliente: ClienteCortes) -> None:
    sitio.get("/api/items").mock(side_effect=[httpx.Response(429), httpx.Response(200, json=[])])
    assert cliente.get_json("/api/items") == []


def test_reintenta_en_timeout(sitio: respx.MockRouter, cliente: ClienteCortes) -> None:
    sitio.get("/api/items").mock(
        side_effect=[httpx.ReadTimeout("lento"), httpx.Response(200, json=[])]
    )
    assert cliente.get_json("/api/items") == []


def test_falla_tras_agotar_intentos(sitio: respx.MockRouter, cliente: ClienteCortes) -> None:
    ruta = sitio.get("/api/items").respond(500)
    with pytest.raises(ErrorDeDescarga):
        cliente.get_json("/api/items")
    assert ruta.call_count == 3


def test_404_no_reintenta(sitio: respx.MockRouter, cliente: ClienteCortes) -> None:
    ruta = sitio.get("/api/items").respond(404)
    with pytest.raises(ErrorDeDescarga):
        cliente.get_json("/api/items")
    assert ruta.call_count == 1


def test_json_invalido_es_error_de_descarga(
    sitio: respx.MockRouter, cliente: ClienteCortes
) -> None:
    sitio.get("/api/items").respond(200, text="<html>no es json</html>")
    with pytest.raises(ErrorDeDescarga):
        cliente.get_json("/api/items")


def test_robots_inaccesible_es_error_de_descarga(
    sitio: respx.MockRouter, cliente: ClienteCortes
) -> None:
    """Si no se puede leer robots.txt (error de servidor), no se scrapea a ciegas."""
    sitio.get("/robots.txt").respond(503)
    ruta = sitio.get("/api/items").respond(200, json={})
    with pytest.raises(ErrorDeDescarga):
        cliente.get_json("/api/items")
    assert not ruta.called
