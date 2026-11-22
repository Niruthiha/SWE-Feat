"""make_task.py <task_id>... - DeepSWE v1.1 task dir for the cell harness (port of swebench-pro/harness/make_task.py).
tasks/<id>/prompt.txt  = deep-swe/tasks/<id>/instruction.md, byte-for-byte (what the official harness shows the agent)
tasks/<id>/verifier/   = deep-swe/tasks/<id>/tests/ unchanged (test.sh, grader.py, config.json, test.patch, Dockerfile)
                         + test_patch.patch (a copy of test.patch, the name run_cell.sh's isolation check reads).
                         Harness side only: copied into the ACCEPTANCE container, never the agent's.
tasks/<id>/gold.patch  = deep-swe/tasks/<id>/solution/solution.patch (preflight only)
tasks/<id>/meta.json   = ids, image, scattering metrics (deepswe_units.tsv), source shas"""
import csv, hashlib, json, pathlib, shutil, subprocess, sys, tomllib
SRC = pathlib.Path.home() / "features/deep-swe"                       # git clone of datacurve-ai/deep-swe
UNITS = pathlib.Path(__file__).resolve().parent.parent / "lists/deepswe_units.tsv"
HERE = pathlib.Path(__file__).resolve().parent
sha = lambda p: hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
units = {r["task"]: r for r in csv.DictReader(open(UNITS), delimiter="\t")} if UNITS.exists() else {}
for tid in sys.argv[1:]:
    src = SRC / "tasks" / tid; td = HERE / "tasks" / tid
    if td.exists(): shutil.rmtree(td)
    td.mkdir(parents=True)
    shutil.copyfile(src / "instruction.md", td / "prompt.txt")
    shutil.copytree(src / "tests", td / "verifier")
    shutil.copyfile(src / "tests/test.patch", td / "verifier/test_patch.patch")
    shutil.copyfile(src / "solution/solution.patch", td / "gold.patch")
    t = tomllib.loads((src / "task.toml").read_text()); md = t["metadata"]
    u = units.get(tid, {})
    meta = {"instance_id": tid, "benchmark": "DeepSWE v1.1", "image": t["environment"]["docker_image"],
            "repo": md["repository_url"], "lang": md["language"], "category": md.get("category"),
            "base_commit": md["base_commit_hash"],
            "selection": {k: u.get(k) for k in ("n_src_files", "n_dirs", "n_units", "units", "added")},
            "verifier_timeout_sec": t["verifier"]["timeout_sec"], "agent_timeout_sec": t["agent"]["timeout_sec"],
            "memory_mb": t["environment"]["memory_mb"], "cpus": t["environment"]["cpus"],
            "config": json.load(open(src / "tests/config.json")),
            "source_repo_commit": subprocess.check_output(["git", "-C", str(SRC), "rev-parse", "HEAD"], text=True).strip(),
            "sha256": {"instruction.md": sha(src / "instruction.md"), "solution.patch": sha(src / "solution/solution.patch"),
                       **{f"tests/{p.name}": sha(p) for p in sorted((src / "tests").iterdir())}}}
    json.dump(meta, open(td / "meta.json", "w"), indent=1)
    print(tid, meta["image"], f"prompt {len((td / 'prompt.txt').read_text())} chars")
