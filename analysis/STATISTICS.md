# Statistical methods, corrections and caveats

This covers every test behind `page/index.html`, `stats.py` and `verify/verify.py`, for both benchmarks. It also lists what we decided along the way and why. Every number in the results section was produced by the code in this folder from `cells.csv`, so rerunning the pipeline (README, "Rebuilding the analysis") reproduces it.

Everything here is **associational**. Each task was run once (seed 1). Benchmark, prompt style, repository, language and task size all change together, so no result here shows cause.

---

## 1. The sample

| | FeatureBench | SWE-bench Pro |
|---|---|---|
| Runs | 21 | 61 |
| Seeds per task | 1 | 1 |
| Prompt | goal-only rewrite (`prompt_goalrw.txt`): no file, function or path names | the dataset's own issue text, verbatim (`prompt.txt` / `prompt_verbatim.txt`) |
| Repos (runs) | sphinx 5, seaborn 4, mlflow 3, pandas 3, astropy 3, xarray 3 (see `featurebench/ran21.tsv`) | protonmail/webclients 15, flipt 9, navidrome 7, vuls 7, ansible 6, qutebrowser 5, element-web 4, teleport 4, openlibrary 3, NodeBB 1 (see `swebench-pro/lists/ran50.tsv` + `ran_batch4.tsv`) |
| Language | Python | Go, Python, TypeScript/JS |
| Subsets (column `subset`) | `fresh` (16): no other arm of our study had run that task before; `seen_other_arm` (5): the same task had also been run in an earlier arm of our study (baseline / doc / impact), each in its own fresh container. Same prompt shape either way. | `batch1` (5) and `nohint` (7, all protonmail): the 12 early runs; `batch3` (38): run with `prompt_verbatim.txt`; `batch4` (11): multi-file tasks run by a teammate on 2026-11-20/21, same harness |

### How the runs were picked

**SWE-bench Pro.**
- The pool is the 121 "no-hint" tasks (`lists/neither121.json`, `select_121.py`). These are tasks whose issue text names neither a gold file path nor a gold file stem.
- `batch3_cap50.txt` capped the sample at 50 runs (12 early + 38).
- Batch 4 (`lists/batch4_multifile.txt`) was added afterwards. It holds every remaining no-hint task whose reference patch changes **3 or more hand-written source files**, minus excluded, network-dependent, flaky or dropped tasks. The reason: the median SWE-Pro run changed 1 file, so there was little variation in scattering to correlate with.
- 11 of the 12 batch-4 tasks ran. `vuls-8d5ea98e` failed preflight (its gold patch needs a module version the offline image lacks) and counts as excluded, not as a failure.
- **Batch 4 is selected on gold-patch size,** so it is not a random draw. It raises the share of multi-file tasks on purpose. Results with and without batch 4 are both reported (section 6e).

**FeatureBench.**
- Tasks were picked per repo by the selection notes in `featurebench/harness/*-GOALRW-SELECTION.md`, before any run.
- Tasks were dropped before running when the hidden test was infeasible for a goal-only prompt: for example, mlflow `test_genai_metrics`, whose hidden test imports `_format_args_string`, a name the masked tree never references.
- transformers was abandoned before any run: its gold patch fails offline because it needs the HF Hub.

### Isolation (applies to every run)

- The agent's container has no tests, gold patch or verifier, no WebSearch/WebFetch, no MCP, and network only to the Anthropic API.
- Acceptance runs in a separate `--network none` container.
- Later rounds get only the blind message, never test output.
- `audit_isolation.sh` (FB) and `preflight_task.sh` (both) check this before each run.
- The audit's tested-name check is whole-word. Words that appear in the dataset's own task statement are exempt, because the goal-only prompt is allowed to keep them.

---

## 2. Variables

All measures use **the same code for both benchmarks**:
- `extract_all.py` runs `dv_extract_common.py`, with the repo root and prompt file passed in as parameters.
- Only production code counts. Paths under `test/ tests/ __tests__/ testing/ spec/`, plus `test_*.py`, `*_test.go|py`, `*.test|spec.[jt]sx?` and `conftest.py`, are dropped.

