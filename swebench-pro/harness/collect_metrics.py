#!/usr/bin/env python3
"""collect_metrics.py <run_dir> - derive metrics from a cell's raw records.
FeatureBench variant (harness 6.0) of experiment-hotcrp/collect_metrics.py 4.4.
Reads rounds/r*/transcript.jsonl (claude -p stream-json), rounds.tsv, diff files,
session/ (the CLI's own session store, which keeps the THINKING text that
stream-json redacts), regression.json. Writes metrics.json. Raw files stay
untouched: recompute any time.

Counting rules carried over unchanged (experiment-hotcrp/COUNTING-RULES.md v1):
R1 bash segments, R2 read/search command sets, R3 search yields no reads,
R5 path args, R6 combined channels, R9 bash-channel writes, R10 tokens from the
result event (sum across rounds, last-wins within a round for cost: roundcost.py).
Dropped: the HotCRP suite gate, arm-identity leak (no arms here), spec-kit.
Added: per-round acceptance (the hidden F2P/P2P verdicts the agent never saw),
rounds_to_acceptance, thinking text from the session store, the regression check.
"""
import json, re, sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from roundcost import per_round as _round_costs                   # noqa: E402
from roundcost import all_results as _round_invocations           # noqa: E402
from roundcost import usage_sum_matches_modelusage as _usage_ok   # noqa: E402
from test_integrity import audit as _integrity_audit, TEST_RE     # noqa: E402

METRICS_VERSION = "6.0"
run = Path(sys.argv[1])
events = []
round_of_event = []
for f in sorted(run.glob("rounds/r*/transcript.jsonl")) or [run / "transcript.jsonl"]:
    n = int(re.search(r"r(\d+)", f.parent.name).group(1)) if f.parent.name.startswith("r") else 0
    for line in f.read_text(errors="replace").splitlines():
        line = line.strip()
        if line:
            try:
                events.append(json.loads(line)); round_of_event.append(n)
            except json.JSONDecodeError:
                pass
m = {"run_dir": run.name, "metrics_version": METRICS_VERSION}
m.update(json.loads((run / "manifest.json").read_text()))

# ---- tokens, cost, turns (R10; roundcost.py owns the cumulative/per-invocation split)
TOKKEYS = ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")
_rounds = _round_costs(run); _invocations = _round_invocations(run)
results = [r for _, r in _rounds if r]
invocations = [r for _, rs in _invocations for r in rs]
rusage = Counter()
for r in invocations:
    for k, v in (r.get("usage") or {}).items():
        if isinstance(v, (int, float)):
            rusage[k] += v
m["tokens"] = {k: rusage.get(k) for k in TOKKEYS}
m["tokens"]["total"] = sum(rusage.get(k) or 0 for k in TOKKEYS)
cw = Counter()
for r in invocations:
    for k, v in ((r.get("usage") or {}).get("cache_creation") or {}).items():
        cw[k] += v or 0
m["tokens"]["cache_creation_split"] = dict(cw)
m["thinking_tokens"] = sum(
    ((r.get("usage") or {}).get("output_tokens_details") or {}).get("thinking_tokens") or 0
    for r in invocations) or None
m["n_result_events"] = len(invocations); m["n_rounds"] = len(_invocations)
m["background_wakeups"] = len(invocations) - len([1 for _, rs in _invocations if rs])
m["usage_sum_matches_modelusage"] = {f"r{n:02d}": _usage_ok(rs) for n, rs in _invocations}
# total_cost_usd and modelUsage in a result event are CUMULATIVE over the resumed
# session (verified: modelUsage.cacheReadInputTokens of round n = sum of the
# per-invocation usage.cache_read_input_tokens of rounds 0..n), so the cell's
# cost is the LAST result's value, not the sum over rounds (which double-counts).
from roundcost import total_cost, cross_round_cumulative
m["cost_usd"] = total_cost(run) or None
m["cost_cross_round_cumulative"] = cross_round_cumulative(run)
# manifest.json's cost_layers were written by run_cell.sh with the pre-Fault-14 rule for
# cells 2/4/5; recompute both layers here so metrics.json is authoritative
m["cost_layers"] = {"attempt1_oneshot": round(total_cost(run, 0), 4) or None, "to_acceptance": round(total_cost(run), 4) or None}
m["cost_usd_naive_round_sum"] = sum(r.get("total_cost_usd") or 0 for r in results) or None  # = rounds.tsv cum_usd of cells run before the fix; NOT the cost when cumulative
m["turns"] = sum(r.get("num_turns") or 0 for r in invocations)
m["agent_reported_duration_ms"] = sum(r.get("duration_ms") or 0 for r in invocations) or None
m["api_duration_ms"] = sum(r.get("duration_api_ms") or 0 for r in invocations) or None
m["result_subtype"] = invocations[-1].get("subtype") if invocations else None
m["result_is_error"] = any(r.get("is_error") for r in invocations) if invocations else None
# the last result's modelUsage is the session-cumulative token picture and, unlike
# usage.*, INCLUDES subagent (Agent tool) traffic: mlflow test_mlflow r04 ran a
# subagent and its modelUsage.outputTokens exceeds the summed usage by 19,517
m["tokens_modelusage_final"] = {model: {k: u.get(k) for k in ("inputTokens", "outputTokens", "cacheReadInputTokens", "cacheCreationInputTokens", "webSearchRequests", "contextWindow")}
                                for model, u in ((results[-1].get("modelUsage") or {}) if results else {}).items()}
