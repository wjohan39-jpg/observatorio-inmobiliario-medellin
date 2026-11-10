from datetime import date
from typing import Any

import pytest
from pydantic import ValidationError

from observatorio_inmobiliario.modelos import AnuncioNormalizado, Operacion

FECHA = date(2026, 11, 10)


def crear(**campos: Any) -> AnuncioNormalizado:
    """Crea un anuncio con los campos obligatorios y los extra que se indiquen."""
    base: dict[str, Any] = {
        "fuente": "santafe",
        "id_fuente": "A22843",
        "operacion": Operacion.ARRIENDO,
        "fecha_observacion": FECHA,
    }
    return AnuncioNormalizado(**(base | campos))


def test_anuncio_valido_minimo() -> None:
    anuncio = crear()
    assert anuncio.fuente == "santafe"
    assert anuncio.operacion is Operacion.ARRIENDO
    assert anuncio.precio is None
    assert anuncio.estrato is None
    assert anuncio.barrio is None


def test_anuncio_completo() -> None:
    anuncio = crear(
        precio=2_500_000,
        administracion=350_000,
        area_m2=72.5,
        habitaciones=3,
        banos=2,
        parqueaderos=1,
        estrato=4,
        barrio="Laureles",
        municipio="Medellín",
        latitud=6.2442,
        longitud=-75.5812,
        tipo_inmueble="apartamento",
    )
    assert anuncio.precio == 2_500_000
    assert anuncio.estrato == 4


@pytest.mark.parametrize("estrato", [0, 7, -1])
def test_estrato_fuera_de_rango_falla(estrato: int) -> None:
    with pytest.raises(ValidationError):
        crear(estrato=estrato)


@pytest.mark.parametrize("precio", [0, -100])
def test_precio_no_positivo_falla(precio: int) -> None:
    with pytest.raises(ValidationError):
        crear(precio=precio)


def test_administracion_puede_ser_cero() -> None:
    assert crear(administracion=0).administracion == 0


@pytest.mark.parametrize("area", [0, -5, 100_000])
def test_area_fuera_de_rango_falla(area: float) -> None:
    with pytest.raises(ValidationError):
        crear(area_m2=area)


@pytest.mark.parametrize(("campo", "valor"), [("latitud", 91), ("longitud", -181)])
def test_coordenadas_fuera_de_rango_fallan(campo: str, valor: float) -> None:
    with pytest.raises(ValidationError):
        crear(**{campo: valor})


def test_textos_se_limpian() -> None:
    assert crear(barrio="  Laureles ").barrio == "Laureles"
    assert crear(barrio="").barrio is None
    assert crear(barrio="   ").barrio is None
    assert crear(barrio=None).barrio is None


def test_campos_obligatorios_no_pueden_quedar_vacios() -> None:
    with pytest.raises(ValidationError):
        crear(id_fuente="   ")
    with pytest.raises(ValidationError):
        crear(fuente="")


def test_tipo_inmueble_en_minusculas() -> None:
    assert crear(tipo_inmueble=" APARTAMENTO ").tipo_inmueble == "apartamento"


def test_campo_extra_prohibido() -> None:
    """Protege la regla del proyecto: no se guardan datos personales ni campos no definidos."""
    with pytest.raises(ValidationError):
        crear(telefono="3001234567")


def test_es_inmutable() -> None:
    anuncio = crear(precio=1_000_000)
    with pytest.raises(ValidationError):
        anuncio.precio = 1  # type: ignore[misc]


def test_operacion_se_serializa_como_texto() -> None:
    datos = crear(operacion=Operacion.VENTA).model_dump(mode="json")
    assert datos["operacion"] == "venta"
    assert datos["fecha_observacion"] == "2026-11-10"
