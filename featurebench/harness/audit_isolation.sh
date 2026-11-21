#!/usr/bin/env bash
# audit_isolation.sh - run BEFORE any launch. One question: can anything from a
# previous run, from the experimenter's machine, or from the benchmark's answer key
# (the hidden tests, the mask patch, the pristine copy) reach the agent?
# Harness 6.0 port of experiment-hotcrp/audit_isolation.sh (checks renumbered).
HERE=$(realpath "$(dirname "$0")"); FAILED=0
ok ()  { printf '  PASS  %s\n' "$1"; }
bad () { printf '  FAIL  %s\n' "$1"; FAILED=1; }
RC="$HERE/run_cell.sh"

echo "== 1. the prompt is the benchmark's problem statement and nothing else =="
for d in "$HERE"/tasks/*/; do
  [ -f "$d/meta.json" ] || continue
  want=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['problem_statement_sha256'])" "$d/meta.json")
  have=$(sha256sum "$d/prompt.txt" | cut -d' ' -f1)
  [ "$want" = "$have" ] && ok "$(basename "$d"): prompt.txt sha256 == dataset problem_statement" || bad "$(basename "$d"): prompt.txt differs from the dataset"
done
grep -q 'PROMPT_FILE="\${SMOKE_PROMPT:-\$TASK_DIR/prompt.txt}"' "$RC" && ok "baseline round 0 sends tasks/<id>/prompt.txt verbatim (stdin, no wrapper text)" || bad "round 0 prompt is not the raw file"
# index arm v2 (2026-10-27): round 0 = index_preamble.txt + blank line + prompt.txt, nothing else
grep -qF '{ cat "$TASK_DIR/prompt.txt"; printf '"'"'\n'"'"'; cat "$HERE/index_preamble.txt"; } > "$RUN_DIR/prompt_r0.txt"' "$RC" && ok "index round 0 = index_preamble.txt + blank line + prompt.txt" || bad "index round 0 assembly changed"
for w in hidden test_patch FAIL_TO_PASS pytest " test"; do grep -qi -- "$w" "$HERE/index_preamble.txt" && bad "index_preamble.txt mentions '$w'"; done
ok "index_preamble.txt: $(tr -d '\n' < "$HERE/index_preamble.txt")"
# change-impact arm (2026-10-29): round 0 = impact_preamble.txt + blank line + prompt.txt, nothing else
grep -qF '{ cat "$TASK_DIR/prompt.txt"; printf '"'"'\n'"'"'; cat "$HERE/impact_preamble.txt"; } > "$RUN_DIR/prompt_r0.txt"' "$RC" && ok "impact round 0 = impact_preamble.txt + blank line + prompt.txt" || bad "impact round 0 assembly changed"
for w in hidden test_patch FAIL_TO_PASS pytest " test"; do grep -qi -- "$w" "$HERE/impact_preamble.txt" && bad "impact_preamble.txt mentions '$w'"; done
ok "impact_preamble.txt: $(tr -d '\n' < "$HERE/impact_preamble.txt")"
# vague-prompt arm (2026-11-02): round 0 = tasks/<id>/prompt_vague.txt raw; every line of it is either a line of the
# dataset prompt.txt or an "Importable as `...`" line (the only test-derived text), so nothing else from the test can enter
grep -qF 'PROMPT_FILE="$TASK_DIR/prompt_vague.txt"' "$RC" && ok "vague round 0 sends tasks/<id>/prompt_vague.txt raw" || bad "vague round 0 assembly changed"
for v in "$HERE"/tasks/*/prompt_vague.txt; do
  extra=$(python3 -c "import sys;o=set(open(sys.argv[1]).read().splitlines());print(sum(1 for l in open(sys.argv[2]).read().splitlines() if l not in o and not l.startswith('Importable as \`')))" "$(dirname "$v")/prompt.txt" "$v")
  [ "$extra" = 0 ] && ok "$(basename "$(dirname "$v")" | cut -c1-50): prompt_vague.txt adds only Importable lines" || bad "$(dirname "$v"): prompt_vague.txt has $extra lines not in prompt.txt"
