from __future__ import annotations

import pytest

import knowledge_skills.ferry_integration.tools as ferry_tools_module
from knowledge_skills.ferry_integration.argument_normalizer import (
    normalize_cli_arguments,
    normalize_string_list,
)
from knowledge_skills.ferry_integration.config import DEFAULT_GRAPH_TOOLS, DEFAULT_RUNTIME_TOOLS
from knowledge_skills.ferry_integration.runtime_reset import reset_ferry_singletons
from knowledge_skills.ferry_integration.tools import (
    configure_runtime_tools,
    execute_skill_script,
    graph_property_filter,
    reload_skill,
    reset_runtime_tools,
)
from knowledge_skills.runtime import SkillCreatorRuntime


def test_string_list_normalizers_share_parsing_behavior():
    assert normalize_cli_arguments('["--branch_name", "蛇口支行"]') == ["--branch_name", "蛇口支行"]
    assert normalize_string_list('["--branch_name", "蛇口支行"]', field_name="return_vars") == [
        "--branch_name",
        "蛇口支行",
    ]
    assert normalize_cli_arguments("--branch_name 蛇口支行") == ["--branch_name", "蛇口支行"]
    assert normalize_string_list("--branch_name 蛇口支行", field_name="return_vars") == [
        "--branch_name",
        "蛇口支行",
    ]


def test_normalize_cli_arguments_preserves_specific_error_message():
    with pytest.raises(ValueError, match="JSON/shell-style string"):
        normalize_cli_arguments(1)


def test_skill_creator_tools_register_with_ferry_tool_manager(tmp_path):
    from ferry.actions.tools.manager import ToolManager

    runtime = SkillCreatorRuntime.from_config(
        {
            "SKILL_CREATOR": {
                "skills_root": str(tmp_path),
            }
        }
    )
    configure_runtime_tools(runtime=runtime)
    reset_ferry_singletons()

    try:
        manager = ToolManager()
        manager.init_from_config({"TOOLS": {"local_functions": DEFAULT_RUNTIME_TOOLS}})

        created = manager.call(
            "create_skill_scaffold",
            skill_name="tool-created-skill",
            description="Created via ferry tool manager.",
            body="# Tool Created Skill",
        )
        reloaded = manager.call("reload_skill", skill_name="tool-created-skill")
        listed = manager.call("list_available_skills")

        assert created.success is True
        assert reloaded.success is True
        assert any(skill["name"] == "tool-created-skill" for skill in listed.data)
    finally:
        reset_ferry_singletons()
        reset_runtime_tools()


def test_graph_tools_register_with_ferry_tool_manager(tmp_path):
    from ferry.actions.tools.manager import ToolManager

    runtime = SkillCreatorRuntime.from_config(
        {
            "SKILL_CREATOR": {
                "skills_root": str(tmp_path),
                "graph_enabled": True,
            }
        }
    )

    class StubGraphConnector:
        def get_object_types(self):
            return ["Organ"]

        def get_object_relations(self):
            return ["Organ-Own-Organ"]

        def get_entity_schema(self, entity_type):
            return {"entity_type": entity_type, "sample_properties": {"uuid": "Node_1"}}

        def query_examples(self, entity_type, *, limit=5, filter_dict=None):
            return [{"entity_type": entity_type, "limit": limit}]

        def property_filter(self, element_class, element_type, filter_dict, *, get_all_properties=False):
            return [{"element_class": element_class, "filter_dict": filter_dict}]

        def property_info_search(self, element_class, element_type, element_uuid):
            return {"element_uuid": element_uuid}

        def hop_search(self, uuid, hop_num, accurate_flag=False):
            return [{"uuid": uuid, "hop_num": hop_num, "accurate_flag": accurate_flag}]

        def count_search(self, element_class, element_type, filter_dict):
            return 5

        def aggregate_search(self, element_class, element_type, target_property, agg_func, filter_dict):
            return 99

        def sorted_search(self, element_class, element_type, filter_dict=None, return_properties=None, sort_by=None, ascending=True):
            return [{"sort_by": sort_by}]

        def pattern_search(self, path_pattern, return_vars=None):
            return [{"return_vars": return_vars}]

    runtime._graph_connector = StubGraphConnector()
    configure_runtime_tools(runtime=runtime)
    reset_ferry_singletons()

    try:
        manager = ToolManager()
        manager.init_from_config({"TOOLS": {"local_functions": [*DEFAULT_RUNTIME_TOOLS, *DEFAULT_GRAPH_TOOLS]}})

        object_types = manager.call("graph_get_object_types")
        relations = manager.call("graph_get_object_relations")
        schema = manager.call("graph_get_entity_schema", entity_type="Organ")
        details = manager.call("graph_property_info", element_class="Organ", element_type="NODE", element_uuid="Organ_1")
        hop = manager.call("graph_hop_search", uuid="Organ_1", hop_num=2, accurate_flag=True)
        count = manager.call("graph_count_search", element_class="Organ", element_type="NODE", filter_dict={})

        assert object_types.success is True
        assert object_types.data == ["Organ"]
        assert relations.data == ["Organ-Own-Organ"]
        assert schema.data["entity_type"] == "Organ"
        assert details.data["element_uuid"] == "Organ_1"
        assert hop.data[0]["accurate_flag"] is True
        assert count.data == 5
    finally:
        reset_ferry_singletons()
        reset_runtime_tools()


