# DeepSWE pilot: 10 tasks (2026-11-21/22)

Model: claude-opus-5-5 through Claude Code 2.1.310, in the `ds-1.0` harness. Each task gets one agent run, one task at a time.
Round 0 is the task's `instruction.md`, unchanged. Later rounds send only a fixed "not passing yet" message, with no
test results. Each task is limited to 20 rounds; this was 30 until it was lowered to 20 during the csstree run.

## Results

| # | Task | Lang | Gold files / packages | Result | Rounds | Cost | Wall |
|---|---|---|---|---|---|---|---|
| 1 | dateutil-rfc5545-timezone-interop | py | 1 / 1 | PASS | 1 | $1.85 | 9 min |
| 2 | csstree-shorthand-expansion-compression | js | 3 / 1 | FAIL f2p 74/79 | 20 counted (26 ran) | $15.70 at round 20 | 64 min |
| 3 | dasel-html-document-format | go | 4 / 1 | PASS | 1 | $1.34 | 6 min |
| 4 | abs-module-cache-flags | go | 4 / 3 | PASS | 1 | $1.00 | 5 min |
| 5 | clack-async-autocomplete-options | ts | 4 / 2 | FAIL f2p 81/82 | 20 | $13.64 | 56 min |
| 6 | fd-deterministic-multi-key-sorting | rust | 5 / 1 | PASS | 4 | $4.21 | 20 min |
| 7 | pest-character-class-coalescing | rust | 5 / 4 | FAIL f2p 103/104 | 20 | $10.09 | 67 min |
| 8 | koota-query-predicates | ts | 17 / 1 | PASS | 1 | $2.10 | 7 min |
| 9 | python-statemachine-state-data-scoping | py | 17 / 6 | PASS | 1 | $3.85 | 18 min |
| 10 | helm-array-merge-strategies | go | 10 / 6 | FAIL f2p 46/47, p2p 10/12 | 19 (stalled) | $18.04 | 85 min |

6 of 10 tasks passed, for $71.82 total. The csstree cost is counted at its 20-round cap; the full run cost $16.58.
csstree was stopped by hand after 26 rounds, and every round was scored 74/79.

**Re-grade:** each run's final diff was applied in a brand-new `--network none` container built from the pristine task image.
All 10 verdicts and test counts matched the recorded ones (`harness/runs/pilot_regrade.tsv`).

## Validation (phase 1)

- **Reference solution and empty change:** for all 10 tasks, the reference solution passed the hidden tests and an empty change failed them.
- **Leave one file out:** coverage was full for dateutil, csstree, dasel, abs and fd. It was partial for:
  - clack: 3 of 4 files;
  - pest: 4 of 5;
  - koota: 14 of 17, where the 3 untested files only declare types;
  - python-statemachine: 12 of 17;
  - helm: 8 of 10, where the 2 untested files wire up command-line flags.

## Isolation and leakage audit (`harness/runs/pilot_audit.txt`)

**Clean in all 10 runs:**
- **Prompt:** the task text was byte-identical to the dataset's `instruction.md`.
- **Hidden paths:** `/tests`, `/solution`, `/logs/verifier` and `/oracle` were absent, and the hidden test patch was not applied.
- **Mounts:** only the credentials file was mounted, read-only.
- **Agent setup:** no MCP servers, and HOME was empty.
- **Snooping:** no tool call ever referred to hidden paths, the grader, `reward.json`, the reference solution or DeepSWE/Datacurve.
- **Web tools:** WebFetch and WebSearch were not used.
- **Egress:** only `api.anthropic.com` and `platform.claude.com` got through. Everything else was refused:
  - package registries: crates.io (203 attempts), PyPI and files.pythonhosted.org (116);
  - source hosts: GitHub (51) and the Go proxy (33);
  - other: charts.helm.sh and telemetry.
- **Existing tests:** in all 10 runs combined, the agents changed one line of an existing test (in dateutil).
- **Instruction files:** `/app/AGENTS.md` (koota, helm) and `/app/CLAUDE.md` (python-statemachine) are files the upstream
  repos track, unchanged since their own commits. They are part of the task as DeepSWE ships it.

**Audit hits that turned out to be false positives:**
- "epoch": the unix epoch in a Go docstring.
- "LOFO": random base64.
- "MEMORY.md": Claude Code's standard memory instructions in its system prompt. The memory directory was empty.
- statemachine "no commit": the audit's regex missed `git -c … commit -s`. The run did commit.

**Issues found by the pilot.** Fixes 1–3 are applied in harness `ds-1.1` and verified by a smoke run. In that run the
`init` event lists `skills: []` and 0 slash commands; the agent's attempt to commit as "Someone" still produced
`DeepSWE <ds@bench.com>`; and a committed-only diff that differed from the working tree was graded separately.
The 10 pilot runs themselves used `ds-1.0`.
1. **Account identity reaches the agent.** Claude Code tells the agent the logged-in account's email, and the agents
   used it, with the user name, to sign their commits. This doesn't leak any answer, but it's personal data in every
   transcript and `tool_sequence.json`. The published files have it replaced with `<redacted-email>` /
   `<redacted-user>` / `<redacted-org>`.
   **ds-1.1:** `prep_agent.sh` sets `git config --system` to DeepSWE <ds@bench.com>. It also exports
   `GIT_AUTHOR_*`/`GIT_COMMITTER_*`, which git ranks above any `-c user.*` the agent passes.
   The agent still *sees* the account email in Claude Code's context, so redaction stays mandatory.
