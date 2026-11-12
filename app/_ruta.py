"""Hace importable el paquete aunque no esté instalado.

Streamlit Cloud instala las dependencias de ``uv.lock``, pero no está documentado si instala
también este proyecto (que vive en ``src/``). Cada página importa este módulo primero: agrega
``src/`` al path de Python, y si el paquete sí está instalado no cambia nada.
"""

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
