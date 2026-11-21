#!/usr/bin/env bash
# run_nohint_chain.sh <iid>... - SWE-bench Pro V2 "no-hint" set (user 2026-11-04): the 5 longest protonmail/webclients
# tasks among the audit's 121 'neither' tasks (prompt names no gold file path/basename/dir and no existing edited symbol),
# prompt = instruction.md VERBATIM (no redaction needed; no CLAUDE.md arm - user: "skip claude.md").
# Per task, in the order given: build agent image -> preflight (gold PASS / empty FAIL / hygiene) -> ONE s1 cell,
# MAX_ROUNDS=30 blind rounds -> trace export -> cleanup (images deleted, fstrim). Preflight failure -> next spare from
# redact/chosen.txt (rank order). ONE Docker job at a time. Stops if C: < 25 GB. Ends with NOHINT_DONE.
set -uo pipefail
cd "$(dirname "$0")"
export CLAUDE_CREDS="${CLAUDE_CREDS:-/home/niruthi/.claude/.credentials.json}"
export MAX_ROUNDS=30
LOG=runs/nohint-chain.log; ST=runs/nohint-state.tsv; touch "$ST"
log () { echo "$(date -Iseconds) $*" | tee -a "$LOG"; }
diskok () { df -BG /mnt/c | awk 'NR==2{gsub("G","",$4); exit ($4+0 < 25)}'; }
cleanup () {
  docker ps -a --format '{{.Names}}' | grep -E '^(sbpcell|acc-sbpcell|sbppre)' | xargs -r docker rm -f >/dev/null 2>&1
  docker rmi "sbpexp-agent:$(echo "$1" | sed -E 's/^instance_//' | cut -c1-120)" "ghcr.io/scaleapi/swe-bench_pro-v2:$1" >> "$LOG" 2>&1 || true
  docker builder prune -f >> "$LOG" 2>&1 || true
  wsl.exe -d docker-desktop fstrim -av >> "$LOG" 2>&1 || log "fstrim not run"
  log "cleanup $1 done; C: free $(df -BG /mnt/c | awk 'NR==2{print $4}')"
}
export_traces () { # export_traces <run_dir>
  local rd="$1" out="$1/traces_readable"; mkdir -p "$out"
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
for iid in "$@"; do
  [ -d "tasks/$iid" ] || python3 make_task.py "$iid" >> "$LOG" 2>&1
  diskok || { log "C: below 25 GB free - stopping"; exit 4; }
  docker info >/dev/null 2>&1 || { log "DOCKER DOWN"; exit 3; }
  log "##### $iid"
  ./build_image.sh "$iid" >> "$LOG" 2>&1 || { log "BUILD FAILED $iid"; printf '%s\tbuild_failed\n' "$iid" >> "$ST"; cleanup "$iid"; continue; }
  PJ="tasks/$iid/preflight.json"; IMGID=$(docker image inspect -f '{{.Id}}' "ghcr.io/scaleapi/swe-bench_pro-v2:$iid" 2>/dev/null)
  if [ -f "$PJ" ] && python3 -c "import json,sys;j=json.load(open('$PJ'));sys.exit(not(j['gold']=='PASS' and j['noop']=='FAIL' and j['image_id']=='$IMGID'))"; then
    log "preflight already PASS for this image id ($IMGID) - reused"
  elif ! ./preflight_task.sh "$iid" > "tasks/$iid/preflight.log" 2>&1; then
    log "PREFLIGHT FAILED $iid: $(grep -E 'gold ->|noop ->|PREFLIGHT' "tasks/$iid/preflight.log" | tr '\n' ' ')"
    printf '%s\tpreflight_failed\n' "$iid" >> "$ST"; cleanup "$iid"; continue; fi
  log "preflight OK: $(grep -E 'gold ->|noop ->' "tasks/$iid/preflight.log" | tr '\n' ' ')"
  CSTART=$(date -Iseconds)
  ./run_cell.sh "$iid" 1 > "runs/cell-$iid-nohint-s1.log" 2>&1; rc=$?
  log "cell exit $rc: $(grep -E '^cell complete|verdict=|INVALID|REFUSED' "runs/cell-$iid-nohint-s1.log" | tr '\n' ' ' | cut -c1-300)"
  rd=$(sed -n 's/^cell complete: //p' "runs/cell-$iid-nohint-s1.log" | tail -1); [ -n "$rd" ] && export_traces "$rd" && log "traces exported $rd/traces_readable"
  # egress evidence from the proxy itself (the in-container curl probe cannot run on Alpine images: no curl)
  [ -n "$rd" ] && { docker logs --since "$CSTART" hcexp-egress > "$rd/egress_proxy.log" 2>&1; log "egress CONNECTs: $(grep -oE 'CONNECT [^ ]+:443' "$rd/egress_proxy.log" | sort | uniq -c | tr -s ' ' | tr '\n' ';')"; }
  printf '%s\tcell_exit_%s\t%s\n' "$iid" "$rc" "$rd" >> "$ST"
  cleanup "$iid"
  [ "$rc" = 3 ] && { log "agent unavailable (quota/session limit) - stopping chain"; exit 3; }
  [ "$rc" = 0 ] && { log "CELL_DONE $iid"; exit 0; }   # one cell per launch: the next is started by the orchestrator
done
log "NOHINT_LIST_EXHAUSTED"