def test_execute_skill_script_normalizes_stringified_argument_array(monkeypatch):
    captured: dict[str, object] = {}

    class StubRuntime:
        def execute_skill_script(self, skill_name, script_name, args=None, cwd=None, timeout=300):
            captured["skill_name"] = skill_name
            captured["script_name"] = script_name
            captured["args"] = args
            captured["cwd"] = cwd
            captured["timeout"] = timeout
            return {"ok": True}

    monkeypatch.setattr(ferry_tools_module, "get_runtime_tools", lambda: StubRuntime())

    result = execute_skill_script(
        "branch-deposit-analysis",
        "branch_deposit_analysis.py",
        arguments='["--branch_name", "蛇口支行"]',
        timeout="60",
    )

    assert result == {"ok": True}
    assert captured["args"] == ["--branch_name", "蛇口支行"]
    assert captured["timeout"] == 60


def test_execute_skill_script_normalizes_python_literal_argument_array(monkeypatch):
    captured: dict[str, object] = {}

    class StubRuntime:
        def execute_skill_script(self, skill_name, script_name, args=None, cwd=None, timeout=300):
            captured["args"] = args
            return {"ok": True}

    monkeypatch.setattr(ferry_tools_module, "get_runtime_tools", lambda: StubRuntime())

    execute_skill_script(
        "branch-deposit-analysis",
        "branch_deposit_analysis.py",
        arguments="['--branch_name', '蛇口支行']",
    )

    assert captured["args"] == ["--branch_name", "蛇口支行"]


def test_reload_skill_uses_one_runtime_lookup(monkeypatch):
    calls = 0

    class StubRuntime:
        @staticmethod
        def reload_skill(skill_name):
            return {"name": skill_name}

        @staticmethod
        def skill_to_dict(skill):
            return {"skill": skill["name"]}

    def get_runtime_tools_once():
        nonlocal calls
        calls += 1
        if calls > 1:
            raise AssertionError("reload_skill should reuse the runtime from the first lookup.")
        return StubRuntime()

    monkeypatch.setattr(ferry_tools_module, "get_runtime_tools", get_runtime_tools_once)

    assert reload_skill("demo-skill") == {"skill": "demo-skill"}
    assert calls == 1


def test_graph_property_filter_normalizes_stringified_filter_dict(monkeypatch):
    captured: dict[str, object] = {}

    class StubRuntime:
        def graph_property_filter(
            self,
            element_class,
            element_type="NODE",
            filter_dict=None,
            *,
            get_all_properties=False,
        ):
            captured["element_class"] = element_class
            captured["element_type"] = element_type
            captured["filter_dict"] = filter_dict
            captured["get_all_properties"] = get_all_properties
            return [{"ok": True}]

    monkeypatch.setattr(ferry_tools_module, "get_runtime_tools", lambda: StubRuntime())

    result = graph_property_filter(
        "Organ",
        filter_dict='{"name": "CONTAINS \\"蛇口\\""}',
        get_all_properties="true",
    )

    assert result == [{"ok": True}]
    assert captured["filter_dict"] == {"name": 'CONTAINS "蛇口"'}
    assert captured["get_all_properties"] is True


def test_graph_property_filter_normalizes_python_literal_filter_dict(monkeypatch):
    captured: dict[str, object] = {}

    class StubRuntime:
        def graph_property_filter(
            self,
            element_class,
            element_type="NODE",
            filter_dict=None,
            *,
            get_all_properties=False,
        ):
            captured["filter_dict"] = filter_dict
            return [{"ok": True}]

    monkeypatch.setattr(ferry_tools_module, "get_runtime_tools", lambda: StubRuntime())

    graph_property_filter(
        "Organ",
        filter_dict="{'name': \"CONTAINS '蛇口'\"}",
    )

    assert captured["filter_dict"] == {"name": "CONTAINS '蛇口'"}
