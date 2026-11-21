# Seaborn goal-only batch: selection (2026-11-13)
Replaces astropy (closed at 3 cells, images deleted). User asked for a new repo, 4 tasks, 2 localized + 2 scattered.
No unused repo in featurebench/inventory/tasks.csv (dup_dropped excluded) has >=2 localized (dos_pkg < 0.4) AND
>=2 scattered (dos_pkg >= 0.6) tasks. User chose (AskUserQuestion) seaborn 2+1+1:
  localized: test_relational.f23eb542 (impl 559, 8 files, 1 pkg, dos_pkg 0.00)
             test_regression.ce8c62e2 (impl 568, 5 files, 1 pkg, dos_pkg 0.00)   -- the two largest localized
  scattered: test_line.25304a8b       (impl 177, 10 files, 4 pkgs, dos_pkg 0.65) -- the only scattered task
  2nd slot:  test_scales.d9dcdef6     (impl 560, 4 files, 3 pkgs, dos_pkg 0.42) -- most spread of the rest; MIDDLE band
             (0.4 <= dos_pkg < 0.6), NOT scattered under the rule. Disclose.
No random draw: the picks are forced (only 1 scattered; the 2nd slot is the max-dos_pkg remaining task; localized =
the two largest by impl_loc). Seaborn never ran in any earlier arm (doc arm infeasible: import-time docstring parse;
irrelevant to goalrw, which strips nothing). All 4 share image libercoders/featurebench-specs_seaborn-instance_52738fbb.
Harness-side tool change (disclose): make_vague_prompt.py defined() falls back to a regex for top-level def/class
names when an interface block does not parse (test_line: a def whose body is only "# <your code>"). It only feeds
the audit's forbidden-name list (prompt_vague.json); no vague cells are run. Backup in session scratchpad.
- 2026-11-13 test_relational preflight run 1: gold f2p FAIL only on test_relplot_complex (pytest-timeout >10s, the dataset's timeout_one); run 2: gold PASS / noop FAIL. Timing flake; a cell FAIL on that test alone is to be defect-adjusted. Run-1 output kept as preflight.run1/.
