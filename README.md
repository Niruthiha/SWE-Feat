# SWE-Feat: scattering vs agent effort on SWE-bench Pro and FeatureBench

This repo holds the harness, task lists, prompts and analysis for the scattering study. There are 50 SWE-bench Pro runs and 21 FeatureBench runs, each with Claude Code (Opus 5.5), 1 seed per task. With it you can rerun the same tasks, or run the 12 queued multi-file SWE-bench Pro tasks.

The question: when the agent's diff is spread across more files and packages, does the agent explore more and cost more?

## What's here

| Path | What it is |
|---|---|
| `swebench-pro/harness/` | `run_cell.sh` (one task × one seed), `run_nohint_chain.sh` (build → preflight → cell → cleanup), `run_batch3.sh` (a list of tasks, strictly one at a time), `build_image.sh`, `preflight_task.sh`, `make_task.py`, `collect_metrics.py`, cost scripts, `instruments/` (agent Dockerfile, acceptance/regression scripts, egress proxy) |
| `swebench-pro/tasks/<instance_id>/` | for each of the 50 tasks run: `prompt.txt` (the dataset's `instruction.md`), `prompt_verbatim.txt` (what the 38 batch-3 runs got), `meta.json` |
| `swebench-pro/lists/` | `ran50.tsv` (the 50 runs), `neither121.json` + `select_121.py` (the 121 "no-hint" tasks the 50 came from), `batch3_cap50.txt`, **`batch4_multifile.txt` (the 12 queued multi-file tasks)**, `NOHINT_PLAN.md` |
| `featurebench/harness/` | `run_cell.sh`, `prep_goalrw*.sh`, `build_image.sh`, `preflight_task.sh`, `make_task.py`, `audit_isolation.sh`, `HARNESS.md` (full protocol), `*-GOALRW-SELECTION.md` (how tasks were picked per repo) |
| `featurebench/tasks/<instance_id>/` | `prompt_goalrw.txt` (the goal-only prompt each run got), `meta.json` |
| `featurebench/ran21.tsv` | the 21 runs |
| `swebench-pro/runs/`, `featurebench/runs/` | full output of the 71 runs: transcripts, per-round snapshots and diffs, acceptance logs, `manifest.json`, `metrics.json`. The account email and organization id are replaced with `<redacted-email>` / `<redacted-org>`. Regression `results.tsv` files over 20 MB (3 pandas runs) are left out |
| `analysis/` | the full analysis pipeline, its CSVs, the statistics check (`verify/`) and the results page (`page/index.html`) |

**Not included on purpose:**
- Hidden tests (`verifier/`, `test.patch`), gold patches and mask patches. `make_task.py` rebuilds them from the public datasets on your machine. Keep them out of anything the agent can see.
- The pinned Claude CLI binary (`instruments/claude-cli`, 279 MB) and `musl`. `claude-cli.sha256` records the exact build.
- Credentials.

## Setup

1. **Datasets.**
   - SWE-bench Pro: clone the SWE-bench Pro OS repo, with its `v2/tasks/` layout.
   - FeatureBench: save the dataset as a parquet file (`featurebench/analysis/full.parquet` in our layout).
2. **Edit the hard-coded paths.** Several scripts contain `/home/niruthi/...`; point them at your own copies (`grep -rn /home/niruthi`).
3. **Docker.**
   - Task images: `ghcr.io/scaleapi/swe-bench_pro-v2:<instance_id>` for SWE-bench Pro, and the FeatureBench images listed in each `meta.json`.
   - Egress proxy: build it from `swebench-pro/harness/instruments/docker-egress/` and tag it `hcexp-egress:2`. It allows only the Anthropic API.
4. **Claude CLI.** Put a Claude Code CLI binary at `instruments/claude-cli`; the version we used is in `claude-cli.sha256`.
5. **Credentials.** Set `CLAUDE_CREDS` to your own `~/.claude/.credentials.json`. It is mounted **read-only**, outside the agent's HOME. Never copy it into the repo or a run directory. `run_cell.sh` scans every session log for credential strings after each run.
6. **Disk.** One task image is 2–20 GB. The chain deletes images after each task and stops below 25 GB free.

## Running tasks

**One SWE-bench Pro task:**
```bash
cd swebench-pro/harness
python3 make_task.py <instance_id>          # writes tasks/<id>/ from the dataset
VERB=1 ./run_nohint_chain.sh <instance_id>  # build image -> preflight -> one s1 cell -> cleanup
```
Preflight checks that the gold patch passes and an empty patch fails before any agent runs.

**A list of tasks, one at a time and detached:**
```bash
LIST=lists/batch4_multifile.txt MATCH=verb setsid nohup ./run_batch3.sh > runs/batch4.log 2>&1 < /dev/null &
```

**One FeatureBench task:** run `make_task.py <id>`, then the matching `prep_goalrw*.sh`, then `GOALRW=1 ./run_cell.sh <id> 1`. See `HARNESS.md`.

## Protocol, both benchmarks

- **Round 0** is the task prompt. Each later round is only `blind_msg.txt` ("This is not done correctly. Keep working on it until it is."). The agent never sees test output.
- **The agent's container** is fresh, runs as uid 1000 with an empty HOME and no MCP. WebSearch and WebFetch are disabled, and the network allows the Anthropic API only.
- **The acceptance check** runs after every round in a separate `--network none` container built from the pristine image. It applies the agent's diff and runs the benchmark's own tests. A run passes when every FAIL_TO_PASS and PASS_TO_PASS test passes.
- **Stops:** the run stops when it converges, after 10 identical trees, at the round cap, or if the agent is unavailable (exit 3: invalid, never a verdict).

## Prompts used

- **SWE-bench Pro, 12 early runs:** `prompt.txt`, the dataset's `instruction.md` byte for byte.
- **SWE-bench Pro, 38 batch-3 runs:** `prompt_verbatim.txt`. It is identical to `prompt.txt` except in 2 tasks, `openlibrary-7c8dc180` and `qutebrowser-cf06f4e3`. There, only text naming *where* the code is (a function or class name) was rephrased; the behaviour requirements were kept.
- **FeatureBench, all 21 runs:** `prompt_goalrw.txt`, a goal-only rewrite of the dataset problem statement.

## The 12 queued multi-file tasks

`lists/batch4_multifile.txt` lists every remaining task in the 121 no-hint set that meets all of these:
- its reference patch changes 3 or more hand-written source files;
- it isn't flagged as excluded, network-dependent, flaky or dropped;
- it isn't among the 50 already run.

They span ansible, navidrome, protonmail, flipt and vuls, with 3–6 source files each. They are meant to give more variation in scattering on SWE-bench Pro, where the median run changes 1 file. None has been run yet.

## Rebuilding the analysis

```bash
cd analysis
python3 extract_all.py && python3 build_table.py
python3 patchshape.py && python3 callgraph.py && python3 agentshape.py && python3 behaviour.py && python3 techniques_xb.py && python3 interfaces.py
python3 stats.py
(cd verify && python3 verify.py)
python3 make_page.py      # -> page/index.html
```
`extract_all.py` reads the run directories under `*/runs/` (edit its paths). The CSVs here are its output for the 71 runs.

## Rules we followed

- Run one cell at a time.
- Never put test, gold or verifier content in the agent's view.
- Keep credentials read-only and outside the repo.
- Report correlations only: nothing here shows cause.