2. **The skill set changes between runs.** 4 of 10 runs (dasel, clack, koota, python-statemachine) loaded about 13 extra
   account-level `anthropic-skills:*`; the other 6 didn't. No agent used them, but the environment should be identical
   every time.
   **ds-1.1:** `--disable-slash-commands` turns off all skills and commands, built-in and account. Every run now starts
   with `skills: []`, and the Skill tool is gone, so 22 tools instead of 23. That's stricter than the SWE-bench
   Pro/FeatureBench runs, where the built-in skills were available but never used.
3. **The grading rule differs from the official one.** We grade the working-tree diff; the official harness grades only
   committed work.
   **ds-1.1:** every round also takes `git diff base HEAD`, into `rounds/rNN/committed/`, and grades it in its own
   fresh container unless it's identical to the working-tree diff. `rounds.tsv` gains `accept_committed`,
   `f2p_committed` and `p2p_committed`, and `manifest.json` gains `accept_committed_final`.
   The stop rule is unchanged: it still uses the working tree.
4. **Harness bookkeeping.** Tasks now run one at a time with `harness/launch_one.sh <task>`, which calls `run_one.sh`.
   The batch loop chained tasks without a stop point. csstree's `manifest.json` is unfinished because that run was
   stopped by hand; `STOPPED_BY_USER.txt` in its folder explains.

## Agent's own spread vs the task's spread (`lists/pilot_spread.tsv`, `lists/agent_spread.py`)

Source files and units follow the same rules as task selection:
- TS/JS units are the nearest `package.json`, `deno.json` or `jsr.json` at the base commit;
- Rust units are the nearest `Cargo.toml`;
- Go and Python units are directories.

The columns are:
- "LOFO": the reference-solution files the hidden tests need;
- "in gold": how many of the agent's files are also in the reference solution;
- "extra": the agent's files that aren't.

| Task | Result | Gold files/units | LOFO files/units | Agent files/units | In gold | Extra |
|---|---|---|---|---|---|---|
| dateutil | PASS | 1/1 | 1/1 | 1/1 | 1 | 0 |
| csstree | FAIL | 3/1 | 3/1 | 3/1 | 2 | 1 |
| dasel | PASS | 4/1 | 4/1 | 4/2 | 3 | 1 |
| abs | PASS | 4/3 | 4/3 | 3/2 | 2 | 1 |
| clack | FAIL | 4/2 | 3/2 | 4/2 | 3 | 1 |
| fd | PASS | 5/1 | 5/1 | 6/1 | 5 | 1 |
| pest | FAIL | 5/4 | 4/3 | 6/5 | 5 | 1 |
| koota | PASS | 17/1 | 14/1 | 14/1 | 9 | 5 |
| python-statemachine | PASS | 17/6 | 12/4 | 15/5 | 14 | 1 |
| helm | FAIL | 10/6 | 8/5 | 17/9 | 10 | 7 |

- **The files the tests need are a property of the reference solution, not of the task.**
  - koota passed while missing 8 of the 14 files the leave-one-file-out check marks as required. dasel passed missing 1 and abs missing 2.
  - Those agents put the code somewhere else. The check shows the hidden tests need each of those files *given the reference solution's design*.
- **The failing agents spread as wide as the reference or wider.** pest used 5 units vs 4, and helm 9 vs 6. So their failures weren't from a too-narrow change.

## Failure modes

- **All 4 failures were near misses that stayed flat from the start.** They were 1–5 tests short in round 0 and never
  improved. Rounds then shrank to under 30 seconds, meaning the agent declared itself done and stopped trying.
  The only task that converted after round 0 was fd, in round 3. The blind rounds after round 3 cost about $50 and fixed nothing.
- **helm met the target and broke existing behavior.** In round 0 it passed all 47 target tests but broke 2 existing
  ones (`TestHarness_Lint_MergeStrategy_ValidAnnotations` …). Later rounds swapped one failure for another.
- **Spread is not a hard requirement.** Passing agents left many of the reference solution's files untouched: dasel
  touched 3 of 4, abs 2 of 4, koota 9 of 17 and python-statemachine 14 of 17. The reference solution's spread is
  therefore an upper bound. For analysis, report the agent's own spread and the leave-one-file-out spread next to it.
- **In this small sample, spread didn't predict failure.** Both 17-file tasks passed in round 0, including
  python-statemachine's 6 packages. The failures were spread from 1 to 6 packages. By language, Go and Python passed
  4 of 5, and JS, TS and Rust passed 2 of 5. With n=10 this is only a hint, and it's why language must be a covariate.

## Projection for the full 50 (same settings)

- **Cost:** about $7 per task on average, so about $350–400.
- **Time:** about 5.5 hours of agent time per 10 tasks, so about 30 hours, one task at a time.
- **Disk:** about 780 GB free, so the task images are no problem.