m["subagent_tool_calls"] = sum(1 for e in events if e.get("type") == "assistant"
                              for b in ((e.get("message") or {}).get("content") or [])
                              if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("name") == "Agent")
m["cost_by_model_usd"] = {model: (u.get("costUSD") or 0)
                          for model, u in ((results[-1].get("modelUsage") or {}) if results else {}).items()}

# per-message cross-check (dedup by message id; exact for input/cache keys)
per_msg = {}
for e in events:
    if e.get("type") == "assistant":
        msg = e.get("message") or {}
        per_msg[msg.get("id")] = msg.get("usage") or {}
cross = Counter()
for u in per_msg.values():
    for k in TOKKEYS: cross[k] += u.get(k) or 0
m["tokens_crosscheck_per_message"] = dict(cross)
m["tokens_crosscheck_agrees"] = {k: (cross[k] == (rusage.get(k) or 0)) for k in TOKKEYS}
m["api_calls"] = len(per_msg)
ctx = [((u.get("input_tokens") or 0) + (u.get("cache_read_input_tokens") or 0) + (u.get("cache_creation_input_tokens") or 0))
       for u in per_msg.values()]
m["context_k"] = {"mean": round(sum(ctx) / len(ctx) / 1000, 1) if ctx else None,
                  "max": round(max(ctx) / 1000, 1) if ctx else None}
models = sorted({e["message"]["model"] for e in events if e.get("type") == "assistant"
                 and isinstance(e.get("message"), dict) and e["message"].get("model")})
m["model_used"] = models
m["model_matches_requested"] = (models == [m["model_requested"]] if m.get("model_requested") else None)
m["assistant_events"] = sum(1 for e in events if e.get("type") == "assistant")

# ---- per-round table: cost/turns from transcripts, acceptance from rounds.tsv ---
acc_rows = {}
rt = run / "rounds.tsv"
if rt.exists():
    lines = rt.read_text().splitlines()
    hdr = lines[0].split("\t") if lines else []
    for l in lines[1:]:
        d = dict(zip(hdr, l.split("\t")))
        if d.get("round", "").isdigit(): acc_rows[int(d["round"])] = d
m["per_round"] = []
_prev_cum = 0.0
for n, rs in _invocations:
    a = acc_rows.get(n, {})
    _cum_n = (total_cost(run, n) if rs else None)
    _round_cost = (round(_cum_n - _prev_cum, 6) if _cum_n is not None else None)
    if _cum_n is not None: _prev_cum = _cum_n
    m["per_round"].append({
        "round": n, "kind": a.get("kind"), "invocations": len(rs),
        "cost_usd": _round_cost, "cum_cost_usd": _cum_n,
        "turns": sum(r.get("num_turns") or 0 for r in rs) or None,
        "duration_ms": sum(r.get("duration_ms") or 0 for r in rs) or None,
        "wall_ms": int(a["wall_ms"]) if a.get("wall_ms", "").isdigit() else None,
        "subtype": (rs[-1].get("subtype") if rs else None),
        "is_error": any(r.get("is_error") for r in rs) if rs else None,
        "tokens": {k: sum((r.get("usage") or {}).get(k) or 0 for r in rs) for k in TOKKEYS},
        "accept": a.get("accept"), "f2p": a.get("f2p"), "p2p": a.get("p2p"),
        "test_integrity": a.get("test_integrity"),
        "tool_calls": sum(1 for e, rn in zip(events, round_of_event) if rn == n and e.get("type") == "assistant"
                          for b in ((e.get("message") or {}).get("content") or [])
                          if isinstance(b, dict) and b.get("type") == "tool_use"),
    })
