#!/usr/bin/env bash
# run_seeds.sh <instance_id> <arms> <seeds>: repeat cells for a task, e.g.
#   run_seeds.sh mlflow__mlflow.93dab383.test_mlflow.d1847ff9.lv1 "base imp" "2 3 4 5 6"
# Added 2026-11-02 (user: run test_mlflow 5 more times in baseline and change-impact). One cell at a time,
# each through the unchanged run_cell.sh (fresh container, fresh HOME, fresh session, read-only creds,
# hidden tests deleted, separate --network none acceptance). Isolation audit before EVERY cell.
# Per seed the base/imp order is drawn with shuf from a seed-derived key (logged). Recoverable: finished
# cells are skipped, partial ones deleted with their containers. State: runs/seeds-state.tsv.
# Launch with setsid nohup so it outlives the Claude session.
# Arm names: base doc map imp vague goal goalrw, or any other name = PROMPT_ARM=<name> (tasks/<id>/prompt_<name>.txt).
set -uo pipefail
cd "$(dirname "$0")"
[ -n "${CLAUDE_CREDS:-}${ANTHROPIC_API_KEY:-}" ] || { echo "set CLAUDE_CREDS=/path/to/.credentials.json or ANTHROPIC_API_KEY" >&2; exit 1; }
export MODEL="${MODEL:-claude-opus-5-5}"
IID="$1"; ARMS="$2"; SEEDS="$3"
SHORTT=$(echo "$IID" | sed -E 's/.*\.(test_[a-zA-Z0-9_]+)\..*/\1/')
suffix () { case $1 in base) echo "";; doc) echo "-doc";; map) echo "-map";; imp) echo "-imp";; vague) echo "-vague";; goal) echo "-goal";; goalrw) echo "-goalrw";; *) echo "-$1";; esac; }   # any other name = PROMPT_ARM=<name>
run_of () { ls -d runs/*-$SHORTT-s$2$(suffix "$1") 2>/dev/null | awk -F/ '$2 ~ /^[0-9]/' | sort; }
done_dir () { for d in $(run_of "$1" "$2"); do [ -s "$d/metrics.json" ] && python3 -c "import json,sys;m=json.load(open('$d/metrics.json'));sys.exit(0 if 'converged' in m else 1)" && { echo "$d"; return 0; }; done; return 1; }
for s in $SEEDS; do
  ORDER=$(printf '%s\n' $ARMS | shuf --random-source=<(yes "$(printf %s "$IID$s" | sha256sum | cut -d" " -f1)"))
  echo "seed $s order: $(echo $ORDER)"
  for arm in $ORDER; do
    if d=$(done_dir "$arm" "$s"); then echo "skip $arm s$s: done $d"; continue; fi
    for d in $(run_of "$arm" "$s"); do echo "deleting partial $d"; rm -rf "$d"; done
    docker ps -a --format '{{.Names}}' | grep -E '^fb(cell|reg)' | xargs -r docker rm -f >/dev/null
    docker info >/dev/null 2>&1 || { echo "DOCKER DOWN before $arm s$s"; exit 3; }
    case $arm in base) E=;; doc) E=DOCSTRIP=1;; map) E=INDEX=1;; imp) E=IMPACT=1;; vague) E=VAGUE=1;; goal) E=GOAL=1;; goalrw) E=GOALRW=1;; *) E=PROMPT_ARM=$arm;; esac
    mkdir -p runs; env $E ./audit_isolation.sh > "runs/audit-seeds-$SHORTT-$arm-s$s.txt" 2>&1
    grep -q 'AUDIT: PASS' "runs/audit-seeds-$SHORTT-$arm-s$s.txt" || { echo "AUDIT FAILED before $arm s$s"; exit 2; }
    echo "##### $(date -Iseconds) $arm s$s #####"
    env $E ./run_cell.sh "$IID" "$s" > "runs/cellseed-$arm-$IID-s$s.log" 2>&1; rc=$?
    printf '%s\t%s\t%s\ts%s\t%s\n' "$(date -Iseconds)" "$IID" "$arm" "$s" "$rc" >> runs/seeds-state.tsv
    echo "== $(date -Iseconds) $arm s$s exit $rc"; grep -E '^cell complete|verdict=' "runs/cellseed-$arm-$IID-s$s.log" | tail -2 | cut -c1-200
    df -BG "${DISK_CHECK_PATH:-.}" | awk 'NR==2{gsub("G","",$4); if ($4+0 < 25) {print "disk below 25 GB free - stopping"; exit 1}}' || exit 4
  done
done
echo SEEDS_DONE
