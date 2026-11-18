"""M7 integrity_check on gaming attempts beyond the public traps. Run: pytest -m student -o addopts= -k advanced

Each case is a report (or spec) a motivated engineer might hand the gate. The gate must say INTEGRITY, and an
untouched report must still pass, because a gate that blocks honest work gets switched off.
"""
import copy
import math

import pytest

pytestmark = pytest.mark.student

SEEDS = (1, 2)
ROWS = [{"item_id": f"E-{i:03d}", "seed": s, "pass_rate": True, "slices": ["denial"] if i < 2 else [], "cost": 1.0}
        for i in range(4) for s in SEEDS]
SPEC = {"eval_set_version": "v2", "pass_k": [],
        "metrics": [{"id": "pass_rate", "kind": "capability", "blocking": True,
                     "threshold": {"min": 0.8, "no_significant_drop": True, "no_new_failures": True}}],
        "slices": [{"name": "denial", "metric": "pass_rate", "min": 0.9, "no_significant_drop": True, "blocking": True}]}


def report(rows=None, metrics=None, items=4, seeds=SEEDS, failures=()):
    rows = copy.deepcopy(ROWS if rows is None else rows)
    return {"manifest": {"eval_set_sha": "x", "items": items, "seeds": list(seeds)}, "rows": rows,
            "metrics": {"pass_rate": 1.0} if metrics is None else metrics, "evaluator_failures": list(failures)}


@pytest.fixture(scope="module")
def gate():
    from lab9 import gate

    return gate


def test_untouched_report_and_baseline_against_itself_pass(gate):
    base = report()
    assert gate.integrity_check(base, base, SPEC, SPEC) == []
    blocked, _ = gate.check(base, base, SPEC, SPEC)
    assert blocked == []


def test_duplicate_row_with_the_count_kept_right(gate):
    base = report()
    rows = copy.deepcopy(ROWS)
    rows[7] = copy.deepcopy(rows[0])          # a row dropped, another one repeated: 8 rows, 7 distinct
    problems = gate.integrity_check(report(rows), base, SPEC)
    assert any("duplicated" in p for p in problems) and any("missing" in p for p in problems)


def test_metrics_edited_by_hand_do_not_follow_from_the_rows(gate):
    base = report()
    rows = copy.deepcopy(ROWS)
    rows[0]["pass_rate"] = False
    problems = gate.integrity_check(report(rows, {"pass_rate": 1.0}), base, SPEC)
    assert any("rows give" in p for p in problems)


def test_manifest_rewritten_to_match_dropped_items(gate):
    base = report()
    rows = [r for r in ROWS if r["item_id"] != "E-003"]
    problems = gate.integrity_check(report(rows, items=3), base, SPEC)
    assert any("manifest differs" in p for p in problems)


def test_relabelling_an_item_out_of_a_slice(gate):
    base = report()
    rows = copy.deepcopy(ROWS)
    for r in rows:
        if r["item_id"] == "E-000":
            r["slices"] = []
    assert any("slice tags" in p for p in gate.integrity_check(report(rows), base, SPEC))


def test_grader_crash_on_an_otherwise_green_run(gate):
    base = report()
    assert gate.integrity_check(report(failures=["E-001@2:SecretLeak:boom"]), base, SPEC)


def test_score_erased_to_none_and_non_boolean_score(gate):
    base = report()
    rows = copy.deepcopy(ROWS)
    rows[0]["pass_rate"] = None
    assert any("no score" in p for p in gate.integrity_check(report(rows), base, SPEC))
    rows = copy.deepcopy(ROWS)
    rows[0]["pass_rate"] = 1
    assert any("non-boolean" in p for p in gate.integrity_check(report(rows), base, SPEC))


@pytest.mark.parametrize("value", [float("nan"), float("inf")])
def test_non_finite_metric(gate, value):
    base = report()
    assert any("metric pass_rate" in p for p in gate.integrity_check(report(metrics={"pass_rate": value}), base, SPEC))
    assert not math.isfinite(value)


@pytest.mark.parametrize("edit,needle", [
    (lambda s: s.__setitem__("slices", []), "was removed"),
    (lambda s: s["slices"][0].__setitem__("blocking", False), "no longer blocking"),
    (lambda s: s["slices"][0].__setitem__("min", 0.5), "loosened"),
    (lambda s: s["slices"][0].pop("no_significant_drop"), "no_significant_drop was dropped"),
    (lambda s: s.__setitem__("metrics", []), "was removed"),
    (lambda s: s["metrics"][0]["threshold"].__setitem__("min", 0.1), "loosened"),
    (lambda s: s["metrics"][0]["threshold"].pop("no_new_failures"), "no_new_failures was dropped"),
    (lambda s: s["metrics"][0].__setitem__("blocking", False), "no longer blocking"),
])
def test_ratchet_refuses_a_looser_spec(gate, edit, needle):
    base = report()
    loose = copy.deepcopy(SPEC)
    edit(loose)
    assert any(needle in p for p in gate.integrity_check(base, base, loose, SPEC))


def test_ratchet_allows_a_stricter_spec_and_a_new_eval_set_version(gate):
    base = report()
    strict = copy.deepcopy(SPEC)
    strict["metrics"][0]["threshold"]["min"] = 0.95
    assert gate.integrity_check(base, base, strict, SPEC) == []
    newer = copy.deepcopy(SPEC)
    newer["eval_set_version"] = "v3"
    newer["metrics"][0]["threshold"]["min"] = 0.1
    assert gate.integrity_check(base, base, newer, SPEC) == []      # a new eval set starts a new ratchet


def test_new_failures_catch_a_bug_that_moved_to_another_seed(gate):
    """Same number of failing trials as the baseline, on different ones: every mean is identical."""
    base_rows = copy.deepcopy(ROWS)
    base_rows[0]["pass_rate"] = False                   # baseline fails E-000@1
    pr_rows = copy.deepcopy(ROWS)
    pr_rows[1]["pass_rate"] = False                     # the PR fails E-000@2 instead
    base = report(base_rows, {"pass_rate": 0.875})
    pr = report(pr_rows, {"pass_rate": 0.875})
    blocked, lines = gate.check(pr, base, SPEC)
    assert "pass_rate" in blocked and any("newly failing" in line for line in lines)
