#!/usr/bin/env bash
set -uo pipefail
t="$1"; CSTART="$2"; cd ~/features/SWE-Feat/deepswe/harness; LOG=runs/pilot.log; ST=runs/pilot-state.tsv
log () { echo "$(date -Iseconds) $*" | tee -a "$LOG"; }
while pgrep -f "run_cell.sh $t" >/dev/null; do sleep 30; done
L="runs/cell-$t-s1.log"; rd=$(sed -n 's/^cell complete: //p' "$L" | tail -1)
log "cell finished (run_cell rc not captured; loop was detached): $(grep -E '^cell complete|verdict=|INVALID|REFUSED' "$L" | tr '\n' ' ' | cut -c1-300)"
if [ -n "$rd" ]; then
  mkdir -p "$rd/traces_readable"
  for tr in "$rd"/rounds/r*/transcript.jsonl; do r=$(basename "$(dirname "$tr")"); python3 instruments/tools_trace2txt.py "$tr" > "$rd/traces_readable/$r.txt" 2>/dev/null; done
  docker logs --since "$CSTART" hcexp-egress > "$rd/egress_proxy.log" 2>&1
  log "egress CONNECTs: $(grep -oE 'CONNECT [^ ]+:443' "$rd/egress_proxy.log" | sort | uniq -c | tr -s ' ' | tr '\n' ';')"
fi
rc=$(grep -qE 'INVALID|REFUSED' "$L" && echo 3 || echo 0)
printf '%s\tcell_exit_%s\t%s\n' "$t" "$rc" "$rd" >> "$ST"
docker ps -a --format '{{.Names}}' | grep -E '^(dscell|acc-dscell)' | xargs -r docker rm -f >/dev/null 2>&1
echo "rd=$rd"; tail -40 "$L" | grep -vE '^\s*$' | tail -12; [ -n "$rd" ] && cat "$rd/rounds.tsv"
