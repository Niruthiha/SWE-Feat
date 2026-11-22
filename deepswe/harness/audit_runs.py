"""ds_audit.py - pilot audit for DeepSWE cells (run from deepswe/harness in WSL).
Per cell: isolation (prompt identical, hidden paths absent, mounts, MCP/tools/instruction files, contamination needles,
credential strings), egress (which hosts were NOT refused), agent behaviour (hidden-path probes, network/install attempts,
web tools, git commit - the official harness grades only committed work), test integrity, overlap of the agent diff with
the hidden test patch (conflict risk) and with the gold files (spread reached), failure mode, cost/rounds/wall."""
import json, re, sys, pathlib, collections
H = pathlib.Path(".").resolve(); DS = pathlib.Path.home() / "features/deep-swe/tasks"
NEEDLES = ["nirut", "SWE-Feat", "scratchpad", "deepswe", "deep-swe", "epoch.ai", "Epoch AI", "lofo_", "drop_0", "preflight", "gold.patch",
           "solution.patch", "test_patch", "grader.py", "MEMORY.md", "batch4", "selected50", "pilot10"]
CRED = re.compile(r"sk-ant-[A-Za-z0-9_-]{10,}|\"accessToken\"|\"refreshToken\"|@gmail\.com")
PROBE = re.compile(r"(?<![\w.])/(tests|solution|logs|oracle)(/|\b)|reward\.json|grader\.py|test\.patch|solution\.patch|datacurve|deep-?swe", re.I)
NET = re.compile(r"\b(curl|wget|pip3? install|uv pip|npm (install|i)\b|pnpm (add|install)|yarn add|cargo (fetch|update|add|install)|go (get|mod download)|git (fetch|pull|clone|remote))", re.I)
def patch_files(p):
    return [m.group(2) for m in re.finditer(r"(?m)^diff --git a/(.+?) b/(.+)$", p.read_text(errors="replace"))] if p.exists() else []
def tool_uses(rd):
    for t in sorted(rd.glob("rounds/r*/transcript.jsonl")):
        for line in open(t, errors="replace"):
            try: e = json.loads(line)
            except Exception: continue
            if e.get("type") == "assistant":
                for c in e["message"].get("content", []):
                    if c.get("type") == "tool_use": yield t.parent.name, c["name"], json.dumps(c.get("input"), ensure_ascii=False)
