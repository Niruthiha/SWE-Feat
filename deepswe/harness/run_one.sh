#!/usr/bin/env bash
# ds_one.sh <task> : ONE agent cell (phase-2 body of run_pilot.sh) for a single task, then traces + egress log + state line
set -uo pipefail
cd ~/features/SWE-Feat/deepswe/harness
export CLAUDE_CREDS=/mnt/c/Users/nirut/.claude/.credentials.json MAX_ROUNDS=19 MEM=8g  # 20 rounds total = round 0 + 19 blind (user: "stop at 20 rounds")
t="$1"; LOG=runs/pilot.log; ST=runs/pilot-state.tsv
log () { echo "$(date -Iseconds) $*" | tee -a "$LOG"; }
grep -qE "^$t	cell_exit_" "$ST" && { log "$t already ran"; echo DONE > runs/one-$t.done; exit 0; }
python3 -c "import json,sys;p=json.load(open('tasks/$t/preflight.json'));sys.exit(not(p['gold']=='PASS' and p['noop']=='FAIL'))" || { log "skip $t (not validated)"; echo DONE > runs/one-$t.done; exit 1; }
log "##### cell $t"; CSTART=$(date -Iseconds)
./run_cell.sh "$t" 1 > "runs/cell-$t-s1.log" 2>&1; rc=$?
log "cell exit $rc: $(grep -E '^cell complete|verdict=|INVALID|REFUSED' "runs/cell-$t-s1.log" | tr '\n' ' ' | cut -c1-300)"
rd=$(sed -n 's/^cell complete: //p' "runs/cell-$t-s1.log" | tail -1)
if [ -n "$rd" ]; then
  mkdir -p "$rd/traces_readable"
  for tr in "$rd"/rounds/r*/transcript.jsonl; do r=$(basename "$(dirname "$tr")"); python3 instruments/tools_trace2txt.py "$tr" > "$rd/traces_readable/$r.txt" 2>/dev/null; done
  docker logs --since "$CSTART" hcexp-egress > "$rd/egress_proxy.log" 2>&1
  log "egress CONNECTs: $(grep -oE 'CONNECT [^ ]+:443' "$rd/egress_proxy.log" | sort | uniq -c | tr -s ' ' | tr '\n' ';')"
fi
printf '%s\tcell_exit_%s\t%s\n' "$t" "$rc" "$rd" >> "$ST"
docker ps -a --format '{{.Names}}' | grep -E '^(dscell|acc-dscell)' | xargs -r docker rm -f >/dev/null 2>&1
echo "rc=$rc rd=$rd" > runs/one-$t.done
