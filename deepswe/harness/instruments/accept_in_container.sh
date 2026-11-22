#!/bin/bash
# accept_in_container.sh - DeepSWE acceptance, run as root in a FRESH --network none container from the PRISTINE task
# image (never the agent's). Inputs: /tests (the task's tests/ dir, unchanged), /tmp/agent.patch (diff vs base commit).
# Runs the task's OWN verifier exactly as DeepSWE's harness does: model.patch at /logs/artifacts/model.patch, then
# /tests/test.sh (grader.py prepare: reset+apply model.patch, apply hidden test.patch; run suites; grader.py grade).
# Exit: 0 = reward 1 (every f2p passes AND no p2p fails) | 1 = reward 0 | 2 = patch did not apply | 3 = verifier crash.
set -u
mkdir -p /logs/artifacts /logs/verifier
cd /app || { echo "ACCEPT SUMMARY no /app"; exit 3; }
git config --global --add safe.directory /app
if [ -s /tmp/agent.patch ]; then cp /tmp/agent.patch /logs/artifacts/model.patch; else rm -f /logs/artifacts/model.patch; fi
echo "== workdir /app HEAD $(git rev-parse HEAD)  patch $(wc -c < /tmp/agent.patch 2>/dev/null || echo 0) bytes"
timeout "${VERIFIER_TIMEOUT:-1800}" bash /tests/test.sh > /logs/verifier/test-stdout.txt 2>&1; rc=$?
tail -40 /logs/verifier/test-stdout.txt
python3 - "$rc" <<'PY'
import json, sys, pathlib
rc = int(sys.argv[1]); p = pathlib.Path("/logs/verifier/reward.json")
if not p.exists():
    t = pathlib.Path("/logs/verifier/reward.txt")
    print(f"ACCEPT SUMMARY crash test.sh_rc={rc} reward.txt={t.read_text().strip() if t.exists() else 'none'}"); sys.exit(3)
r = json.loads(p.read_text())
print(f"ACCEPT SUMMARY f2p={r['f2p_passed']}/{r['f2p_total']} p2p={r['p2p_passed']}/{r['p2p_total']} reward={r['reward']}"
      + (" apply_failed=1" if r.get("apply_failed") else "") + f" test.sh_rc={rc}")
sys.exit(2 if r.get("apply_failed") else (0 if r["reward"] == 1 else 1))
PY