passes = [n for n, a in sorted(acc_rows.items()) if a.get("accept") == "PASS"]
m["acceptance"] = {
    "rounds_to_acceptance": (passes[0] + 1) if passes else None,   # 1 = first attempt
    "blind_rounds_before_pass": passes[0] if passes else None,
    "accepted": bool(passes),
    "f2p_by_round": [acc_rows[n].get("f2p") for n in sorted(acc_rows)],
    "p2p_by_round": [acc_rows[n].get("p2p") for n in sorted(acc_rows)],
    "first_f2p_pass_round": next((n for n in sorted(acc_rows) if acc_rows[n].get("f2p") == "PASS"), None),
    "note": "the agent never saw any of these verdicts; blind rounds carried only blind_msg.txt",
}

# ---- reasoning: stream-json redacts thinking text; the session store keeps it ----
think_blocks_stream = think_chars_stream = text_chars = 0
for e in events:
    for blk in ((e.get("message") or {}).get("content") or []):
        if isinstance(blk, dict):
            if blk.get("type") == "thinking":
                think_blocks_stream += 1; think_chars_stream += len(blk.get("thinking", ""))
            elif blk.get("type") == "text":
                text_chars += len(blk.get("text", ""))
m["response_text_chars"] = text_chars
sess_files = sorted((run / "session").rglob("*.jsonl")) if (run / "session").exists() else []
sess_think_blocks = sess_think_chars = 0; sess_tool_uses = 0; sess_lines = 0
sess_ids = set()
for f in sess_files:
    for line in f.read_text(errors="replace").splitlines():
        try: e = json.loads(line)
        except json.JSONDecodeError: continue
        sess_lines += 1
        if e.get("sessionId"): sess_ids.add(e["sessionId"])
        for blk in ((e.get("message") or {}).get("content") or []) if isinstance(e.get("message"), dict) else []:
            if isinstance(blk, dict):
                if blk.get("type") == "thinking":
                    sess_think_blocks += 1; sess_think_chars += len(blk.get("thinking", ""))
                elif blk.get("type") == "tool_use":
                    sess_tool_uses += 1
m["reasoning"] = {
    "stream_json_thinking_blocks": think_blocks_stream,
    "stream_json_thinking_chars": think_chars_stream,
    "session_store_files": [str(f.relative_to(run)) for f in sess_files],
    "session_store_session_ids": sorted(sess_ids),
    "session_store_thinking_blocks": sess_think_blocks,
    "session_store_thinking_chars": sess_think_chars,
    "session_store_tool_uses": sess_tool_uses,
    "thinking_text_captured": sess_think_chars > 0,
    "note": ("thinking TEXT comes from session/ (the CLI's own store, copied out of the container); "
             "stream-json carries only redacted thinking blocks; thinking_tokens from the result event is the volume"),
}

# ---- tool usage (tool channel) --------------------------------------------------
tools = Counter(); reads = []; edits = []; searches = 0
first_edit_seen = False; reads_before_first_edit = 0
tool_seq = []
for e, rn in zip(events, round_of_event):
    for blk in ((e.get("message") or {}).get("content") or []):
        if not (isinstance(blk, dict) and blk.get("type") == "tool_use"):
            continue
        name = blk.get("name", "?"); tools[name] += 1
        inp = blk.get("input") or {}
        path = inp.get("file_path") or inp.get("path") or inp.get("notebook_path") or ""
        path = re.sub(r"^/testbed/", "", path)
        tool_seq.append({"round": rn, "tool": name, "path": path or None,
                         "cmd": (inp.get("command") or "")[:200] if name == "Bash" else None})
        if name in ("Read", "View", "NotebookRead"):
            reads.append(path)
            if not first_edit_seen: reads_before_first_edit += 1
        elif name in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
            edits.append(path); first_edit_seen = True
        elif name in ("Grep", "Glob", "WebSearch", "Search"):
            searches += 1
