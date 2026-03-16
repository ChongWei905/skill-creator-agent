from __future__ import annotations

from skill_creator_agent.connectors import GraphConnector


def test_graph_connector_supports_success_envelope(monkeypatch):
    connector = GraphConnector("http://example.com")

    monkeypatch.setattr(
        connector,
        "_request",
        lambda method, path, payload=None: ["Organ", "Person"] if path.endswith("get_object_types") else [],
    )

    assert connector.get_object_types() == ["Organ", "Person"]


def test_graph_connector_flattens_get_all_properties(monkeypatch):
    connector = GraphConnector("http://example.com")

    def fake_request(method, path, payload=None):
        assert payload["get_all_properties"] is True
        return [{"properties": {"uuid": "Node_1", "name": "Demo"}}]

    monkeypatch.setattr(connector, "_request", fake_request)

    result = connector.property_filter(
        "Organ",
        "NODE",
        {"name": "CONTAINS '深圳'"},
        get_all_properties=True,
    )

    assert result == [{"uuid": "Node_1", "name": "Demo"}]


def test_graph_connector_builds_schema_from_examples(monkeypatch):
    connector = GraphConnector("http://example.com")

    monkeypatch.setattr(
        connector,
        "property_filter",
        lambda element_class, element_type, filter_dict, get_all_properties=False: [
            {"uuid": "Node_1", "name": "Demo", "rank": 1}
        ],
    )

    schema = connector.get_entity_schema("Organ")

    assert schema["entity_type"] == "Organ"
    assert schema["sample_properties"]["name"] == "Demo"
    assert schema["total_count"] == 1
