#!/usr/bin/env python3
"""roundcost.py - the ONE place that knows how to read cost out of a transcript.

Why this exists (harness 4.2, 2026-09-04):
A `claude -p` invocation can emit MORE THAN ONE result event. When the agent
starts a background task, the CLI wakes the session when that task finishes and
emits a fresh `system/init` + a fresh `result`. Every such result carries the
CUMULATIVE total for the whole invocation, not that segment's increment --
verified on cell 1 r00, where result 2's modelUsage reads outputTokens 73392 =
71820 + 1572 and cacheRead 19,576,916 = 18,709,135 + 867,781, and the haiku
entry is byte-identical in both rather than doubled.

So: SUM ACROSS ROUNDS, LAST-WINS WITHIN A ROUND. Summing every result event --
which is what cell_cost.py did through harness 4.1 -- double-counts any round in
which the agent used a background task. It inflated cell 1 from $19.39 to
$37.87. Do not "simplify" this back into a sum.

An invocation boundary is a FILE (one round = one `claude -p`), not an `init`
event: the background-task wake-up emits its own init inside the same
invocation, so segmenting on init reproduces the double count.

WHICH FIELDS ARE CUMULATIVE AND WHICH ARE NOT (harness 4.3, 2026-09-06).
The last-wins rule above is correct for cost, and WRONG for everything else,
because a result event mixes two kinds of field. Verified on
20260905-161349-arm-a-degraded-C3-withdraw-notify-s3 r00, four results:

  CUMULATIVE, take the last          PER-INVOCATION, must be SUMMED
  ------------------------           ------------------------------
  total_cost_usd 15.49->17.52        usage.*        out 92875, 1258, 1383, 1010
  modelUsage.*   out 92875->96526    num_turns      158, 8, 3, 4
                                     duration_ms    1260574, 27481, 19459, 17541

and the two agree exactly: 92875+1258+1383+1010 = 96526 = the last modelUsage.
That identity is a free cross-check and `usage_sum_matches_modelusage()` asserts
it. Taking the last result's `usage`/`num_turns` -- which is what happens if you
reuse the cost list for them -- reports the background wake-up alone: 6 turns and
2,066 output tokens for a run that actually took 209 turns and 135,021.
"""
import json
from pathlib import Path

TOKKEYS = ("input_tokens", "output_tokens",
           "cache_read_input_tokens", "cache_creation_input_tokens")


def results_in(path):
    """Every result event in one transcript file, in order."""
    out = []
    try:
        text = Path(path).read_text(errors="replace")
    except OSError:
        return out
    for line in text.splitlines():
        if '"result"' not in line:
            continue
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        if e.get("type") == "result":
            out.append(e)
    return out


def final_result(path):
    """The authoritative result for one invocation: the last one it emitted."""
    r = results_in(path)
    return r[-1] if r else None


def round_files(run_dir):
    """Per-round transcripts if this is a v4 cell, else the single transcript."""
    rd = sorted(Path(run_dir).glob("rounds/r*/transcript.jsonl"))
    if rd:
        return rd
    single = Path(run_dir) / "transcript.jsonl"
    return [single] if single.exists() else []


def round_number(path):
    import re
    m = re.search(r"/r(\d+)/", str(path))
    return int(m.group(1)) if m else 0


def per_round(run_dir, through=None):
    """[(round_no, final_result_or_None)], optionally only rounds <= through."""
    out = []
    for f in round_files(run_dir):
        n = round_number(f)
        if through is not None and n > through:
            continue
        out.append((n, final_result(f)))
    return out


def cross_round_cumulative(run_dir):
    """Does total_cost_usd/modelUsage accumulate ACROSS rounds (resumed session)?

    Harness 6.0 / Claude Code 2.1.310 (verified 2026-10-26 on every multi-round
    FeatureBench cell): a round resumed with --resume reports modelUsage and
    total_cost_usd for the WHOLE SESSION so far, e.g. astropy test_containers
    r03 modelUsage.outputTokens 113017 = 36682+44384+28894+3057 = the summed
    per-invocation usage of r00..r03. Summing rounds then double-counts (mlflow
    test_mlflow: $22.27 naive vs $7.52 real). Detected, not assumed: a round
    n>=1 whose last modelUsage output count exceeds that round's own summed usage
    and matches the running total means cumulative. Returns False for a cell with
    one round (nothing to decide) or for a CLI that resets on resume.
    """
    cum = 0
    for n, results in all_results(run_dir):
        own = sum((r.get("usage") or {}).get("output_tokens") or 0 for r in results)
        cum += own
        if not results or n == 0:
            continue
        mu = sum((u.get("outputTokens") or 0)
                 for u in (results[-1].get("modelUsage") or {}).values())
        if mu > own and mu >= 0.98 * cum:
            return True
    return False


def total_cost(run_dir, through=None):
    """Dollars spent through round <through> (all rounds when None).

    Last-wins within a round always; across rounds, last-wins too when the CLI
    carries cost over --resume (see cross_round_cumulative), else summed.
    """
    rs = [r for _, r in per_round(run_dir, through) if r]
    if not rs:
        return 0.0
    if cross_round_cumulative(run_dir):
        return float(rs[-1].get("total_cost_usd") or 0.0)
    return sum((r.get("total_cost_usd") or 0.0) for r in rs)


def all_results(run_dir, through=None):
    """[(round_no, [every result event in that round, in order])].

    Use this for per-invocation fields (usage, num_turns, duration_ms).
    `per_round` above keeps the last result only and is for cumulative fields.
    """
    out = []
    for f in round_files(run_dir):
        n = round_number(f)
        if through is not None and n > through:
            continue
        out.append((n, results_in(f)))
    return out


def usage_sum_matches_modelusage(results):
    """Cross-check one round: summed per-invocation usage == last modelUsage.

    Returns {key: bool} over TOKKEYS, or {} when the round has no modelUsage to
    check against. cache_creation is not carried in modelUsage and is skipped.
    """
    if not results:
        return {}
    mu = (results[-1].get("modelUsage") or {})
    opus = {k: v for k, v in mu.items() if "opus" in k}
    if len(opus) != 1:
        return {}
    last = next(iter(opus.values()))
    summed = {k: sum((r.get("usage") or {}).get(k) or 0 for r in results)
              for k in TOKKEYS}
    return {"input_tokens": summed["input_tokens"] == (last.get("inputTokens") or 0),
            "output_tokens": summed["output_tokens"] == (last.get("outputTokens") or 0),
            "cache_read_input_tokens":
                summed["cache_read_input_tokens"] == (last.get("cacheReadInputTokens") or 0)}
