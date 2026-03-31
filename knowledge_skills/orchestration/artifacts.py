from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class ArtifactStore:
    root: Path

    def __post_init__(self) -> None:
        """Ensure the backing artifact directory exists before use."""
        self.root.mkdir(parents=True, exist_ok=True)

    def write_text(self, relative_path: str, content: str) -> str:
        """Persist one text artifact and return its relative artifact reference."""
        target = (self.root / relative_path).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return str(target.relative_to(self.root))

    def write_json(self, relative_path: str, payload: Any) -> str:
        """Persist one JSON artifact and return its relative artifact reference."""
        target = (self.root / relative_path).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return str(target.relative_to(self.root))

    def read_text(self, artifact_ref: str) -> str:
        """Read one text artifact by artifact reference."""
        return self.resolve(artifact_ref).read_text(encoding="utf-8")

    def read_json(self, artifact_ref: str) -> Any:
        """Read and decode one JSON artifact by artifact reference."""
        return json.loads(self.read_text(artifact_ref))

    def resolve(self, artifact_ref: str) -> Path:
        """Resolve one artifact reference to an absolute filesystem path."""
        return (self.root / artifact_ref).resolve()
