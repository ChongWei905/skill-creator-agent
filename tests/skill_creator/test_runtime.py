from __future__ import annotations

import pytest

from skill_creator_agent.runtime import SkillCreatorRuntime
from skill_creator_agent.settings import DEFAULT_SKILLS_ROOT


def test_runtime_lists_and_reads_fixture_skill():
    runtime = SkillCreatorRuntime.from_config(
        {
            "SKILL_CREATOR": {
                "skills_root": "fixtures/minimal_skills",
            }
        }
    )

    skills = runtime.list_skills()
    content = runtime.read_skill_content("skill-creator-smoke")
    scripts = runtime.list_skill_scripts("skill-creator-smoke")

    assert len(skills) == 1
    assert skills[0]["name"] == "skill-creator-smoke"
    assert "Skill Creator Smoke" in content
    assert scripts[0]["name"] == "echo_input"


def test_runtime_executes_script_and_returns_structured_result():
    runtime = SkillCreatorRuntime.from_config(
        {
            "SKILL_CREATOR": {
                "skills_root": "fixtures/minimal_skills",
            }
        }
    )

    result = runtime.execute_skill_script("skill-creator-smoke", "echo_input", args=["runtime"])

    assert result["skill"] == "skill-creator-smoke"
    assert result["script"] == "echo_input"
    assert result["exit_code"] == 0
    assert result["stdout"].strip() == "runtime"
    assert result["stderr"] == ""


def test_runtime_executes_graph_script_with_connectors_compat_import(tmp_path):
    runtime = SkillCreatorRuntime.from_config(
        {
            "SKILL_CREATOR": {
                "skills_root": str(tmp_path / "temp-skill-root"),
                "graph_enabled": True,
                "graph_base_url": "http://127.0.0.1:8000",
                "graph_timeout": 45,
            }
        }
    )

    runtime.create_skill_scaffold(
        "connector-compat-skill",
        "Checks GraphConnector compatibility imports.",
        body="# Connector Compat Skill",
        script_files={
            "check_connector.py": (
                "import json\n"
                "import os\n"
                "from connectors import GraphConnector\n\n"
                "connector = GraphConnector(\n"
                "    base_url=os.getenv('GRAPH_DB_BASE_URL', ''),\n"
                "    timeout=int(os.getenv('GRAPH_DB_TIMEOUT', '0')),\n"
                ")\n"
                "print(json.dumps({\n"
                "    'connector_class': connector.__class__.__name__,\n"
                "    'base_url': connector.base_url,\n"
                "    'timeout': connector.timeout,\n"
                "}, ensure_ascii=False))\n"
            )
        },
    )
    runtime.reload_skill("connector-compat-skill")

    result = runtime.execute_skill_script("connector-compat-skill", "check_connector")

    assert result["exit_code"] == 0
    assert '"connector_class": "GraphConnector"' in result["stdout"]
    assert '"base_url": "http://127.0.0.1:8000"' in result["stdout"]
    assert '"timeout": 45' in result["stdout"]
    assert "Traceback" not in result["stderr"]
    assert "ImportError" not in result["stderr"]


def test_runtime_builds_system_prompt_with_skill_context_and_reminder():
    runtime = SkillCreatorRuntime.from_config(
        {
            "SKILL_CREATOR": {
                "skills_root": str(DEFAULT_SKILLS_ROOT),
                "graph_enabled": False,
            }
        }
    )

    prompt = runtime.build_system_prompt(
        just_created_skill="skill-creator-smoke",
        original_intent="Create a smoke-test skill",
    )

    assert "skill-creator-smoke" in prompt
    assert "Create a smoke-test skill" in prompt
    assert "Available Skills" in prompt
    assert "## ⚠️ CRITICAL: SKILL.md Format Requirements" in prompt
    assert "## 🎯 IMPORTANT: Skill Just Created!" in prompt
    assert "## Skill Creation Workflow (MUST follow ALL steps in order)" in prompt


def test_runtime_builds_direct_query_prompt_with_direct_fallback():
    runtime = SkillCreatorRuntime.from_config(
        {
            "SKILL_CREATOR": {
                "skills_root": str(DEFAULT_SKILLS_ROOT),
            }
        }
    )

    prompt = runtime.build_system_prompt(direct_query=True)

    assert "## ⚠️ DIRECT QUERY MODE - NO SKILL CREATION" in prompt
    assert "DO NOT create new skills. Always use direct graph database queries." in prompt


