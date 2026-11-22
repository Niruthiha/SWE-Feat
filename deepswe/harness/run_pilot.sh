#!/usr/bin/env bash
# run_pilot.sh [list] - DeepSWE pilot, strictly ONE Docker job at a time.
#   phase 1 (no agent, no API cost): per task make_task -> build agent image -> preflight (gold PASS / noop FAIL /
#            hygiene / leave-one-file-out). Task images are KEPT for phase 2 and the later full run.
#   phase 2: one s1 cell per task that passed preflight (round 0 = instruction.md verbatim, then blind rounds,
#            MAX_ROUNDS=30, same protocol as swebench-pro/harness/run_nohint_chain.sh) -> trace export -> egress log.
# Resumable: tasks with preflight.json are not re-validated; tasks with cell_exit_* in runs/pilot-state.tsv are skipped.
# Stops on Docker down, < 25 GB free, or agent unavailable (exit 3: quota/login; that cell is INVALID).
set -uo pipefail
cd "$(dirname "$0")"
export CLAUDE_CREDS="${CLAUDE_CREDS:-$HOME/.claude/.credentials.json}" MAX_ROUNDS="${MAX_ROUNDS:-30}" MEM="${MEM:-8g}"
LIST="${1:-../lists/pilot10.txt}"; mkdir -p runs; LOG=runs/pilot.log; ST=runs/pilot-state.tsv; touch "$ST"
log () { echo "$(date -Iseconds) $*" | tee -a "$LOG"; }
diskok () { df -BG /mnt/c | awk 'NR==2{gsub("G","",$4); exit ($4+0 < 25)}'; }
export_traces () { local rd="$1" out="$1/traces_readable"; mkdir -p "$out"
  for t in "$rd"/rounds/r*/transcript.jsonl; do r=$(basename "$(dirname "$t")"); python3 instruments/tools_trace2txt.py "$t" > "$out/$r.txt" 2>/dev/null; done
  python3 - "$rd" > "$out/tool_calls.tsv" <<'PY'
import json, sys, pathlib
rd = pathlib.Path(sys.argv[1]); print("round\tidx\ttool\tinput")
for t in sorted(rd.glob("rounds/r*/transcript.jsonl")):
    i = 0
    for line in open(t, errors="replace"):
        try: e = json.loads(line)
        except Exception: continue
        if e.get("type") != "assistant": continue
        for c in e["message"].get("content", []):
            if c.get("type") == "tool_use":
                i += 1; print(f"{t.parent.name}\t{i}\t{c['name']}\t{json.dumps(c.get('input'), ensure_ascii=False)[:400]}")
PY
}
mapfile -t TASKS < <(grep -v '^\s*$' "$LIST")
log "== PHASE 1: validate ${#TASKS[@]} tasks"
for t in "${TASKS[@]}"; do
  docker info >/dev/null 2>&1 || { log "DOCKER DOWN"; exit 3; }; diskok || { log "C: below 25 GB - stopping"; exit 4; }
  [ -f "tasks/$t/preflight.json" ] && { log "$t preflight already done: $(python3 -c "import json;p=json.load(open('tasks/$t/preflight.json'));print(p['gold'],p['noop'],p['lofo_covered'],'/',p['lofo_src_files'])")"; continue; }
  log "##### $t"; python3 make_task.py "$t" >> "$LOG" 2>&1 || { log "MAKE_TASK FAILED $t"; continue; }
  ./build_image.sh "$t" >> "$LOG" 2>&1 || { log "BUILD FAILED $t"; printf '%s\tbuild_failed\n' "$t" >> "$ST"; continue; }
  if ./preflight_task.sh "$t" > "tasks/$t/preflight.log" 2>&1; then log "preflight OK $t: $(grep -E 'gold ->|noop ->|== lofo' "tasks/$t/preflight.log" | tr '\n' ' ')"
  else log "PREFLIGHT FAILED $t: $(grep -E 'gold ->|noop ->|PREFLIGHT' "tasks/$t/preflight.log" | tr '\n' ' ')"; printf '%s\tpreflight_failed\n' "$t" >> "$ST"; fi
  docker ps -a --format '{{.Names}}' | grep -E '^dspre' | xargs -r docker rm -f >/dev/null 2>&1
done
log "PHASE1_DONE"
[ "${PHASE1_ONLY:-0}" = 1 ] && exit 0
log "== PHASE 2: one cell per validated task"
for t in "${TASKS[@]}"; do
  grep -qE "^$t	cell_exit_" "$ST" && continue
  python3 -c "import json,sys;p=json.load(open('tasks/$t/preflight.json'));sys.exit(not(p['gold']=='PASS' and p['noop']=='FAIL'))" 2>/dev/null || { log "skip $t (not validated)"; continue; }
  docker info >/dev/null 2>&1 || { log "DOCKER DOWN"; exit 3; }; diskok || { log "C: below 25 GB - stopping"; exit 4; }
  log "##### cell $t"; CSTART=$(date -Iseconds)
  ./run_cell.sh "$t" 1 > "runs/cell-$t-s1.log" 2>&1; rc=$?
  log "cell exit $rc: $(grep -E '^cell complete|verdict=|INVALID|REFUSED' "runs/cell-$t-s1.log" | tr '\n' ' ' | cut -c1-300)"
  rd=$(sed -n 's/^cell complete: //p' "runs/cell-$t-s1.log" | tail -1)
  [ -n "$rd" ] && { export_traces "$rd"; docker logs --since "$CSTART" hcexp-egress > "$rd/egress_proxy.log" 2>&1
    log "egress CONNECTs: $(grep -oE 'CONNECT [^ ]+:443' "$rd/egress_proxy.log" | sort | uniq -c | tr -s ' ' | tr '\n' ';')"; }
  printf '%s\tcell_exit_%s\t%s\n' "$t" "$rc" "$rd" >> "$ST"
  docker ps -a --format '{{.Names}}' | grep -E '^(dscell|acc-dscell)' | xargs -r docker rm -f >/dev/null 2>&1
  [ "$rc" = 3 ] && { log "agent unavailable (quota/session limit) - stopping"; exit 3; }
done
log "PILOT_DONE"
