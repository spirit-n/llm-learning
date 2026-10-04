import pytest

from context_lab.tool_discovery import DeferredToolCatalog, ToolDefinition, run_tool_discovery_experiment


def test_deferred_loading_reduces_schema_budget_and_preserves_fixture_recall():
    result = run_tool_discovery_experiment()
    assert result["tool_recall"] == result["tool_precision"] == 1.0
    assert result["selected_tools"] == result["schemas_loaded"] == ["metric_definition"]
    assert result["deferred_definition_tokens"] < result["eager_definition_tokens"]
    assert result["extra_discovery_steps"] == 2


def test_permission_filter_happens_before_discovery_search_and_loading():
    hidden = ToolDefinition("secret", "敏感目录", ("keyword",), "admin", {"type": "object"})
    catalog = DeferredToolCatalog([hidden], scopes=frozenset({"read"}))
    assert catalog.lightweight_index() == []
    assert catalog.search("keyword") == ()
    with pytest.raises(PermissionError, match="unavailable"):
        catalog.load_schema("secret")
    assert catalog.loaded_schema_names == []


def test_index_and_search_do_not_load_schema_and_unknown_query_does_not_guess():
    tool = ToolDefinition("one", "目录", ("keyword",), "read", {"type": "object"})
    catalog = DeferredToolCatalog([tool], scopes=frozenset({"read"}))
    catalog.lightweight_index()
    assert catalog.search("unknown") == ()
    assert catalog.search("KEYWORD") == ("one",)
    assert catalog.loaded_schema_names == []
    catalog.load_schema("one")
    catalog.load_schema("one")
    assert catalog.loaded_schema_names == ["one"]


def test_schema_result_is_not_a_mutable_alias_of_the_catalog():
    tool = ToolDefinition("one", "目录", ("keyword",), "read", {"type": "object"})
    catalog = DeferredToolCatalog([tool], scopes=frozenset({"read"}))
    catalog.load_schema("one")["parameters"]["type"] = "array"
    assert catalog.load_schema("one")["parameters"]["type"] == "object"
