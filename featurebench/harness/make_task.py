#!/usr/bin/env python3
"""make_task.py <instance_id>... - materialise FeatureBench tasks for the cell harness.

Reads the frozen local dataset copy (featurebench/analysis/full.parquet) and writes
tasks/<instance_id>/ with:
  prompt.txt   the dataset's problem_statement, byte-for-byte (the ONLY text the agent gets)
  mask.patch   the dataset `patch` (removes the implementation + the F2P test file)
  test.patch   the dataset `test_patch` (reverse-applied by the acceptance check)
  meta.json    image, repo, base_commit, F2P, P2P, test_cmd, timeouts, covariates
Nothing here is ever mounted into the agent container: the cell copies ONLY
prompt.txt into the round-0 message, and mask.patch is applied as root BEFORE the
agent exists, then deleted.
"""
import csv, hashlib, json, os, pathlib, sys
import pandas as pd

HERE = pathlib.Path(__file__).resolve().parent
FB = HERE.parent / "featurebench"
# FB_PARQUET: path to the FeatureBench "full" split as parquet (HF LiberCoders/FeatureBench, 200 rows).
# FB_SELECTION: optional covariate CSV (our sampling inventory; not in the public repo).
PARQUET = pathlib.Path(os.environ.get("FB_PARQUET", FB / "analysis" / "full.parquet"))
SELECTION = pathlib.Path(os.environ.get("FB_SELECTION", FB / "inventory" / "selection.csv"))

# verbatim from featurebench/harness/test_parsers.py (only pydantic is overridden)
MAP_REPO_TO_TEST_CMD = {"pydantic/pydantic": "pytest -rA -v --color=no"}  # = featurebench/harness/test_parsers.py

t = pd.read_parquet(PARQUET)
sel = {r["instance_id"]: r for r in csv.DictReader(open(SELECTION))} if SELECTION.exists() else {}
for iid in sys.argv[1:]:
    rows = t[t.instance_id == iid]
    assert len(rows) == 1, f"{iid}: {len(rows)} rows"
    r = rows.iloc[0]
    rs = json.loads(r["repo_settings"]) if isinstance(r["repo_settings"], str) else dict(r["repo_settings"])
    d = HERE / "tasks" / iid
    d.mkdir(parents=True, exist_ok=True)
    (d / "prompt.txt").write_text(r["problem_statement"], encoding="utf-8")
    for col, name in (("patch", "mask.patch"), ("test_patch", "test.patch")):
        p = r[col] or ""
        if p and not p.endswith("\n"):   # _normalize_patch_content, harness/runtime.py
            p += "\n"
        (d / name).write_text(p, encoding="utf-8")
    test_cmd = MAP_REPO_TO_TEST_CMD.get(r["repo"]) or rs.get("test_cmd") or "pytest -rA -p no:cacheprovider --color=no"
    cov = sel.get(iid, {})
    meta = {
        "instance_id": iid, "repo": r["repo"], "base_commit": r["base_commit"],
        "image": "docker.io/" + r["image_name"],
        "image_name": r["image_name"],
        "FAIL_TO_PASS": list(r["FAIL_TO_PASS"]), "PASS_TO_PASS": list(r["PASS_TO_PASS"]),
        "test_cmd": test_cmd, "timeout_one": rs.get("timeout_one", 10),
        "timeout_run": rs.get("timeout_run", 1800), "use_uv": bool(rs.get("use_uv", False)),
        "repository": rs.get("repository", r["repo"]),
        "problem_statement_sha256": hashlib.sha256(r["problem_statement"].encode()).hexdigest(),
        "covariates": {k: cov.get(k) for k in ("stratum", "dos_pkg", "dos_file", "n_files", "n_packages",
                                               "impl_loc", "n_ops", "hidden_tests", "task_kind")},
    }
    old = d / "meta.json"
    if old.exists():   # repo-shipped meta.json (with covariates) wins; it must describe the same statement
        om = json.loads(old.read_text())
        assert om.get("problem_statement_sha256") == meta["problem_statement_sha256"], \
            f"{iid}: dataset problem_statement differs from the shipped meta.json - wrong dataset version"
        print(f"{iid}: kept existing meta.json (problem_statement sha256 matches)")
    else:
        old.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"{iid}: prompt {len(r['problem_statement'])} chars, mask {len(r['patch'])}, "
          f"F2P {meta['FAIL_TO_PASS']}, P2P {len(meta['PASS_TO_PASS'])}, image {r['image_name']}")
