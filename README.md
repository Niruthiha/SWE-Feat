# SWE-Feat: scattering vs agent effort on SWE-bench Pro and FeatureBench

This repo holds the harness, task lists, prompts and analysis for the scattering study. There are 61 SWE-bench Pro runs (50 earlier + 11 multi-file batch-4 runs) and 21 FeatureBench runs, 82 in all, each with Claude Code (Opus 5.5), 1 seed per task. With it you can rerun the same tasks.

- **[`RUNS.md`](RUNS.md)** lists every run: task, run directory, pass/rounds, cost, tool calls, diff size and recall.
- **[`featurebench/RUN_NEW_PROMPT.md`](featurebench/RUN_NEW_PROMPT.md)** is a step-by-step guide to rerunning the 21 FeatureBench tasks with a different prompt (`PROMPT_ARM=<name>`): dataset, images, preflight, prompt audit, run, outputs.
- **[`ISOLATION.md`](ISOLATION.md)** explains every isolation mechanism: network allowlist, disabled web tools and MCP, empty HOME, credentials, hidden tests, blind feedback. It also covers what was *not* disabled (account skills, SWE-Pro git identity), with per-run checks.
- **[`analysis/STATISTICS.md`](analysis/STATISTICS.md)** documents the statistics: variables, every test, the corrections, the decisions and caveats, and the results at 82 runs.

The question: when the agent's diff is spread across more files and packages, does the agent explore more and cost more?

## What's here

