#!/usr/bin/env bash
# run_batch3.sh - batch 3 (user "run all" 2026-11-18): 38 goal-only (GOALRW=1) cells from redact/batch3_cap50.txt, strictly one
# at a time (each its own run_nohint_chain.sh call). Waits for any running cell first. Checks Docker before each launch;
# stops on Docker down / C: < 25 GB / quota (rc 3|4). Done = cell_exit_* in nohint-state.tsv for a goalrw run.
cd "$(dirname "$0")"; export VERB=1
while ps -eo args | awk '/run_nohint_chain.sh/ && !/awk/{f=1} END{exit !f}'; do sleep 60; done
while read -r iid; do
  [ -z "$iid" ] && continue
  grep -qE "^$iid	cell_exit_.*${MATCH:-(goalrw|verb)}" runs/nohint-state.tsv && continue
  docker info >/dev/null 2>&1 || { echo "$(date -Iseconds) BATCH3 STOPPED: DOCKER DOWN before $iid" >> runs/nohint-chain.log; exit 3; }
  ./run_nohint_chain.sh "$iid" </dev/null; rc=$?
  case $rc in 3|4) echo "$(date -Iseconds) BATCH3 STOPPED rc=$rc at $iid" >> runs/nohint-chain.log; exit $rc;; esac
done < "${LIST:-redact/batch3_cap50.txt}"
echo "$(date -Iseconds) BATCH3_DONE" >> runs/nohint-chain.log
