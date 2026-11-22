#!/usr/bin/env bash
# launch run_one.sh <task> detached (survives if the waiter is killed), then wait for it and print the result
t="$1"; H=~/features/SWE-Feat/deepswe/harness; cd $H
pgrep -f 'run_pilot.sh|run_one.sh|run_cell.sh' >/dev/null && { echo "SOMETHING ALREADY RUNNING"; exit 1; }
rm -f runs/one-$t.done
setsid nohup bash $H/run_one.sh "$t" > runs/one-$t.out 2>&1 < /dev/null &
until [ -f runs/one-$t.done ] || ! pgrep -f "run_one.sh $t" >/dev/null; do sleep 30; done
cat runs/one-$t.done 2>/dev/null; tail -3 runs/pilot.log | cut -c1-400
rd=$(sed -n 's/^cell complete: //p' runs/cell-$t-s1.log | tail -1); [ -n "$rd" ] && { cat "$rd/rounds.tsv" 2>/dev/null | tail -5; }
