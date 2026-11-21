# Harness 6.0 — FeatureBench cells (Opus 5.5, as-is repos, DoS contrast)

Experiment dir: `/home/niruthi/features/experiment-featurebench/`. Harness 6.0 is the
FeatureBench port of the HotCRP cell harness 5.2 (`experiment-hotcrp/HARNESS.md`).
Everything that harness learned (Faults 1–13) is carried over; what changed is the
subject (a Python repo prepared exactly as the benchmark prepares it) and the
oracle (the benchmark's own hidden tests, scored the benchmark's own way).

## 1. Design in one paragraph

One cell = one task × one seed. A fresh container is started from the task's
FeatureBench instance image plus a pinned Claude Code CLI (2.1.310). As root, the
benchmark's own tree preparation runs (`prepare_tree`): restore `/testbed` from the
pristine copy, apply the mask patch, delete the hidden test file, repo env fixes,
clear bytecode, re-init git to a single anonymous commit, clear package caches;
then the tree is handed to uid 1000 and the mask patch and pristine copy are gone.
The agent (`claude -p`, model `claude-opus-5-5`, no MCP, empty HOME, internal
network with an allowlist egress proxy) gets the dataset `problem_statement`
byte-for-byte as its round-0 message, through stdin, with no wrapper text. After
every round the agent's diff is scored in a SEPARATE fresh container by a
line-for-line port of FeatureBench's level-1 evaluator (`accept_in_container`):
mask tree + agent diff + hidden F2P test restored; pass = F2P file exit 0 AND every
P2P file exit 0. If it fails, the same session is resumed with only
`blind_msg.txt` ("This is not done correctly. Keep working on it until it is.").
No test output ever reaches the agent. The primary outcome is the number of rounds
to the first PASS; attempt-1 (one-shot) and to-acceptance cost are both recorded.
After convergence, `run_regress.sh` runs the repo's existing tests around the
touched code on the pristine tree and on the agent's tree and lists pass→fail.

## 2. Files

| file | role |
|---|---|
| `make_task.py` | materialises `tasks/<id>/` from the frozen parquet: prompt.txt (verbatim), mask.patch, test.patch, meta.json |
| `build_image.sh` | `fbexp-agent:<repo-hash>` = instance image + node + `@anthropic-ai/claude-code@2.1.310` + the three in-container scripts |
| `instruments/prepare_tree.sh` | benchmark `_initialize_level1` steps 1–6 + `clear_package_caches`, then `chown` to uid 1000 |
| `instruments/accept_in_container.sh` | benchmark `run_instance_level1` steps, prints `ACCEPT SUMMARY f2p= p2p= patch_applied=` |
| `instruments/regress_in_container.sh` | harness-only: pytest -rA over given paths on GOLD or agent tree, per-test outcomes |
| `preflight_task.sh` | per task on this image: gold (reverse mask minus test files) must PASS, no-op patch must FAIL; writes `preflight.json`, `gold.patch`, `test_dirs.txt`. `run_cell.sh` refuses without it (exit 4) |
| `run_cell.sh` | the cell: container, prepare, attestation, manifest, round loop, snapshots, acceptance, session-store copy, metrics, regression |
| `run_regress.sh` | post-convergence existing-feature regression (gold vs agent), `regression.json/.md` |
| `roundcost.py`, `cell_cost.py` | cost rule: LAST result wins within a round (Fault 2); across rounds, last-wins when the CLI carries cost over `--resume` (detected per cell, Fault 14), else summed |
| `collect_metrics.py` | metrics.json: tokens, cost, turns, api calls, thinking tokens, tool calls, bash-channel reads/writes (COUNTING-RULES v1), diff shape, acceptance per round, isolation, regression |
| `test_integrity.py` | lines removed/changed in pre-existing tests (python path rule) per round |
| `audit_isolation.sh` | static audit of all of the above; run before a launch |
| `blind_msg.txt` | the only text sent after round 0 |

## 3. What a cell records (`runs/<ts>-<repo>-<test>-s<seed>/`)

