from __future__ import annotations

import ast
import json
import shlex
from collections.abc import Mapping, Sequence
from typing import Any


def normalize_cli_arguments(arguments: Any) -> list[str] | None:
    """Normalize CLI-style arguments into a list of strings."""
    return _normalize_string_list(
        arguments,
        error_message="arguments must be a list of strings or a JSON/shell-style string.",
    )


def normalize_mapping_argument(value: Any, *, field_name: str) -> dict[str, Any] | None:
    """Normalize a native or stringified mapping argument."""
    if value is None:
        return None
    if isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            return None
        parsed = _try_parse_json(normalized)
        if not isinstance(parsed, dict):
            raise ValueError(f"{field_name} must be a JSON object or a native mapping.")
        value = parsed
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be a mapping.")
    return {str(key): item for key, item in value.items()}


def normalize_string_list(value: Any, *, field_name: str) -> list[str] | None:
    """Normalize a native or stringified list of strings."""
    return _normalize_string_list(value, error_message=f"{field_name} must be a list of strings.")


def _normalize_string_list(value: Any, *, error_message: str) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            return None
        parsed = _try_parse_json(normalized)
        if isinstance(parsed, list):
            return [str(item) for item in parsed]
        return [str(item) for item in shlex.split(normalized)]
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [str(item) for item in value]
    raise ValueError(error_message)


def normalize_nested_list(value: Any, *, field_name: str) -> list[list[Any]]:
    """Normalize a native or stringified nested list."""
    if isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            return []
        parsed = _try_parse_json(normalized)
        if not isinstance(parsed, list):
            raise ValueError(f"{field_name} must be a JSON array of arrays or a native nested list.")
        value = parsed
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ValueError(f"{field_name} must be a nested list.")
    normalized_rows: list[list[Any]] = []
    for item in value:
        if not isinstance(item, Sequence) or isinstance(item, (str, bytes, bytearray)):
            raise ValueError(f"{field_name} must contain only nested lists.")
        normalized_rows.append(list(item))
    return normalized_rows


def normalize_bool(value: Any, *, field_name: str) -> bool:
    """Normalize a boolean-like value."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "y", "on"}:
            return True
        if normalized in {"false", "0", "no", "n", "off", ""}:
            return False
    if isinstance(value, int):
        return bool(value)
    raise ValueError(f"{field_name} must be a boolean.")


def normalize_int(value: Any, *, field_name: str) -> int | None:
    """Normalize an integer-like value."""
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be an integer.")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            return None
        return int(normalized)
    raise ValueError(f"{field_name} must be an integer.")


def _try_parse_json(value: str) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        try:
            return ast.literal_eval(value)
        except (ValueError, SyntaxError):
            return value
