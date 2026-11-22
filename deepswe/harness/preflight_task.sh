#!/usr/bin/env bash
# preflight_task.sh <task_id> - the oracle must discriminate on THIS image before any cell runs (port of the SWE-bench
# Pro preflight), plus the leave-one-file-out (LOFO) check of whether the hidden tests cover the patch's spread:
#   gold   solution.patch applied -> the task's own verifier must give reward 1
#   noop   empty patch            -> reward 0
#   lofo   gold minus ONE source file at a time -> reward 0 means the tests need that file ("covered");
#          reward 1 means they pass without it ("uncovered"). Non-source files in the patch are always kept.
# All in fresh --network none containers from the PRISTINE image (instruments/accept_in_container.sh).
# Writes tasks/<id>/preflight.json; run_cell.sh refuses to start without gold=PASS noop=FAIL (exit 4).
set -euo pipefail
export DOCKER_CONFIG="$(realpath "$(dirname "$0")")/instruments/docker-anon"
HERE=$(realpath "$(dirname "$0")"); IID="$1"; TD="$HERE/tasks/$IID"
IMAGE=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['image'])" "$TD/meta.json")
MEM="${MEM:-8g}"; LOFO="${LOFO:-1}"
docker image inspect "$IMAGE" >/dev/null 2>&1 || docker pull -q "$IMAGE"
OUT="$TD/preflight"; rm -rf "$OUT"; mkdir -p "$OUT"; : > "$OUT/empty.patch"
run_acc () { # run_acc <label> <patch> -> PASS|FAIL|APPLY_FAILED|ERROR(rc)
  local c="dspre-$1-$$"; docker rm -f "$c" >/dev/null 2>&1 || true
  docker run -d --name "$c" --network none --memory "$MEM" "$IMAGE" sleep infinity >/dev/null
  docker cp "$TD/verifier" "$c:/tests"; docker cp "$HERE/instruments/accept_in_container.sh" "$c:/tmp/accept_in_container.sh"
  docker cp "$2" "$c:/tmp/agent.patch"
  set +e; docker exec "$c" bash /tmp/accept_in_container.sh > "$OUT/$1.stdout" 2>&1; local rc=$?; set -e
  docker cp "$c:/logs/verifier" "$OUT/$1" >/dev/null 2>&1 || true; docker rm -f "$c" >/dev/null 2>&1 || true
  case "$rc" in 0) echo PASS;; 1) echo FAIL;; 2) echo APPLY_FAILED;; *) echo "ERROR($rc)";; esac
}
summ () { grep -a '^ACCEPT SUMMARY' "$OUT/$1.stdout" | tail -1; }
echo "== history hygiene (pristine image) =="
docker run --rm --network none -v "$TD/verifier/test.patch:/x/test.patch:ro" -v "$TD/gold.patch:/x/gold.patch:ro" "$IMAGE" bash -c 'cd /app; git config --global --add safe.directory /app; echo "HEAD $(git rev-parse HEAD)"; echo "refs_ahead_of_HEAD $(git rev-list --all --not HEAD | wc -l)"; echo "stash $(git stash list | wc -l)"; echo "status_lines $(git status --porcelain | wc -l)"; for p in /tests /solution /logs/verifier /oracle; do [ -e $p ] && echo "PRESENT $p" || echo "absent $p"; done; git apply --check /x/test.patch 2>/dev/null && echo "test_patch_not_yet_applied yes" || echo "test_patch_not_yet_applied NO"; git apply --check /x/gold.patch 2>/dev/null && echo "gold_not_yet_applied yes" || echo "gold_not_yet_applied NO"' > "$OUT/hygiene.txt" 2>&1
cat "$OUT/hygiene.txt"
BASE=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['base_commit'])" "$TD/meta.json")
grep -q "HEAD $BASE" "$OUT/hygiene.txt" || echo "WARNING: image HEAD is not task base_commit $BASE"
echo "== gold =="; GOLD=$(run_acc gold "$TD/gold.patch"); echo "  gold -> $GOLD  $(summ gold)"
echo "== noop =="; NOOP=$(run_acc noop "$OUT/empty.patch"); echo "  noop -> $NOOP  $(summ noop)"
# ---- LOFO: split gold.patch per file; drop one SOURCE file (same classify rules as the selection) at a time ----------
mkdir -p "$OUT/lofo"; : > "$OUT/lofo/results.tsv"
if [ "$LOFO" = 1 ] && [ "$GOLD" = PASS ]; then
  python3 "$HERE/lofo_split.py" "$TD/gold.patch" "$OUT/lofo"     # writes drop_NN.patch + files.tsv (idx, path, kind)
  while IFS=$'\t' read -r idx path kind; do
    [ "$kind" = src ] || continue
    R=$(run_acc "lofo-$idx" "$OUT/lofo/drop_$idx.patch")
    printf '%s\t%s\t%s\t%s\n' "$idx" "$path" "$R" "$(summ "lofo-$idx" | sed 's/^ACCEPT SUMMARY //')" | tee -a "$OUT/lofo/results.tsv"
  done < "$OUT/lofo/files.tsv"
fi
python3 - "$TD/preflight.json" "$OUT" <<PY
import json, sys, pathlib
o = pathlib.Path(sys.argv[2]); last = lambda f: ([l for l in (o/f).read_text(errors="replace").splitlines() if l.startswith("ACCEPT SUMMARY")] or [""])[-1]
h = dict(l.split(" ", 1) for l in (o/"hygiene.txt").read_text().splitlines() if " " in l)
lofo = [dict(zip(("idx", "file", "result", "summary"), l.split("\t"))) for l in (o/"lofo/results.tsv").read_text().splitlines() if l]
cov = sum(1 for r in lofo if r["result"] in ("FAIL", "APPLY_FAILED"))
json.dump({"instance_id": "$IID", "image": "$IMAGE", "image_id": "$(docker image inspect -f '{{.Id}}' "$IMAGE")",
           "gold": "$GOLD", "noop": "$NOOP", "gold_summary": last("gold.stdout"), "noop_summary": last("noop.stdout"),
           "lofo": lofo, "lofo_src_files": len(lofo), "lofo_covered": cov, "lofo_uncovered": len(lofo) - cov,
           "hygiene": h, "memory": "$MEM", "when": "$(date -Iseconds)"}, open(sys.argv[1], "w"), indent=2)
PY
H="$OUT/hygiene.txt"
grep -q 'refs_ahead_of_HEAD 0' "$H" && grep -q 'test_patch_not_yet_applied yes' "$H" && grep -q 'gold_not_yet_applied yes' "$H" && ! grep -q PRESENT "$H" \
  || { echo "PREFLIGHT FAILED (hygiene)"; exit 1; }
echo "== lofo: $(python3 -c "import json;p=json.load(open('$TD/preflight.json'));print(f\"{p['lofo_covered']}/{p['lofo_src_files']} source files covered (dropping each makes the tests fail)\")")"
[ "$GOLD" = PASS ] && [ "$NOOP" = FAIL ] && echo "PREFLIGHT OK" || { echo "PREFLIGHT FAILED"; exit 1; }
