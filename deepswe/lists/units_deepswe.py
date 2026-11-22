# Real package units for DeepSWE reference solutions.
#   ts/js : nearest ancestor dir holding a package.json at the base commit (the npm project / workspace package)
#   rust  : nearest ancestor Cargo.toml (crate)
#   go    : directory (= Go package, by definition)
#   python: directory (kept; also report nearest pyproject/setup.py project)
# File list at base commit comes from a blobless, no-checkout clone (trees only, no file contents).
import json, os, re, subprocess, sys, tomllib, pathlib
from collections import Counter
HOME = pathlib.Path.home(); TASKS = HOME / "features/deep-swe/tasks"; CACHE = HOME / "features/deep-swe-repos"
src = (HOME / "features/SWE-bench-Live/filter_2026_multifile.py").read_text()
g = {"os": os, "re": re, "Counter": Counter}; exec(src[src.index("CODE_EXT = {"): src.index("rows = []")], g)
classify, files_of = g["classify"], g["files_of"]
flagged = set((HOME / "features/deep-swe-epoch/epoch_flagged_tasks.txt").read_text().split())
LANGMAP = {"typescript": "ts", "javascript": "js", "go": "go", "python": "python", "rust": "rust"}
JSM = ("package.json", "deno.json", "deno.jsonc", "jsr.json")   # npm / Deno / JSR projects
MANIFEST = {"ts": JSM, "js": JSM, "rust": ("Cargo.toml",), "python": None, "go": None}

def tree_files(url, sha):
    d = CACHE / re.sub(r"[^A-Za-z0-9]+", "_", url.removeprefix("https://github.com/"))
    if not d.exists():
        for _ in range(4):
            r = subprocess.run(["git", "clone", "-q", "--filter=blob:none", "--no-checkout", url, str(d)], capture_output=True, text=True)
            if r.returncode == 0: break
            subprocess.run(["rm", "-rf", str(d)])
        else: raise RuntimeError(f"clone failed {url}: {r.stderr[-300:]}")
    r = subprocess.run(["git", "-C", str(d), "ls-tree", "-r", "--name-only", sha], capture_output=True, text=True)
    if r.returncode != 0:
        subprocess.run(["git", "-C", str(d), "fetch", "-q", "--filter=blob:none", "origin", sha], capture_output=True)
        r = subprocess.run(["git", "-C", str(d), "ls-tree", "-r", "--name-only", sha], capture_output=True, text=True, check=True)
    return r.stdout.splitlines()

def nearest(path, roots):
    p = os.path.dirname(path)
    while True:
        if p in roots: return p or "."
        if not p: return None
        p = os.path.dirname(p)

rows = []
for d in sorted(x for x in TASKS.iterdir() if (x / "task.toml").exists()):
    meta = tomllib.loads((d / "task.toml").read_text())
    md = meta["metadata"]; lang = LANGMAP.get(md["language"], md["language"])
    patch = (d / "solution/solution.patch").read_text(errors="replace")
    fs = files_of(patch); srcf = [f for f in fs if classify(f) == "src"]
    dirs = {os.path.dirname(f) for f in srcf}
    unit, n_proj_total, note = dirs, None, ""
    man = MANIFEST.get(lang)
    if man or lang == "python":
        files = tree_files(md["repository_url"], md["base_commit_hash"])
        names = list(man) if man else ["pyproject.toml", "setup.py", "setup.cfg"]
        roots = {os.path.dirname(f) for f in files if os.path.basename(f) in names and "node_modules/" not in f and not re.search(r"(^|/)(fixtures?|__fixtures__|test-?fixtures|examples?)/", f)}
        n_proj_total = len(roots)
        projs = {nearest(f, roots) for f in srcf}
        if None in projs: note = "file outside any manifest"; projs.discard(None); projs.add("<root-no-manifest>")
        if man: unit = projs
        else: note = (note + f" py_projects={len(projs)}").strip()
    rows.append(dict(task=d.name, lang=lang, repo=md["repository_url"].removeprefix("https://github.com/"),
                     category=md.get("category", ""), n_src_files=len(srcf), n_dirs=len(dirs), n_units=len(unit),
                     repo_projects=n_proj_total if n_proj_total is not None else "", flagged=int(d.name in flagged),
                     added=sum(1 for l in patch.splitlines() if l.startswith("+") and not l.startswith("+++")),
                     image=meta["environment"]["docker_image"], units=";".join(sorted(unit)), note=note))
    print(f"{d.name:52s} {lang:6s} files={len(srcf):3d} dirs={len(dirs):2d} units={len(unit):2d} repo_projects={n_proj_total}", file=sys.stderr)
out = HOME / "features/deep-swe/deepswe_units.tsv"
cols = list(rows[0])
with out.open("w") as f:
    f.write("\t".join(cols) + "\n")
    for r in rows: f.write("\t".join(str(r[c]) for c in cols) + "\n")
print("wrote", out, len(rows))
for lang in ("ts", "js", "rust"):
    d = [r for r in rows if r["lang"] == lang]
    print(f"{lang}: tasks={len(d)} dirs->units changed in {sum(r['n_dirs'] != r['n_units'] for r in d)}; single-project repos {sum(1 for r in d if r['repo_projects'] == 1)}; "
          f"units dist {dict(sorted(Counter(min(r['n_units'], 5) for r in d).items()))} vs dirs dist {dict(sorted(Counter(min(r['n_dirs'], 5) for r in d).items()))}")
