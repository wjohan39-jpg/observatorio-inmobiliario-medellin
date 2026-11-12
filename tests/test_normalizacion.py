import pytest

from observatorio_inmobiliario.normalizacion import (
    MUNICIPIOS_VALLE,
    TIPOS,
    normalizar_municipio,
    normalizar_texto,
    normalizar_tipo,
)


@pytest.mark.parametrize(
    ("crudo", "esperado"),
    [
        ("BELÉN", "belen"),
        ("  Belén   Los  Alpes ", "belen los alpes"),
        ("Manrique Central No. 1", "manrique central 1"),
        ("Manrique Central No.1", "manrique central 1"),
        ("San José la Cima No.2", "san jose la cima 2"),
        ("El Nogal-Los Almendros", "el nogal los almendros"),
        ("B. Cerro  El Volador", "b cerro el volador"),
        ("Itagüí", "itagui"),
        ("Noel", "noel"),  # "no" solo se quita antes de un número
    ],
)
def test_normalizar_texto(crudo: str, esperado: str) -> None:
    assert normalizar_texto(crudo) == esperado


@pytest.mark.parametrize(
    ("crudo", "esperado"),
    [
        ("MEDELLIN", "Medellín"),
        ("Medellín", "Medellín"),
        ("medellin ", "Medellín"),
        ("ITAGUI", "Itagüí"),
        ("La Estrella", "La Estrella"),
        ("SABANETA", "Sabaneta"),
        ("EL RETIRO", "El Retiro"),  # fuera del valle: se conserva con mayúsculas normales
        ("", None),
        ("   ", None),
        (None, None),
    ],
)
def test_normalizar_municipio(crudo: str | None, esperado: str | None) -> None:
    assert normalizar_municipio(crudo) == esperado


def test_municipios_del_valle() -> None:
    assert {
        "Medellín",
        "Bello",
        "Itagüí",
        "Envigado",
        "Sabaneta",
        "La Estrella",
        "Caldas",
        "Copacabana",
        "Girardota",
        "Barbosa",
    } == MUNICIPIOS_VALLE


@pytest.mark.parametrize(
    ("crudo", "esperado"),
    [
        ("apartamento", "apartamento"),
        ("apartamento amoblado", "apartamento"),
        ("penthouse", "apartamento"),
        ("apto loft", "apartaestudio"),
        ("apartaestudio", "apartaestudio"),
        ("casa", "casa"),
        ("casa - apartamento(s)", "casa"),
        ("casa-local", "local"),
        ("casa local", "local"),
        ("comercial (casa para comercio)", "local"),
        ("oficina-local", "local"),
        ("oficina", "oficina"),
        ("oficina-consultorio", "oficina"),
        ("consultorio", "consultorio"),
        ("bodega", "bodega"),
        ("lote", "lote"),
        ("terreno", "lote"),
        ("casalote", "lote"),
        ("finca", "finca"),
        ("casa-finca", "finca"),
        ("casafinca", "finca"),
        ("casa campestre", "finca"),
        ("finca de recreo", "finca"),
        ("parqueadero", "parqueadero"),
        ("garaje", "parqueadero"),
        ("edificio", "edificio"),
        ("hotel", "edificio"),
        ("inmueble residencial", "otro"),
        (None, "otro"),
        ("", "otro"),
    ],
)
def test_normalizar_tipo(crudo: str | None, esperado: str) -> None:
    assert normalizar_tipo(crudo) == esperado
    assert esperado in TIPOS


def test_tipos_son_doce() -> None:
    assert len(TIPOS) == len(set(TIPOS)) == 12


@pytest.mark.parametrize(
    "corregimiento",
    ["Santa Elena", "SAN ANTONIO DE PRADO", "San Cristóbal", "Altavista", "Palmitas"],
)
def test_corregimientos_son_medellin(corregimiento: str) -> None:
    """Los corregimientos son parte del municipio de Medellín."""
    assert normalizar_municipio(corregimiento) == "Medellín"
