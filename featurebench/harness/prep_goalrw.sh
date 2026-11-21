#!/usr/bin/env bash
# prep for the goalrw cell on test_mlflow (2026-11-11): egress image -> task image -> preflight. No agent cell.
set -uo pipefail; cd "$(dirname "$0")"; LOG=runs/goalrw-prep.log
IID=mlflow__mlflow.93dab383.test_mlflow.d1847ff9.lv1
echo "== $(date -Iseconds) egress build" | tee -a $LOG
docker build -t hcexp-egress:2 /home/niruthi/features/instruments/docker-egress >> $LOG 2>&1 || { echo EGRESS_BUILD_FAILED | tee -a $LOG; exit 1; }
echo "== $(date -Iseconds) image build" | tee -a $LOG
./build_image.sh "$IID" >> $LOG 2>&1 || { echo IMAGE_BUILD_FAILED | tee -a $LOG; exit 2; }
df -BG /mnt/c | awk 'NR==2{gsub("G","",$4); exit ($4+0 < 25)}' || { echo "C_BELOW_25GB" | tee -a $LOG; exit 3; }
echo "== $(date -Iseconds) preflight" | tee -a $LOG
./preflight_task.sh "$IID" >> $LOG 2>&1
python3 -c "import json;d=json.load(open('tasks/$IID/preflight.json'));print('PREFLIGHT gold',d['gold'],'noop',d['noop'])" | tee -a $LOG
echo PREP_DONE | tee -a $LOG
