# Astropy goal-only batch: selection (2026-11-13)
Replaces the abandoned transformers batch (user chose "switch to another repo": transformers gold fails offline).
Rule as for transformers ("pick 4 at random, 2 localized 2 scattered big tasks"):
Pool: all 15 astropy tasks in featurebench/inventory/tasks.csv. big = impl_loc >= repo median (419) -> 8 tasks.
localized = dos_pkg < 0.4; scattered = dos_pkg >= 0.6. random.Random(20261113).sample over each sorted pool.
Deviation (disclosed): 3 of the 4 big localized tasks are D4 near-duplicates (dup_group 17, dup_dropped=1:
tiled_compression, tilde_path, compressed; all io/fits compression). Only test_compression_failures (the kept
member) is eligible, so the 2nd localized slot is filled by the largest remaining non-duplicate localized task.
  localized: test_compression_failures.48dc420b (impl 530, 12 files, 1 pkg, dos_pkg 0.00)
             test_containers.6079987d          (impl 306, 2 files, dos_pkg 0.00; below median -> not "big")
  scattered: test_comparison.445d81a3 (impl 419, 15 files, 5 pkgs, dos_pkg .628)
             test_vo.8fd473ce         (impl 538, 11 files, 4 pkgs, dos_pkg .679)
Scattered pool has exactly 2 tasks -> no scattered backups. Localized backups: quantity_erfa_ufuncs (194), basic_rgb (160).
containers and comparison ran in earlier (base/doc/vague) arms; goalrw is a new arm, so they are eligible (same as pandas).
All 4 share image libercoders/featurebench-specs_astropy-instance_493bb78b.
- 2026-11-13 user: test_comparison DROPPED from goalrw (infeasible: hidden test imports private _cosmology_not_equal at module level; no reference to it remains in the agent tree once the hidden test is removed; same as mlflow test_genai_metrics). Prompt kept as prompt_goalrw.txt.infeasible. Batch = 3 cells (2 localized + 1 scattered).
