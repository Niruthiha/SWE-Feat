"""make_task.py <instance_id>... - SWE-bench Pro V2 task dir for the cell harness (2026-11-03).
tasks/<iid>/prompt.txt   = v2/tasks/<iid>/instruction.md, byte-for-byte (what the official harness shows the agent)
tasks/<iid>/prompt_goal.txt = the PR title + description only (Requirements and New Interfaces removed) - goal arm
tasks/<iid>/verifier/    = v2/tasks/<iid>/tests/ unchanged (test.sh, run_script.sh, parser.py, config.json,
                           test_patch.patch) - harness side only, copied into the ACCEPTANCE container, never the agent's
tasks/<iid>/gold.patch   = v2/tasks/<iid>/solution/gold_patch.diff (preflight only)
tasks/<iid>/meta.json    = ids, image, selection metrics (selection/candidates.csv), source shas"""
import csv, hashlib, json, pathlib, re, shutil, subprocess, sys
SRC = pathlib.Path("/home/niruthi/features/swebench-pro/SWE-bench_Pro-os")
SEL = pathlib.Path("/home/niruthi/features/swebench-pro/selection/candidates.csv")
HERE = pathlib.Path(__file__).resolve().parent
sha = lambda p: hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
cand = {r["instance_id"]: r for r in csv.DictReader(open(SEL))}
for iid in sys.argv[1:]:
    v2 = SRC / "v2/tasks" / iid; td = HERE / "tasks" / iid
    if td.exists(): shutil.rmtree(td)
    td.mkdir(parents=True)
    ins = (v2 / "instruction.md").read_text()
    (td / "prompt.txt").write_text(ins)
    a = ins.index("<pr_description>"); b = ins.index("## Requirements", a)
    goal = ins[:a + len("<pr_description>")] + "\n" + ins[a + len("<pr_description>"):b].strip() + "\n</pr_description>\n" + ins[ins.index("</pr_description>") + len("</pr_description>"):]
    assert "New Interfaces" not in goal and "Path:" not in goal
    (td / "prompt_goal.txt").write_text(goal)
    shutil.copytree(v2 / "tests", td / "verifier")
    shutil.copy(v2 / "solution/gold_patch.diff", td / "gold.patch")
    toml = (v2 / "task.toml").read_text()
    img = re.search(r'docker_image = "([^"]+)"', toml).group(1)
    c = cand.get(iid, {})
    meta = {"instance_id": iid, "image": img, "repo": c.get("repo"), "lang": c.get("lang"),
            "stratum": c.get("stratum"), "rank": c.get("rank"),
            "selection": {k: c.get(k) for k in ("impl_loc", "n_files", "n_packages", "dos_pkg", "dos_file", "mptd", "f2p", "p2p", "hard", "source_paths")},
            "config": json.load(open(v2 / "tests/config.json")),
            "source_repo_commit": subprocess.check_output(["git", "-C", str(SRC), "rev-parse", "HEAD"], text=True).strip(),
            "sha256": {"instruction.md": sha(v2 / "instruction.md"), "prompt_goal.txt": sha(td / "prompt_goal.txt"),
                       "gold_patch.diff": sha(v2 / "solution/gold_patch.diff"),
                       **{f"tests/{p.name}": sha(p) for p in sorted((v2 / "tests").iterdir())}}}
    json.dump(meta, open(td / "meta.json", "w"), indent=1)
    print(iid, img, f"prompt {len(ins)} chars, goal {len(goal)} chars")