### 2a. Scattering, measured on the agent's own final diff (`agentshape.py`, prefix `a_`)

These are the main explanatory variables. We use the agent's diff, not the gold patch: the question is about what the agent did, and the two can differ (an agent may touch fewer or more files than the reference).

| Column | Definition |
|---|---|
| `a_n_files` | production files changed |
| `a_n_packages` | distinct packages changed; a package = the top two path components |
| `a_dos_pkg` | package dispersion = 1 − HHI of changed lines over packages (0 = all in one package, higher = more spread) |
| `a_n_functions` | distinct (file, enclosing def/class/func) touched by a hunk, plus newly defined ones. Parsed from the patch text with a regex, not a language parser |
| `a_focus_top_file` | share of changed lines in the single largest file |
| `a_n_lines` | added + removed production lines. **This is the size control (`SIZE`)** |

The pre-task tree is rebuilt only to measure call-graph distance. FB uses the upstream base with gold reversed; SWE-Pro uses the instance commit, with gold reversed if it is already applied. The gold patch is used for nothing else here.

### 2b. Task-side shape, from the gold patch (`build_table.py`, `patchshape.py`, `callgraph.py`)

`n_files`, `impl_lines`, `n_dirs`, `dos_dir` (1 − HHI over parent directories), `cue_files` (the share of gold files whose path or stem, ≥ 4 chars, exact case and whole word, the prompt names) and `cue_tokens` (code-shaped tokens in the prompt). These are used in `stats.py` families A–C and on the benchmark-vs-benchmark part of the page.

### 2c. Effort and navigation (trace-derived, `dv_extract_common.py` `DEFS`)

- A **call** is one tool_use block. A Bash call is split into segments on `; && || |` and newlines.
- `searches` = segments running grep/rg/ag/git grep/find/fd/git ls-files.
- `files_opened` = read in full or in part.
- `test_runs`, `orient_calls` (calls before the first repo edit), `rework` (re-edit after discovering a new file).
- `gold_found_pre_edit` = share of required gold files the agent had opened or edited before its first edit.
- `navshare_*` = how each required gold file was **first** seen: by search, by following code (an import of its module appeared in a result first), by a benchmark clue (path in the prompt), by recall (edited without any lookup), or not found.
- `cost_usd` is the CLI's own reported cost at list price. `api_turns` and `wall_s` also come from the CLI.

### 2d. Memorisation proxy (`overlap_sbp.py`; FB uses the same `overlap()`)

- `recall_all` is the share of gold added production lines that also appear, stripped and as a multiset, among the agent's added lines.
- `recall_long` is the same, restricted to lines of ≥ 40 characters.
- `recall_comments` is the same, over gold comment lines only. Comment syntax is `#` for Python and `//` or `/* *` for Go/TS. Bare `#`, pragma, noqa and `type:` lines are excluded.
- Comment wording is free, so a verbatim comment match is the sharpest signal. Runs whose gold patch has no comments are left out of the comment analysis.
- **Recall is a control, not a diagnosis.** A high value is consistent with the reference being in training data, but generic or repo-copied lines also match.

### 2e. Outcomes

- `r0_pass`: passed acceptance in round 0, before any blind feedback.
- `accept_final` and `rounds`.
- Regression:
  - FB runs `run_regress` on the tests of the touched modules. A verdict is recorded raw and again after the documented flaky/timeout reruns (`REG_ADJUST` in `build_table.py`: two pandas runs).
  - SWE-Pro has only the benchmark's PASS_TO_PASS tests, so there is no broader check.

### 2f. Task type (`tasktype.csv`)

- Labels were hand-assigned **from the prompt text only, before looking at any outcome**.
- FB labels: library / plotting / pipeline, plus `bundled` (the prompt asks for several features).
- SWE-Pro labels: pipeline / ui / fix.
- The 11 batch-4 labels were added the same way, from prompt text.

