"""Los workflows de GitHub Actions son YAML válido y respetan las decisiones de seguridad."""

from pathlib import Path
from typing import Any

import yaml

from observatorio_inmobiliario.tablero.datos import RAIZ

FLUJOS = RAIZ / ".github" / "workflows"


def _cargar(nombre: str) -> dict[Any, Any]:
    flujo: dict[Any, Any] = yaml.safe_load((FLUJOS / nombre).read_text("utf-8"))
    return flujo


def _disparadores(flujo: dict[Any, Any]) -> dict[str, Any]:
    disparadores: dict[str, Any] = flujo[True] if True in flujo else flujo["on"]  # "on" → True
    return disparadores


def _pasos_semanal() -> list[dict[str, Any]]:
    pasos: list[dict[str, Any]] = _cargar("semanal.yml")["jobs"]["actualizar"]["steps"]
    return pasos


def test_semanal_es_yaml_valido() -> None:
    flujo = _cargar("semanal.yml")
    disparadores = _disparadores(flujo)
    assert disparadores["schedule"] == [{"cron": "0 11 * * 1"}]
    assert "fuentes" in disparadores["workflow_dispatch"]["inputs"]
    assert flujo["permissions"] == {"contents": "write"}
    assert flujo["concurrency"]["group"] == "semanal"
    assert flujo["jobs"]["actualizar"]["timeout-minutes"] == 300


def test_semanal_usa_el_secret() -> None:
    pasos = _pasos_semanal()
    privado = [p for p in pasos if p.get("with", {}).get("path") == "datos-privados"]
    assert len(privado) == 1
    assert privado[0]["with"]["token"] == "${{ secrets.DATOS_TOKEN }}"
    assert privado[0]["with"]["repository"] == "wjohan39-jpg/observatorio-inmobiliario-datos"
    # El token solo se usa en el checkout: no debe aparecer en ningún comando.
    assert not any("secrets." in p.get("run", "") for p in pasos)


def test_semanal_no_hace_commits_vacios() -> None:
    commits = [p["run"] for p in _pasos_semanal() if "git commit" in p.get("run", "")]
    assert len(commits) == 2
    assert all("git diff --cached --quiet ||" in c for c in commits)


def test_semanal_rutas_privadas() -> None:
    ejecuta = [p["run"] for p in _pasos_semanal() if "observatorio semana" in p.get("run", "")]
    assert len(ejecuta) == 1
    for opcion in ("--crudo", "--limpio", "--compartidos"):
        assert f"{opcion} datos-privados/" in ejecuta[0]
    resumen = [p for p in _pasos_semanal() if "GITHUB_STEP_SUMMARY" in p.get("run", "")]
    assert resumen[0]["if"] == "always()"


def test_pages_escucha_al_semanal() -> None:
    flujo = _cargar("pages.yml")
    escucha = _disparadores(flujo)["workflow_run"]
    assert escucha["workflows"] == [_cargar("semanal.yml")["name"]]
    assert escucha["types"] == ["completed"]
    condicion = flujo["jobs"]["construir"]["if"]
    assert "github.event.workflow_run.conclusion == 'success'" in condicion


def test_workflow_pages_es_yaml_valido() -> None:
    flujo = _cargar("pages.yml")
    disparadores = _disparadores(flujo)
    assert "workflow_dispatch" in disparadores
    assert "data/agregados/**" in disparadores["push"]["paths"]
    assert flujo["permissions"] == {"contents": "read", "pages": "write", "id-token": "write"}
    pasos = [p.get("uses", p.get("run", "")) for p in flujo["jobs"]["construir"]["steps"]]
    assert any("observatorio sitio" in p for p in pasos)
    assert any(p.startswith("actions/upload-pages-artifact") for p in pasos)
    despliegue = flujo["jobs"]["publicar"]["steps"]
    assert despliegue[0]["uses"].startswith("actions/deploy-pages")


def test_datos_privados_no_se_versionan() -> None:
    lineas = (Path(RAIZ) / ".gitignore").read_text("utf-8").splitlines()
    assert "datos-privados/" in lineas
