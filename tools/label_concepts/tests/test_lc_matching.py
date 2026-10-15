"""ADR-0048 matching rule: normalised label/alias equality, one-to-one, adjudication, relations, F1 edge cases."""

from lc_fixtures import concept, labels, rel
from matching import f1, match_window, micro


def test_label_matches_after_normalisation():
    s = match_window(labels([concept("Batch-Learning")]), labels([concept("batch learning")]), 0)
    assert (s.concept_tp, s.concept_f1) == (1, 1.0)
    assert s.pairs == [("Batch-Learning", "batch learning", "string")]


def test_alias_to_label_and_alias_to_alias():
    gold = labels([concept("batch learning", "offline learning"), concept("online learning", "incremental mode")])
    pred = labels([concept("offline learning"), concept("streaming", "Incremental Mode")])
    s = match_window(pred, gold, 0)
    assert s.concept_tp == 2


def test_no_match_on_partial_overlap_of_words():
    s = match_window(labels([concept("learning")]), labels([concept("batch learning")]), 0)
    assert s.concept_tp == 0 and s.concept_f1 == 0.0


def test_matching_is_one_to_one():
    gold = labels([concept("batch learning", "offline learning")])
    pred = labels([concept("batch learning"), concept("offline learning")])
    s = match_window(pred, gold, 0)
    assert (s.concept_tp, s.concept_pred, s.concept_ref) == (1, 2, 1)
    assert [c["label"] for c in s.unmatched_pred] == ["offline learning"]


def test_maximum_matching_not_greedy():
    # pred0 could take g0 or g1; pred1 can only take g0. A greedy pass gives 1, the maximum is 2.
    gold = labels([concept("model", "estimator"), concept("predictor", "regressor")])
    pred = labels([concept("estimator", "regressor"), concept("model")])
    assert match_window(pred, gold, 0).concept_tp == 2


def test_adjudication_match_no_match_pending_and_taken():
    gold = labels([concept("recommender system"), concept("spam filter")])
    pred = labels([concept("recommendation engine"), concept("email classifier"), concept("netflix"),
                   concept("spam filter")])
    adj = {(4, "recommendationengine"): "recommender system", (4, "emailclassifier"): "spam filter",
           (4, "netflix"): None}
    s = match_window(pred, gold, 4, adj)
    assert s.concept_tp == 2  # string match spam filter, adjudicated recommender system
    assert ("recommendation engine", "recommender system", "adjudicated") in s.pairs
    assert [c["label"] for c in s.unmatched_pred] == ["email classifier", "netflix"]  # target taken; no-match
    assert s.pending_pred == []
    s = match_window(pred, gold, 5, adj)  # entries are per window
    assert [c["label"] for c in s.pending_pred] == ["recommendation engine", "email classifier", "netflix"]


def test_adjudication_never_overrides_a_string_match():
    gold = labels([concept("batch learning")])
    pred = labels([concept("batch learning")])
    s = match_window(pred, gold, 0, {(0, "batchlearning"): None})
    assert s.concept_tp == 1


def test_relations_respect_direction_except_contrasts_with():
    gold = labels([concept("A"), concept("B")], [rel("A", "part_of", "B"), rel("A", "contrasts_with", "B")])
    pred = labels([concept("a"), concept("b")], [rel("b", "part_of", "a"), rel("b", "contrasts_with", "a")])
    s = match_window(pred, gold, 0)
    assert (s.relation_tp, s.relation_pred, s.relation_ref) == (1, 2, 2)


def test_relation_type_must_be_equal_and_endpoints_matched():
    gold = labels([concept("A"), concept("B")], [rel("A", "example_of", "B")])
    assert match_window(labels([concept("A"), concept("B")], [rel("A", "part_of", "B")]), gold, 0).relation_tp == 0
    pred = labels([concept("A"), concept("C")], [rel("A", "example_of", "C")])
    assert match_window(pred, gold, 0).relation_tp == 0


def test_relations_follow_adjudicated_endpoints():
    gold = labels([concept("A"), concept("B")], [rel("A", "example_of", "B")])
    pred = labels([concept("A"), concept("Bee")], [rel("A", "example_of", "Bee")])
    assert match_window(pred, gold, 2, {(2, "bee"): "B"}).relation_tp == 1


def test_f1_edge_cases_and_micro():
    assert f1(0, 0, 0) == 1.0 and f1(0, 1, 0) == 0.0 and f1(0, 0, 2) == 0.0
    empty = match_window(labels(), labels(), 0)
    assert empty.concept_f1 == 1.0 and empty.relation_f1 == 1.0
    one = match_window(labels([concept("A")], important=True, cue="x"), labels([concept("A"), concept("B")]), 1)
    m = micro([empty, one])
    assert m["concept"] == {"tp": 1, "pred": 1, "ref": 2, "precision": 1.0, "recall": 0.5, "f1": 2 / 3}
    assert m["important"]["pred"] == 1 and m["important"]["ref"] == 0 and m["important"]["recall"] is None
    assert m["important"]["agreement"] == 0.5
