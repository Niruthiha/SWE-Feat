#!/usr/bin/env python3
"""dv_extract_common.py - copy of experiment-swebench-pro/analysis/dv_extract.py, repo root / prompt file parameterised (REPO, PROMPT, ROOT) so FeatureBench cells get identical measures.

ORIGINAL DOC: automated dependent variables for the no-hint SWE-Pro cells.

usage: dv_extract.py            (all cells listed in runs/nohint-state.tsv with cell_exit_*)
writes analysis/dv/auto/<short>.json (per-cell detail: call table, per-required-file discovery) and is merged with the
hand coding in analysis/dv/coded.json by dv_table.py into analysis/dv/DV_TABLE.csv + DV_QUAL.json.

All measures are computed from the agent's own transcript (run root transcript.jsonl, all rounds), the task's gold.patch
and the preflight leave-one-file-out ablation (tasks/<iid>/ablation/results.txt). Heuristics are listed in DEFS below
and copied into every output so a reader can audit them.
"""
import json, re, os, sys, glob, collections, posixpath

ROOT = None  # set by caller
REPO = "/app"
PROMPT = "prompt.txt"
OUT = None
CODE_EXT = r"\.(tsx?|jsx?|mjs|cjs|scss|css|py|go|json|md|mdx|yml|yaml|html|snap)"
PATH_RE = re.compile(r"(?<![\w@])((?:\.{1,2}/|/)?[\w@.\-]+(?:/[\w@.\-\[\]]+)*" + CODE_EXT + r")\b")
TEST_RE = re.compile(r"(\.test\.|\.spec\.|__tests__|/tests?/|jest\.|\.snap$)")
DOC_RE = re.compile(r"(\.mdx?$|(^|/)README|(^|/)docs?/|CHANGELOG)", re.I)

DEFS = {
 "call": "one tool_use block. Bash calls are split into segments on ; && || | and newlines (heredoc bodies kept with their segment).",
 "search": "segment whose command is grep/rg/ag/git grep/find/fd/git ls-files.",
 "list": "ls/tree/du/wc -l of paths.",
 "read_full": "cat/bat/less/nl or Read tool on a file without range -> whole file body read.",
 "read_part": "sed -n / head / tail / awk with a file argument, or Read with offset/limit -> part of a body.",
 "grep_on_file": "grep/rg naming specific files (not -r over a dir) -> only matching lines seen (signature-level).",
 "edit": "Edit/Write/MultiEdit/NotebookEdit tool, sed -i, perl -pi, tee, '>'/'>>' redirect into a repo file, python heredoc with open(<path>,'w') or a p='<path>' variable later written, git apply/checkout -- <file>.",
 "test_run": "segment running jest/vitest/mocha/npm|yarn test/pytest/go test.",
 "typecheck": "tsc / yarn check-types / eslint (lint counted separately).",
 "probe": "segment running node -e/-p, ts-node, tsx, python -c, or a scratch script/test that is NOT in the final diff.",
 "required_gold": "gold.patch code files (non-test) that exist at base.",
 "required_test": "files whose removal from the gold patch makes the hidden tests FAIL (preflight ablation).",
 "seen": "file path (or its relative suffix) appears in a tool result.",
 "opened": "file read_full or read_part.",
 "found": "opened or edited.",
 "nav_method": "how a required file was FIRST seen: benchmark_clue (path in prompt) | search (path printed by a search segment) | listing (ls/find without pattern) | following_code (an import/require of its module stem appears in a result before it is seen) | tests (first seen in a test file body or test-run output) | documentation | recall (opened/edited with no prior sighting).",
 "orientation": "calls / API turns / context tokens before the first edit to a repo file.",
 "first_done": "end of round 0 (last result event of r00). Mid-round result events caused by background-task waits are not counted as 'done'.",
 "rework": "an edit to a file already edited, where between that file's previous edit and this one the agent opened or saw a not-previously-opened file (discovery-triggered).",
}

