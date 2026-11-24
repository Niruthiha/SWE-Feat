# Rerunning FeatureBench with a different prompt

This guide covers running the 21 FeatureBench tasks again with your own round-0 prompt. The harness, image, hidden-test oracle, isolation and blind retry message stay exactly as in our 21 goal-only (`goalrw`) runs. Only the first message to the agent changes.

- **Harness:** `featurebench/harness/run_cell.sh` (v6.0). One task × one seed per invocation.
- **New in this version:** `PROMPT_ARM=<name>`. It sends `tasks/<id>/prompt_<name>.txt` as round 0. Everything else matches the baseline arm.
- **Isolation:** see `../ISOLATION.md` for how the network, web tools, MCP and HOME are disabled and checked.

---

## 0. Prerequisites

- **Machine:** Linux or WSL2, Docker, `python3`, and `pandas` + `pyarrow` (`pip install -r ../requirements.txt`).
- **Disk:** at least 25 GB free at all times. Images are 2–23 GB each, one per repo; mlflow is about 23 GB.
- **Docker resources:** we used memory 12 GB and swap 8 GB (see the top-level README).
- **Credentials**, one of:
  - `CLAUDE_CREDS=/path/to/.credentials.json`. It is mounted **read-only** into the container and never copied into the run directory.
  - `ANTHROPIC_API_KEY=...`.

  Never commit credentials. `isolation.txt` and the copied session store are scanned and redacted, but check before you push.
- **Egress proxy and networks**, as described in the top-level `README.md` under "Docker images" and the network setup:
  ```bash
  docker build -t hcexp-egress:2 swebench-pro/harness/instruments/docker-egress
  docker network create --internal hcexp-cellnet
  docker network create hcexp-egressnet
  docker run -d --name hcexp-egress --network hcexp-cellnet hcexp-egress:2
  docker network connect hcexp-egressnet hcexp-egress
  ```

All commands below run from `featurebench/harness/`. `harness/tasks` is a symlink to `featurebench/tasks`.

---

## 1. Regenerate the task inputs from the dataset

Git ships only `meta.json`, `prompt_goalrw.txt` and `test_dirs.txt` per task. The other inputs are **generated, never committed** (see `featurebench/.gitignore`):

| File | What it is | Made by |
|---|---|---|
| `prompt.txt` | the dataset `problem_statement` | `make_task.py` |
| `mask.patch` | removes the implementation and the hidden test file | `make_task.py` |
| `test.patch` | the hidden tests | `make_task.py` |
| `prompt_vague.json` | masked module paths and symbol names, used by the prompt audit | `make_vague_prompt.py` |
| `preflight.json`, `gold.patch` | oracle validation | `preflight_task.sh` |

**Do not open `test.patch` or `gold.patch` while writing prompts.** Our prompts were written without reading them. The audit in step 4 checks for leaked names mechanically.

1. Download the FeatureBench **full** split (HF `LiberCoders/FeatureBench`, 200 rows) as parquet:
   ```bash
   python3 -c "from datasets import load_dataset; load_dataset('LiberCoders/FeatureBench', split='full').to_parquet('/data/fb_full.parquet')"
   ```
   Ours had sha256 prefix `1989012f1d7003bd`. A different dataset version is caught in step 2.
2. Generate the task files:
   ```bash
   FB_PARQUET=/data/fb_full.parquet python3 make_task.py $(ls tasks/)
   for t in $(ls tasks/); do python3 make_vague_prompt.py tasks/$t; done
   ```
   - `make_task.py` keeps the shipped `meta.json` and **asserts** that the dataset's `problem_statement` sha256 equals the one recorded there. If it fails, you have a different dataset version: stop.
   - We checked that this regenerates `prompt.txt`, `mask.patch`, `test.patch` and `prompt_vague.json` byte-identical to the files our 21 runs used.

---

## 2. Build the images (one per repo)

The 21 tasks use six images. Build each once, using any task id from that repo:

```bash
./build_image.sh mlflow__mlflow.93dab383.test_mlflow.d1847ff9.lv1                 # fbexp-agent:mlflow-efffa87e
./build_image.sh sphinx-doc__sphinx.e347e59c.test_command_line.039d53a2.lv1        # fbexp-agent:sphinx-6191afb1
./build_image.sh pandas-dev__pandas.82fa2715.test_describe.3b919815.lv1            # fbexp-agent:pandas-15f634a6
./build_image.sh astropy__astropy.b0db0daa.test_vo.8fd473ce.lv1                    # fbexp-agent:astropy-493bb78b
./build_image.sh mwaskom__seaborn.7001ebe7.test_line.25304a8b.lv1                  # fbexp-agent:seaborn-52738fbb
./build_image.sh pydata__xarray.97f3a746.test_treenode.aa8ba777.lv1                # fbexp-agent:xarray-62de996a
```

- The Claude Code CLI is pinned to **2.1.310**, the default of `build_image.sh`. Keep it, or the comparison with our runs breaks.
- To save disk, build one repo's image, run that repo's tasks, delete the image, then move on.

---

## 3. Preflight every task (validate the oracle on your image)

```bash
./preflight_task.sh <instance_id>     # gold tree must PASS, no-op patch must FAIL
```

- This writes `tasks/<id>/preflight.json`.
- `run_cell.sh` refuses to start (exit 4) without a passing preflight on the same image.
- Run it one task at a time.

---

## 4. Write your prompt and audit it

