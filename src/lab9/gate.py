"""CI gate: compare a PR eval report with the main-branch baseline using the metric spec.

    python -m lab9.gate --pr reports/eval_workflow.json --baseline reports/baseline_v1.json

exit 0 = merge, exit 1 = blocked. Safety metrics: max 0, no averaging away.
Capability metrics: meet the floor AND the paired CI of (PR - main) is not entirely below 0.
Thresholds may only get stricter on the same eval-set version (ratchet).
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from lab8.console import utf8_stdio
from lab9 import stats
from lab9.eval import SPEC, load_spec, per_item


def integrity_check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> list[str]:
    """M7 (Expert): refuse to compare reports that cannot be trusted. Return a list of problems
    (empty = trustworthy). A gate that passes a broken report is worse than no gate.
    Must catch at least:
      - any metric value in pr["metrics"] that is NaN or inf
      - len(pr["rows"]) != manifest items x len(manifest seeds)   (dropped / duplicated rows)
      - the (item_id, seed) set of PR differs from the baseline's (cherry-picked seeds/items)
      - pr["evaluator_failures"] non-empty, or a row whose value for a graded spec metric is
        None (a crashed grader silently scores as "missing" and drops out of the mean)
      - base_spec given and a threshold in spec is LOOSER than in base_spec for the same
        eval-set version (ratchet: max may not rise, min may not fall, a blocking metric may
        not become non-blocking, a metric may not disappear; the same for spec["slices"],
        including dropping no_significant_drop)
      - an item's slice tags in PR rows differ from the baseline's (relabelling an item out of a
        slice hides its regression from the slice gate)

    Beyond that list: a duplicated (item, seed) row (count kept right by dropping a failing row and
    repeating a passing one), a row value that is not a plain True/False/None, and metrics that no
    longer follow from the rows (a hand-edited report). The manifest of the PR is compared with the
    baseline's, never trusted alone: a cheater can rewrite the PR's own manifest to match its rows."""
    problems: list[str] = []
    graded = _graded_metrics(spec, base)

    # 1. numbers that fall out of every comparison: NaN < min is False, so a naive gate passes it
    for k, v in (pr.get("metrics") or {}).items():
        if isinstance(v, float) and not math.isfinite(v):
            problems.append(f"metric {k} is {v}")

    # 2. grader crashes
    if pr.get("evaluator_failures"):
        problems.append(f"{len(pr['evaluator_failures'])} evaluator failure(s), first: {pr['evaluator_failures'][0]}")

    rows = pr.get("rows") or []
    keys = [(r.get("item_id"), r.get("seed")) for r in rows]
    base_keys = [(r.get("item_id"), r.get("seed")) for r in base.get("rows") or []]

    # 3. row count and duplicates, against the manifest and against the baseline
    pm, bm = pr.get("manifest") or {}, base.get("manifest") or {}
    want = int(bm.get("items", 0)) * len(bm.get("seeds") or [])
    if len(rows) != want:
        problems.append(f"{len(rows)} rows, the baseline manifest says {want} ({bm.get('items')} items x {len(bm.get('seeds') or [])} seeds)")
    own = int(pm.get("items", 0)) * len(pm.get("seeds") or [])
    if own != len(rows):
        problems.append(f"{len(rows)} rows but the PR's own manifest says {own}")
    if (pm.get("items"), sorted(pm.get("seeds") or [])) != (bm.get("items"), sorted(bm.get("seeds") or [])):
        problems.append(f"manifest differs from the baseline's: items {pm.get('items')} vs {bm.get('items')}, seeds {pm.get('seeds')} vs {bm.get('seeds')}")
    dup = sorted({k for k in keys if keys.count(k) > 1}, key=str)
    if dup:
        problems.append(f"duplicated (item, seed) row(s): {', '.join(f'{i}@{s}' for i, s in dup[:5])}")

    # 4. the same (item, seed) set as the baseline: no cherry-picked seeds, no missing or extra items
    missing, extra = sorted(set(base_keys) - set(keys), key=str), sorted(set(keys) - set(base_keys), key=str)
    if missing:
        problems.append(f"{len(missing)} (item, seed) from the baseline missing, e.g. {missing[0][0]}@{missing[0][1]}")
    if extra:
        problems.append(f"{len(extra)} (item, seed) not in the baseline, e.g. {extra[0][0]}@{extra[0][1]}")

    # 5. every graded metric has a plain True/False on every row; None means the grader never scored it
    for m in graded:
        none = [k for r, k in zip(rows, keys) if r.get(m) is None]
        odd = [k for r, k in zip(rows, keys) if r.get(m) is not None and not isinstance(r.get(m), bool)]
        if none:
            problems.append(f"{len(none)} row(s) with no score for {m}, e.g. {none[0][0]}@{none[0][1]}")
        if odd:
            problems.append(f"{len(odd)} row(s) with a non-boolean score for {m}")

    # 6. the reported metrics must follow from the rows
    problems += _metrics_not_from_rows(pr, rows, graded, spec)

    # 7. relabelling an item out of a slice hides its regression from the slice gate
    tags = {r["item_id"]: sorted(r.get("slices") or []) for r in base.get("rows") or []}
    moved = sorted({r["item_id"] for r in rows if r.get("item_id") in tags and sorted(r.get("slices") or []) != tags[r["item_id"]]})
    if moved:
        problems.append(f"slice tags differ from the baseline's for {', '.join(moved[:5])}")

    # 8. ratchet: only on the same eval-set version
    if base_spec is not None and base_spec.get("eval_set_version") == spec.get("eval_set_version"):
        problems += _ratchet(spec, base_spec)
    return problems


def _graded_metrics(spec: dict, base: dict) -> list[str]:
    """Spec metrics that the harness scores per row (they are keys of the baseline's rows)."""
    first = (base.get("rows") or [{}])[0]
    return [m["id"] for m in spec.get("metrics", []) if m["id"] in first]


def _metrics_not_from_rows(pr: dict, rows: list[dict], graded: list[str], spec: dict) -> list[str]:
    """Recompute what a report claims from its own rows; a hand-edited number will not match."""
    if not rows:
        return []
    from lab9.eval import aggregate
    out = []
    try:
        fixed = [{**r, "cost": r.get("cost", 0.0)} for r in rows]
        again = aggregate(fixed, [m for m in graded if m in rows[0]], k_values=spec.get("pass_k", []))
    except Exception as exc:     # rows too broken to aggregate are themselves the finding
        return [f"rows cannot be re-aggregated: {exc}"]
    has_cost = all("cost" in r for r in rows)
    for k, v in (pr.get("metrics") or {}).items():
        if k not in again or (k == "cost_per_success" and not has_cost):
            continue
        a = again[k]
        if v is None or a is None or isinstance(v, float) and not math.isfinite(v):
            continue                  # already reported above, or undefined for these rows
        if abs(float(v) - float(a)) > 1e-3:
            out.append(f"metric {k} is {v} but its rows give {a}")
    return out


def _ratchet(spec: dict, base_spec: dict) -> list[str]:
    """A threshold may only get stricter on the same eval-set version."""
    out = []
    new = {m["id"]: m for m in spec.get("metrics", [])}
    for bm in base_spec.get("metrics", []):
        out += _ratchet_entry(f"metric {bm['id']}", new.get(bm["id"]), bm)
    new_sl = {(s["name"], s["metric"]): s for s in spec.get("slices") or []}
    for bs in base_spec.get("slices") or []:
        out += _ratchet_entry(f"slice {bs['name']}/{bs['metric']}", new_sl.get((bs["name"], bs["metric"])), bs)
    return out


def _ratchet_entry(label: str, now: dict | None, was: dict) -> list[str]:
    if now is None:
        return [f"{label} was removed from the spec"]
    out = []
    # metrics keep their limits under "threshold"; slices keep them on the entry itself
    t_now, t_was = (now.get("threshold", now) or {}), (was.get("threshold", was) or {})
    if was.get("blocking") and not now.get("blocking"):
        out.append(f"{label} is no longer blocking")
    for k, loose in (("min", lambda n, w: n < w), ("max", lambda n, w: n > w), ("max_increase", lambda n, w: n > w)):
        if k in t_was:
            if k not in t_now:
                out.append(f"{label}: {k} was dropped")
            elif loose(t_now[k], t_was[k]):
                out.append(f"{label}: {k} loosened from {t_was[k]} to {t_now[k]}")
    for flag in ("no_significant_drop", "no_new_failures"):
        if t_was.get(flag) and not t_now.get(flag):
            out.append(f"{label}: {flag} was dropped")
    return out


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """M5 (Advanced): an average can hide a regression on a small, important slice.
    For each entry of spec["slices"] ({"name", "metric", "min"?, "no_significant_drop"?, "blocking"}):
      - value = mean of per_item(pr, metric, slice_name=name)
      - fail if below "min", or if no_significant_drop and the paired CI over the slice's items
        lies entirely below 0
    Return (blocked ids like "slice:money_movement/pass_rate", report lines)."""
    bs = spec.get("bootstrap", {})
    blocked: list[str] = []
    lines: list[str] = []
    for sl in spec.get("slices") or []:
        name, metric = sl["name"], sl["metric"]
        sid = f"slice:{name}/{metric}"
        a, b = per_item(pr, metric, slice_name=name), per_item(base, metric, slice_name=name)
        verdict, note = "ok", ""
        if not a:
            # No scored row for this slice: it cannot be verified, which is not the same as passing.
            verdict, note = "fail", "no scored rows in this slice"
            val = None
        else:
            val = sum(a.values()) / len(a)
            if "min" in sl and val < sl["min"]:
                verdict = "fail"
            if sl.get("no_significant_drop"):
                keys = sorted(set(a) & set(b))
                if keys:
                    d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                                       n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
                    note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}] n={len(keys)}"
                    if hi < 0:
                        verdict = "fail"
                else:
                    verdict, note = "fail", "no item in common with the baseline slice"
        if verdict != "ok" and sl.get("blocking"):
            blocked.append(sid)
        label = "ok" if verdict == "ok" else ("BLOCK" if sl.get("blocking") else "warn")
        shown = "—" if val is None else f"{val:.4f}"
        lines.append(f"  {sid:<34} {shown:<8} {json.dumps({k: sl[k] for k in ('min', 'no_significant_drop') if k in sl}):<40} {note:<34} {label}")
    return blocked, lines