m["tool_calls"] = dict(tools)
m["tool_calls_total"] = sum(tools.values())
m["files_read_unique"] = len(set(reads)); m["file_reads_total"] = len(reads)
m["file_rereads"] = len(reads) - len(set(reads))
m["reads_before_first_edit"] = reads_before_first_edit
m["searches"] = searches
m["files_edited_unique"] = len(set(edits))
m["files_read"] = sorted(set(reads)); m["files_edited"] = sorted(set(edits))
m["subagents"] = tools.get("Agent", 0) + tools.get("Task", 0)
m["web_tools"] = tools.get("WebFetch", 0) + tools.get("WebSearch", 0)
(run / "tool_sequence.json").write_text(json.dumps(tool_seq, indent=1))

# ---- bash-channel reading (COUNTING-RULES.md v1, R1-R9) ---------------------------
COUNTING_RULES_VERSION = "1"
READ_CMDS = {"cat", "sed", "head", "tail", "nl", "awk", "od", "strings", "diff", "less", "more", "view", "bat"}
SEARCH_CMDS = {"grep", "egrep", "fgrep", "rg", "ag", "ack", "find", "ls", "locate", "fd", "tree"}
EXTS = ("py", "pyi", "pyx", "pxd", "txt", "md", "rst", "sh", "json", "toml", "cfg", "ini", "yml", "yaml",
        "c", "h", "cpp", "js", "css", "html", "xml", "ipynb", "csv", "tex")
EXT_RE = re.compile(r"\.(" + "|".join(EXTS) + r")$")
RANGE_RE = re.compile(r"^[0-9,]+[a-z]?$")
HEREDOC_RE = re.compile(r"<<-?\s*['\"]?([A-Za-z_][A-Za-z_0-9]*)['\"]?")
CMDNAME_RE = re.compile(r"^[A-Za-z_][A-Za-z_0-9.+-]*$")

def strip_heredocs(cmd):
    lines = (cmd or "").split("\n"); out = []; i = 0
    while i < len(lines):
        out.append(lines[i]); tags = HEREDOC_RE.findall(lines[i]); i += 1
        for tag in tags:
            while i < len(lines) and lines[i].strip() != tag: i += 1
            i += 1
    return "\n".join(out)

def split_top_level(cmd):
    segs, cur, q, i, n = [], [], None, 0, len(cmd)
    while i < n:
        ch = cmd[i]
        if q:
            cur.append(ch)
            if ch == "\\" and q == '"' and i + 1 < n: cur.append(cmd[i + 1]); i += 2; continue
            if ch == q: q = None
            i += 1; continue
        if ch in "'\"": q = ch; cur.append(ch); i += 1; continue
        if ch == "\\" and i + 1 < n and cmd[i + 1] == "\n": cur.append(" "); i += 2; continue
        if ch in ";\n": segs.append("".join(cur)); cur = []; i += 1; continue
        if ch == "|":
            i += 2 if (i + 1 < n and cmd[i + 1] == "|") else 1
            segs.append("".join(cur)); cur = []; continue
        if ch == "&" and i + 1 < n and cmd[i + 1] == "&": segs.append("".join(cur)); cur = []; i += 2; continue
        cur.append(ch); i += 1
    segs.append("".join(cur)); return segs

def bash_segments(cmd):
    for seg in split_top_level(strip_heredocs(cmd or "")):
        parts = seg.strip().split()
        while parts and re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*=.*", parts[0]): parts = parts[1:]
        if not parts: continue
        name = parts[0].split("/")[-1]
        if CMDNAME_RE.match(name): yield name, parts[1:]

REDIR_RE = re.compile(r"^[0-9&]*>>?$"); DUPFD_RE = re.compile(r"^[0-9]*>>?&[0-9-]+$")
def redirect_targets(args):
    out, take = [], False
    for a in args:
        if take: take = False; out += path_args([a]); continue
        if DUPFD_RE.match(a): continue
        if REDIR_RE.match(a): take = True; continue
        if a.startswith(">"): out += path_args([a.lstrip(">")])
    return out
def path_args(args):
    out = []; skip_next = False
    for a in args:
        if skip_next: skip_next = False; continue
        if DUPFD_RE.match(a): continue
        if REDIR_RE.match(a): skip_next = True; continue
        if a.startswith(">"): continue
        if not a or a[0] in "-$'\"(": continue
        if RANGE_RE.match(a): continue
        if a.endswith("/"): continue
        if "/" not in a and not EXT_RE.search(a): continue
        a = re.sub(r"^/testbed/", "", a)
        out.append(re.sub(r"^\./", "", a))
    return out
