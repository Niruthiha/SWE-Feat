"""agent_spread.py <state.tsv> <out.tsv> - the agent's OWN spread next to the task's spread, per run.
Same rules as units_deepswe.py (task spread): source files = classify()=="src" (tests, docs, generated, non-code
dropped); units: ts/js = nearest package.json/deno.json/deno.jsonc/jsr.json at the base commit, rust = nearest
Cargo.toml, go/python = directory. Columns:
  gold_*  : the reference solution (task spread as selected)
  lofo_*  : gold source files the hidden tests need (leave-one-file-out: dropping the file makes the tests fail)
  agent_* : the agent's final working-tree diff (and committed-only diff when the run recorded one)
Run from deepswe/harness (reads tasks/<t>/gold.patch, tasks/<t>/preflight.json, run dirs)."""
import os, re, sys, json, pathlib
from collections import Counter
HERE = pathlib.Path(__file__).resolve().parent
HOME = pathlib.Path.home(); H = pathlib.Path(".").resolve()
src = (HOME / "features/SWE-bench-Live/filter_2026_multifile.py").read_text()
g = {"os": os, "re": re, "Counter": Counter}; exec(src[src.index("CODE_EXT = {"): src.index("rows = []")], g)
classify, files_of = g["classify"], g["files_of"]
sys.argv, (state, out) = sys.argv[:1], sys.argv[1:3]
units_tsv = {l.split("\t")[0]: dict(zip(H.joinpath("../lists/deepswe_units.tsv").read_text().splitlines()[0].split("\t"), l.split("\t")))
             for l in H.joinpath("../lists/deepswe_units.tsv").read_text().splitlines()[1:]}
JSM = ("package.json", "deno.json", "deno.jsonc", "jsr.json"); MAN = {"ts": JSM, "js": JSM, "rust": ("Cargo.toml",)}
def tree(task):
    m = json.load(open(H / "tasks" / task / "meta.json")); url, sha = m["repo"], m["base_commit"]
    d = HOME / "features/deep-swe-repos" / re.sub(r"[^A-Za-z0-9]+", "_", url.removeprefix("https://github.com/"))
    import subprocess
    r = subprocess.run(["git", "-C", str(d), "ls-tree", "-r", "--name-only", sha], capture_output=True, text=True, check=True)
    return r.stdout.splitlines()
def nearest(path, roots):
    p = os.path.dirname(path)
    while True:
        if p in roots: return p or "."
        if not p: return "<root-no-manifest>"
        p = os.path.dirname(p)
def units(files, lang, roots):
    return sorted({nearest(f, roots) for f in files}) if lang in MAN else sorted({os.path.dirname(f) for f in files})
rows = []
for line in open(state):
    f = line.rstrip("\n").split("\t")
    if len(f) < 3 or not f[1].startswith("cell_exit") or not f[2]: continue
    t, rd = f[0], pathlib.Path(f[2]); lang = units_tsv[t]["lang"]
    roots = set()
    if lang in MAN:
        roots = {os.path.dirname(x) for x in tree(t) if os.path.basename(x) in MAN[lang] and "node_modules/" not in x
                 and not re.search(r"(^|/)(fixtures?|__fixtures__|test-?fixtures|examples?)/", x)}
    rt = [l.rstrip("\n").split("\t") for l in open(rd / "rounds.tsv")]; hdr, rt = rt[0], rt[1:]
    if "stopped_by_user" in f[1]: rt = [x for x in rt if int(x[0]) <= 19]   # 20-round cap applied
    last = rd / "rounds" / f"r{int(rt[-1][0]):02d}"
    gold = [x for x in files_of((H / "tasks" / t / "gold.patch").read_text(errors="replace")) if classify(x) == "src"]
    pf = json.load(open(H / "tasks" / t / "preflight.json"))
    lofo = [x["file"] for x in pf["lofo"] if x["result"] == "FAIL"]
    agent = [x for x in files_of((last / "diff.patch").read_text(errors="replace")) if classify(x) == "src"]
    cp = last / "committed/diff.patch"
    agent_c = [x for x in files_of(cp.read_text(errors="replace")) if classify(x) == "src"] if cp.exists() else None
    gu, lu, au = units(gold, lang, roots), units(lofo, lang, roots), units(agent, lang, roots)
    r = dict(task=t, lang=lang, result=rt[-1][2], rounds=len(rt),
             gold_files=len(gold), gold_units=len(gu), lofo_files=len(lofo), lofo_units=len(lu),
             agent_files=len(agent), agent_units=len(au), agent_dirs=len({os.path.dirname(x) for x in agent}),
             agent_files_in_gold=len(set(agent) & set(gold)), agent_files_not_in_gold=len(set(agent) - set(gold)),
             lofo_files_missed=len(set(lofo) - set(agent)),
             agent_units_committed=(len(units(agent_c, lang, roots)) if agent_c is not None else ""),
             gold_unit_list=";".join(gu), agent_unit_list=";".join(au))
    rows.append(r)
with open(out, "w") as fo:
    fo.write("\t".join(rows[0]) + "\n")
    for r in rows: fo.write("\t".join(str(v) for v in r.values()) + "\n")
for r in rows:
    print(f"{r['task'][:40]:40s} {r['lang']:6s} {r['result']:4s} gold {r['gold_files']:2d}f/{r['gold_units']}u  lofo {r['lofo_files']:2d}f/{r['lofo_units']}u  "
          f"agent {r['agent_files']:2d}f/{r['agent_units']}u  in-gold {r['agent_files_in_gold']} extra {r['agent_files_not_in_gold']} lofo-missed {r['lofo_files_missed']}")
