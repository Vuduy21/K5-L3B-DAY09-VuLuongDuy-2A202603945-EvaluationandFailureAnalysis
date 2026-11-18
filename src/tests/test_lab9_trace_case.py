"""Regression test for docs/trace_case.md: C-002 (ticket says 5 days late, the DB row says 2).

First wrong step: the `model_override` event (ticket value replaces the DB value). The swarm of Day 8
does this when seed % 5 == 0; `fixed` never does. Run: python -m pytest -q -m student -o addopts= -k lab9_trace
"""
import pytest

pytestmark = pytest.mark.student


def _grade(grader_cls, trial, label):
    from pydantic_evals.evaluators import EvaluatorContext

    ctx = EvaluatorContext(name="t", inputs={}, metadata=None, expected_output=label, output=trial,
                           duration=0.0, _span_tree=None, attributes={}, metrics={})
    return grader_cls().evaluate(ctx).value


def _case(shape, seed):
    from lab9.trace_case import investigate

    return investigate(shape, "C-002", seed)


def _kinds(trial):
    return [e["kind"] for e in trial["events"]]


def test_swarm_seed_55_overrides_db_with_ticket():
    from lab9 import graders

    case = _case("swarm", 55)
    trial, label = case["trial"], case["label"]
    assert trial["lab8_pass"] is False
    override = next(e for e in trial["events"] if e["kind"] == "model_override")
    assert override["payload"] == {"delay_days": 5}                      # ticket value, DB says 2
    assert _kinds(trial).index("model_override") < _kinds(trial).index("quote")   # first wrong step precedes the quote
    assert trial["snapshot"]["refund_vnd"] == 20000 and label["refund_vnd"] == 0
    assert _grade(graders.DbFactKept, trial, label) is False             # step-level grader sees the cause
    assert _grade(graders.RefundAmountCorrect, trial, label) is False    # outcome-level grader sees the effect


def test_seeded_regression_trips_the_same_graders():
    from lab9 import graders

    case = _case("seeded_regression", 11)
    trial, label = case["trial"], case["label"]
    assert "model_override" in _kinds(trial)
    assert _grade(graders.DbFactKept, trial, label) is False
    assert _grade(graders.RefundAmountCorrect, trial, label) is False


@pytest.mark.parametrize("seed", [11, 22, 33, 44, 55])
def test_fixed_never_overrides_db_fact(seed):
    from lab9 import graders

    case = _case("fixed", seed)
    trial, label = case["trial"], case["label"]
    assert trial["lab8_pass"] is True
    assert "model_override" not in _kinds(trial)
    assert trial["snapshot"]["refund_vnd"] == 0 and trial["result"]["status"] == "denied"
    assert _grade(graders.DbFactKept, trial, label) is True
    assert _grade(graders.RefundAmountCorrect, trial, label) is True
