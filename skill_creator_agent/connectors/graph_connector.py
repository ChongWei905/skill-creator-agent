from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Any
from urllib import error, request


class GraphConnector:
    """HTTP connector for the graph service used by workflow-svc style tools."""

    def __init__(self, base_url: str, timeout: int = 30):
        """Initialize a graph connector bound to one HTTP service endpoint."""
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    @staticmethod
    def _normalize_return_vars(return_vars: list[str]) -> list[str]:
        normalized: list[str] = []
        for name in return_vars:
            if name.startswith("var") and name[3:].isdigit():
                normalized.append(chr(97 + int(name[3:])))
            else:
                normalized.append(name)
        return normalized

    @staticmethod
    def _normalize_filter_atom(atom: str) -> str:
        if not atom:
            raise ValueError("Filter expression parts cannot be empty.")

        textual_prefixes = ["CONTAINS", "STARTS WITH", "ENDS WITH"]
        upper_atom = atom.upper()
        for prefix in textual_prefixes:
            if upper_atom.startswith(prefix):
                suffix = atom[len(prefix):].strip()
                if not suffix:
                    raise ValueError(f"Filter expression '{atom}' is missing a value after {prefix}.")
                return f"{prefix} {suffix}"

        if atom.startswith(("=", ">", "<")):
            return atom

        raise ValueError(
            "Unsupported filter expression. Use strings like "
            "\"= '0400000012'\", \"> 0\", \"< 100\", \"CONTAINS '深圳'\", "
            "\"STARTS WITH '04'\", or \"ENDS WITH '30'\". "
            "Use OR inside one property, for example \"CONTAINS '深圳' OR CONTAINS '罗湖'\"."
        )

    @staticmethod
    def _normalize_element_target(element_class: str, element_type: str | None) -> tuple[str, str]:
        normalized_type = (element_type or "NODE").upper()
        if normalized_type in {"NODE", "EDGE"}:
            return element_class, normalized_type

        generic_classes = {"entity", "element", "node", "nodes", "class"}
        if element_class.strip().lower() in generic_classes:
            return str(element_type), "NODE"

        return element_class, "NODE"

    @staticmethod
    def close() -> None:
        """Close the connector interface.

        The current HTTP implementation is stateless, so there is nothing to release.
        """
        return None

    @classmethod
    def _normalize_filter_dict(cls, filter_dict: dict[str, Any] | None) -> dict[str, str]:
        if not filter_dict:
            return {}
        normalized: dict[str, str] = {}
        for prop_name, condition_expr in filter_dict.items():
            if not isinstance(condition_expr, str):
                raise ValueError(
                    f"Invalid filter for '{prop_name}': filter expressions must be strings such as "
                    "\"= '0400000012'\", \"> 0\", or \"CONTAINS '深圳'\"."
                )
            normalized[str(prop_name)] = cls._normalize_filter_expression(condition_expr)
        return normalized

    @classmethod
    def _normalize_filter_expression(cls, condition_expr: str) -> str:
        expr = condition_expr.strip()
        if not expr:
            raise ValueError("Filter expressions cannot be empty.")
        if re.search(r"\bAND\b", expr, flags=re.IGNORECASE):
            raise ValueError(
                "A single property filter expression cannot contain AND. "
                "Use separate filter_dict entries for different properties, and use OR only within one property."
            )

        parts = re.split(r"\s+OR\s+", expr, flags=re.IGNORECASE)
        normalized_parts = [cls._normalize_filter_atom(part.strip()) for part in parts]
        return " OR ".join(normalized_parts)

    @lru_cache(maxsize=1)
    def get_object_types(self) -> list[str]:
        """Return all object types exposed by the graph service."""
        return self._request("GET", "/api/v1/search/get_object_types")

    @lru_cache(maxsize=1)
    def get_object_relations(self) -> list[str]:
        """Return all relation types exposed by the graph service."""
        return self._request("GET", "/api/v1/search/get_object_relations")

    def property_filter(
        self,
        element_class: str,
        element_type: str = "NODE",
        filter_dict: dict[str, Any] | None = None,
        *,
        get_all_properties: bool = False,
    ) -> list[dict[str, Any]]:
        """Query elements by property filters and optionally unwrap their properties."""
        element_class, element_type = self._normalize_element_target(element_class, element_type)
        normalized_filter_dict = self._normalize_filter_dict(filter_dict)
        output_raw = self._request(
            "POST",
            "/api/v1/search/property_filter",
            {
                "element_class": element_class,
                "element_type": element_type,
                "filter_dict": normalized_filter_dict,
                "get_all_properties": get_all_properties,
            },
        )
        if get_all_properties:
            return [item.get("properties", {}) for item in output_raw]
        return output_raw

    def hop_search(
        self,
        uuid: str,
        hop_num: int,
        accurate_flag: bool = False,
    ) -> list[dict[str, Any]]:
        """Run a hop expansion search from one graph element UUID."""
        return self._request(
            "POST",
            "/api/v1/search/hop_search",
            {
                "uuid": uuid,
                "hop_num": hop_num,
                "accurate_flag": accurate_flag,
            },
        )

    def count_search(
        self,
        element_class: str,
        element_type: str = "NODE",
        filter_dict: dict[str, Any] | None = None,
    ) -> int:
        """Count graph elements that match the provided filter set."""
        element_class, element_type = self._normalize_element_target(element_class, element_type)
        normalized_filter_dict = self._normalize_filter_dict(filter_dict)
        result = self._request(
            "POST",
            "/api/v1/search/count_search",
            {
                "element_class": element_class,
                "element_type": element_type,
                "filter_dict": normalized_filter_dict,
            },
        )
        if result and isinstance(result[0], dict):
            return int(result[0].get("count", 0))
        return 0

    def aggregate_search(
        self,
        element_class: str,
        element_type: str = "NODE",
        target_property: str | None = None,
        agg_func: str | None = None,
        filter_dict: dict[str, Any] | None = None,
    ) -> Any:
        """Run an aggregate query and return the first aggregate value from the response."""
        if not target_property or not agg_func:
            raise ValueError("target_property and agg_func are required")
        element_class, element_type = self._normalize_element_target(element_class, element_type)
        normalized_filter_dict = self._normalize_filter_dict(filter_dict)
        result = self._request(
            "POST",
            "/api/v1/search/aggregate_search",
            {
                "element_class": element_class,
                "element_type": element_type,
                "target_property": target_property,
                "agg": agg_func,
                "filter_dict": normalized_filter_dict,
            },
        )
        if result and isinstance(result[0], dict):
            for key, value in result[0].items():
                normalized = key.lower()
                if "value" in normalized or normalized.startswith(agg_func.lower()):
                    return value
            return next(iter(result[0].values()), None)
        return None

    def sorted_search(
        self,
        element_class: str,
        element_type: str = "NODE",
        filter_dict: dict[str, Any] | None = None,
        return_properties: list[str] | None = None,
        sort_by: str | None = None,
        ascending: bool = True,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Run a sorted search and optionally trim the returned result set."""
        element_class, element_type = self._normalize_element_target(element_class, element_type)
        normalized_filter_dict = self._normalize_filter_dict(filter_dict)
        payload: dict[str, Any] = {
            "element_class": element_class,
            "element_type": element_type,
        }
        if normalized_filter_dict:
            payload["filter_dict"] = normalized_filter_dict
        if return_properties is not None:
            payload["return_properties"] = return_properties
        if sort_by is not None:
            payload["sort_by"] = sort_by
            payload["ascending"] = ascending
        result = self._request("POST", "/api/v1/search/sorted_search", payload)
        if limit is not None:
            return result[:limit]
        return result

    def pattern_search(
        self,
        path_pattern: list[list[Any]],
        return_vars: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Execute a path pattern query against the graph service."""
        payload: dict[str, Any] = {
            "path_pattern": path_pattern,
        }
        if return_vars is not None:
            payload["return_vars"] = self._normalize_return_vars(return_vars)
        return self._request("POST", "/api/v1/search/pattern_search", payload)

    def property_info_search(
        self,
        element_class: str,
        element_type: str = "NODE",
        element_uuid: str | None = None,
    ) -> dict[str, Any]:
        """Fetch the property payload for one concrete graph element."""
        if not element_uuid:
            raise ValueError("element_uuid is required")
        element_class, element_type = self._normalize_element_target(element_class, element_type)
        result = self._request(
            "POST",
            "/api/v1/search/property_info_search",
            {
                "element_class": element_class,
                "element_type": element_type,
                "element_uuid": element_uuid,
            },
        )
        if result and isinstance(result[0], dict):
            return result[0].get("properties", {})
        return {}

    def get_entity_schema(self, entity_type: str) -> dict[str, Any]:
        """Infer a lightweight schema snapshot from sample entity records."""
        examples = self.property_filter(
            element_class=entity_type,
            element_type="NODE",
            filter_dict={},
            get_all_properties=True,
        )
        if not examples:
            return {
                "entity_type": entity_type,
                "sample_properties": {},
                "note": "No examples found",
            }
        return {
            "entity_type": entity_type,
            "sample_properties": examples[0],
            "total_count": len(examples),
        }

    def query_examples(
        self,
        entity_type: str,
        *,
        limit: int = 5,
        filter_dict: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Return example entity records for prompt grounding or inspection."""
        results = self.property_filter(
            element_class=entity_type,
            element_type="NODE",
            filter_dict=filter_dict or {},
            get_all_properties=True,
        )
        return results[:limit]

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        url = f"{self.base_url}{path}"
        data = None
        headers = {"Content-Type": "application/json"}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")

        req = request.Request(url, data=data, method=method.upper(), headers=headers)
        try:
            with request.urlopen(req, timeout=self.timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            raise RuntimeError(f"Graph request failed with HTTP {exc.code}: {url}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"Graph request failed: {url}") from exc

        if "success" in body:
            if not body.get("success", False):
                raise RuntimeError(f"Graph API error: {body.get('message', 'Unknown error')}")
            return body.get("result", [])

        if body.get("code") != 200:
            raise RuntimeError(f"Graph API error: {body.get('msg', 'Unknown error')}")
        return body.get("result", [])
