from __future__ import annotations

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
SRC_ROOT_TEXT = str(SRC_ROOT)
if SRC_ROOT_TEXT not in sys.path:
    sys.path.insert(0, SRC_ROOT_TEXT)

from skill_creator_agent.entrypoint import main


if __name__ == "__main__":
    raise SystemExit(main())