### 2g. Technique codebook (`techniques_xb.py`)

- This is the SlopCodeBench codebook (validated 57/60 on Python traces).
- It is extended for Go/TS: `go test`, jest, vitest and npm/yarn test count as test runs, and `go run`, node, ts-node and tsx count as probes.
- The extension is **not** part of the validated classifier. Hand validation of all 101 Go/TS Bash calls is in `GOTS_VALIDATION.md` (v1 90/101, v2 after fixes).
- Counts are multi-label: one call can hold several techniques.

---

## 3. Tests run

All p-values are **two-sided permutation p-values**, computed as (hits + 1) / (B + 1). The seeds are fixed (`20261117` in stats.py, `20261118` in scatterfig.py, `0` in verify.py), so reruns are bit-identical. We checked this: pandas 3.0/3.1, numpy 2.4/2.5 and scipy 1.17/1.18 give identical output.

### 3a. Main page: scattering vs effort, within each benchmark (`scatterfig.py`)

| Test | Detail |
|---|---|
| **Spearman ρ, raw** | x = scattering measure (agent diff); y = log10(outcome). p from 4,000 shuffles of y |
| **Spearman ρ, size-adjusted** | y = residual of log10(outcome) on log10(`a_n_lines`), fitted by OLS **within each benchmark separately**. A trend that survives this is association beyond lines changed |
| Grid shown | x ∈ {files, packages, package dispersion} × y ∈ {tool calls, cost, searches}. The appendix adds functions touched, focus (x) and API turns, wall time, r0 pass (y) |
| Navigation table | the same Spearman test against `navshare_*`, `gold_found_pre_edit`, searches and files opened, in three groups: FB, SWE-Pro (runs with ≥ 1 required gold file) and **low-recall runs pooled** (recall_all < 0.8, both benchmarks) |
| **Median split** (appendix) | runs above vs at-or-below the benchmark's median files / packages / dispersion. Effect = rank-biserial r (P(scattered > localized) − P(<)); p from 5,000 label shuffles; BH within each split table |
| **First-attempt pass** | does round-0 pass go with the shape of the round-0 diff (`attempt1.diff.patch`)? FB only, since SWE-Pro passes almost always. Rank-biserial with 5,000 shuffles, raw and size-adjusted (residual on log lines) |
| **Technique vs scattering** | Spearman of log10(technique count + 1) vs scattering, raw and size-adjusted |
| **Task type** | Kruskal–Wallis H across the type labels within each benchmark, permutation p (4,000). FB bundled vs single: rank-biserial, 5,000 shuffles |
| **Pooled 82-run chart** | each effort measure as a percentile rank, Spearman pooled across both benchmarks. **Descriptive only**: pooling mixes the benchmark size difference into the slope, so use the within-benchmark results for inference |

### 3b. `stats.py` (families A–E, written to `stats_out.json`)

| Family | Question | Test |
|---|---|---|
| **A** | Do the benchmarks differ on each variable? | Mann–Whitney as a permutation of labels on ranks (20,000), Cliff's δ, bootstrap 95% CI of the median difference (4,000) |
| **B** | Does the benchmark difference survive a memorisation control? | Freedman–Lane permutation (20,000) of the benchmark coefficient in rank(DV) ~ bench + rank(control), where control ∈ {recall_all}, {recall_long}, {recall_all + log impl_lines} |
| **C** | Within a benchmark, does task shape go with effort? | Spearman of n_files / dos_dir / log impl_lines / cue_files vs log cost, tool calls, searches, test runs, files opened, gold_found_pre_edit, navshare_search and recall. Run plain, partial on log impl_lines and partial on recall_all (partial = Pearson of rank residuals); 5,000 shuffles. Groups: fb, sbp, fb_fresh |
| **D** | Does memorisation go with less effort? | Spearman of recall_all / recall_comments / recall_long vs effort, within fb, within sbp and pooled, plus partial on size |
| **E** | Pass and regression rates | Fisher's exact test on r0 pass; regression counts raw and adjusted |
| Robustness | | leave-one-repo-out sign stability for the key D estimates (FB); SWE-Pro without protonmail; FB fresh-only (in C) |
| Power | | minimum detectable \|ρ\| at α .05 / power .8 for each n (Fisher z) |