WRITE_CMDS = {"tee", "cp", "mv", "patch", "install", "truncate", "touch"}
bash_reads, bash_searches, bash_written, unclassified = [], 0, [], Counter()
bash_python_runs = 0; bash_pytest_runs = 0; bash_git = 0
first_write_at = None
for e in events:
    for blk in ((e.get("message") or {}).get("content") or []):
        if not (isinstance(blk, dict) and blk.get("type") == "tool_use" and blk.get("name") == "Bash"): continue
        cmd = (blk.get("input") or {}).get("command", "")
        for c, args in bash_segments(cmd):
            if c in READ_CMDS: bash_reads += path_args(args)
            elif c in SEARCH_CMDS: bash_searches += 1
            elif c in ("python", "python3", "pytest", "py.test", "bin/test"):
                if c.startswith("py") and c != "python" and c != "python3": bash_pytest_runs += 1
                elif any(a in ("-m",) for a in args[:1]) and len(args) > 1 and args[1] in ("pytest", "sympy"): bash_pytest_runs += 1
                else: bash_python_runs += 1
            elif c == "git": bash_git += 1
            else: unclassified[c] += 1
            w = redirect_targets(args)
            if c in WRITE_CMDS or (c == "sed" and "-i" in args): w += [p for p in path_args(args)][-1:]
            if w:
                bash_written += w
                if first_write_at is None: first_write_at = len(reads) + len(bash_reads)
all_reads = reads + bash_reads
m["reading"] = {
    "rules_version": COUNTING_RULES_VERSION,
    "tool_channel": {"unique": len(set(reads)), "total": len(reads)},
    "bash_channel": {"unique": len(set(bash_reads)), "total": len(bash_reads)},
    "combined_unique": len(set(all_reads)), "combined_total": len(all_reads),
    "combined_rereads": len(all_reads) - len(set(all_reads)),
    "searches_tool": searches, "searches_bash": bash_searches,
    "bash_python_runs": bash_python_runs, "bash_pytest_runs": bash_pytest_runs, "bash_git": bash_git,
    "unclassified_commands": dict(unclassified.most_common(20)),
}
m["writing"] = {"tool_channel_edits": len(set(edits)), "bash_channel_writes_unique": len(set(bash_written)),
                "bash_channel_writes_total": len(bash_written), "bash_written_files": sorted(set(bash_written))}
m["reads_before_first_write"] = first_write_at

# ---- diff shape ---------------------------------------------------------------------
stat = run / "diff.stat"
if stat.exists() and stat.read_text().strip():
    last = stat.read_text().strip().splitlines()[-1]
    g = lambda p: (re.search(p, last) or [None, "0"])[1]
    m["diff"] = {"files_changed": int(g(r"(\d+) files? changed")), "insertions": int(g(r"(\d+) insertions?")),
                 "deletions": int(g(r"(\d+) deletions?"))}
touched = run / "files_touched.txt"
tl = touched.read_text().splitlines() if touched.exists() else []
paths = [l.split("\t", 1)[1] for l in tl if "\t" in l]
m["files_touched"] = len(paths)
m["files_touched_split"] = {"test": sorted(p for p in paths if TEST_RE.search(p)),
                            "source": sorted(p for p in paths if not TEST_RE.search(p))}
# the files the MASK removed/changed = the benchmark's own implementation footprint
mask_files = set()
mp = Path(__file__).resolve().parent / "tasks" / m.get("instance_id", "") / "mask.patch"
if mp.exists():
    for l in mp.read_text(errors="replace").splitlines():
        if l.startswith("--- a/") or l.startswith("+++ b/"): mask_files.add(l[6:])
m["mask_files"] = sorted(mask_files)
m["agent_vs_mask_files"] = {"agent_only": sorted(set(paths) - mask_files),
                            "mask_only_not_touched": sorted(mask_files - set(paths)),
                            "both": sorted(mask_files & set(paths))}
# attempt-1 (round 0) diff shape for the one-shot layer
a1 = run / "attempt1.diff.patch"
if a1.exists():
    m["attempt1_files"] = sorted({l[6:] for l in a1.read_text(errors="replace").splitlines() if l.startswith("+++ b/")})

