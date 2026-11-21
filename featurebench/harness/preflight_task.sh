#!/usr/bin/env bash
# preflight_task.sh <instance_id> - validate the oracle on THIS image before any cell:
#   gold  the pristine implementation (mask patch reverse-applied) must PASS acceptance
#   noop  a patch that touches nothing the tests see must FAIL (F2P really fails)
# Also records the repo's test directories (for run_regress.sh scope) and the gold
# patch itself (tasks/<id>/gold.patch, never mounted anywhere the agent can see).
# Writes tasks/<id>/preflight.json; run_cell.sh refuses to start without it (exit 4).
set -euo pipefail
HERE=$(realpath "$(dirname "$0")"); IID="$1"; TD="$HERE/tasks/$IID"
meta () { python3 -c "import json,sys;v=json.load(open(sys.argv[1]))$1;print(v if not isinstance(v,list) else ' '.join(v))" "$TD/meta.json" "$1"; }
REPO=$(meta "['repository']" ""); IMAGE_NAME=$(meta "['image_name']" "")
F2P=$(meta "['FAIL_TO_PASS'][0]" ""); P2P=$(meta "['PASS_TO_PASS']" "")
TEST_CMD=$(meta "['test_cmd']" ""); T_ONE=$(meta "['timeout_one']" ""); T_RUN=$(meta "['timeout_run']" "")
IMAGE="fbexp-agent:$(echo "$IMAGE_NAME" | sed -E 's#.*featurebench-specs_##; s#-instance_#-#')"
[ -s "$TD/image_tag" ] && IMAGE="fbexp-agent:$(tr -d "[:space:]" < "$TD/image_tag")"  # per-task image override (environment repair, see instruments/Dockerfile.iers)
OUT="$TD/preflight"; rm -rf "$OUT"; mkdir -p "$OUT"
C="fbpre-$(date +%s)"
docker rm -f "$C" >/dev/null 2>&1 || true
docker run -d --name "$C" "$IMAGE" sleep infinity >/dev/null
trap 'docker rm -f "$C" >/dev/null 2>&1 || true' EXIT
docker cp "$TD/mask.patch" "$C:/tmp/mask.patch"; docker cp "$TD/mask.patch" "$C:/tmp/mask_keep.patch"
docker cp "$TD/test.patch" "$C:/tmp/test.patch"
echo "== prepare tree (as the cell does) =="
docker exec --user 0:0 "$C" prepare_tree /tmp/mask.patch "$F2P" "$REPO" > "$OUT/prepare_tree.log" 2>&1 || { echo "prepare_tree failed"; tail -5 "$OUT/prepare_tree.log"; exit 1; }
echo "== gold patch = reverse of the mask, as a diff against the prepared baseline =="
# the mask may also carry the hidden test file (sympy, mlflow do); that part is
# restored by the acceptance's reverse-apply of test.patch, so the gold patch is the
# reverse of the mask with every test.patch file excluded.
EXCL=$(grep '^diff --git' "$TD/test.patch" | sed -E 's#^diff --git a/([^ ]+) .*#--exclude=\1#' | tr '\n' ' ')
docker exec --user 1000:1000 "$C" bash -c "cd /testbed && git apply --reverse --whitespace=fix $EXCL /tmp/mask_keep.patch && git add -A && git diff --cached --no-color HEAD" > "$TD/gold.patch"
echo "  gold.patch: $(grep -c '^diff --git' "$TD/gold.patch") files"
echo "== test directories in the pristine tree (regression scope) =="
docker exec --user 1000:1000 "$C" bash -c 'cd /testbed && git ls-files | grep -E "(^|/)test_[^/]*\.py$|(^|/)tests?/.*\.py$" | xargs -n1 dirname | sort -u' > "$TD/test_dirs.txt"
echo "  $(wc -l < "$TD/test_dirs.txt") test dirs"
printf 'diff --git a/fbexp_noop.txt b/fbexp_noop.txt\nnew file mode 100644\nindex 0000000..e69de29\n' > "$OUT/noop.patch"
run_acc () { # run_acc <label> <patch> -> PASS|FAIL|ERROR
  local acc="$C-$1"; docker rm -f "$acc" >/dev/null 2>&1 || true
  docker run -d --name "$acc" --network none "$IMAGE" sleep infinity >/dev/null
  docker cp "$TD/mask.patch" "$acc:/tmp/mask.patch"; docker cp "$TD/test.patch" "$acc:/tmp/test.patch"; docker cp "$2" "$acc:/tmp/agent.patch"
  set +e
  docker exec --user 0:0 "$acc" accept_in_container /tmp/mask.patch /tmp/test.patch /tmp/agent.patch "$F2P" "$REPO" "$TEST_CMD" "$T_ONE" "$T_RUN" /tmp/out $P2P > "$OUT/$1.stdout" 2>&1
  local rc=$?; set -e
  docker cp "$acc:/tmp/out" "$OUT/$1" >/dev/null 2>&1 || true; docker rm -f "$acc" >/dev/null 2>&1 || true
  case "$rc" in 0) echo PASS;; 1) echo FAIL;; *) echo ERROR;; esac
}
echo "== gold acceptance =="; GOLD=$(run_acc gold "$TD/gold.patch"); echo "  gold -> $GOLD  $(grep -a '^ACCEPT SUMMARY' "$OUT/gold.stdout" | tail -1)"
echo "== noop acceptance =="; NOOP=$(run_acc noop "$OUT/noop.patch"); echo "  noop -> $NOOP  $(grep -a '^ACCEPT SUMMARY' "$OUT/noop.stdout" | tail -1)"
python3 - "$TD/preflight.json" <<PY
import json, sys
json.dump({"instance_id": "$IID", "image": "$IMAGE", "gold": "$GOLD", "noop": "$NOOP",
           "gold_summary": open("$OUT/gold.stdout").read().strip().splitlines()[-1],
           "noop_summary": open("$OUT/noop.stdout").read().strip().splitlines()[-1],
           "f2p_tests_on_gold": sum(1 for l in open("$OUT/gold/test_output.txt", errors="replace") if l.startswith("PASSED ")),
           "when": "$(date -Iseconds)"}, open(sys.argv[1], "w"), indent=2)
PY
cat "$TD/preflight.json"
[ "$GOLD" = PASS ] && [ "$NOOP" = FAIL ] && echo "PREFLIGHT OK" || { echo "PREFLIGHT FAILED"; exit 1; }