1. Pick a short arm name: lowercase letters, digits and `-`, e.g. `spec1`. Existing names (`goal`, `goalrw`, `vague`, `imp`, …) are refused.
2. For **each** task, write `tasks/<id>/prompt_<name>.txt`. That file's bytes are exactly what the agent receives in round 0.
3. If your prompt must hide locations, as ours did, it must not contain:
   - any `/testbed` path or `Path:` line;
   - any `*.py` file name;
   - any masked module path, or any masked or tested function, class or method name (except words the dataset's own task statement already uses).
4. Run the audit with your arm name. It applies the same name check to `prompt_<name>.txt` as to `prompt_goalrw.txt`:
   ```bash
   PROMPT_ARM=spec1 ./audit_isolation.sh | tail -3      # must end with: AUDIT: PASS
   ```
   - The audit also checks that `prompt.txt` matches the dataset and that every task has a passing preflight.
   - If your prompt is *meant* to name locations (e.g. a "detailed" arm), a FAIL on the name check is expected. Record that decision in your notes.

---

## 5. Run a cell

**Run one cell at a time**: a single Docker job, detached so it survives your terminal closing.

```bash
export CLAUDE_CREDS=/path/to/.credentials.json   # or ANTHROPIC_API_KEY
export AGENT_MEM=6g                              # see the settings table below
setsid nohup env PROMPT_ARM=spec1 ./run_cell.sh <instance_id> 1 \
  > runs/cell-spec1-<instance_id>-s1.log 2>&1 < /dev/null &
```

Or use the seeds wrapper. It audits before every cell, skips cells that are already finished, and stops below 25 GB free:

```bash
setsid nohup ./run_seeds.sh <instance_id> "spec1" "1 2 3" > runs/seeds-spec1.log 2>&1 < /dev/null &
# DISK_CHECK_PATH=/path/on/the/docker/disk  (default: current directory)
```

`run_seeds.sh` runs the arms you list. To also rerun our goal-only prompt for new seeds, pass `"goalrw spec1"`. The order within each seed is drawn deterministically.

**Settings we used.** Keep them the same if you want to compare with our 21 runs:

| Setting | Our runs | How |
|---|---|---|
| model | `claude-opus-5-5` | `MODEL` (default) |
| CLI | 2.1.310 | `build_image.sh` default |
| effort | CLI default | leave `EFFORT` unset |
| rounds | unlimited, stop after 10 identical trees | `MAX_ROUNDS=0`, `STALL_ROUNDS=10` (defaults) |
| cost cap | none | `MAX_USD=0` (default) |
| memory cap | `AGENT_MEM=6g` for pandas, astropy, seaborn; none for mlflow, sphinx, xarray | `AGENT_MEM` |
| regression check | on | `REGRESS=1` (default) |
| seed | 1 only | 2nd argument |

Our 21 runs are **seed 1 only**. If you run several seeds of your prompt, run the same seeds of `goalrw` too, so both arms have the same n.

---

## 6. Outputs

Each cell writes `runs/<date>-<time>-<repo>-<test>-s<seed>-<name>/`. The same layout is used in `featurebench/runs/`:

| File | Content |
|---|---|
| `manifest.json` | arm, model, CLI, image, `prompt_sha256`, egress allowlist, settings |
| `rounds/r00/prompt.txt` | **the exact bytes sent in round 0**; `prompt_r0.sha256` is their hash |
| `task.md` | your prompt; for `PROMPT_ARM` runs it is the prompt sent (see note) |
| `transcript.jsonl`, `rounds/rNN/` | per-round transcript, diff, acceptance result |
| `metrics.json` | `converged`, rounds, cost, tokens, wall time |
| `isolation.txt` | in-container whoami, HOME, env (redacted), network probes, absent test paths |
| `regression.json` / `.md` | existing-test regression check after convergence |

**Before analysing, check every run** for these three things:

1. `rounds/r00/prompt.txt` sha256 equals your `prompt_<name>.txt`.
2. `isolation.txt` shows the egress probes refused.
3. The `skills` list in the transcript's first `init` event is the same in every run (see below).

---

## 7. Known caveats

- **Account skills.** These were *not* turned off in our runs: 9 of 21 loaded the account skill set, 12 built-in only, and no run called the Skill tool (`ISOLATION.md` §9).
  - For a cleaner rerun, run every cell with the same credentials, so the skill set is the same, and record the `init` skills list.
  - Optionally add `Skill` to `--disallowedTools` in `run_cell.sh` (line with `--disallowedTools WebSearch WebFetch`). If you do, note it, because it differs from our runs.
- **Git identity.** The FeatureBench tree is prepared with a neutral identity (`fb@bench.com`, `instruments/prepare_tree.sh`). Agents did not commit. The graded diff is `git add -A` against the base commit, so it includes uncommitted work.
- **`task.md` in our `goalrw` runs** holds the dataset `prompt.txt`, not the goal-only prompt. It is a harness quirk of those arms; `PROMPT_ARM` copies the right file. What was actually sent is in `rounds/r00/prompt.txt`, which matches `prompt_r0.sha256` in every run.
- **`test_build_gettext/prompt_goalrw.txt`** was edited locally after its run, introducing a one-word typo. The repo copy has been restored to the bytes actually sent. All 21 `prompt_goalrw.txt` files now match their runs' round-0 hashes.

---

## Quick checklist

```text
[ ] Docker + egress proxy + hcexp-cellnet up            (README)
[ ] FB_PARQUET make_task.py + make_vague_prompt.py      (step 1, sha assert passes)
[ ] build_image.sh per repo, CLI 2.1.310               (step 2)
[ ] preflight_task.sh per task: gold PASS / noop FAIL   (step 3)
[ ] tasks/<id>/prompt_<name>.txt for all 21             (step 4)
[ ] PROMPT_ARM=<name> ./audit_isolation.sh → AUDIT: PASS
[ ] one cell at a time, detached, same settings table   (step 5)
[ ] per-run checks: r00 prompt hash, egress refused, skills list (step 6)
```
