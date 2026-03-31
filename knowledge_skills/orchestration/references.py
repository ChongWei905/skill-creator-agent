from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ReferenceSource:
    path: str
    content: str


@dataclass(frozen=True)
class ReferenceIntakeResult:
    user_reply: str
    raw_path_candidates: list[str]
    resolved_sources: list[ReferenceSource]
    missing_paths: list[str]
    inline_reference_text: str
    explicit_no_references: bool
    has_readable_reference: bool
    needs_clarification: bool
    clarification_reason: str


def extract_reference_paths(text: str) -> list[Path]:
    """Extract readable local reference file paths from free-form user text."""
    return [Path(source.path) for source in intake_references(text).resolved_sources]


def load_reference_sources(text: str) -> list[dict[str, str]]:
    """Load referenced local files and return their resolved paths plus text content."""
    return [
        {"path": source.path, "content": source.content}
        for source in intake_references(text).resolved_sources
    ]


def intake_references(text: str) -> ReferenceIntakeResult:
    """Parse one reference reply into validated files, inline text, and clarification hints."""
    raw_candidates = _extract_reference_path_candidates(text)
    resolved_sources: list[ReferenceSource] = []
    missing_paths: list[str] = []

    for raw_candidate in raw_candidates:
        normalized = _normalize_reference_path(raw_candidate)
        candidate = Path(normalized).expanduser()
        try:
            exists = candidate.exists()
            is_file = candidate.is_file() if exists else False
        except OSError:
            exists = False
            is_file = False
        if not exists or not is_file:
            missing_paths.append(normalized)
            continue
        try:
            content = candidate.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = candidate.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            missing_paths.append(normalized)
            continue
        resolved_sources.append(ReferenceSource(path=str(candidate.resolve()), content=content))

    inline_reference_text = _extract_inline_reference_text(text, raw_candidates)
    explicit_no_references = _is_no_references_reply(text)
    attempted_reference_input = _looks_like_reference_attempt(text, raw_candidates)
    has_readable_reference = bool(resolved_sources) or bool(inline_reference_text)
    needs_clarification = attempted_reference_input and not has_readable_reference and not explicit_no_references
    clarification_reason = _clarification_reason(
        raw_candidates=raw_candidates,
        missing_paths=missing_paths,
        needs_clarification=needs_clarification,
    )

    return ReferenceIntakeResult(
        user_reply=text,
        raw_path_candidates=raw_candidates,
        resolved_sources=resolved_sources,
        missing_paths=missing_paths,
        inline_reference_text=inline_reference_text,
        explicit_no_references=explicit_no_references,
        has_readable_reference=has_readable_reference,
        needs_clarification=needs_clarification,
        clarification_reason=clarification_reason,
    )


def build_reference_bundle(user_reply: str | ReferenceIntakeResult) -> str:
    """Build a markdown bundle from reference intake results or raw user text."""
    intake = user_reply if isinstance(user_reply, ReferenceIntakeResult) else intake_references(user_reply)
    source_blocks: list[str] = []
    for source in intake.resolved_sources:
        source_blocks.append(f"## Source: {source.path}\n\n{source.content}")

    if intake.inline_reference_text:
        source_blocks.append(f"## Inline Reference Content\n\n{intake.inline_reference_text}")

    if not source_blocks:
        return "未提供参考资料。" if intake.explicit_no_references else "未提供可读取的参考资料。"
    return "\n\n".join(source_blocks)


def build_reference_clarification_message(intake: ReferenceIntakeResult) -> str:
    """Build a user-facing follow-up question when reference intake needs clarification."""
    if intake.missing_paths:
        joined = "，".join(f"`{path}`" for path in intake.missing_paths[:3])
        return (
            "我看到了你提供的参考文档路径，但当前没有找到可读取的文件："
            f"{joined}。\n\n"
            "请确认路径是否写错了；如果方便，也可以直接把关键文档内容贴在这里。"
            "如果不提供参考资料也可以，请直接回复“没有”。"
        )
    return (
        "我理解你想提供参考资料，但当前回复里还没有可读取的文件内容。"
        "你可以继续提供文件路径，或者直接把关键文档内容贴在这里；"
        "如果没有参考资料，请直接回复“没有”。"
    )


def _clarification_reason(
    *,
    raw_candidates: list[str],
    missing_paths: list[str],
    needs_clarification: bool,
) -> str:
    if not needs_clarification:
        return "none"
    if raw_candidates and missing_paths:
        return "path_not_found"
    return "reference_content_missing"


def _extract_inline_reference_text(text: str, raw_candidates: list[str]) -> str:
    cleaned = _strip_reference_paths(text, raw_candidates)
    return cleaned if _is_meaningful_inline_reference(cleaned) else ""


def _extract_reference_path_candidates(text: str) -> list[str]:
    pattern = re.compile(
        r"((?:/|~/|Users/|[A-Za-z]:[\\/])[^\"'，。；,;()]+?\.(?:md|markdown|txt|rst|json|yaml|yml|pdf))",
        re.IGNORECASE,
    )
    candidates: list[str] = []
    seen: set[str] = set()
    for raw in pattern.findall(text):
        normalized = raw.strip().strip(".,)")
        if normalized in seen:
            continue
        seen.add(normalized)
        candidates.append(normalized)
    return candidates


def _normalize_reference_path(raw_candidate: str) -> str:
    normalized = raw_candidate.strip().strip(".,)").strip("\"'")
    if normalized.startswith(("~", "/")) or re.match(r"^[A-Za-z]:[\\/]", normalized):
        return normalized
    if normalized.startswith("Users/"):
        return f"/{normalized}"
    return normalized


def _is_meaningful_inline_reference(text: str) -> bool:
    collapsed = re.sub(r"\s+", " ", text).strip()
    if not collapsed:
        return False
    normalized = re.sub(r"[：:，,。；;\s]+", "", collapsed)
    if len(normalized) < 4:
        return False
    signal_text = re.sub(
        r"(有文档|有资料|有参考资料|有参考文档|文档|文件|资料|参考资料|参考文档|位置在|路径在|文件在|文档在|文档位置在|文件路径在|文档路径在|资料在|参考资料在|参考文档在|位置|路径|内容如下|如下|要点)",
        "",
        collapsed,
    )
    signal_text = re.sub(r"[：:，,。；;\s]+", "", signal_text)
    return len(signal_text) >= 2


def _is_no_references_reply(text: str) -> bool:
    collapsed = re.sub(r"\s+", "", text)
    return collapsed in {
        "没有",
        "无",
        "没有资料",
        "没有文档",
        "没有参考资料",
        "没有参考文档",
        "不用文档",
        "不需要文档",
        "不需要参考资料",
    }


def _looks_like_reference_attempt(text: str, raw_candidates: list[str]) -> bool:
    if raw_candidates:
        return True
    return bool(re.search(r"(文档|文件|资料|参考|附件|路径|位置|markdown|md)", text, re.IGNORECASE))


def _strip_reference_paths(text: str, raw_candidates: list[str]) -> str:
    cleaned = text
    for raw_candidate in raw_candidates:
        cleaned = cleaned.replace(raw_candidate, " ")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()