def load_calls(run):
    """Return list of calls in order with result text, round, and api turn index; plus api turns usage."""
    calls, results, turns, seen_msg = [], {}, [], {}
    rnd = 0; nres = 0; rounds_end = []
    tr = f"{run}/transcript.jsonl"
    # map rounds by result events per round dir
    per_round_results = {}
    for d in sorted(glob.glob(f"{run}/rounds/r*")):
        n = 0
        for l in open(f"{d}/transcript.jsonl", errors="replace"):
            try: o = json.loads(l)
            except Exception: continue
            if o.get("type") == "result": n += 1
        per_round_results[os.path.basename(d)] = n
    bounds = []; acc = 0
    for r, n in per_round_results.items():
        acc += n; bounds.append(acc)
    ri = 0
    for l in open(tr, errors="replace"):
        try: o = json.loads(l)
        except Exception: continue
        t = o.get("type")
        if t == "assistant":
            m = o["message"]; mid = m.get("id")
            u = m.get("usage", {}) or {}
            if mid not in seen_msg:
                seen_msg[mid] = len(turns)
                turns.append({"id": mid, "round": ri, "ctx": (u.get("input_tokens") or 0) + (u.get("cache_read_input_tokens") or 0) + (u.get("cache_creation_input_tokens") or 0),
                              "out": u.get("output_tokens") or 0, "ncalls_before": len(calls)})
            else:
                ti = seen_msg[mid]; turns[ti]["out"] = max(turns[ti]["out"], u.get("output_tokens") or 0)
            for b in m.get("content", []):
                if b.get("type") == "tool_use":
                    calls.append({"i": len(calls) + 1, "id": b["id"], "tool": b["name"], "input": b.get("input", {}), "round": ri, "turn": seen_msg[mid], "ts": o.get("timestamp")})
                elif b.get("type") == "text":
                    calls.append({"i": None, "text": b["text"], "round": ri, "turn": seen_msg[mid]})
        elif t == "user":
            c = o.get("message", {}).get("content")
            if isinstance(c, list):
                for b in c:
                    if b.get("type") == "tool_result":
                        cc = b.get("content")
                        cc = cc if isinstance(cc, str) else "\n".join(x.get("text", "") for x in (cc or []) if isinstance(x, dict))
                        results[b["tool_use_id"]] = cc
        elif t == "result":
            nres += 1
            if ri < len(bounds) and nres >= bounds[ri]:
                rounds_end.append(len([c for c in calls if c.get("i")])); ri += 1
    for c in calls:
        if c.get("i"): c["result"] = results.get(c["id"], "")
    return calls, turns, rounds_end

HEREDOC = re.compile(r"<<-?\s*['\"]?(\w+)['\"]?.*?\n(.*?)\n\s*\1\s*(?:\n|$)", re.S)

def segments(cmd):
    """split a bash command into (segment_text, heredoc_body) pieces."""
    bodies = []
    def keep(m):
        bodies.append(m.group(2)); return f" __HEREDOC{len(bodies)-1}__\n"
    flat = HEREDOC.sub(keep, cmd)
    flat = re.sub(r"\w+=\$\(|(?<!['\"])\$\(", "\n", flat)   # command substitution: treat the inner command as its own statement
    segs = []
    # quote-aware split: statements on newline ; && || ; pipeline stages on single |
    stmts, cur, stages, q, i = [], [], [], None, 0
    def flush_stage():
        t = "".join(cur).strip(); cur.clear()
        if t: stages.append(t)
    def flush_stmt():
        flush_stage()
        if stages: stmts.append(list(stages)); stages.clear()
    while i < len(flat):
        ch = flat[i]
        if q:
            if ch == "\\" and q == '"' and i + 1 < len(flat): cur.append(flat[i:i+2]); i += 2; continue
            if ch == q: q = None
            cur.append(ch); i += 1; continue
        if ch in "'\"": q = ch; cur.append(ch); i += 1; continue
        if ch == "\\" and i + 1 < len(flat): cur.append(flat[i:i+2]); i += 2; continue
        two = flat[i:i+2]
        if two in ("&&", "||"): flush_stmt(); i += 2; continue
        if ch in "\n;": flush_stmt(); i += 1; continue
        if ch == "|": flush_stage(); i += 1; continue
        cur.append(ch); i += 1
    flush_stmt()
    for st in stmts:
        for k, s in enumerate(st):
            m = re.search(r"__HEREDOC(\d+)__", s)
            segs.append((s, bodies[int(m.group(1))] if m else "", k > 0))
    return segs

def norm(cwd, p):
    p = p.strip("'\"")
    if not p or p.startswith("-"): return None
    if not p.startswith("/"): p = posixpath.join(cwd, p)
    p = posixpath.normpath(p)
    if p.startswith(REPO + "/"): return p[len(REPO) + 1:]
    return None  # outside repo (scratch, /tmp)