def new_failures(pr: dict, base: dict, metric: str) -> list[tuple[str, int]]:
    """(item, seed) trials that passed on the baseline and fail on the PR.

    An average cannot see a regression that fails the same NUMBER of trials as the baseline but
    on different ones (a bug that moves from seed 55 to seed 33 leaves every mean unchanged).
    Each trial is deterministic here, so a trial that used to pass and now fails is a regression
    whatever the means say. With a real LLM this needs a tolerance (see docs/eval_card.md)."""
    was = {(r["item_id"], r["seed"]): r.get(metric) for r in base["rows"]}
    return sorted((r["item_id"], r["seed"]) for r in pr["rows"]
                  if r.get(metric) is False and was.get((r["item_id"], r["seed"])) is True)


def check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> tuple[list[str], list[str]]:
    if pr["manifest"]["eval_set_sha"] != base["manifest"]["eval_set_sha"]:
        return ["eval_set_sha"], ["  EVAL SET differs from the baseline's: re-run the baseline on the same eval set"]
    problems = integrity_check(pr, base, spec, base_spec)
    if problems:
        return ["integrity"], [f"  INTEGRITY {p}" for p in problems]
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for m in spec["metrics"]:
        mid, th, val = m["id"], m.get("threshold", {}), pr["metrics"].get(m["id"])
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif "max" in th and val > th["max"]:
            verdict = "fail"
        elif "min" in th and val < th["min"]:
            verdict = "fail"
        elif "max_increase" in th and base["metrics"].get(mid):
            if val > base["metrics"][mid] * (1 + th["max_increase"]):
                verdict = "fail"
        if th.get("no_significant_drop") and val is not None:
            a, b = per_item(pr, mid), per_item(base, mid)
            keys = sorted(set(a) & set(b))
            d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                               n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
            note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            if hi < 0:
                verdict = "fail"
        if th.get("no_new_failures") and val is not None:
            new = new_failures(pr, base, mid)
            if new:
                verdict = "fail"
                note = (note + " " if note else "") + f"{len(new)} newly failing trial(s), e.g. {new[0][0]}@{new[0][1]}"
        if verdict != "ok" and m.get("blocking"):
            blocked.append(mid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if m.get("blocking") else "warn")
        lines.append(f"  {mid:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    if spec.get("slices"):
        sb, sl = slice_check(pr, base, spec)
        blocked += sb
        lines += sl
    return blocked, lines


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.gate")
    ap.add_argument("--pr", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--base-spec", help="metric spec on main, for the ratchet check (M7)")
    args = ap.parse_args(argv)
    pr = json.loads(Path(args.pr).read_text(encoding="utf-8"))
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    base_spec = load_spec(Path(args.base_spec)) if args.base_spec else None
    blocked, lines = check(pr, base, load_spec(Path(args.spec)), base_spec)
    print(f"gate: PR {pr['run_id']} vs main {base['run_id']} · eval set {pr['manifest']['eval_set_sha']}")
    print("\n".join(lines))
    if blocked:
        print(f"exit 1 — blocked: {', '.join(blocked)}")
        return 1
    print("exit 0 — merge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