| Path | What it is |
|---|---|
| `swebench-pro/harness/` | `run_cell.sh` (one task × one seed), `run_nohint_chain.sh` (build → preflight → cell → cleanup), `run_batch3.sh` (a list of tasks, strictly one at a time), `build_image.sh`, `preflight_task.sh`, `make_task.py`, `collect_metrics.py`, cost scripts, `instruments/` (agent Dockerfile, acceptance/regression scripts, egress proxy) |
| `swebench-pro/tasks/<instance_id>/` | for each of the 61 tasks run: `prompt.txt` (the dataset's `instruction.md`), `prompt_verbatim.txt` (what the 38 batch-3 and 11 batch-4 runs got), `meta.json` |
| `swebench-pro/lists/` | `ran50.tsv` (the 50 runs), `neither121.json` + `select_121.py` (the 121 "no-hint" tasks the 50 came from), `batch3_cap50.txt`, `batch4_multifile.txt` (the 12 multi-file tasks), `ran_batch4.tsv` (the 11 that ran), `NOHINT_PLAN.md` |
| `featurebench/harness/` | `run_cell.sh`, `run_seeds.sh`, `run_regress.sh`, `prep_goalrw*.sh`, `build_image.sh`, `preflight_task.sh`, `make_task.py`, `make_vague_prompt.py`, `audit_isolation.sh`, `HARNESS.md` (full protocol), `*-GOALRW-SELECTION.md` (how tasks were picked per repo) |
| `featurebench/tasks/<instance_id>/` | `prompt_goalrw.txt` (the goal-only prompt each run got), `meta.json` |
| `featurebench/ran21.tsv` | the 21 runs |
| `swebench-pro/runs/`, `featurebench/runs/` | full output of the 82 runs: transcripts, per-round snapshots and diffs, acceptance logs, `manifest.json`, `metrics.json`. The account email and organization id are replaced with `<redacted-email>` / `<redacted-org>`. Regression `results.tsv` files over 20 MB (3 pandas runs) are left out |
| `analysis/` | the full analysis pipeline, its CSVs, the statistics check (`verify/`) and the results page (`page/index.html`) |

**Not included on purpose:**
- Hidden tests (`verifier/`, `test.patch`), gold patches and mask patches. `make_task.py` rebuilds them from the public datasets on your machine. Keep them out of anything the agent can see.
- The pinned Claude CLI binary (`instruments/claude-cli`, 279 MB) and `musl`. `claude-cli.sha256` records the exact build.
- Credentials.

## Setup, exactly as we ran it

### Machine
- Windows 11 + WSL2 (Ubuntu), Docker Desktop with the WSL backend, Docker Engine 29.9.2.
- `%USERPROFILE%\.wslconfig`:
  ```ini
  [wsl2]
  memory=12GB
  swap=8GB
  [experimental]
  bestEffortDnsParsing=true
  ```
- Python 3.12 on the host: `pip install -r requirements.txt` (pandas 3.0.1, numpy 2.4.2, scipy 1.17.1). These are for `make_task.py` and the analysis; the harness itself needs only bash, python3, git and docker. We also reran `stats.py` with newer versions (pandas 3.1.0, numpy 2.5.4, scipy 1.18.1) and got identical results.
- At least 25 GB free disk. Task images are 2–20 GB, the chain deletes each one after its task, and it stops below 25 GB. On WSL, run `wsl -d docker-desktop fstrim -av` before compacting the Docker disk.

### Datasets (pinned versions we used)

**SWE-bench Pro v2.** Your repo does not include it. Clone it and check out the commit we used:
```bash
git clone https://github.com/scaleapi/SWE-bench_Pro-os.git
cd SWE-bench_Pro-os && git checkout 66f92766bba642462d4bbe5479e83f91f9211862   # 2026-09-22, 642 tasks in v2/tasks/
```
Set `SRC` in `swebench-pro/harness/make_task.py` to this folder. `make_task.py` records the commit in each `meta.json` (`source_repo_commit`), so you can check you match. Task images are pulled from `ghcr.io/scaleapi/swe-bench_pro-v2:<instance_id>`.

**FeatureBench.** We used the Hugging Face dataset `LiberCoders/FeatureBench` (200 rows) saved as one parquet file:
```bash
python3 -c "from datasets import load_dataset; load_dataset('LiberCoders/FeatureBench', split='full')  # splits: lite, full, fast.to_parquet('full.parquet')"
sha256sum full.parquet   # ours: 1989012f1d7003bde5e79cb5d6f7b5580c1597ae36d533019a53a1da44b2c160
```
If the hash differs, the dataset has changed since our runs. Check the 21 tasks in `featurebench/ran21.tsv` against our `prompt_goalrw.txt` and `meta.json` before running. The benchmark code is at https://github.com/LiberCoders/FeatureBench (we used commit `8d4e347ec57546685c5a87e8676bf575db022ea6`). Task images are pulled from Docker Hub (`image_name` in each `meta.json`).

**Hard-coded paths:** several scripts contain `/home/niruthi/...`. Run `grep -rn /home/niruthi` and point each at your copies.

### Claude CLI (pinned 2.1.310)
- **SWE-bench Pro:** the image takes the native CLI binary from the build context.
  - glibc images: put it at `swebench-pro/harness/instruments/claude-cli`.
  - Alpine images (some NodeBB/element tasks): put it at `instruments/musl/claude-cli-musl`.
  - The `.sha256` files record the exact builds. `build_image.sh` picks glibc or musl automatically.
- **FeatureBench:** the image installs `@anthropic-ai/claude-code@2.1.310` from npm at build time, so no binary is needed.
- **Model:** `claude-opus-5-5`, set by `MODEL`, with default effort.

### Docker images
| Image | Built by | From |
|---|---|---|
| `sbpexp-agent:<iid>` | `swebench-pro/harness/build_image.sh <iid>` | `ghcr.io/scaleapi/swe-bench_pro-v2:<iid>` unchanged + CLI at `/opt/claude-cli` + wrapper at `/usr/local/bin/claude` |
| `fbexp-agent:<repo>` | `featurebench/harness/build_image.sh <iid>` | `docker.io/<image_name from meta.json>` (libercoders FeatureBench images) + node 22 + ripgrep + CLI (one image per repo) |
| `hcexp-egress:2` | `docker build -t hcexp-egress:2 swebench-pro/harness/instruments/docker-egress` | alpine 3.20 + tinyproxy, allowlist in `filter` |

The SWE-bench Pro build sets `DOCKER_CONFIG=instruments/docker-anon` (an empty `config.json`), which pulls public ghcr images without the Windows credential helper. On WSL that helper times out now and then.

The acceptance check uses the **pristine** task image, not the agent image, so keep both until the cell ends.

### Networks (made on first run by `run_cell.sh`)
```bash
docker network create --internal hcexp-cellnet   # agent containers: no route out
docker network create hcexp-egressnet            # normal bridge
docker run -d --name hcexp-egress --network hcexp-cellnet hcexp-egress:2
docker network connect hcexp-egressnet hcexp-egress
```
- The agent reaches the internet only through `HTTP(S)_PROXY=http://hcexp-egress:8888`.
- The allowlist is `api.anthropic.com`, `statsig.anthropic.com`, `console.anthropic.com` and `platform.claude.com`. Nothing else answers: no pip, npm, git or web.
- Every run tests this before the agent starts and logs the result in `isolation.txt`.
- Acceptance containers run with `--network none`.

### Credentials
- `export CLAUDE_CREDS=$HOME/.claude/.credentials.json`, which must be your own subscription login.
- It is mounted read-only at `/creds/credentials.json` and copied into the agent's empty HOME at start.
- If `ANTHROPIC_API_KEY` is set instead, it is passed through, but all our runs used `CLAUDE_CREDS`. After each run, `run_cell.sh` greps the session logs for `sk-ant` / `accessToken` and fails the run if either appears.
- Never copy the file into the repo or a run directory.

### Agent container settings
- Runs as uid 1000 with HOME `/agent-home`, which is empty: no CLAUDE.md and no memory.
- `--strict-mcp-config` with an empty MCP config; `WebSearch` and `WebFetch` disallowed.
- Run as `claude -p --output-format stream-json --verbose --dangerously-skip-permissions`. Round 0 uses `--session-id`; each later round uses `--resume` of the same session.
- Memory cap:
  - SWE-bench Pro: `MEM` (default `4g`).
  - FeatureBench: `AGENT_MEM` (unset by default; `6g` for the pandas runs).
- `/tests`, `/solution`, `/logs/verifier` and `/oracle` must be absent from the agent container. `prep_agent.sh` checks this as root before the agent exists and stops the run if any is present.
- **Stop settings** (env vars):
  - `MAX_ROUNDS=0`: no cap on blind rounds.
  - `STALL_ROUNDS=10`: stop after 10 identical trees.
  - `MAX_USD=0`: no cost cap.
  - `STOP_RULE=official`: all FAIL_TO_PASS and PASS_TO_PASS tests must pass.

### Before every run
- `docker info` must work, and `hcexp-egress` must be running from `hcexp-egress:2`.
- Run one cell at a time. Launch it detached so it survives the terminal:
  `setsid nohup ./run_nohint_chain.sh <iid> > runs/<name>.log 2>&1 < /dev/null &`
- **Exit codes:**
  - 3 = agent unavailable (usage limit or login). The run is invalid: rerun it, don't score it.
  - 4 = refused to start (for example, low disk).
- **After the run:**
  - check `isolation.txt` and `manifest.json` in the run folder;
  - read the verdict from `accept_final.txt`;
  - cost is in `metrics.json` (computed by `roundcost.py`).

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
- **Full detail on every mechanism, and how each was checked, is in [`ISOLATION.md`](ISOLATION.md).**
- **Not disabled: account skills.** The harness turns off MCP servers and web tools, but not Claude Code skills. The skills list in each transcript's `init` event shows two setups:
  - the CLI's built-in skills only;
  - the built-ins plus the account's `anthropic-skills:*` set (docs, pdf, xlsx, browser, …).
  - The account set was loaded in 40 of 61 SWE-bench Pro runs and 9 of 21 FeatureBench runs.
  - **No agent called the Skill tool in any of the 82 runs,** so the difference was never exercised. It is still a setup difference between runs.
  - **For new runs:** turn account skills off (or pin one fixed set) so every run starts identically, and record the `init` skills list per run.
- **Git identity:** FeatureBench containers set a neutral git identity (`fb@bench.com` / `FeatureBench`, in `prepare_tree.sh`); SWE-bench Pro containers don't. No agent in the 82 runs made a commit. For new runs, set a neutral `user.name`/`user.email` in every container so the account email can't end up in commits.
- **What is graded:** the diff against the base commit, built through a temporary index. It includes uncommitted working-tree edits and any commits alike. DeepSWE's official harness grades committed changes only, so for new runs record both.

## Prompts used

- **SWE-bench Pro, 12 early runs:** `prompt.txt`, the dataset's `instruction.md` byte for byte.
- **SWE-bench Pro, 38 batch-3 runs:** `prompt_verbatim.txt`. It is identical to `prompt.txt` except in 2 tasks, `openlibrary-7c8dc180` and `qutebrowser-cf06f4e3`. There, only text naming *where* the code is (a function or class name) was rephrased; the behaviour requirements were kept.
- **FeatureBench, all 21 runs:** `prompt_goalrw.txt`, a goal-only rewrite of the dataset problem statement.

## The 12 queued multi-file tasks

`lists/batch4_multifile.txt` lists every remaining task in the 121 no-hint set that meets all of these:
- its reference patch changes 3 or more hand-written source files;
- it isn't flagged as excluded, network-dependent, flaky or dropped;
- it isn't among the 50 already run.

They span ansible, navidrome, protonmail, flipt and vuls, with 3–6 source files each. They are meant to give more variation in scattering on SWE-bench Pro, where the median run changes 1 file.

**Batch 4 results (run 2026-11-20/21, `lists/ran_batch4.tsv`, runs under `swebench-pro/runs/`, email/org/account ids redacted):**
- 11 of the 12 ran, all with `prompt_verbatim.txt` (= `prompt.txt` byte for byte for these tasks), same harness and protocol as above.
- All 11 converged in round 0 (no blind rounds), $0.11–$0.40 each, about $2.30 in total.
- `vuls-8d5ea98e` was not run: preflight failed because the gold patch itself fails offline (it bumps `golang.org/x/crypto` in `go.mod` to a version not in the image, and the `--network none` acceptance container cannot fetch it). It is network-dependent and should be counted as excluded.
- The protonmail tasks use Alpine images and need the musl CLI at `instruments/musl/claude-cli-musl/claude` (`@anthropic-ai/claude-code-linux-x64-musl@2.1.310`, sha256 in `claude-cli-musl.sha256`).
- `make_task.py` does not write `prompt_verbatim.txt`; for new tasks copy `prompt.txt` to it before running with `VERB=1` / `MATCH=verb`. Run `run_batch3.sh` with `LIST=../lists/batch4_multifile.txt` (the path is relative to `harness/`).

## Rebuilding the analysis

```bash
cd analysis
python3 extract_all.py && python3 build_table.py
python3 patchshape.py && python3 callgraph.py && python3 agentshape.py && python3 behaviour.py && python3 techniques_xb.py && python3 interfaces.py
python3 stats.py
(cd verify && python3 verify.py)
python3 make_page.py      # -> page/index.html
```
`extract_all.py` reads the run directories under `*/runs/` (edit its paths). The CSVs here are its output for the 82 runs. `build_table.py` also reads `goalrw_cells.csv` (the FeatureBench run list), and it tags batch-4 runs by run-directory date (≥ 2026-11-20 22:00). `stats_out.json` and `verify/verify_out.txt` are the outputs that `STATISTICS.md` cites.

## Rules we followed

- Run one cell at a time.
- Never put test, gold or verifier content in the agent's view.
- Keep credentials read-only and outside the repo.
- Report correlations only: nothing here shows cause.
