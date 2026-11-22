#!/usr/bin/env bash
# ds_regrade.sh: re-grade every pilot cell's FINAL diff in a brand-new --network none container from the pristine task
# image (same steps as run_cell.sh run_accept). Checks the recorded verdict reproduces. One container at a time.
cd ~/features/SWE-Feat/deepswe/harness; out=runs/pilot_regrade.tsv; printf 'task\trecorded\tregrade\tsummary\n' > $out
while IFS=$'\t' read -r t st rd; do
  [[ "$st" == cell_exit* && -n "$rd" ]] || continue
  last=$(ls -d $rd/rounds/r* | sort | tail -1); [ "$st" = cell_exit_stopped_by_user_cap20 ] && last=$rd/rounds/r19
  rec=$(cat $last/accept_result); img=$(python3 -c "import json;print(json.load(open('tasks/$t/meta.json'))['image'])")
  acc=regrade-$RANDOM; docker run -d --name $acc --network none --memory 8g $img sleep infinity >/dev/null
  docker cp tasks/$t/verifier $acc:/tests; docker cp instruments/accept_in_container.sh $acc:/tmp/; docker cp $last/diff.patch $acc:/tmp/agent.patch
  docker exec $acc bash /tmp/accept_in_container.sh > /tmp/regrade.out 2>&1; rc=$?; docker rm -f $acc >/dev/null
  case $rc in 0) v=PASS;; 1|2) v=FAIL;; *) v=ERROR;; esac
  s=$(grep -a '^ACCEPT SUMMARY' /tmp/regrade.out | tail -1)
  printf '%s\t%s\t%s\t%s\n' "$t" "$rec" "$v" "$s" | tee -a $out
done < runs/pilot-state.tsv
