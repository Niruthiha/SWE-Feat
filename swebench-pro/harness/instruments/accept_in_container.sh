#!/bin/bash
# accept_in_container.sh - runs as root in a FRESH container from the PRISTINE V2 image, --network none.
# /tmp/agent.patch is applied exactly as the official patch_replay agent applies a captured diff, then the task's
# UNCHANGED verifier (/tests/test.sh: resets test-space, applies test_patch, runs run_script.sh + parser.py, requires
# every fail_to_pass and pass_to_pass test to pass) decides. Exit 0 = PASS, 1 = FAIL, 2 = patch did not apply.
cd /app 2>/dev/null || cd /testbed || exit 3
echo "== workdir $(pwd) HEAD $(git rev-parse HEAD)"
if [ -s /tmp/agent.patch ]; then
  git apply --verbose /tmp/agent.patch || git apply --3way /tmp/agent.patch || patch --fuzz=3 -p1 -i /tmp/agent.patch \
    || { echo "ACCEPT SUMMARY apply=FAIL"; exit 2; }
else echo "(empty patch: nothing applied)"; fi
echo "== post-apply: $(git status --short | wc -l) changed paths"
mkdir -p /logs/verifier
bash /tests/test.sh; rc=$?
python3 - <<'PY'
import json, ast
def L(x):
    if isinstance(x, list): return x
    try: return json.loads(x)
    except Exception: return ast.literal_eval(x)
c = json.load(open("/tests/config.json")); f2p, p2p = set(L(c["fail_to_pass"])), set(L(c["pass_to_pass"]))
try: out = json.load(open("/logs/verifier/output.json"))
except Exception: out = {"tests": []}
ok = {t["name"] for t in out.get("tests", []) if t.get("status") == "PASSED"}
print(f"ACCEPT SUMMARY f2p={len(f2p & ok)}/{len(f2p)} p2p={len(p2p & ok)}/{len(p2p)} reported={len(out.get('tests', []))}")
PY
exit $rc
