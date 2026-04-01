from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
IMPORT_ROOT = PROJECT_ROOT.parent
IMPORT_ROOT_TEXT = str(IMPORT_ROOT)

if IMPORT_ROOT_TEXT not in sys.path:
    sys.path.insert(0, IMPORT_ROOT_TEXT)