### 3c. `verify/verify.py`: an independent re-implementation

- verify.py is written separately in pandas and re-derives the headline results: descriptives, Mann–Whitney + Cliff + permutation + BH, and Freedman–Lane with no covariate, + size (rank log size + rank n_files), + recall, and + recall + size.
- It also covers comment-line matching, a recall-overlap stratum (0.6 ≤ recall ≤ 0.9, where both benchmarks have runs), within-benchmark Spearman with a partial on recall, leave-one-repo-out (LORO), drop-protonmail, bootstrap CIs of Cliff's δ, and simulated power.
- Its output is `verify/verify_out.txt`. The page's numbers were checked against it.

### 3d. Benchmark-vs-benchmark page section (`make_page.py`)

- Cliff's δ with a bootstrap 95% CI (2,000 resamples of runs).
- Permutation p (5,000 label shuffles), with Fisher's exact test for pass rate.
- BH within each variable group.
- Cut-offs for |δ|: < .15 negligible, < .33 small, < .47 medium, otherwise large.

---

## 4. Multiple-comparison correction

- **Benjamini–Hochberg FDR** gives q values. We correct **within each table or family**, not across the whole study:
  - each page table: corr grid, navigation table, technique table, each median-split table, the task-type KW tests within a benchmark;
  - each `stats.py` family (A, B, and C/D separately per kind: plain, partial-size, partial-recall).
- Main findings boxes report only results with **q < .05**. The "Leads that do not survive correction" part lists results with p < .05 but q ≥ .05: things to re-test, not results.
- On charts, a star means **uncorrected** p < .05, and this is stated in each caption.
- The page shows a per-table count of tests, p < .05 and q < .05 (`qsummary`), so the scale of testing is visible.
- We did not apply a study-wide (Bonferroni-style) correction. With this many exploratory tests, a single q < .05 result should be read as a lead to replicate, not a settled fact.

---

## 5. Decisions we made, and why

1. **Agent diff, not gold patch, as the scattering measure.** The question is about the agent's behaviour. The gold patch is used only for the recall control and the "required file" navigation measures. Gold-patch shape stays in `stats.py` C as task-side context.

2. **Size adjustment.** File count is mostly a measure of size: bigger changes touch more files and also cost more. So every main result is shown both raw and size-adjusted (residual on log lines, fitted within each benchmark).
   - Only a result that holds size-adjusted is evidence of something beyond size.
   - Fitting within each benchmark avoids turning the benchmark size gap into a slope.

3. **Within-benchmark inference only.** The benchmarks differ in prompt style, language, repos and size, so pooled correlations confound all of these. Pooled figures are labelled descriptive. The one pooled inferential group is the low-recall runs, because it is the only overlap where the memorisation difference is reduced.

4. **Log scales.** Effort measures are right-skewed, so y is log10. Spearman is rank-based, so the log changes only the size adjustment and the charts, not the raw ρ. Technique counts use log10(count + 1), because zero counts occur.

5. **Recall as a control.**
   - FeatureBench prompts name no code, yet the median FB run reproduces most gold lines verbatim (section 6). That pattern is consistent with training-data exposure.
   - So the benchmark comparison is repeated with recall controlled (B; verify T2b), with comment-line recall as a sharper control (verify T2c) and within the recall overlap stratum (T2d).
   - We do not treat recall as proof of memorisation.

6. **Prompt fidelity.**
   - SWE-Pro uses the dataset text verbatim, with two exceptions: in `openlibrary-7c8dc180` and `qutebrowser-cf06f4e3`, a function or class name that the tests do not use, and that only said *where* the code is, was rephrased.
   - FB uses goal-only rewrites. We tightened them only where they said where to find code, never the behaviour requirements.
   - The prompt shape changed across dates in earlier FB arms, so check `shapeHash` in the manifests. All 21 FB runs here are goalrw.