`manifest.json` (ids, image, cli, model, session id, prompt+mask sha256, caps,
base tree/commit, verdict, rounds, cost layers), `isolation.txt` (attestation
before the agent runs: uid, HOME contents, env names, CLAUDE.md search path, hidden
test absent, mask/pristine absent as root, git log, mounts, caches, egress probes),
`task.md` (= prompt), `rounds.tsv` (round, kind, accept, f2p, p2p, test_integrity,
cum_usd, wall_ms), `rounds/rNN/` (prompt.txt, transcript.jsonl, agent.stderr,
agent_exit, wall_ms, diff.patch, diff.stat, files_touched.txt, tree,
test_integrity.json, accept/ with the benchmark's test_output*.txt and VERDICT),
`snapshots/`, `session/` (the CLI's own session store, copied out before the
container dies), `transcript.jsonl` (all rounds concatenated), `attempt1.*`,
`diff.patch` (final), `metrics.json`, `tool_sequence.json`, `regress/` +
`regression.json/.md`.

## 4. Faults carried forward and how 6.0 handles them

| fault (hcexp) | 6.0 |
|---|---|
| 2 cost double count | roundcost.py in every reader |
| MCP connector leak | `--strict-mcp-config --mcp-config '{"mcpServers":{}}'`; attestation records mcp tools offered (0) |
| 11 provisioning inside the cell | nothing is installed per cell; the instance image carries the whole env; no internet |
| 12/13 OAuth refresh host | hcexp-egress:2 allowlist includes platform.claude.com; attested per cell |
| refused/quota rounds | `is_error` result → `agent_unavailable`, exit 3, cell marked INVALID, excluded |
| root refuses `--dangerously-skip-permissions` | agent is uid 1000; tree chowned; conda env stays root-owned (= cannot install into it) |
| unvalidated oracle | preflight gold=PASS / noop=FAIL per task and image, gate on start |
| thinking text | Mostly NOT available: Claude Code redacts raw thinking text in print mode in stream-json, in partial deltas and in its own session store (verified 2026-10-26 on CLI 2.1.310 with haiku and opus). What does survive is the API's short *summarized* thinking, when the model emits one (e.g. sympy smtlib: 30 thinking blocks, 696 chars of summary text; the two other finished cells: 0 chars). Thinking VOLUME (thinking_tokens) is captured per round; the agent's visible narration is captured. metrics.json `reasoning` records both counts per cell |
| benchmark name visible to the agent | The FeatureBench instance images carry git user `FeatureBench` and the commit message `Initial commit for FeatureBench evaluation`, so an agent that runs `git log` sees the benchmark name (mlflow tracing cell: leak_words featurebench=2, from git log output). This is a property of the benchmark images, not of the harness; it reveals no test content. Recorded, not scrubbed, because the repos are run as-is |
| answer key in reach | mask.patch deleted after apply, /root/my_repo removed (benchmark step 1), hidden test deleted and verified, tasks/ and runs/ never mounted, acceptance in a separate container with `--network none` |
| server-side web tools (found by the 6.0 verifier) | WebSearch/WebFetch run on Anthropic's side, so the egress proxy cannot block them → `--disallowedTools WebSearch WebFetch`; metrics assert `server_tool_use` = 0 and neither tool offered. The pilot (run before the fix) had both offered but 0 requests: valid |
| snapshot vs agent `git commit` (verifier) | snapshot diffs against the recorded base commit, not HEAD, so committed work cannot vanish from diff.patch |
| hung pytest (verifier) | `timeout -k 10` in acceptance and regression runners |
| regression parser (verifier) | full pytest nodeid kept (parametrized ids with spaces), SKIPPED keyed file:line |

| 14 cost double count ACROSS rounds (found 2026-10-26, cells 2/4/5) | Claude Code 2.1.310 reports `total_cost_usd`/`modelUsage` for the whole resumed session, so summing per-round values double-counts (mlflow test_mlflow: $22.27 naive vs $7.52 real). `roundcost.cross_round_cumulative()` tests the identity "last modelUsage.outputTokens == summed per-invocation usage over rounds 0..n" and `total_cost()` then takes the last round's value; `collect_metrics.py` records `cost_usd` (true), `cost_usd_naive_round_sum` (what rounds.tsv `cum_usd` shows for rounds written before the fix) and `cost_cross_round_cumulative`. The HotCRP cells (older CLI) reset on resume: the identity test shows per-round values there, so those costs stand. rounds.tsv files of cells 2/4/5 keep the inflated `cum_usd` as a raw record; metrics.json is authoritative. |
| 15 subagent tokens | `usage.*` excludes Agent-tool subagent traffic; `modelUsage` includes it (mlflow test_mlflow r04: +19,517 output tokens from one subagent). metrics.json carries both (`tokens`, `tokens_modelusage_final`, `subagent_tool_calls`). |
| 16 regression parser (found 2026-10-26, cell 4) | `regress_in_container` had a backslash inside an f-string expression (SyntaxError on the images' Python 3.11), so results.tsv was empty and the verdict vacuous. Fixed in the container script (effective on next image build) plus a host-side parse of the raw pytest -rA outputs in `run_regress.sh`/`recheck_flaky.sh`; a tree with zero parsed outcomes now yields status `error`, never a verdict. mlflow conftest's `| MEM .. | DISK ..` prefix is stripped from test ids. |

## 5. Tasks (6 + 4, within-repo pairs, loc-matched, DoS contrast)

| repo | low DoS | high DoS |
|---|---|---|
| sympy | test_runtests_pytest (1 file) | test_smtlib (21 files / 10 pkgs) |
| astropy | test_containers (2 files) | test_comparison (15 files / 5 pkgs; replaced test_lombscargle_multiband, whose gold tree fails a hidden test on an expired leap-second table — see tasks/_dropped/README.md) |
| mlflow | test_tracing (1 file) | test_mlflow (19 files / 5 pkgs) |

Extension (2026-10-26 evening, user: "run two more high dos and 2 low dos tasks"),
`run_more.sh`, four cells on the images already built (no disk for a fourth repo
image: the Docker vhdx is capped at 64 GB on a C: drive with 13 GB free):

| repo | low DoS | high DoS |
|---|---|---|
| mlflow | test_databricks_adapter (3 files / 1 pkg, 212 loc) | test_scorers (10 files / 5 pkgs, 660 loc) |
| astropy | test_compression_failures (12 files / 1 pkg, dos_pkg 0, 530 loc) | test_lombscargle_multiband (15 files / 5 pkgs, 320 loc) REINSTATED on `fbexp-agent:astropy-493bb78b-iers` |

Environment repair for the reinstated task (`instruments/Dockerfile.iers`): the
benchmark image pins astropy-iers-data 0.2025.11.10 whose leap-second table expired
2026-06-28, so by the run date astropy's own check errors on the gold tree. The
derived image upgrades ONLY that data package (tables, no code) to the release
current at run time (0.2026.10.19, pinned, --no-deps); nothing in /testbed changes.
`tasks/<iid>/image_tag` names the image for one task and is honoured by
preflight_task.sh, run_cell.sh, run_regress.sh, recheck_flaky.sh; the other astropy
cells (containers, comparison, compression_failures) run on the base image.

One seed each; cells run one at a time. Pilot: sympy test_runtests_pytest
(2026-10-26, converged round 0, $0.30, 4 turns, no regression). Independent verifier
report after the pilot: no blocker; majors fixed as listed in §4; minor notes kept:
only FAIL_TO_PASS[0] is deleted (all 52 selected tasks have a single F2P file); agent
is uid 1000 so it cannot install into the root-owned conda env (benchmark's own agent
runs as root but also has no network); nested .git dirs are not pruned (no network to
clone). `run_remaining.sh` = rebuild images, re-preflight all six, audit, five cells.

## 6. Running

```
./build_image.sh <instance_id>          # once per repo
./preflight_task.sh <instance_id>       # once per task
./audit_isolation.sh                    # before a launch
CLAUDE_CREDS=~/.claude/.credentials.json ./run_cell.sh <instance_id> 1
./run_regress.sh runs/<run>             # re-run the regression check if needed
```
Env: `MODEL` (default claude-opus-5-5), `MAX_ROUNDS`/`MAX_USD` (0 = unlimited),
`STALL_ROUNDS` (10), `REGRESS` (1), `REGRESS_SCOPE` (touched|all), `EFFORT`.

## 7. Extension dropped; index arm (2026-10-27)

- The 4-task extension in §5 was **dropped** by the user before any of it ran. Only the
  six tasks in the first table are reported.
- **Index arm** (design: DOCS-ARM-PLAN.md). The same 6 tasks, images, harness, isolation,
  blind loop and acceptance as baseline. Only two things change:
  1. `prepare_tree` (running as root, before the agent exists) runs
     `instruments/make_nav_index.py` (sha256 905f69e2…) on the masked tree. It writes a
     root `CLAUDE.md` and `docs/nav/*.md`. For mlflow, the repo's own CLAUDE.md is kept
     below the index. The generator is then deleted from the container.
  2. `nav_audit.py` gates the cell. It aborts if any removed def, any hidden test name or
     the F2P path appears in the index.
- `snapshot()` excludes the index from the scored diff. `rounds/rNN/index_touched.txt`
  records any edit the agent makes to it.
- Run with `INDEX=1`; `run_index_arm.sh START=n COUNT=1` runs a single cell. Run ids end
  in `-idx`.
- **v1 (archived).** The index was present and CLAUDE.md said to use it, but the prompt
  was unchanged. In cells 1–2 the agent never opened the index. Archived in
  `runs/_index_v1_claudemd_only`.
- **v2 (reported).** Round 0 = `index_preamble.txt` (sha256 3791ed0b…, one sentence: read
  CLAUDE.md and docs/nav first) + a blank line + the verbatim problem_statement. The
  result is saved as `prompt_r0.txt` and hashed. Later rounds get the same blind
  message.
- **Regression check (`REGRESS=0`).** It ran for index cell 1 only. The user dropped it
  for cells 2–6 because of machine load.
- **Machine crashes on 2026-10-27.** The WSL VM (7.6 GB RAM) restarted at 13:03, and
  VS Code + the Claude session restarted at 14:15. The load came from agent pytest
  workers, 10-worker regression runs and SonarLint Java (~1.4 GB).
  - Every interrupted cell was deleted and rerun from scratch.
  - Fixes: one cell at a time; cells launched detached (`setsid nohup`) so a session
    restart cannot kill them; SonarLint uninstalled; regression check dropped.
  - Not applied (user's call): `.wslconfig` memory=12GB, swap=8GB.
- **Results.** All 6 v2 cells converged.

  | Task | DoS | Rounds (baseline / index) | Cost (baseline / index) |
  |---|---|---|---|
  | runtests_pytest | low | 1 / 1 | $0.30 / $0.37 |
  | tracing | low | 1 / 1 | $0.84 / $0.66 |
  | containers | low | 5 / 1 | $6.73 / $1.49 |
  | smtlib | high | 2 / 3 | $1.10 / $1.74 |
  | test_mlflow | high | 5 / 8 | $7.52 / $6.52 |
  | comparison | high | 1 / 2 | $2.61 / $3.05 |

  - The agent opened the index 1–3 times per cell.
  - Index cheaper in 3 of 6 pairs; mean −$0.88, carried by containers.
  - One seed: per-pair observations only.
  - Tables: `runs/ARMS.md` and `runs/SUMMARY.txt` §9. The CSVs carry an `arm` column
    plus index columns: index_tool_calls, index_files_opened, index_touched_by_agent,
    nav_audit_*, nav_generator_sha256, index_preamble_sha256.
- **Post-run verifier: CLEAN.** It found no sign of a mid-run restart. Should-fix items:
  - Stale baseline running-cost columns in `rounds.tsv` and the manifest's
    `cost_layers.to_acceptance`. They predate the double-count fix; every table uses
    `metrics.json` `cost_usd`.
  - The ARMS.md regression column read None for index cells. Fixed to "skipped".
  - Index-arm `isolation.txt` calls the generated `/testbed/CLAUDE.md` "repo-shipped".
    Wording only.
- **Image deleted (user, 2026-10-27).** `fbexp-agent:astropy-493bb78b-iers` was built only
  for the dropped extension task test_lombscargle_multiband, so I deleted it to free C:
  space. To rerun that task, rebuild the image with `instruments/Dockerfile.iers`.
- **Images kept.** The three images the 6 tasks run on stay, along with the index-arm
  results (37 MB).

**Index-arm results deleted (user request, 2026-10-27 evening).**
- **Deleted:** the 6 v2 cells (`runs/*-s1-idx`), the archived v1 cells
  (`runs/_index_v1_claudemd_only`), the index logs and launchers, and
  `runs/ARMS.md` + `arms.json`.
- **Next arm.** The user plans a docstring-stripping arm as the real "documentation"
  condition. The index arm was a map of where code lives (it acts on search), not
  interface documentation.
- **Kept:** the harness code (generator, preamble, `run_index_arm.sh`, `nav_audit.py`,
  `compare_arms.py`) and this write-up, as a record.
- **Summaries regenerated as baseline-only:** `SUMMARY.txt` and the `SUMMARY_*.csv`
  files. They keep the parser fixes made today: mlflow failing-test names, and
  n_failed / n_errors split.

## 8. Threats to validity

**8.1 The mask removes more than the feature: a property of the benchmark, verified.**
- **The check (2026-10-28).** For each of the 6 tasks, in a fresh container from the cell image:
  1. take the pristine repo (`/root/my_repo`);
  2. apply `mask.patch` (`--whitespace=fix`, as `prepare_tree` does), then `gold.patch`;
  3. delete the hidden test file, then reverse-apply `test.patch` (as acceptance does);
  4. `diff -r` against the pristine repo.
- **Excluded from the diff:** `.git`, bytecode, and mlflow's `libs/{skinny,tracing}` copies,
  which the benchmark's own environment fix deletes.
- **Result:** all 6 are **byte-identical** to pristine (`runs/MASK-GOLD-ROUNDTRIP.txt`).
  The mask is exactly the reverse of gold plus the hidden test file. The harness removes
  nothing extra, and gold restores everything removed.
- **What the masks remove besides the target feature:**
  - imports in other modules that used it;
  - re-exports from `__init__.py`;
  - small helpers in files the feature never names. The tracing mask, for example, also
    removes helpers that the remaining code still calls.

  Non-test import lines removed:

  | Task | Import lines removed |
  |---|---|
  | sympy runtests | 0 |
  | sympy smtlib | 17 |
  | mlflow tracing | 0 |
  | mlflow test_mlflow | 24 (e.g. `from mlflow.deployments import get_deploy_client`, `import pandas as pd` in `deployments/*`) |
  | astropy containers | 1 |
  | astropy comparison | 7 |

- **Consequence:** an agent must find and restore these to pass. Any "missing import" an agent
  meets is the benchmark's construction, identical across arms. It raises difficulty unevenly
  across tasks: smtlib, test_mlflow and comparison are wide masks. It is not a harness artifact.

**8.2 A second Python environment in every image (`/opt/miniconda3/envs/pytorch_base`).**
- **Present in all three images**, as shipped by the benchmark.
- **sympy:** its site-packages hold a released sympy 1.13.1 with full docstrings, readable by
  the agent uid. It ALSO holds older released versions of both sympy tasks' gold module
  (`sympy/testing/runtests_pytest.py`, `sympy/printing/smtlib.py`) and hidden test files
  (`test_runtests_pytest.py`, `test_smtlib.py`). Found 2026-10-28.
- **astropy and mlflow:** no copy of their own package there.
- **Baseline:** no transcript (baseline or index) ever touched `pytorch_base` or that
  site-packages path (grep over both sympy baseline transcripts incl. attempt 1: 0 hits; no
  `find /`, `pip show`, `conda list` style commands either). The baseline is therefore
  unaffected in fact, but the copy was reachable; disclosed here.
- **Docstring arm:** it is an unstripped documentation source for the two sympy tasks. The
  docstring-arm leak gate found it (19 files hit by the 40 probe phrases, sympy runtests
  preflight). Operator decision 2026-10-28: in the docstring arm, prepare_tree deletes any
  copy of the repo's own package in another env (`EXTRA_COPY_REMOVED` in prepare_tree.log).
  The preflight leak grep now covers binary files, and an answer-key scan (hidden-test and
  gold-patch lines not visible in /testbed, searched over the whole container) must find 0.

**8.3 Docstring arm: the agent imitates the stripped style.**
- In the pilot, the agent wrote `""` placeholders where the baseline wrote 23 real docstrings.
- The arm therefore changes the agent's output style, not only its inputs. Diff line counts
  across arms are not directly comparable.