done
# goal-only arm (2026-11-03): round 0 = tasks/<id>/prompt_goal.txt raw; it must be a verbatim PREFIX of the dataset
# prompt.txt (nothing added or reworded) and contain no /testbed path, no Path: line and no .py file name
grep -qF 'PROMPT_FILE="$TASK_DIR/prompt_goal.txt"' "$RC" && ok "goal round 0 sends tasks/<id>/prompt_goal.txt raw" || bad "goal round 0 assembly changed"
for v in "$HERE"/tasks/*/prompt_goal.txt; do
  [ -e "$v" ] || continue
  python3 -c "import re,sys;o=open(sys.argv[1]).read();g=open(sys.argv[2]).read();sys.exit(0 if o.startswith(g.rstrip(chr(10))) and '/testbed' not in g and 'Path:' not in g and not re.search(r'\w+\.py\b',g) else 1)" "$(dirname "$v")/prompt.txt" "$v" \
    && ok "$(basename "$(dirname "$v")" | cut -c1-50): prompt_goal.txt is a verbatim prefix, no paths" || bad "$(dirname "$v"): prompt_goal.txt not a clean prefix"
done
# rewritten-goal arm (2026-11-11): round 0 = tasks/<id>/prompt_goalrw.txt raw (hand-written). It must contain no /testbed
# path, no Path: line, no .py name, and none of the masked module paths or masked/tested symbol names (from prompt_vague.json),
# (2026-11-13: tested names / test imports matched as whole words, not substrings: unit names m, s matched every prompt)
# except a name that the dataset's own pre-interface text (task statement, NOTE, black_links in prompt.txt) already uses as a word (2026-11-11)
grep -qF 'PROMPT_FILE="$TASK_DIR/prompt_goalrw.txt"' "$RC" && ok "goalrw round 0 sends tasks/<id>/prompt_goalrw.txt raw" || bad "goalrw round 0 assembly changed"
for v in "$HERE"/tasks/*/prompt_goalrw.txt; do
  [ -e "$v" ] || continue
  hits=$(python3 -c "
import re,sys,json,os
g=open(sys.argv[1]).read(); j=json.load(open(os.path.join(os.path.dirname(sys.argv[1]),'prompt_vague.json')))
bad=[w for w in ('/testbed','Path:') if w in g]+re.findall(r'\w+\.py\b',g)
for d in j['decisions']:
  bad+=[x for x in [d['module'],d['path'].replace('/testbed/','')]+d['defs'] if re.search(r'(?<![\w.])'+re.escape(x)+r'(?![\w])',g)]
  for m,ns in d.get('tested_names',{}).items(): bad+=[n for n in ns if re.search(r'(?<![\w.])'+re.escape(n)+r'(?![\w])',g)]
for n,ms in j.get('test_project_imports',{}).items(): bad+=[x for x in [n]+ms if re.search(r'(?<![\w.])'+re.escape(x)+r'(?![\w])',g)]
pre=open(os.path.join(os.path.dirname(sys.argv[1]),'prompt.txt')).read().split('## Interface Descriptions')[0]
bad=[x for x in bad if x in ('/testbed','Path:') or x.endswith('.py') or not re.search(r'(?<![\w.])'+re.escape(x)+r'(?![\w])',pre)]
print(' '.join(sorted(set(bad))))" "$v")
  [ -z "$hits" ] && ok "$(basename "$(dirname "$v")" | cut -c1-50): prompt_goalrw.txt names no path, module or masked/tested symbol" || bad "$(dirname "$v"): prompt_goalrw.txt names: $hits"
done
grep -q 'PROMPT_FILE="\$HERE/blind_msg.txt"' "$RC" && ok "later rounds send blind_msg.txt only" || bad "later rounds send something else"
grep -q 'cat /dev/stdin' "$RC" && ok "prompt passed through stdin: no shell interpolation into the text" || bad "prompt interpolated"
for w in FeatureBench hidden "test_patch" FAIL_TO_PASS pytest; do
  grep -qi "$w" "$HERE/blind_msg.txt" && bad "blind_msg.txt mentions '$w'" ; done
ok "blind_msg.txt: $(cat "$HERE/blind_msg.txt" | tr -d '\n')"

echo "== 2. the answer key never reaches the agent =="
grep -q 'rm -f -- "\$MASK"' "$HERE/instruments/prepare_tree.sh" && ok "mask patch deleted right after it is applied (prepare_tree)" || bad "mask patch left in the container"
grep -q 'rm -rf /root/my_repo' "$HERE/instruments/prepare_tree.sh" && ok "pristine copy /root/my_repo removed before the agent exists (benchmark step 1)" || bad "/root/my_repo stays"
grep -q 'rm -f "\$P"; \[ -e "\$P" \] && exit 13' "$HERE/instruments/prepare_tree.sh" && ok "hidden F2P test file deleted, deletion verified (exit 13)" || bad "F2P deletion unverified"
grep -q 'rm -rf .git && git init' "$HERE/instruments/prepare_tree.sh" && ok "git history replaced by one commit: no upstream commit/branch names (benchmark step 6)" || bad "git history visible"
if grep -qE '^\s+-v .*(tasks|test\.patch|gold|runs)' "$RC"; then bad "a tasks/ or runs/ path is mounted into the agent container"; else ok "tasks/ (test.patch, gold.patch, meta) and runs/ are never mounted"; fi
grep -q 'docker run -d --name "\$acc" --network none "\$IMAGE"' "$RC" && ok "acceptance runs in a SEPARATE fresh container; test.patch is copied there only" || bad "acceptance not isolated from the agent container"
grep -q 'never shown to the agent\|Nothing from that run ever reaches the agent' "$RC" && ok "no acceptance output is routed into any prompt" || bad "acceptance output routing unverified"
grep -qE 'accept\.stdout|VERDICT' "$HERE/blind_msg.txt" && bad "blind message references acceptance output" || ok "blind message is a fixed string"

echo "== 3. the agent container is clean =="
grep -q 'HOME=/agent-home' "$RC" && ok "HOME is a fresh empty dir inside the container: no ~/.claude memory, settings, projects, plugins" || bad "HOME not neutralized"
grep -q 'creds/credentials.json:ro' "$RC" && ok "credential mounted read-only OUTSIDE HOME, copied in with mode 600" || bad "credential mount not read-only"
grep -q 'user 1000:1000' "$RC" && ok "agent is non-root (uid 1000); conda env and / are root-owned" || bad "agent runs as root"
grep -q -- '--strict-mcp-config --mcp-config' "$RC" && ok "MCP: strict empty config (no claude.ai connectors; the 2026-09-03 leak)" || bad "MCP not pinned empty"
grep -q -- '--network hcexp-cellnet' "$RC" && ok "agent container on the INTERNAL network only" || bad "agent container has a routable network"
grep -q 'hcexp-egress:2' "$RC" && ok "egress proxy hcexp-egress:2 (allowlist: api.anthropic.com, statsig, console, platform.claude.com = OAuth refresh, Fault 13)" || bad "egress proxy version unpinned"
grep -q 'ANTHROPIC_API_KEY' "$RC" && ok "API key only if explicitly exported; otherwise OAuth credential" || true
mounts=$(grep -oE '^\s+-v "[^"]+' "$RC" | sed 's/.*-v "//'); echo "$mounts" | sed 's/^/        mount: /'
[ "$(echo "$mounts" | grep -c .)" -le 1 ] && ok "only the read-only credential is mounted; the tree is INSIDE the image, prepared per cell" || bad "unexpected mounts"
grep -q 'cp -r /root/my_repo/\* /testbed/' "$HERE/instruments/prepare_tree.sh" && ok "each cell starts from the image's pristine copy (benchmark step 1)" || bad "tree not fresh per cell"
sid=$(grep -c 'SESSION_ID=\$(python3 -c .import uuid' "$RC"); [ "$sid" = 1 ] && ok "fresh session uuid per cell; one container per cell, removed at exit" || bad "session id not per-cell"
# change-impact arm: exactly one extra settings file, passed by --settings, root-owned outside HOME
[ "$(grep -c -- 'ARM_ARGS="--settings' "$RC")" = 1 ] && [ "$(grep -c -- '--settings /' "$RC")" = 2 ] && grep -q 'ARM_ARGS="--settings /opt/impact/settings.json"' "$RC" && ok "impact arm: one recorded settings file (--settings /opt/impact/settings.json, sha in manifest); HOME stays empty" || bad "settings flag use changed"
grep -q 'chown -R 0:0 /opt/impact' "$RC" && ok "impact arm: hook, graph, settings root-owned, read-only to the agent" || bad "/opt/impact ownership not set"
grep -q 'IMPACT_GRAPH_SHA" = "\$WANT"' "$RC" && ok "impact arm: in-container graph sha must equal the offline-gated sha (exit 6)" || bad "graph sha not compared"
grep -q 'docker rm -f "\$CONTAINER"' "$RC" && ok "container removed on exit (trap)" || bad "container may persist"

echo "== 4. the oracle has been validated per task (preflight) =="
for d in "$HERE"/tasks/*/; do
  n=$(basename "$d")
  if [ -f "$d/preflight.json" ]; then
    python3 -c "import json,sys;p=json.load(open(sys.argv[1]));sys.exit(0 if p['gold']=='PASS' and p['noop']=='FAIL' else 1)" "$d/preflight.json" \
      && ok "$n: gold=PASS noop=FAIL on $(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['image'])" "$d/preflight.json")" || bad "$n: preflight not gold=PASS/noop=FAIL"
  else echo "  ----  $n: no preflight yet (run_cell.sh will refuse, exit 4)"; fi
done
grep -q 'CELL REFUSED TO START' "$RC" && ok "run_cell.sh refuses without a passing preflight" || bad "no preflight gate"

echo "== 5. cost rule and records =="
grep -q 'from roundcost import' "$HERE/collect_metrics.py" && grep -q 'roundcost' "$HERE/cell_cost.py" && ok "cost: sum across rounds, last-wins within a round (roundcost.py, Fault 2) in both readers" || bad "cost rule not shared"
grep -q 'docker cp "\$CONTAINER:/agent-home/.claude/projects"' "$RC" && ok "session store copied out before the container dies (thinking text is redacted by the CLI; only thinking_tokens are measurable)" || bad "session store not preserved"
grep -q 'sk-ant' "$RC" && ok "copied session store scanned for credential-like strings" || bad "no credential scan on the copied store"

echo "== 6. superseded data is quarantined, not pooled =="
stale=$(python3 - "$HERE/runs" <<'PYAUDIT'
import json, pathlib, sys
bad = []
for d in sorted(pathlib.Path(sys.argv[1]).glob("2026*")):
    if not d.is_dir(): continue
    m = d / "manifest.json"
    if not m.is_file(): bad.append("%s: no manifest" % d.name); continue
    try: j = json.loads(m.read_text(encoding="utf-8"))
    except Exception as e: bad.append("%s: unreadable manifest (%s)" % (d.name, e)); continue
    if j.get("protocol") != "run-to-acceptance": bad.append("%s: protocol %r" % (d.name, j.get("protocol")))
    elif not j.get("finished"): bad.append("%s: never finished" % d.name)
    elif j.get("valid") is False: bad.append("%s: INVALID cell (agent_unavailable) - exclude" % d.name)
print("\n".join(bad))
PYAUDIT
)
if [ -n "$stale" ]; then bad "runs/ holds non-current, unfinished or invalid cells"; echo "$stale" | sed 's/^/        /'; else ok "runs/ holds only completed, valid cells"; fi
echo; [ "$FAILED" = 0 ] && echo "AUDIT: PASS" || echo "AUDIT: FAIL"; exit $FAILED