7. **`seen_other_arm` FB runs.** In 5 FB tasks, the same task had run in an earlier arm on the same image. Each run is still a fresh container and no state carries over. The subset tag is kept so that results can be checked fresh-only (`stats.py` C `fb_fresh`).

8. **Regression adjustments.**
   - Two pandas runs had a raw regression verdict caused by flaky or timeout tests. They were rerun as documented (`featurebench/runs/<run>/regress/EXT_RERUN.md` and `ONLINE_RERUN.md` in the test_describe and test_formats runs).
   - Both the raw and the adjusted counts are reported.
   - Three pandas regression `results.tsv` files over 20 MB are not in the repo.

9. **Acceptance labels.** Pass/fail comes from the harness's acceptance log (every FAIL_TO_PASS and PASS_TO_PASS test passes), never from the agent's own claim.

10. **Exit 3 runs** (agent unavailable, session limit) are invalid, never a verdict. They were rerun from scratch, and none are in the sample.

11. **Batch-4 provenance.**
    - A teammate ran these from this repo, with the same harness version (sbp-1.0), CLI 2.1.310, claude-opus-5-5, egress image hcexp-egress:2, max_rounds 30 and stall 10.
    - We checked each manifest before adding the runs. Each run directory has an `ORIGIN.txt`.
    - `subset` = batch4 is assigned by run timestamp ≥ 2026-11-20 22:00 among `-verb` runs.

---

## 6. Results at 82 runs (21 FB + 61 SWE-Pro)

Seeds fixed; these are the outputs of the current pipeline (`stats_out.json`, `verify/verify_out.txt`, `page/index.html`). ρ = Spearman, q = BH within the table.

**Power.** Minimum detectable |ρ| (α .05, power .8): FB .58, SWE-Pro .35, pooled .31.

### 6a. Scattering vs effort, within each benchmark (agent diff; 30 tests per column)

| | FeatureBench raw | FeatureBench size-adj. | SWE-Pro raw | SWE-Pro size-adj. |
|---|---|---|---|---|
| files changed ~ tool calls | +.89 | +.62 | +.41 | +.25 (p .06) |
| files changed ~ cost | +.88 | +.64 | +.43 | +.16 (p .21) |
| files changed ~ searches | +.89 | +.55 | +.47 | +.34 (p .01, q .11) |
| package dispersion ~ tool calls | +.48 | +.61 | +.36 | +.22 (p .08) |
| focus (share in largest file) ~ tool calls | −.82 | −.55 | −.38 | −.26 (p .05) |
| functions touched ~ tool calls | +.70 | +.08 | +.26 | −.04 |
| tests with q < .05 | 15 / 30 | 17 / 30 | 22 / 30 | **0 / 30** (best q .11) |

- **FeatureBench:** scattering goes with more tool calls, cost and searches **beyond size** (ρ ≈ .5–.65 size-adjusted, q < .05).
- **SWE-Pro:** the raw links survive correction, but nothing survives after the size adjustment. There, scattering mostly tracks size.
- **Functions touched** carries nothing beyond size in either benchmark.

### 6b. Navigation (q < .05 unless stated)

- **FB:** files changed ~ searches +.89 and ~ files opened +.71. Focus ~ searches −.82. Wide diffs had found fewer needed files before the first edit (files −.70, functions −.60).
- **SWE-Pro (59 runs with ≥ 1 required file):** files ~ files opened +.74 and ~ searches +.48. Focus ~ files opened −.68. There is **no** start-editing-earlier link (files ~ gold_found_pre_edit +.16, p .22). Functions touched goes the other way (+.35, q .02).
- **Low-recall runs pooled (n = 56):** more scattered diffs had more needed files first found by search (ρ +.41 to +.54).
- **Median split, SWE-Pro** (files > 1: 28 vs 33 runs): files opened 6 vs 2 (r +.73, q .003), searches 7 vs 4 (r +.42, q .035), cost $0.38 vs $0.28 (r +.37, q .043). No action-mix share differs (all q > .19).

