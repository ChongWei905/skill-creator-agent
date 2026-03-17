from __future__ import annotations

import pytest

from skill_creator_agent.connectors import GraphConnector


class RecordingGraphConnector(GraphConnector):
    def __init__(self):
        super().__init__(base_url="http://example.com")
        self.calls: list[tuple[str, str, dict | None]] = []

    def _request(self, method: str, path: str, payload: dict | None = None):
        self.calls.append((method, path, payload))
        if path.endswith("/aggregate_search"):
            return [{"count_Value": 10}]
        if path.endswith("/pattern_search"):
            return [{"a.name": "深圳罗湖支行", "c.uuid": "Kpi_1"}]
        if path.endswith("/property_info_search"):
            return [{"properties": {"uuid": "Organ_1", "name": "罗湖支行"}}]
        if path.endswith("/count_search"):
            return [{"count": 11}]
        return []


def test_graph_connector_aggregate_search_uses_service_agg_field():
    connector = RecordingGraphConnector()

    value = connector.aggregate_search(
        "KpiOfDailyPersonalBusinessLoan",
        "NODE",
        "Value",
        "COUNT",
        {},
    )

    assert value == 10
    assert connector.calls[-1][2]["agg"] == "COUNT"
    assert "agg_func" not in connector.calls[-1][2]


def test_graph_connector_pattern_search_normalizes_var_style_return_vars():
    connector = RecordingGraphConnector()

    result = connector.pattern_search(
        [["Organ", {}], ["Hold", "->"], ["KpiOfDailyPersonalBusinessLoan", {}]],
        return_vars=["var0", "var2"],
    )

    assert result[0]["a.name"] == "深圳罗湖支行"
    assert connector.calls[-1][2]["return_vars"] == ["a", "c"]


def test_graph_connector_property_info_search_extracts_properties():
    connector = RecordingGraphConnector()

    result = connector.property_info_search("Organ", "NODE", "Organ_1")

    assert result == {"uuid": "Organ_1", "name": "罗湖支行"}


def test_graph_connector_count_search_extracts_integer():
    connector = RecordingGraphConnector()

    result = connector.count_search("Organ", "NODE", {})

    assert result == 11


def test_graph_connector_property_filter_normalizes_generic_element_target():
    connector = RecordingGraphConnector()

    connector.property_filter("entity", "Person", {"逾期多次标识": "= '是'"})

    _, _, payload = connector.calls[-1]
    assert payload["element_class"] == "Person"
    assert payload["element_type"] == "NODE"


def test_graph_connector_sorted_search_accepts_limit_passthrough():
    connector = RecordingGraphConnector()

    result = connector.sorted_search("Organ", "NODE", sort_by="name", limit=1)

    assert result == []
    _, _, payload = connector.calls[-1]
    assert payload["sort_by"] == "name"


def test_graph_connector_property_filter_normalizes_case_insensitive_or_contains():
    connector = RecordingGraphConnector()

    connector.property_filter(
        "Organ",
        "NODE",
        {"name": "contains '深圳' or contains '罗湖'"},
    )

    _, _, payload = connector.calls[-1]
    assert payload["filter_dict"]["name"] == "CONTAINS '深圳' OR CONTAINS '罗湖'"


def test_graph_connector_property_filter_rejects_invalid_expression():
    connector = RecordingGraphConnector()

    with pytest.raises(ValueError):
        connector.property_filter("Organ", "NODE", {"name": "深圳"})


def test_graph_connector_property_filter_rejects_and_inside_single_expression():
    connector = RecordingGraphConnector()

    with pytest.raises(ValueError):
        connector.property_filter("Organ", "NODE", {"name": "CONTAINS '深圳' AND CONTAINS '罗湖'"})
