"""Extraction schema v1: the stdlib validator, and agreement with the JSON Schema file where jsonschema exists."""

import copy

import pytest
from extraction_schema import check_document, check_window_record, load_schema, normalise
from lc_fixtures import concept, record, rel


def doc(*windows):
    return {"schema_version": 1, "lecture_id": "L", "producer": {"kind": "human", "name": "bilal"},
            "windows": list(windows)}


GOOD = doc(
    record("L", 0, 0, 30, concepts=[concept("batch learning", "offline learning", "بیچ لرننگ"),
                                    concept("online learning")],
           relations=[rel("batch learning", "contrasts_with", "online learning")], important=True,
           cue="Teacher says this is important."),
    record("L", 1, 30, 60),
)


def mutate(fn):
    d = copy.deepcopy(GOOD)
    fn(d)
    return d


# (name, document, structural?) structural cases must also fail the JSON Schema; semantic ones only the validator.
BAD = [
    ("wrong version", mutate(lambda d: d.update(schema_version=2)), True),
    ("unknown top field", mutate(lambda d: d.update(extra=1)), True),
    ("producer kind", mutate(lambda d: d["producer"].update(kind="robot")), True),
    ("bad sha", mutate(lambda d: d.update(sample_manifest_sha256="abc")), True),
    ("missing cue", mutate(lambda d: d["windows"][1].pop("cue")), True),
    ("cue without importance", mutate(lambda d: d["windows"][1].update(cue="x")), True),
    ("importance without cue", mutate(lambda d: d["windows"][1].update(important=True)), True),
    ("blank cue", mutate(lambda d: d["windows"][0].update(cue="  ")), True),
    ("blank label", mutate(lambda d: d["windows"][0]["concepts"][1].update(label=" ")), True),
    ("aliases not a list", mutate(lambda d: d["windows"][0]["concepts"][1].update(aliases="x")), True),
    ("unknown relation type", mutate(lambda d: d["windows"][0]["relations"][0].update(type="causes")), True),
    ("negative index", mutate(lambda d: d["windows"][1]["window"].update(window_index=-1)), True),
    ("bool index", mutate(lambda d: d["windows"][1]["window"].update(window_index=True)), True),
    ("is_recap not bool", mutate(lambda d: d["windows"][1].update(is_recap="yes")), True),
    ("unknown window field", mutate(lambda d: d["windows"][1].update(notes="x")), True),
    ("endpoint not a concept", mutate(lambda d: d["windows"][0]["relations"][0].update(tail="gradient descent")),
     False),
    ("self relation", mutate(lambda d: d["windows"][0]["relations"][0].update(tail="batch learning")), False),
    ("duplicate symmetric relation", mutate(lambda d: d["windows"][0]["relations"].append(
        rel("online learning", "contrasts_with", "batch learning"))), False),
    ("duplicate concept by normalisation", mutate(lambda d: d["windows"][0]["concepts"].append(
        concept("Online-Learning"))), False),
    ("alias shared across concepts", mutate(lambda d: d["windows"][0]["concepts"][1]["aliases"].append(
        "Offline learning")), False),
    ("alias repeats own label", mutate(lambda d: d["windows"][0]["concepts"][1]["aliases"].append(
        "ONLINE learning")), False),
    ("label only punctuation", mutate(lambda d: d["windows"][0]["concepts"][1].update(label="--")), False),
    ("end before start", mutate(lambda d: d["windows"][1]["window"].update(end_s=30)), False),
    ("duplicate window", mutate(lambda d: d["windows"][1]["window"].update(window_index=0)), False),
    ("window lecture differs", mutate(lambda d: d["windows"][1]["window"].update(lecture_id="M")), False),
]


def test_good_document_is_valid():
    assert check_document(GOOD) == []
    assert check_window_record(GOOD["windows"][0]) == []


def test_is_recap_is_optional():
    assert check_document(mutate(lambda d: d["windows"][1].update(is_recap=True))) == []


def test_directed_relations_in_both_directions_are_distinct():
    d = mutate(lambda d: d["windows"][0]["relations"].__setitem__(slice(None), [
        rel("batch learning", "part_of", "online learning"), rel("online learning", "part_of", "batch learning")]))
    assert check_document(d) == []


@pytest.mark.parametrize("name,bad,structural", BAD, ids=[b[0] for b in BAD])
def test_bad_documents_are_rejected(name, bad, structural):
    assert check_document(bad), name


@pytest.mark.parametrize("name,bad,structural", BAD, ids=[b[0] for b in BAD])
def test_json_schema_agrees_on_structure(name, bad, structural):
    jsonschema = pytest.importorskip("jsonschema")
    validator = jsonschema.Draft202012Validator(load_schema())
    assert validator.is_valid(GOOD)
    assert validator.is_valid(bad) is (not structural), name


def test_normalise():
    assert normalise("K-Means") == normalise("k means") == normalise("kmeans") == "kmeans"
    assert normalise("  Batch  Learning. ") == "batchlearning"
    assert normalise("ＭＬ") == "ml"  # NFKC folds full-width letters
    assert normalise("بیچ‌لرننگ،") == "بیچلرننگ"  # zero-width non-joiner and Urdu comma removed
    assert normalise("learning-rate (η)") == "learningrateη"