def classify_bash(cmd, cwd, shvars=None):
    """return list of events: (kind, path_or_None, extra) and new cwd"""
    ev = []; shvars = shvars if shvars is not None else {}
    loops = {m.group(1): m.group(2).split() for m in re.finditer(r"\bfor\s+(\w+)\s+in\s+([^;\n]+?)\s*;\s*do\b", cmd)}
    expanded = []
    for seg in segments(cmd):
        vs = [v for v in loops if re.search(r"\$\{?" + v + r"\b", seg[0])]
        if vs:
            v = vs[0]
            for item in loops[v]:
                expanded.append((re.sub(r"\$\{?" + v + r"\}?(?!\w)", item.strip("'\""), seg[0]), seg[1], seg[2]))
        else: expanded.append(seg)
    for s, body, piped in expanded:
        s = re.sub(r"^(for\s+\w+\s+in\s+[^;]*|do|then|else)\s+", "", s)
        for k_, v_ in re.findall(r"^(?:export\s+)?([A-Za-z_]\w*)=(\S+)$", s): shvars[k_] = v_.strip("'\"")
        for k_, v_ in sorted(shvars.items(), key=lambda kv: -len(kv[0])): s = s.replace("${" + k_ + "}", v_).replace("$" + k_, v_)
        toks = re.findall(r"""'[^']*'|"[^"]*"|\S+""", s)
        if not toks: continue
        # strip env assignments / sudo / timeout
        while toks and (re.match(r"^\w+=", toks[0]) or toks[0] in ("sudo", "timeout", "time", "xargs", "env")):
            toks = toks[1:] if not toks[0] == "timeout" else toks[2:]
        if not toks: continue
        c0 = toks[0]
        if c0 == "cd" and len(toks) > 1:
            d = toks[1].strip("'\"")
            cwd = posixpath.normpath(d if d.startswith("/") else posixpath.join(cwd, d)); continue
        args = [t for t in toks[1:] if not t.startswith("-") and not t.startswith(">")]
        if body and c0 not in ("python3", "python", "node") and re.search(r"open\([^)]*['\"][wa]['\"]|writeFileSync|write_text", body):
            # script saved via heredoc (cat > /tmp/x.py) that writes repo files when run: credit the path literals it names
            for m in re.finditer(PATH_RE, body):
                p_ = norm(cwd, m.group(1))
                if p_: ev.append(("edit", p_, "script-heredoc"))
        redir = re.findall(r">>?\s*([^\s;&|]+)", s)
        for r in redir:
            p = norm(cwd, r)
            if p and not r.startswith("/dev/") and not r.startswith("&"): ev.append(("edit", p, "redirect"))
        if piped and c0 in ("grep", "egrep", "head", "tail", "sort", "uniq", "wc", "awk", "sed", "cut", "tr", "xargs") and not re.search(CODE_EXT + r"\b", " ".join(toks[1:])):
            continue  # stdin filter of the previous command, not a search/read of its own
        if c0 in ("grep", "rg", "ag", "egrep") or (c0 == "git" and len(toks) > 1 and toks[1] == "grep"):
            recursive = any(re.match(r"^-\w*[rR]", t) for t in toks) or c0 in ("rg", "ag") or (c0 == "git")
            files = [norm(cwd, a) for a in args[1:]] if not recursive else []
            files = [f for f in files if f and re.search(CODE_EXT + "$", f)]
            ev.append(("search", None, s[:200]))
            for f in files: ev.append(("grep_on_file", f, s[:120]))
        elif c0 in ("find", "fd") or (c0 == "git" and len(toks) > 1 and toks[1] == "ls-files"):
            ev.append(("search" if ("-name" in s or "-path" in s or c0 == "fd" or "ls-files" in s) else "list", None, s[:200]))
        elif c0 in ("ls", "tree", "du"):
            ev.append(("list", None, s[:200]))
        elif c0 in ("cat", "bat", "less", "nl", "more"):
            for a in args:
                p = norm(cwd, a)
                if p and re.search(CODE_EXT + "$", p): ev.append(("read_full", p, c0))
        elif c0 in ("head", "tail") or (c0 == "sed" and ("-n" in toks or any(t.startswith("-n") for t in toks)) and "-i" not in toks) or c0 == "awk":
            for a in args:
                p = norm(cwd, a)
                if p and re.search(CODE_EXT + "$", p): ev.append(("read_part", p, c0))
        elif c0 == "sed" and any(t.startswith("-i") for t in toks) or c0 == "perl" and "-pi" in s:
            for a in args:
                p = norm(cwd, a)
                if p and re.search(CODE_EXT + "$", p): ev.append(("edit", p, c0 + " -i"))
        elif c0 == "tee":
            for a in args:
                p = norm(cwd, a)
                if p: ev.append(("edit", p, "tee"))
        elif c0 in ("python3", "python", "node") and body:
            # heredoc script: find written files
            var = collections.defaultdict(list)
            for k_, v_ in re.findall(r"(\w+)\s*=\s*['\"]([^'\"\n]+\.\w+)['\"]", body): var[k_].append(v_)
            written = set()
            for m in re.finditer(r"open\(\s*([^,\)]+)\s*,\s*['\"][wa]", body):
                a = m.group(1).strip()
                if a in var: written.update(var[a])
                else: written.add(a.strip("'\""))
            for m in re.finditer(r"writeFileSync\(\s*([^,]+),|(?:Path|pathlib\.Path)\(([^)]+)\)\.write_text", body):
                a = (m.group(1) or m.group(2)).strip()
                if a in var: written.update(var[a])
                else: written.add(a.strip("'\""))
            unresolved = [w for w in written if not re.search(CODE_EXT + "$", w)]
            written = {w for w in written if re.search(CODE_EXT + "$", w)}
            if unresolved:
                written |= {m.group(1) for m in PATH_RE.finditer(body)}
            for w in written:
                p = norm(cwd, w)
                if p: ev.append(("edit", p, c0 + " heredoc"))
            if not written: ev.append(("probe", None, (c0 + " heredoc: " + body[:150])))
        elif c0 in ("node", "ts-node", "tsx") and ("-e" in toks or "-p" in toks) or c0 in ("python3", "python") and "-c" in toks:
            ev.append(("probe", None, s[:200]))
        elif re.search(r"\b(jest|vitest|mocha|pytest)\b|\b(yarn|npm|pnpm) (run )?test\b|\bgo test\b", s):
            ev.append(("test_run", None, s[:200]))
        elif re.search(r"\btsc\b|check-types|type-check", s):
            ev.append(("typecheck", None, s[:200]))
        elif re.search(r"\beslint\b|\blint\b", s):
            ev.append(("lint", None, s[:200]))
        elif c0 == "git":
            sub = toks[1] if len(toks) > 1 else ""
            ev.append(("git_" + sub, None, s[:200]))
            if sub in ("checkout", "restore") and "--" in toks:
                for a in toks[toks.index("--") + 1:]:
                    p = norm(cwd, a)
                    if p: ev.append(("edit", p, "git " + sub))
            if sub == "apply": ev.append(("edit", None, "git apply"))
        elif c0 in ("rm", "mv", "cp", "mkdir", "touch"):
            ev.append(("fs_" + c0, None, s[:200]))
            if c0 in ("cp", "mv", "touch") and args:
                p = norm(cwd, args[-1])
                if p and re.search(CODE_EXT + "$", p): ev.append(("edit", p, c0))
        elif c0 in ("sleep", "echo", "printf", "true", "wait", "pwd", "which", "type", "for", "do", "done", "then", "fi", "if", "else", "x", "f"):
            continue
        else:
            ev.append(("other:" + c0[:20], None, s[:200]))
    return ev, cwd

