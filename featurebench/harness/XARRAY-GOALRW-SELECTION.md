# Xarray goal-only batch: selection (2026-11-17)
User (AskUserQuestion 2026-11-17): repo xarray, 4 tasks, goalrw arm only, s1, one cell per launch.
Pool: all 4 xarray tasks in featurebench/inventory/tasks.csv (base 97f3a746, one image
libercoders/featurebench-specs_xarray-instance_62de996a). Deviation (disclosed): test_coordinate_transform.6cacb660
is a D4 near-duplicate of test_range_index (dup_group 115, dup_dropped=1) -> not eligible. Batch = 3 tasks:
  test_backends_chunks.fa55f68a   impl 132,  6 files, 5 pkgs, dos_pkg .245  (smallest)
  test_treenode.aa8ba777          impl 412,  5 files, 2 pkgs, dos_pkg .005  (localized)
  test_range_index.7b95ba66       impl 709, 21 files, 6 pkgs, dos_pkg .134  (9 deleted_internal modules, many files)
No xarray cell has run in any arm. Task dirs made with make_task.py; prompt_vague.json (audit forbidden-name list)
with make_vague_prompt.py (no vague cells run). prompt_goalrw.txt hand-written 2026-11-17 from prompt.txt only
(statement + interface descriptions); no test.patch read. Audit: all 3 "names no path, module or masked/tested
symbol" PASS. range_index needed rewording: DataArray/Variable -> "data array"/"variable", "Coordinates:" header ->
"the usual coordinates header" (test-imported names, whole-word, case-sensitive rule).
Blocked 2026-11-17: Docker not reachable from WSL; C: 18 GB free (< 25 GB rule). Next per task, one at a time:
build_image (first only) -> preflight_task.sh (gold PASS / noop FAIL) -> C: >= 25 GB -> audit PASS -> run_seeds.sh <iid> goalrw 1 detached.
