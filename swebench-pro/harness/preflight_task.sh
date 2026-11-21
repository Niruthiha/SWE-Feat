#!/usr/bin/env bash
# preflight_task.sh <instance_id> - the oracle must discriminate on THIS image before any cell runs:
#   gold   solution/gold_patch.diff applied -> the official verifier must PASS
#   noop   empty patch                       -> it must FAIL
# Both in fresh --network none containers from the PRISTINE V2 image (instruments/accept_in_container.sh), i.e. the
# acceptance the cell uses. Also records history hygiene (no refs ahead of HEAD, test_patch not yet applied).
# Writes tasks/<id>/preflight.json; run_cell.sh refuses to start without gold=PASS noop=FAIL (exit 4).
set -euo pipefail
# public ghcr pulls without the Windows credential helper (desktop.exe over WSL vsock times out intermittently)
export DOCKER_CONFIG="$(realpath "$(dirname "$0")")/instruments/docker-anon"
HERE=$(realpath "$(dirname "$0")"); IID="$1"; TD="$HERE/tasks/$IID"
IMAGE=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['image'])" "$TD/meta.json")
MEM="${MEM:-4g}"
docker image inspect "$IMAGE" >/dev/null 2>&1 || docker pull -q "$IMAGE"
OUT="$TD/preflight"; rm -rf "$OUT"; mkdir -p "$OUT"; : > "$OUT/empty.patch"
run_acc () { # run_acc <label> <patch>
  local c="sbppre-$1-$$"; docker rm -f "$c" >/dev/null 2>&1 || true
  docker run -d --name "$c" --network none --memory "$MEM" "$IMAGE" sleep infinity >/dev/null
  docker cp "$TD/verifier" "$c:/tests"; docker cp "$HERE/instruments/accept_in_container.sh" "$c:/tmp/accept_in_container.sh"
  docker cp "$2" "$c:/tmp/agent.patch"
  set +e; docker exec "$c" bash /tmp/accept_in_container.sh > "$OUT/$1.stdout" 2>&1; local rc=$?; set -e
  docker cp "$c:/logs/verifier" "$OUT/$1" >/dev/null 2>&1 || true; docker rm -f "$c" >/dev/null 2>&1 || true
  case "$rc" in 0) echo PASS;; 1) echo FAIL;; *) echo "ERROR($rc)";; esac
}
echo "== history hygiene (pristine image) =="
docker run --rm --network none "$IMAGE" bash -c 'cd /app 2>/dev/null || cd /testbed; echo "HEAD $(git rev-parse HEAD)"; echo "refs_ahead_of_HEAD $(git rev-list --all --not HEAD | wc -l)"; echo "stash $(git stash list | wc -l)"; echo "status_lines $(git status --porcelain | wc -l)"; for p in /tests /solution /logs/verifier; do [ -e $p ] && echo "PRESENT $p" || echo "absent $p"; done' > "$OUT/hygiene.txt" 2>&1
docker run --rm --network none -v "$TD/verifier/test_patch.patch:/x/test_patch.patch:ro" -v "$TD/gold.patch:/x/gold.patch:ro" "$IMAGE" bash -c 'cd /app 2>/dev/null || cd /testbed; git apply --check /x/test_patch.patch && echo "test_patch_not_yet_applied yes" || echo "test_patch_not_yet_applied NO"; git apply --check /x/gold.patch && echo "gold_not_yet_applied yes" || echo "gold_not_yet_applied NO"' >> "$OUT/hygiene.txt" 2>&1
cat "$OUT/hygiene.txt"
echo "== gold =="; GOLD=$(run_acc gold "$TD/gold.patch"); echo "  gold -> $GOLD  $(grep -a '^ACCEPT SUMMARY' "$OUT/gold.stdout" | tail -1)"
echo "== noop =="; NOOP=$(run_acc noop "$OUT/empty.patch"); echo "  noop -> $NOOP  $(grep -a '^ACCEPT SUMMARY' "$OUT/noop.stdout" | tail -1)"
python3 - "$TD/preflight.json" "$OUT" <<PY
import json, sys, pathlib
o = pathlib.Path(sys.argv[2]); last = lambda f: ([l for l in (o/f).read_text(errors="replace").splitlines() if l.startswith("ACCEPT SUMMARY")] or [""])[-1]
h = dict(l.split(" ", 1) for l in (o/"hygiene.txt").read_text().splitlines() if " " in l)
json.dump({"instance_id": "$IID", "image": "$IMAGE", "image_id": "$(docker image inspect -f '{{.Id}}' "$IMAGE")",
           "gold": "$GOLD", "noop": "$NOOP", "gold_summary": last("gold.stdout"), "noop_summary": last("noop.stdout"),
           "hygiene": h, "memory": "$MEM", "when": "$(date -Iseconds)"}, open(sys.argv[1], "w"), indent=2)
PY
cat "$TD/preflight.json"
H="$OUT/hygiene.txt"
grep -q 'refs_ahead_of_HEAD 0' "$H" && grep -q 'test_patch_not_yet_applied yes' "$H" && grep -q 'gold_not_yet_applied yes' "$H" && ! grep -q PRESENT "$H" \
  || { echo "PREFLIGHT FAILED (hygiene)"; exit 1; }
[ "$GOLD" = PASS ] && [ "$NOOP" = FAIL ] && echo "PREFLIGHT OK" || { echo "PREFLIGHT FAILED"; exit 1; }
# 2026-11-03 (user): leave-one-file-out ablation of the gold patch while the pristine image is here (harness side,
# never seen by the agent). Non-fatal: preflight's verdict above is unchanged by it.
echo "== ablation (leave-one-file-out) =="
"$HERE/ablate_task.sh" "$IID" || echo "ablation error (non-fatal)"
exit 0
