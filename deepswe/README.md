# DeepSWE (Datacurve, 2026): 50-task study of change spread

The benchmark is DeepSWE v1.1, in Harbor format. Each task has `instruction.md`, `tests/` (`test.sh`, `grader.py`,
`test.patch`) and `solution/solution.patch`. Task images come from `public.ecr.aws/d3j8x8q7/swe-bench-202605:<id>-v1.1`.
Reward is 1 only if every fail-to-pass test passes and no pass-to-pass test fails.

## Task selection (`lists/`)

- **Flagged tasks are excluded.** Epoch AI's 23 flagged tasks (`epoch_flagged_tasks.txt`) are removed before selection.
- **Packages are counted by real package unit** (`units_deepswe.py` → `deepswe_units.tsv`):
  - TS/JS: the nearest `package.json`, `deno.json`, `deno.jsonc` or `jsr.json` at the base commit;
  - Rust: the nearest `Cargo.toml`;
  - Go and Python: the directory.
- **50 tasks span the whole range,** from single-package tasks to the most scattered (`select50_deepswe.py` →
  `deepswe_selected50.tsv`, `selected50.txt`). File count and spread are decoupled (Spearman 0.18); for example, there
  are 5-file tasks with 1 package and 5-file tasks with 4.
- **Language is a covariate.** TS and JS tasks are almost always 1 package, so the multi-package tasks come mostly from Go and Python.
- **The pilot** is 10 tasks (`pilot10.txt`), a subset of the 50 covering every language, from localized to scattered.
  Its results are in `PILOT_REPORT.md`.

## Harness (`harness/`)

This is a port of `swebench-pro/harness`, with the same isolation as described in the top-level `ISOLATION.md`:
- an internal network with an allowlist proxy;
- an empty HOME;
- no MCP servers and no web tools;
- uid 1000;
- the hidden tests, solution and verifier are never in the agent container;
- grading in a fresh `--network none` container after every round;
- blind feedback.

**The steps for each task:**
1. `make_task.py <task>` creates `tasks/<task>/`, containing:
   - `prompt.txt`, which is `instruction.md` byte for byte;
   - `meta.json`;
   - for the grader only, `verifier/` (= `tests/`) and `gold.patch`.
2. `build_image.sh <task>` builds the task image unchanged, plus the vendored CLI 2.1.310.
3. `preflight_task.sh <task>` checks hygiene, that the gold patch passes and an empty change fails, and runs
   leave-one-file-out. The results go to `preflight.json`.
4. `launch_one.sh <task>` runs one agent run (`run_one.sh` → `run_cell.sh`), then saves the readable traces, the
   egress log and a state line. Tasks run strictly one at a time, with up to 20 rounds per task (round 0 + 19 blind).
5. `audit_runs.py` runs the isolation and leakage audit, `regrade.sh` re-grades each final diff in a new container,
   and `../lists/agent_spread.py` puts the agent's own spread next to the task's.

**Harness versions:**
- **`ds-1.0`:** the 10 pilot runs.
- **`ds-1.1`:** the 50-task run. It adds three things after the pilot:
  - **Skills off:** `--disable-slash-commands`, so `skills: []` in every run.
  - **Neutral git identity:** `DeepSWE <ds@bench.com>`, both as system git config and as `GIT_AUTHOR_*`/`GIT_COMMITTER_*` env.
  - **Committed-only grading:** `git diff base HEAD`, the official DeepSWE view, is recorded and graded every round next
    to our working-tree grading. The results are in `rounds.tsv`, as `accept_committed`/`f2p_committed`/`p2p_committed`,
    and in `manifest.json`, as `accept_committed_final`.

## Not in this repo

- **Hidden content:** `tasks/<t>/verifier/`, `gold.patch` and `preflight/`. The leave-one-out patches are reference-solution code.
- **Binaries:** the Claude Code binaries and Docker `buildx`.
- **Credentials.**

`tasks/<t>/` here keeps `prompt.txt`, `meta.json` and `preflight.json`, which holds results and file names only.

**Redaction:** the account email, user name and organization id are replaced with `<redacted-email>`, `<redacted-user>`
and `<redacted-org>` in every file. Third-party addresses in upstream repo history are kept.