def gold_info(task):
    gp = open(f"{task}/gold.patch", errors="replace").read()
    files = re.findall(r"^diff --git a/(\S+) b/(\S+)", gp, re.M)
    new = set(re.findall(r"^\+\+\+ b/(\S+)", gp, re.M)) - set(re.findall(r"^--- a/(\S+)", gp, re.M))
    renamed = dict(re.findall(r"^rename from (\S+)\nrename to (\S+)", gp, re.M))
    code = []
    for a, b in files:
        if TEST_RE.search(b) or DOC_RE.search(b) or b.endswith((".json", ".lock", ".snap")): continue
        code.append({"path": b, "base_path": a, "created": (b in new and a == b and f"--- /dev/null\n+++ b/{b}" in gp), "renamed": a != b})
    lines = sum(1 for l in gp.splitlines() if l[:1] in "+-" and not l.startswith(("+++", "---")))
    abl = {}
    ap = f"{task}/ablation/results.txt"
    if os.path.exists(ap):
        for l in open(ap):
            m = re.match(r"minus \d+ (\S+) -> (PASS|FAIL)", l)
            if m: abl[m.group(1)] = m.group(2)
    return code, lines, abl

def prompt_text(task):
    return open(f"{task}/{PROMPT}", errors="replace").read()

def analyse(run, iid):
    task = f"{ROOT}/tasks/{iid}"
    calls, turns, rounds_end = load_calls(run)
    tcalls = [c for c in calls if c.get("i")]
    met = json.load(open(f"{run}/metrics.json"))
    code, glines, abl = gold_info(task)
    prompt = prompt_text(task)
    final_diff = open(f"{run}/diff.patch", errors="replace").read() if os.path.exists(f"{run}/diff.patch") else ""
    final_files = re.findall(r"^diff --git a/\S+ b/(\S+)", final_diff, re.M)
    # ---- per call events
    cwd = REPO; events = []; shvars = {}
    for c in tcalls:
        tool, inp = c["tool"], c["input"]
        if tool == "Bash":
            ev, cwd = classify_bash(inp.get("command", ""), cwd, shvars)
        elif tool == "Read":
            p = norm(REPO, inp.get("file_path", ""))
            ev = [("read_part" if (inp.get("offset") or inp.get("limit")) else "read_full", p, "Read")] if p else []
        elif tool in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
            p = norm(REPO, inp.get("file_path", inp.get("notebook_path", "")))
            ev = [("edit", p, tool)] if p else []
        elif tool in ("Grep", "Glob"):
            ev = [("search", None, json.dumps(inp)[:200])]
        elif tool in ("WebFetch", "WebSearch"):
            ev = [("web", None, json.dumps(inp)[:200])]
        else:
            ev = [("tool:" + tool, None, json.dumps(inp)[:120])]
        c["events"] = ev
        c["paths_seen"] = sorted(set(m.group(1).lstrip("./") for m in PATH_RE.finditer(c.get("result", "")))) if c.get("result") else []
    # first edit to a repo file (exclude scratch files later deleted? keep: any repo edit)
    first_edit = next((c["i"] for c in tcalls if any(e[0] == "edit" and e[1] for e in c["events"])), None)
    n_r0 = rounds_end[0] if rounds_end else len(tcalls)
    r0 = [c for c in tcalls if c["i"] <= n_r0]
    # ---- counts
    kinds = collections.Counter(e[0] for c in tcalls for e in c["events"])
    kinds_r0 = collections.Counter(e[0] for c in r0 for e in c["events"])
    tools = collections.Counter(c["tool"] for c in tcalls)
    read_full = {e[1] for c in tcalls for e in c["events"] if e[0] == "read_full" and e[1]}
    read_part = {e[1] for c in tcalls for e in c["events"] if e[0] == "read_part" and e[1]} - read_full
    grep_only = {e[1] for c in tcalls for e in c["events"] if e[0] == "grep_on_file" and e[1]} - read_full - read_part
    edited = {e[1] for c in tcalls for e in c["events"] if e[0] == "edit" and e[1]}
    seen_all = set(p for c in tcalls for p in c["paths_seen"])
    gold_paths = {g["path"] for g in code} | {g["base_path"] for g in code}
    req_gold = [g for g in code if not g["created"]]
    req_test = [p for p, v in abl.items() if v == "FAIL"]
    def is_test(p): return bool(TEST_RE.search(p))
    def is_doc(p): return bool(DOC_RE.search(p))
    def cat(p):
        if "*" in p or p.endswith((".json", ".lock", ".yml", ".yaml")): return "config"
        if p in edited: return "edited"
        if p in gold_paths: return "gold_not_edited"
        if is_test(p): return "test"
        if is_doc(p): return "doc"
        return "other"
    opened = read_full | read_part
    # dependency exposure: non-edited, non-test, non-doc, non-gold source files the agent touched at body or signature level
    dep_full = {p for p in read_full if cat(p) == "other"}
    dep_part = {p for p in read_part if cat(p) == "other"}
    dep_sig = {p for p in grep_only if cat(p) == "other"}
    # ---- per required file discovery
    def sighting(call, path):
        stem = posixpath.basename(path); rel_hits = [s for s in call["paths_seen"] if path.endswith(s) and ("/" in s or s == stem)]
        return bool(rel_hits)
    stems_import = lambda txt, path: re.search(r"(from|require\(|import)\s*\(?\s*['\"][^'\"]*/" + re.escape(re.sub(r"\.\w+$", "", posixpath.basename(path))) + r"['\"]", txt)
    req = []
    for g in req_gold:
        p, bp = g["path"], g["base_path"]
        rec = {"path": bp, "renamed_to": p if g["renamed"] else None, "test_required": abl.get(p) == "FAIL" or abl.get(bp) == "FAIL"}
        fs = fo = fe = None; how = None; via = None
        for c in tcalls:
            evs = c["events"]
            if fo is None and any(e[0] in ("read_full", "read_part") and e[1] in (p, bp) for e in evs): fo = c["i"]
            if fe is None and any(e[0] == "edit" and e[1] in (p, bp) for e in evs): fe = c["i"]
            if fs is None and (sighting(c, bp) or sighting(c, p)):
                fs = c["i"]
                txt = c.get("result", "")
                m_imp = stems_import(txt, bp)
                rels = [s_ for s_ in c["paths_seen"] if bp.endswith(s_) or p.endswith(s_)]
                pos_path = min((txt.find(r_) for r_ in rels if txt.find(r_) >= 0), default=-1)
                ks = [e[0] for e in evs]
                if m_imp:
                    ls_ = txt.rfind("\n", 0, m_imp.start()) + 1
                    from_grep = bool(re.match(r"\S+\.\w+[:-]\d+[:-]", txt[ls_:m_imp.start()]))  # grep -n line prefix => it is search output, not a body read
                    if via is None and not from_grep and (pos_path < 0 or m_imp.start() < pos_path): via = c["i"]
                if "search" in ks: how = "search"
                elif "list" in ks: how = "listing"
                elif "test_run" in ks: how = "tests"
                else: how = "other_output"
            if fs is None and fo is None and fe is None and how is None:
                txt = c.get("result", "")
                if stems_import(txt, bp): via = c["i"]
        first_any = min([x for x in (fs, fo, fe) if x] or [None]) if any((fs, fo, fe)) else None
        if bp in prompt or p in prompt: nav = "benchmark_clue"
        elif first_any is None: nav = "not_found"
        elif via and (fs is None or via <= fs) and via <= first_any: nav = "following_code"
        elif fs and fs <= first_any:
            nav = how if how != "other_output" else ("following_code" if via else "other_output")
            if how == "search" and via and via < fs: nav = "following_code+search"
        else: nav = "recall"
        # tests: first sighting call is reading a test file
        if fs and nav in ("other_output",):
            c = next(x for x in tcalls if x['i'] == fs)  # fixed: original indexed tcalls[fs-1], wrong once text blocks shift i
            if any(e[0] in ("read_full", "read_part") and e[1] and is_test(e[1]) for e in c["events"]): nav = "tests"
        rec.update({"first_seen_call": fs, "first_opened_call": fo, "first_edit_call": fe, "import_sighting_call": via, "nav_method": nav,
                    "found_before_first_edit": bool((fo and first_edit and fo < first_edit) or (fe and fe == first_edit)),
                    "seen_before_first_edit": bool(fs and first_edit and fs < first_edit),
                    "found_by_done": bool((fo and fo <= n_r0) or (fe and fe <= n_r0)),
                    "edited_final": bp in final_files or p in final_files})
        req.append(rec)
    # ---- rework (discovery-triggered), r0 only
    last_edit = {}; opened_so_far = set(); rework = []
    for c in r0:
        newly = set()
        for e in c["events"]:
            if e[0] in ("read_full", "read_part") and e[1] and e[1] not in opened_so_far: newly.add(e[1])
        for p in c["paths_seen"]:
            pass
        this_call_edits = {e[1] for e in c["events"] if e[0] == "edit" and e[1]}
        for e in c["events"]:
            if e[0] == "edit" and e[1]:
                if e[1] in last_edit:
                    disc = [x for x in last_edit[e[1]]["opened_after"] if x != e[1] and x not in last_edit and x not in this_call_edits]
                    if disc: rework.append({"call": c["i"], "file": e[1], "prev_edit_call": last_edit[e[1]]["call"], "discoveries_between": sorted(disc)[:8]})
                last_edit[e[1]] = {"call": c["i"], "opened_after": set()}
        for f in last_edit.values(): f["opened_after"] |= newly
        opened_so_far |= newly
    # ---- orientation
    pre = [t for t in turns if first_edit is None or t["ncalls_before"] < first_edit]
    tot_ctx = sum(t["ctx"] for t in turns); tot_out = sum(t["out"] for t in turns)
    orient = {"calls_before_first_edit": (first_edit - 1) if first_edit else len(tcalls), "api_turns_before_first_edit": len(pre),
              "ctx_tokens_before_first_edit": sum(t["ctx"] for t in pre), "out_tokens_before_first_edit_streamed": sum(t["out"] for t in pre),
              "share_ctx_before_first_edit": round(sum(t["ctx"] for t in pre) / tot_ctx, 3) if tot_ctx else None,
              "files_opened_before_first_edit": len({e[1] for c in tcalls if first_edit and c["i"] < first_edit for e in c["events"] if e[0] in ("read_full", "read_part") and e[1]}),
              "searches_before_first_edit": sum(1 for c in tcalls if first_edit and c["i"] < first_edit for e in c["events"] if e[0] == "search")}
    # ---- self testing
    test_files_final = [f for f in final_files if is_test(f)]
    added_tests = len(re.findall(r"^\+\s*(it|test)(\.each)?\s*\(", final_diff, re.M))
    modified_existing_tests = [f for f in test_files_final if f"--- /dev/null\n+++ b/{f}" not in final_diff]
    created_tests = [f for f in test_files_final if f not in modified_existing_tests]
    stash_or_revert = sum(1 for c in r0 for e in c["events"] if e[0] in ("git_stash",) or (e[0] == "edit" and e[2].startswith("git ")))
    test_before_edit = any(e[0] == "test_run" for c in r0 if first_edit and c["i"] < first_edit for e in c["events"])
    # ---- docs
    docs_opened = sorted(p for p in opened if is_doc(p))
    docs_seen = sorted(p for p in seen_all if is_doc(p))
    # ---- probes
    scratch = sorted({e[1] for c in tcalls for e in c["events"] if e[0] == "edit" and e[1] and e[1] not in final_files})
    probes = [{"call": c["i"], "what": e[2]} for c in tcalls for e in c["events"] if e[0] == "probe"]
    # ---- per-round
    acc = met.get("acceptance", {})
    rounds = [l.rstrip("\n").split("\t") for l in open(f"{run}/rounds.tsv")][1:] if os.path.exists(f"{run}/rounds.tsv") else []
    tok = met.get("tokens", {})
    r0_tokens = None
    # r0 tokens from round 0 result events (sum usage)
    rt = collections.defaultdict(lambda: collections.Counter())
    for d in sorted(glob.glob(f"{run}/rounds/r*")):
        for l in open(f"{d}/transcript.jsonl", errors="replace"):
            try: o = json.loads(l)
            except Exception: continue
            if o.get("type") == "result":
                for k in ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"):
                    rt[os.path.basename(d)][k] += (o.get("usage") or {}).get(k) or 0
    final_text = [c["text"] for c in calls if not c.get("i") and c["round"] == 0]
    out = {
        "iid": iid, "short": iid, "run": os.path.basename(run), "defs": DEFS,
        "outcome": {"first_try_pass": met.get("acceptance_round") == 0 and met.get("accept") == "PASS", "accept_final": met.get("accept"),
                    "rounds_used": met.get("rounds_used"), "blind_rounds_before_pass": acc.get("blind_rounds_before_pass"),
                    "f2p_by_round": acc.get("f2p_by_round"), "p2p_by_round": acc.get("p2p_by_round"),
                    "cost_first_try_usd": met.get("cost_layers", {}).get("attempt1_oneshot"), "cost_total_usd": met.get("cost_layers", {}).get("to_acceptance"),
                    "tokens_first_try": dict(rt.get("r00", {})), "tokens_total": {k: tok.get(k) for k in ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens", "total")},
                    "wall_s": round(met.get("wall_ms", 0) / 1000), "agent_wall_s_r0": round(int(open(f"{run}/rounds/r00/wall_ms").read().strip()) / 1000) if os.path.exists(f"{run}/rounds/r00/wall_ms") else None},
        "gold": {"lines_changed": glines, "code_files": len(code), "created": sum(g["created"] for g in code), "renamed": sum(g["renamed"] for g in code),
                 "required_gold_existing": len(req_gold), "required_test": len(req_test), "test_required_files": req_test},
        "activity": {"tool_calls": len(tcalls), "tool_calls_r0": len(r0), "tools": dict(tools), "segments_by_kind": dict(kinds), "api_turns": len(turns),
                     "files_read_full": len(read_full), "files_read_part": len(read_part), "files_grep_only": len(grep_only), "files_opened": len(opened),
                     "files_seen_in_output": len(seen_all), "files_edited_any": len(edited), "files_in_final_diff": len(final_files),
                     "searches": kinds.get("search", 0), "calls_with_search": sum(1 for c in tcalls if any(e[0] == "search" for e in c["events"])),
                     "calls_with_read": sum(1 for c in tcalls if any(e[0] in ("read_full", "read_part") for e in c["events"])),
                     "calls_with_edit": sum(1 for c in tcalls if any(e[0] == "edit" for e in c["events"])), "listings": kinds.get("list", 0), "test_runs": kinds.get("test_run", 0), "typechecks": kinds.get("typecheck", 0),
                     "lint_runs": kinds.get("lint", 0), "web_calls": kinds.get("web", 0), "edit_events": kinds.get("edit", 0)},
        "discovery": {"required_gold": req, "share_gold_found_before_first_edit": round(sum(r["found_before_first_edit"] for r in req) / len(req), 3) if req else None,
                      "share_gold_found_by_done": round(sum(r["found_by_done"] for r in req) / len(req), 3) if req else None,
                      "share_gold_seen_by_done": round(sum(bool(r["first_seen_call"] and r["first_seen_call"] <= n_r0) for r in req) / len(req), 3) if req else None,
                      "share_testreq_found_before_first_edit": round(sum(r["found_before_first_edit"] for r in req if r["test_required"]) / max(1, sum(r["test_required"] for r in req)), 3),
                      "share_testreq_found_by_done": round(sum(r["found_by_done"] for r in req if r["test_required"]) / max(1, sum(r["test_required"] for r in req)), 3),
                      "share_gold_edited_final": round(sum(r["edited_final"] for r in req) / len(req), 3) if req else None,
                      "nav_methods": dict(collections.Counter(r["nav_method"] for r in req))},
        "rework": {"n": len(rework), "events": rework},
        "orientation": orient,
        "self_testing": {"test_files_in_final_diff": test_files_final, "existing_test_files_modified": modified_existing_tests, "test_files_created": created_tests,
                         "test_cases_added": added_tests, "ran_tests_before_first_edit": test_before_edit, "stash_or_revert_events": stash_or_revert},
        "exposure": {"dep_files_read_full": sorted(dep_full), "dep_files_read_part": sorted(dep_part), "dep_files_grep_only": sorted(dep_sig),
                     "share_dep_bodies_read": round((len(dep_full) + len(dep_part)) / (len(dep_full) + len(dep_part) + len(dep_sig)), 3) if (dep_full or dep_part or dep_sig) else None,
                     "gold_not_edited_opened": sorted(p for p in opened if cat(p) == "gold_not_edited"), "tests_opened": sorted(p for p in opened if cat(p) == "test")},
        "probing": {"probe_segments": probes, "scratch_repo_files_not_in_final": scratch},
        "docs": {"docs_opened": docs_opened, "docs_seen_in_output": docs_seen[:20], "n_docs_opened": len(docs_opened)},
        "final_message_r0": final_text[-1] if final_text else "",
        "calls": [{"i": c["i"], "round": c["round"], "tool": c["tool"], "events": [[e[0], e[1]] for e in c["events"]],
                   "cmd": (c["input"].get("command") or json.dumps(c["input"]))[:300]} for c in tcalls],
    }
    return out

def cells():
    st = f"{ROOT}/runs/nohint-state.tsv"; seen = {}
    for l in open(st):
        f = l.rstrip("\n").split("\t")
        if len(f) >= 3 and f[1].startswith("cell_exit") and f[2]: seen[f[0]] = f[2]
    return seen

if __name__ == "__main__":
    for iid, run in cells().items():
        if not os.path.exists(f"{run}/transcript.jsonl"): print("skip", iid); continue
        o = analyse(run, iid)
        json.dump(o, open(f"{OUT}/{o['short']}.json", "w"), indent=1, default=list)
        d = o["discovery"]; a = o["activity"]
        print(o["short"], "calls", a["tool_calls"], "searches", a["searches"], "read_full", a["files_read_full"], "part", a["files_read_part"],
              "grep_only", a["files_grep_only"], "| gold found pre-edit", d["share_gold_found_before_first_edit"], "done", d["share_gold_found_by_done"],
              "testreq", d["share_testreq_found_before_first_edit"], d["share_testreq_found_by_done"], "| nav", d["nav_methods"], "| rework", o["rework"]["n"],
              "| orient", o["orientation"]["calls_before_first_edit"], o["orientation"]["ctx_tokens_before_first_edit"])
