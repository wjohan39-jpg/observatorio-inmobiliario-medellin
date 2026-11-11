from observatorio_inmobiliario.html import analizar, decodificar, texto


def test_decodificar_utf8() -> None:
    assert decodificar("Itagüí".encode()) == "Itagüí"


def test_decodificar_cp1252() -> None:
    assert decodificar("Itagüí · 60 M²".encode("cp1252")) == "Itagüí · 60 M²"


def test_texto_quita_espacios_y_vacios() -> None:
    nodos = analizar("<p> 3 \r\n </p><p>  </p>").css("p")

    assert texto(nodos[0]) == "3"
    assert texto(nodos[1]) is None
    assert texto(None) is None
