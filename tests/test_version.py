from observatorio_inmobiliario import __version__, config


def test_version_definida() -> None:
    assert __version__ == "0.1.0"


def test_user_agent_identifica_al_proyecto() -> None:
    assert config.USER_AGENT.startswith(f"ObservatorioInmobiliarioMedellin/{__version__}")
    assert config.URL_REPOSITORIO in config.USER_AGENT


def test_pausa_minima_entre_peticiones() -> None:
    assert config.SEGUNDOS_ENTRE_PETICIONES >= 1.5