# ---- test-integrity (R11): lines removed/changed in pre-existing tests -------------
diff_txt = (run / "diff.patch").read_text(errors="replace") if (run / "diff.patch").exists() else ""
m["test_integrity"] = _integrity_audit(diff_txt)

# ---- existing-feature regression (run_regress.sh) -----------------------------------
rg = run / "regression.json"
if rg.exists():
    r = json.loads(rg.read_text())
    m["regression"] = {k: r.get(k) for k in ("status", "scope", "verdict", "n_regressions", "regressions", "gold", "agent")}
    m["regression"]["paths"] = len(r.get("paths") or [])
else:
    m["regression"] = {"status": "not_run"}

# ---- isolation attestation ------------------------------------------------------------
iso_raw = (run / "isolation.txt").read_text(errors="replace") if (run / "isolation.txt").exists() else ""
home_files = sorted({l.strip() for l in iso_raw.splitlines() if l.startswith("/agent-home")})
FORBIDDEN = ("projects", "sessions", "history.jsonl", "memory", "MEMORY.md", "settings.json",
             "settings.local.json", "backups", "CLAUDE.md", "statsig", "todos", "shell-snapshots", "plugins")
egress = dict(re.findall(r"^\s+(\S+) -> (\d+)$", iso_raw, re.M))
m["isolation"] = {
    "recorded": bool(iso_raw),
    "runs_as_root": "uid=0(" in iso_raw,
    "home_entries": home_files,
    "home_unexpected": sorted({f for f in home_files if any(w in f for w in FORBIDDEN)}),
    "claude_md_present": [l.split()[1] for l in iso_raw.splitlines() if l.startswith("PRESENT ")],
    "repo_shipped_claude_md": [l.split(": ", 1)[1] for l in iso_raw.splitlines() if "repo-shipped:" in l],
    "hidden_test_absent": f"absent  /testbed/{m.get('f2p','')}" in iso_raw,
    "mask_and_pristine_absent": ("absent  /root/my_repo" in iso_raw and "absent  /tmp/mask.patch" in iso_raw),
    "egress": egress,
    "egress_only_model_api": all(v.startswith("000") for h, v in egress.items() if h not in ("api.anthropic.com", "platform.claude.com")),
    "mcp_servers_seen": sorted({sv.get("name", "?") for e in events if e.get("type") == "system"
                                and e.get("subtype") == "init" for sv in (e.get("mcp_servers") or [])}),
    "mcp_tools_offered": max([len([t for t in (e.get("tools") or []) if str(t).startswith("mcp__")])
                              for e in events if e.get("type") == "system" and e.get("subtype") == "init"] or [0]),
    "mcp_tools_invoked": sum(1 for e in events if e.get("type") == "assistant"
                             for b in ((e.get("message") or {}).get("content") or [])
                             if isinstance(b, dict) and b.get("type") == "tool_use" and str(b.get("name", "")).startswith("mcp__")),
    "tools_offered": sorted({str(t) for e in events if e.get("type") == "system" and e.get("subtype") == "init"
                             for t in (e.get("tools") or [])}),
    "server_tool_use": {k: sum(int(((e.get("usage") or {}).get("server_tool_use") or {}).get(k) or 0)
                               for e in events if e.get("type") == "result")
                        for k in ("web_search_requests", "web_fetch_requests")},
}
m["isolation"]["no_server_web_tools"] = (not any(m["isolation"]["server_tool_use"].values())
                                         and not {"WebSearch", "WebFetch"} & set(m["isolation"]["tools_offered"]))
# contamination words: did the agent ever mention the benchmark / hidden tests by name?
raw = "".join(json.dumps(e) for e in events).lower()
m["leak_words"] = {w: raw.count(w) for w in ("featurebench", "fail_to_pass", "pass_to_pass", "hidden test", "my_repo", "mask.patch", "libercoders", "hcexp", "fbexp")
                   if raw.count(w)}

(run / "metrics.json").write_text(json.dumps(m, indent=2))
print(json.dumps({k: m[k] for k in ("run_dir", "instance_id", "verdict", "acceptance", "cost_usd", "turns", "api_calls",
                                     "tokens", "thinking_tokens", "reasoning", "tool_calls", "files_read_unique",
                                     "file_rereads", "reading", "writing", "files_touched_split", "agent_vs_mask_files",
                                     "test_integrity", "regression", "isolation", "leak_words", "model_used",
                                     "model_matches_requested") if k in m}, indent=2, default=str))
