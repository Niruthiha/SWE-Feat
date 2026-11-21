#!/usr/bin/env bash
# goalrw sphinx trio (2026-11-11): per task, preflight on the freshly built image, then launch seed 1
# only if gold PASS / noop FAIL, C: >= 25 GB and the audit passes. Strictly one Docker job at a time.
cd "$(dirname "$0")"
for IID in "$@"; do
  echo "== $(date -Iseconds) preflight $IID"
  [ -f tasks/$IID/preflight.json ] && cp tasks/$IID/preflight.json tasks/$IID/preflight.json.pre-goalrw
  ./preflight_task.sh $IID
  python3 -c "import json;d=json.load(open('tasks/$IID/preflight.json'));print('PREFLIGHT',d['gold'],d['noop'],d.get('f2p_tests_on_gold'),d['when'])"
  python3 -c "import json,sys;d=json.load(open('tasks/$IID/preflight.json'));sys.exit(0 if d['gold']=='PASS' and d['noop']=='FAIL' else 1)" || { echo "PREFLIGHT_BAD_NOT_LAUNCHED $IID"; continue; }
  df -BG /mnt/c | awk 'NR==2{gsub("G","",$4); exit ($4+0 < 25)}' || { echo "C_BELOW_25GB_NOT_LAUNCHED $IID"; exit 3; }
  ./audit_isolation.sh | grep -q "^AUDIT: PASS" || { echo "AUDIT_FAIL_NOT_LAUNCHED $IID"; exit 2; }
  echo "== $(date -Iseconds) launching cell $IID"
  ./run_seeds.sh $IID goalrw 1
done
echo TRIO_DONE
