# conftest.py  (repo root or under functions/)
import sys
from pathlib import Path

# project root = this file's parent if at repo root, or parent of 'functions' if placed there
here = Path(__file__).resolve()
project_root = here if (here / "external").exists() else here.parent

owui_backend = project_root / "external" / "open-webui" / "backend"
if not (owui_backend / "open_webui").exists():
    raise RuntimeError(f"open_webui package not found at: {owui_backend}")

sys.path.insert(0, str(owui_backend))
