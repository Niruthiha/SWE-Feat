# Select 50 DeepSWE tasks spanning localized -> scattered, with file count and package spread decoupled.
import csv, math, pathlib, random, sys
from collections import Counter, defaultdict
HOME = pathlib.Path.home(); D = HOME / "features/deep-swe"
rows = list(csv.DictReader(open(D / "deepswe_units.tsv"), delimiter="\t"))
for r in rows:
    for k in ("n_src_files", "n_dirs", "n_units", "flagged", "added"): r[k] = int(r[k])
elig = [r for r in rows if not r["flagged"] and r["n_src_files"] >= 1]
print(f"all {len(rows)}, Epoch-flagged {sum(r['flagged'] for r in rows)}, eligible {len(elig)}")
FB = [(1, 2, "1-2"), (3, 4, "3-4"), (5, 7, "5-7"), (8, 12, "8-12"), (13, 999, "13+")]
UB = [(1, 1, "1"), (2, 2, "2"), (3, 4, "3-4"), (5, 999, "5+")]
fb = lambda n: next(l for a, b, l in FB if a <= n <= b); ub = lambda n: next(l for a, b, l in UB if a <= n <= b)
grid = defaultdict(list)
for r in elig: grid[(fb(r["n_src_files"]), ub(r["n_units"]))].append(r)
def show(sel, title):
    print(f"\n{title}  (rows: source files, cols: packages)\n        " + "".join(f"{l:>6s}" for *_, l in UB) + "   total")
    c = Counter((fb(r["n_src_files"]), ub(r["n_units"])) for r in sel)
    for *_, f in FB: print(f"  {f:>5s} " + "".join(f"{c[(f, u)]:6d}" for *_, u in UB) + f"   {sum(c[(f, u)] for *_, u in UB):5d}")
def spearman(xs, ys):
    rk = lambda v: [sorted(v).index(x) + (sorted(v).count(x) - 1) / 2 for x in v]
    a, b = rk(xs), rk(ys); ma, mb = sum(a) / len(a), sum(b) / len(b)
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / math.sqrt(sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b))
show(elig, "ELIGIBLE (90)")
# Round-robin over grid cells: each pass takes one task from every non-empty cell, preferring the language and
# repo least represented so far (then most added lines for stability). Stops at 50. Deterministic.
random.seed(0); sel, lang_c, repo_c, lang_ub = [], Counter(), Counter(), Counter()
pools = {k: list(v) for k, v in grid.items()}
while len(sel) < 50 and any(pools.values()):
    for k in sorted(pools, key=lambda k: (len(grid[k]), k)):          # rarest cells first in each pass
        if len(sel) >= 50 or not pools[k]: continue
        # prefer: repo not yet used > language rarest WITHIN this package column (breaks language~spread) > rarest overall
        pools[k].sort(key=lambda r: (repo_c[r["repo"]], lang_ub[(r["lang"], k[1])], lang_c[r["lang"]], -r["added"], r["task"]))
        r = pools[k].pop(0); sel.append(r); lang_c[r["lang"]] += 1; repo_c[r["repo"]] += 1; lang_ub[(r["lang"], k[1])] += 1
show(sel, "SELECTED (50)")
for name, s in (("eligible", elig), ("selected", sel)):
    print(f"spearman(files, packages) {name}: {spearman([r['n_src_files'] for r in s], [r['n_units'] for r in s]):.2f}")
print("selected by language:", dict(lang_c.most_common()), "| repos:", len(repo_c), "max per repo:", max(repo_c.values()))
print("\nlanguage x packages in ELIGIBLE pool:")
ec = Counter((r["lang"], ub(r["n_units"])) for r in elig)
for lang in sorted({r["lang"] for r in elig}): print(f"  {lang:7s}" + "".join(f"{ec[(lang, u)]:6d}" for *_, u in UB))
print("\nlanguage x packages in selection:")
lc = Counter((r["lang"], ub(r["n_units"])) for r in sel)
for lang in sorted(lang_c): print(f"  {lang:7s}" + "".join(f"{lc[(lang, u)]:6d}" for *_, u in UB))
# same file count, different spread (the contrast the user asked for)
print("\nmatched-file-count contrasts in selection (same files, 1 package vs 3+ packages):")
byf = defaultdict(list)
for r in sel: byf[r["n_src_files"]].append(r)
for n in sorted(byf):
    lo = [r for r in byf[n] if r["n_units"] == 1]; hi = [r for r in byf[n] if r["n_units"] >= 3]
    if lo and hi: print(f"  {n:2d} files: 1 pkg -> {', '.join(r['task'] + '(' + r['lang'] + ')' for r in lo)} | 3+ pkgs -> {', '.join(r['task'] + '(' + r['lang'] + ',' + str(r['n_units']) + ')' for r in hi)}")
out = D / "deepswe_selected50.tsv"
cols = ["task", "lang", "repo", "category", "n_src_files", "n_dirs", "n_units", "added", "image", "units"]
with out.open("w") as f:
    f.write("\t".join(cols + ["file_bin", "pkg_bin"]) + "\n")
    for r in sorted(sel, key=lambda r: (r["n_units"], r["n_src_files"])): f.write("\t".join(str(r[c]) for c in cols) + f"\t{fb(r['n_src_files'])}\t{ub(r['n_units'])}\n")
print("\nwrote", out)
