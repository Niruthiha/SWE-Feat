"""The audit's 121 'neither' tasks (no gold file path/basename/dir and no existing edited symbol named in the prompt),
ranked by hand-written source LOC of the gold patch (tests, generated, vendored, data files excluded)."""
import json, csv, re, collections, sys
R="/home/niruthi/features/benchmark-audit/swebench-pro-v2"
sys.argv=["x",R]; src=open(f"{R}/scripts/localization_cues.py").read().split("for lab, f in")[0]
exec(src)   # builds `out`
neither={i for i,(a,b,_,_) in out.items() if not a and not b}
rows=json.load(open("all_tasks_loc.json"))
sel=[r for r in rows if r["iid"] in neither]
print("neither:",len(sel))
for r in sel: r["drop"]=",".join(k for k,v in (("dup/bad",r["excl"]),("net",r["net"]),("flaky",r["flaky"] not in("0","")) ) if v)
json.dump(sel,open("neither121.json","w"),indent=1)
by=collections.defaultdict(list)
for r in sel: by[r["repo"]].append(r)
for repo,L in sorted(by.items(),key=lambda kv:-sum(x["src_loc"] for x in sorted([y for y in kv[1] if not y["drop"]],key=lambda x:-x["src_loc"])[:5])):
    t=sorted(L,key=lambda x:-x["src_loc"])
    ok=[x for x in t if not x["drop"]]
    print(f"{repo:28s} n={len(L)} usable={len(ok)} top5sum={sum(x['src_loc'] for x in ok[:5])}")
    for x in t[:8]: print(f"     {x['short']:10s} src_loc {x['src_loc']:5d} src_files {x['src_files']:3d} new {x['newf']} hard {x['hard']} {x['drop']}")