### 6c. Technique and task type

- **Techniques:**
  - No technique link survives correction size-adjusted in either benchmark (FB min q .08, SWE-Pro min q .13).
  - SWE-Pro size-adjusted probing leans *down* with scattering (ρ −.28 to −.35).
- **Task type:**
  - FB package dispersion differs by nature (KW p .01, q .06).
  - FB effort does not differ by nature.
  - SWE-Pro raw cost and tool calls differ by nature (p .001 / .012; q .005 / .04; fixes cheapest), but not size-adjusted (p .08 / .25).
- **First-attempt pass (FB only, 4 fails vs 17 passes):** no scattering measure separates them.

### 6d. Benchmark vs benchmark (for reference; entangled)

- **Medians (FB vs SWE-Pro):**
  - cost $2.09 vs $0.32, tool calls 50 vs 9, searches 29 vs 6: all Cliff's δ > .9, q < .001.
  - gold lines reproduced verbatim: 96% vs 38%; comment lines 98% vs 0%.
- **Round 0 pass:** FB 17/21 vs SWE-Pro 61/61 (Fisher p = .003). All 82 runs were finally accepted.
- **Memorisation control (Freedman–Lane):** the benchmark gap in tool calls, searches, cost, API turns and test runs survives controlling recall and size (q < .05). files_opened does not survive recall + size (q .28).
- **Regression:**
  - FB: 3 raw verdicts, 1 after the documented reruns (20 measured).
  - SWE-Pro: 0 of 30 measured (P2P only).
- **Memorisation vs effort:**
  - Within FB, recall does not go with effort (ρ ≈ 0).
  - Within SWE-Pro, higher recall goes with *more* cost and tool calls (ρ +.47, +.39, q < .01), also partial on size.

### 6e. Effect of adding batch 4 (SWE-Pro 50 → 61)

| SWE-Pro, size-adjusted | 50 runs (no batch 4) | 61 runs |
|---|---|---|
| files ~ tool calls | +.25 (p .08) | +.25 (p .06) |
| files ~ cost | +.22 (p .14) | +.16 (p .21) |
| files ~ searches | +.33 (p .02) | +.34 (p .01) |
| focus ~ searches | −.30 (p .03) | −.32 (p .015) |

- Batch 4 did not change the conclusion.
- The batch-4 agent diffs were less scattered than their gold patches. Median 2 files changed (6 of 11 changed > 1 file), against a gold median of 3. So the added variation in scattering was modest.

---

## 7. Caveats

1. **One seed per task.** Run-to-run variance is unknown; a single run's cost or tool calls can vary between reruns.
2. **Small n.**
   - FB has 21 runs. Only |ρ| ≳ .58 is reliably detectable there (power .8, α .05).
   - SWE-Pro has 61 runs, where |ρ| ≳ .35 is detectable.
   - A non-significant result is not evidence of no link.
3. **Entangled factors** between the benchmarks: prompt style, language, repos, size and memorisation.
4. **SWE-Pro repo clustering.** 15 runs are protonmail and 9 are flipt, and runs within a repo are not independent. LORO and drop-protonmail checks address this partly.
5. **Batch 4 was selected on gold-patch file count** (≥ 3 files). It widens the range of scattering, but it is not a random sample. It can also change the size distribution the size adjustment is fitted on.
6. **Measure heuristics.** Function counts come from a regex over patch text; search, read and edit classification comes from command text; the call graph is name-based and static. The Go/TS technique extension is hand-validated, not part of the validated classifier.
7. **Verbatim recall** cannot tell memorisation from generic or repo-copied lines.
8. **Regression** checks for SWE-Pro cover only the benchmark's PASS_TO_PASS tests.
9. **Cost** is the CLI's list-price figure. The runs were on a subscription.
