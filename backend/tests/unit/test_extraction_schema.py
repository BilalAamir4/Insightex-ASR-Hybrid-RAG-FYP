"""M7 extraction schema v1 (ADR-0048): production copy, tool copy, and the JSON Schema stay in step."""

import json

import pytest

from insightex.core.config import repo_root
from insightex.extract import extraction_schema as es

TOOL_DIR = repo_root() / "tools" / "label_concepts"
PROD_DIR = repo_root() / "backend" / "src" / "insightex" / "extract"


@pytest.mark.parametrize("name", ["extraction_schema.py", "extraction.schema.json"])
def test_tool_copy_is_byte_identical(name):
    """tools/ may not import backend/, so it keeps its own copy; this test is what keeps the copies equal."""
    assert (TOOL_DIR / name).read_bytes() == (PROD_DIR / name).read_bytes(), f"copy {name} again to {TOOL_DIR}"


def test_schema_constants_match_the_json_schema():
    schema = es.load_schema()
    assert schema["properties"]["schema_version"]["const"] == es.SCHEMA_VERSION == 1
    assert tuple(schema["$defs"]["relation"]["properties"]["type"]["enum"]) == es.RELATION_TYPES
    assert tuple(schema["properties"]["producer"]["properties"]["kind"]["enum"]) == es.PRODUCER_KINDS
    assert schema["$defs"]["nonblank"]["maxLength"] == es.NAME_MAX
    assert schema["$defs"]["window_record"]["then"]["properties"]["cue"]["maxLength"] == es.CUE_MAX


def model_output():
    return {"schema_version": 1, "lecture_id": "yt-x", "producer": {"kind": "model", "name": "qwen3.5:latest"},
            "windows": [{"window": {"lecture_id": "yt-x", "window_index": 0, "start_s": 0, "end_s": 30},
                         "concepts": [{"label": "gradient descent", "aliases": ["GD"]},
                                      {"label": "learning rate", "aliases": []}],
                         "relations": [{"head": "learning rate", "type": "part_of", "tail": "gradient descent"}],
                         "important": False, "cue": None, "is_recap": False}]}


def test_production_validator_accepts_model_output_and_the_json_schema_agrees():
    doc = model_output()
    assert es.check_document(doc) == []
    jsonschema = pytest.importorskip("jsonschema")
    jsonschema.Draft202012Validator(json.loads(es.SCHEMA_PATH.read_text(encoding="utf-8"))).validate(doc)


def test_production_validator_rejects_a_dangling_relation():
    doc = model_output()
    doc["windows"][0]["relations"][0]["tail"] = "stochastic gradient descent"
    assert any("not the label of a concept" in e for e in es.check_document(doc))


def test_concepts_and_relations_are_capped_at_list_max():
    """At most LIST_MAX (10) concepts and 10 relations per window (ADR-0049); the JSON Schema says the same."""
    schema = es.load_schema()
    props = schema["$defs"]["window_record"]["properties"]
    assert props["concepts"]["maxItems"] == props["relations"]["maxItems"] == es.LIST_MAX == 10
    doc = model_output()
    rec = doc["windows"][0]
    rec["concepts"] = [{"label": f"concept {i}", "aliases": []} for i in range(10)]
    rec["relations"] = [{"head": "concept 0", "type": "part_of", "tail": f"concept {i}"} for i in range(1, 10)]
    rec["relations"].append({"head": "concept 1", "type": "part_of", "tail": "concept 2"})
    assert es.check_document(doc) == []  # exactly 10 of each is allowed
    rec["concepts"].append({"label": "concept 10", "aliases": []})
    rec["relations"].append({"head": "concept 1", "type": "part_of", "tail": "concept 3"})
    errors = es.check_document(doc)
    assert any("concepts: at most 10 items, got 11" in e for e in errors)
    assert any("relations: at most 10 items, got 11" in e for e in errors)
    jsonschema = pytest.importorskip("jsonschema")
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(doc, schema)


def test_model_output_format_carries_the_same_cap():
    from insightex.extract.prompts import extraction_format

    record = extraction_format([3, 4])["properties"]["windows"]["items"]
    assert record["properties"]["concepts"]["maxItems"] == record["properties"]["relations"]["maxItems"] == 10
