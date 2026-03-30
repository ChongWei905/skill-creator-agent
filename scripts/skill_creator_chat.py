from __future__ import annotations

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT_TEXT = str(REPO_ROOT)
if REPO_ROOT_TEXT not in sys.path:
    sys.path.insert(0, REPO_ROOT_TEXT)

from skill_creator_agent.main import main


if __name__ == "__main__":
    raise SystemExit(main())
