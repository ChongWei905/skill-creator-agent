from __future__ import annotations

import json
from functools import lru_cache
from typing import Any
from urllib import error, request


class GraphConnector:
    """HTTP connector for the graph service used by workflow-svc style tools."""

    def __init__(self, base_url: str, timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

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

    @lru_cache(maxsize=1)
    def get_object_types(self) -> list[str]:
        return self._request("GET", "/api/v1/search/get_object_types")

    @lru_cache(maxsize=1)
    def get_object_relations(self) -> list[str]:
        return self._request("GET", "/api/v1/search/get_object_relations")

    def property_filter(
        self,
        element_class: str,
        element_type: str = "NODE",
        filter_dict: dict[str, Any] | None = None,
        *,
        get_all_properties: bool = False,
    ) -> list[dict[str, Any]]:
        element_class, element_type = self._normalize_element_target(element_class, element_type)
        output_raw = self._request(
            "POST",
            "/api/v1/search/property_filter",
            {
                "element_class": element_class,
                "element_type": element_type,
                "filter_dict": filter_dict or {},
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
        element_class, element_type = self._normalize_element_target(element_class, element_type)
        result = self._request(
            "POST",
            "/api/v1/search/count_search",
            {
                "element_class": element_class,
                "element_type": element_type,
                "filter_dict": filter_dict or {},
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
        if not target_property or not agg_func:
            raise ValueError("target_property and agg_func are required")
        element_class, element_type = self._normalize_element_target(element_class, element_type)
        result = self._request(
            "POST",
            "/api/v1/search/aggregate_search",
            {
                "element_class": element_class,
                "element_type": element_type,
                "target_property": target_property,
                "agg": agg_func,
                "filter_dict": filter_dict or {},
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
        element_class, element_type = self._normalize_element_target(element_class, element_type)
        payload: dict[str, Any] = {
            "element_class": element_class,
            "element_type": element_type,
        }
        if filter_dict is not None:
            payload["filter_dict"] = filter_dict
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
        results = self.property_filter(
            element_class=entity_type,
            element_type="NODE",
            filter_dict=filter_dict or {},
            get_all_properties=True,
        )
        return results[:limit]

    def close(self) -> None:
        return None

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
    def _normalize_element_target(element_class: str, element_type: str | None) -> tuple[str, str]:
        normalized_type = (element_type or "NODE").upper()
        if normalized_type in {"NODE", "EDGE"}:
            return element_class, normalized_type

        generic_classes = {"entity", "element", "node", "nodes", "class"}
        if element_class.strip().lower() in generic_classes:
            return str(element_type), "NODE"

        return element_class, "NODE"
