from __future__ import annotations

import sys

from _bootstrap import bootstrap_script_imports

bootstrap_script_imports(sys.argv)

from skill_creator_agent.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
