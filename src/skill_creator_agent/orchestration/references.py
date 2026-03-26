from __future__ import annotations

import re
from pathlib import Path


def extract_reference_paths(text: str) -> list[Path]:
    """Extract readable local reference file paths from free-form user text."""
    found: list[Path] = []
    pattern = re.compile(
        r"((?:/|Users/|[A-Za-z]:\\)[^\s\"'，。；,;()]+\.(?:md|markdown|txt|rst|json|yaml|yml|pdf))",
        re.IGNORECASE,
    )
    for raw in pattern.findall(text):
        normalized = raw.strip().strip(".,)")
        if not normalized.startswith(("/", "~")) and not re.match(r"^[A-Za-z]:\\\\", normalized):
            normalized = f"/{normalized}"
        candidate = Path(normalized).expanduser()
        if candidate.exists() and candidate.is_file():
            found.append(candidate.resolve())
    return found


def build_reference_bundle(user_reply: str) -> str:
    """Build a markdown bundle from referenced files and inline user notes."""
    paths = extract_reference_paths(user_reply)
    source_blocks: list[str] = []
    for path in paths:
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = path.read_text(encoding="utf-8", errors="ignore")
        source_blocks.append(f"## Source: {path}\n\n{content}")

    inline_text = _strip_reference_paths(user_reply)
    if inline_text:
        source_blocks.append(f"## Inline Reference Content\n\n{inline_text}")

    if not source_blocks:
        return "未提供可读取的参考资料。"
    return "\n\n".join(source_blocks)


def _strip_reference_paths(text: str) -> str:
    cleaned = text
    for path in extract_reference_paths(text):
        cleaned = cleaned.replace(str(path), "")
    return cleaned.strip()
