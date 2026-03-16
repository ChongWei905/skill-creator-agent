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
        element_type: str,
        filter_dict: dict[str, Any],
        *,
        get_all_properties: bool = False,
    ) -> list[dict[str, Any]]:
        output_raw = self._request(
            "POST",
            "/api/v1/search/property_filter",
            {
                "element_class": element_class,
                "element_type": element_type,
                "filter_dict": filter_dict,
                "get_all_properties": get_all_properties,
            },
        )
        if get_all_properties:
            return [item.get("properties", {}) for item in output_raw]
        return output_raw

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
