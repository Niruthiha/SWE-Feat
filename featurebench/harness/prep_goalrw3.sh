#!/usr/bin/env bash
# goalrw cell 3 (2026-11-11): preflight on current image, then launch seed 1 only if gold PASS / noop FAIL.
cd "$(dirname "$0")"; IID=mlflow__mlflow.93dab383.test_git_versioning.b91d0418.lv1
echo "== $(date -Iseconds) preflight $IID"
./preflight_task.sh $IID
ok=$(python3 -c "import json;d=json.load(open('tasks/$IID/preflight.json'));print(int(d['gold']=='PASS' and d['noop']=='FAIL'))")
python3 -c "import json;d=json.load(open('tasks/$IID/preflight.json'));print('PREFLIGHT gold',d['gold'],'noop',d['noop'],d['when'])"
[ "$ok" = 1 ] || { echo PREFLIGHT_BAD_NOT_LAUNCHED; exit 1; }
df -BG /mnt/c | awk 'NR==2{gsub("G","",$4); exit ($4+0 < 25)}' || { echo C_BELOW_25GB_NOT_LAUNCHED; exit 3; }
./audit_isolation.sh | grep -q "^AUDIT: PASS" || { echo AUDIT_FAIL_NOT_LAUNCHED; exit 2; }
echo "== $(date -Iseconds) launching cell"
./run_seeds.sh $IID goalrw 1