def test_runtime_creates_skill_scaffold_and_reloads_it(tmp_path):
    runtime = SkillCreatorRuntime.from_config(
        {
            "SKILL_CREATOR": {
                "skills_root": str(tmp_path),
            }
        }
    )

    scaffold = runtime.create_skill_scaffold(
        "generated-skill",
        "Generated during tests.",
        body="# Generated Skill\n\n1. Run the script.",
        script_files={"run.sh": "#!/usr/bin/env bash\necho generated\n"},
    )
    skill = runtime.reload_skill("generated-skill")

    assert scaffold["skill_name"] == "generated-skill"
    assert (tmp_path / "generated-skill" / "SKILL.md").exists()
    assert skill.name == "generated-skill"
    assert skill.list_script_names() == ["run"]


def test_runtime_rejects_duplicate_skill_scaffold(tmp_path):
    runtime = SkillCreatorRuntime.from_config(
        {
            "SKILL_CREATOR": {
                "skills_root": str(tmp_path),
            }
        }
    )

    runtime.create_skill_scaffold("duplicate-skill", "Created once.")

    with pytest.raises(FileExistsError):
        runtime.create_skill_scaffold("duplicate-skill", "Created twice.")


def test_runtime_graph_methods_delegate_to_connector():
    runtime = SkillCreatorRuntime.from_config(
        {
            "SKILL_CREATOR": {
                "skills_root": str(DEFAULT_SKILLS_ROOT),
                "graph_enabled": True,
            }
        }
    )

    class StubGraphConnector:
        def get_object_types(self):
            return ["Organ", "Person"]

        def get_object_relations(self):
            return ["Organ-Own-Organ"]

        def get_entity_schema(self, entity_type):
            return {"entity_type": entity_type, "sample_properties": {"uuid": "Node_1"}}

        def query_examples(self, entity_type, *, limit=5, filter_dict=None):
            return [{"uuid": "Node_1", "entity_type": entity_type, "limit": limit, "filter_dict": filter_dict}]

        def property_filter(self, element_class, element_type, filter_dict, *, get_all_properties=False):
            return [{"element_class": element_class, "get_all_properties": get_all_properties, "filter_dict": filter_dict}]

        def property_info_search(self, element_class, element_type, element_uuid):
            return {"element_class": element_class, "element_uuid": element_uuid}

        def hop_search(self, uuid, hop_num, accurate_flag=False):
            return [{"uuid": uuid, "hop_num": hop_num, "accurate_flag": accurate_flag}]

        def count_search(self, element_class, element_type, filter_dict):
            return 3

        def aggregate_search(self, element_class, element_type, target_property, agg_func, filter_dict):
            return {"agg_func": agg_func, "target_property": target_property}

        def sorted_search(self, element_class, element_type, filter_dict=None, return_properties=None, sort_by=None, ascending=True):
            return [{"sort_by": sort_by, "ascending": ascending, "return_properties": return_properties}]

        def pattern_search(self, path_pattern, return_vars=None):
            return [{"path_pattern": path_pattern, "return_vars": return_vars}]

    runtime._graph_connector = StubGraphConnector()

    assert runtime.graph_get_object_types() == ["Organ", "Person"]
    assert runtime.graph_get_object_relations() == ["Organ-Own-Organ"]
    assert runtime.graph_get_entity_schema("Organ")["entity_type"] == "Organ"
    assert runtime.graph_query_examples("Organ", limit=2, filter_dict={"name": "demo"})[0]["limit"] == 2
    assert runtime.graph_property_filter("Organ", "NODE", {"name": "demo"}, get_all_properties=True)[0]["get_all_properties"] is True
    assert runtime.graph_property_info("Organ", "NODE", "Organ_1")["element_uuid"] == "Organ_1"
    assert runtime.graph_hop_search("Organ_1", 2, accurate_flag=True)[0]["accurate_flag"] is True
    assert runtime.graph_count_search("Organ", "NODE", {}) == 3
    assert runtime.graph_aggregate_search("Organ", "NODE", "amount", "COUNT", {})["agg_func"] == "COUNT"
    assert runtime.graph_sorted_search("Organ", "NODE", sort_by="name")[0]["sort_by"] == "name"
    assert runtime.graph_pattern_search([["Organ", {}]], return_vars=["a"])[0]["return_vars"] == ["a"]