rows = []
for line in open("runs/pilot-state.tsv"):
    f = line.rstrip("\n").split("\t")
    if len(f) < 3 or not f[1].startswith("cell_exit") or not f[2]: continue
    t, st, rd = f[0], f[1], pathlib.Path(f[2]); r = {"task": t, "state": st}
    iso = (rd / "isolation.txt").read_text(errors="replace")
    r["prompt_identical"] = (rd / "task.md").read_bytes() == (DS / t / "instruction.md").read_bytes()
    r["hidden_absent"] = all(f"absent  /{p}" in iso for p in ("tests", "solution", "logs/verifier", "oracle"))
    r["instr_files_absent"] = "PRESENT" not in iso.split("== instruction files ==")[1].split("==")[0]
    r["mounts"] = iso.split("== mounts ==")[1].split("==")[0].strip().replace("\n", ";")
    eg = iso.split("== egress")[1].split("==")[0]; r["probe_egress"] = ",".join(l.split()[0] + ":" + l.split()[-1] for l in eg.strip().splitlines()[1:] if "->" in l)
    init = None
    for line2 in open(rd / "rounds/r00/transcript.jsonl"):
        e = json.loads(line2)
        if e.get("type") == "system" and e.get("subtype") == "init": init = e; break
    r["mcp"] = init.get("mcp_servers"); r["model"] = init.get("model"); r["tools"] = len(init.get("tools", []))
    r["plugins_skills"] = [k for k in ("plugins", "skills", "agents") if init.get(k)] and {k: init.get(k) for k in ("plugins", "skills") if init.get(k)}
    blob = "".join(p.read_text(errors="replace") for p in rd.glob("rounds/r*/transcript.jsonl")) + "".join(p.read_text(errors="replace") for p in rd.glob("session/**/*.jsonl"))
    r["needles"] = sorted({n for n in NEEDLES if n in blob})
    allrun = "".join(p.read_text(errors="replace") for p in rd.rglob("*") if p.is_file() and p.stat().st_size < 50_000_000 and p.suffix in (".jsonl", ".json", ".txt", ".log", ".md", ".tsv", ".patch", ""))
    r["cred_strings"] = sorted(set(m.group(0)[:14] for m in CRED.finditer(allrun)))
    el = (rd / "egress_proxy.log").read_text(errors="replace") if (rd / "egress_proxy.log").exists() else ""
    con = collections.Counter(re.findall(r"CONNECT ([^ :]+):443", el)); ref = collections.Counter(re.findall(r'refused on filtered domain "([^"]+)"', el))
    r["egress_allowed"] = {h: n - ref.get(h, 0) for h, n in con.items() if n - ref.get(h, 0) > 0}
    r["egress_refused"] = dict(ref)
    tu = list(tool_uses(rd)); r["tool_calls"] = len(tu); r["tool_mix"] = dict(collections.Counter(n for _, n, _ in tu).most_common(6))
    r["hidden_probes"] = [f"{rr}:{n}:{i[:120]}" for rr, n, i in tu if PROBE.search(i)][:5]
    r["net_attempts"] = len([1 for _, n, i in tu if NET.search(i)]); r["web_tools"] = sum(n in ("WebFetch", "WebSearch") for _, n, _ in tu)
    r["git_commit"] = sum(1 for _, n, i in tu if re.search(r"\bgit\b[^|;&]*\bcommit\b", i))
    r["git_branch"] = sum(1 for _, n, i in tu if re.search(r"git (checkout -b|switch -c|branch \S)", i))
    rt = [l.split("\t") for l in open(rd / "rounds.tsv")][1:]
    r["rounds"] = len(rt); r["final"] = rt[-1][2]; r["f2p_by_round"] = [x[3] for x in rt]
    r["integrity_max"] = max(int(x[5]) for x in rt); r["usd"] = float(rt[-1][6]); r["wall_min"] = round(sum(int(x[7]) for x in rt) / 60000, 1)
    if "stopped_by_user" in st:
        cap = [x for x in rt if int(x[0]) <= 19]; r["usd_at_cap20"] = float(cap[-1][6]); r["rounds_counted"] = len(cap)
    r["round_wall_s_last5"] = [int(x[7]) // 1000 for x in rt[-5:]]
    tp = patch_files(H / "tasks" / t / "verifier/test.patch"); gp = patch_files(H / "tasks" / t / "gold.patch")
    last = rd / "rounds" / f"r{len(rt)-1:02d}"   # killed cells have no top-level diff.patch
    ad = patch_files(rd / "diff.patch") or patch_files(last / "diff.patch")
    r["agent_touches_hidden_test_files"] = sorted(set(ad) & set(tp))
    pf = json.load(open(H / "tasks" / t / "preflight.json")); src = [x["file"] for x in pf["lofo"]]
    r["gold_src_files_touched"] = f"{len(set(ad) & set(src))}/{len(src)}"; r["gold_src_missed"] = sorted(set(src) - set(ad))
    r["agent_files"] = len(ad)
    acc = (rd / "rounds" / f"r{len(rt)-1:02d}" / "accept.stdout")
    a = acc.read_text(errors="replace") if acc.exists() else ""
    r["apply_problems"] = len(re.findall(r"(?i)patch (does not apply|failed)|error: .*patch|APPLY_FAILED|conflict", a))
    r["failing_tests"] = re.findall(r"✗ \[(?:f2p|p2p)\] (.+)", a)[:6]
    man = rd / "manifest.json"; r["manifest_verdict"] = json.load(open(man)).get("verdict") if man.exists() else None
    if r["final"] == "PASS": r["mode"] = "solved r%d" % (r["rounds"] - 1)
    else:
        best = max(int(x[3].split("/")[0]) for x in rt); tot = int(rt[-1][3].split("/")[1])
        flat = len(set(x[3] for x in rt)) == 1; gaveup = sum(s < 30 for s in r["round_wall_s_last5"]) >= 3
        r["mode"] = f"near-miss {best}/{tot}" + (", flat from r0" if flat else ", oscillating") + (", gave up (rounds<30s)" if gaveup else "")
    rows.append(r)
json.dump(rows, open("runs/pilot_audit.json", "w"), indent=1, ensure_ascii=False)
for r in rows:
    print("=" * 100); print(r["task"], "|", r["mode"], "|", r["rounds"], "rounds |", f"${r['usd']:.2f}", "|", r["wall_min"], "min")
    for k in ("prompt_identical", "hidden_absent", "instr_files_absent", "mounts", "mcp", "model", "tools", "plugins_skills", "needles", "cred_strings",
              "probe_egress", "egress_allowed", "egress_refused", "tool_calls", "tool_mix", "hidden_probes", "net_attempts", "web_tools", "git_commit",
              "git_branch", "integrity_max", "f2p_by_round", "round_wall_s_last5", "agent_files", "gold_src_files_touched", "gold_src_missed",
              "agent_touches_hidden_test_files", "apply_problems", "failing_tests", "manifest_verdict", "usd_at_cap20"):
        if k in r: print(f"  {k}: {r[k]}")
