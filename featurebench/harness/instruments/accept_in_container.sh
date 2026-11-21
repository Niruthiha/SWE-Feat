#!/usr/bin/env bash
# accept_in_container <mask.patch> <test.patch> <agent.patch> <f2p-file> <repository> <test_cmd> <timeout_one> <timeout_run> <out-dir> <p2p-file>...
# Run as ROOT in a FRESH container from the same image. A line-for-line port of
# featurebench/harness/runtime.py run_instance_level1 (steps 1-8, non-white-box).
# Pass criteria are the benchmark's: f2p = pytest exit 0 on the restored F2P file,
# p2p = pytest exit 0 on EVERY P2P file; resolved = f2p AND p2p.
# Writes <out-dir>/test_output.txt (F2P) and test_output_p2p_<name>.txt, and prints
# ACCEPT SUMMARY f2p=PASS|FAIL p2p=PASS|FAIL patch_applied=0|1
set -uo pipefail
MASK="$1"; TESTP="$2"; AGENT="$3"; F2P="$4"; REPO="$5"; TEST_CMD="$6"; T_ONE="$7"; T_RUN="$8"; OUT="$9"; shift 9
P2P=("$@"); mkdir -p "$OUT"
log () { echo "[accept] $*"; }
source /opt/miniconda3/etc/profile.d/conda.sh && conda activate testbed && rm -rf /testbed/* && cp -r /root/my_repo/* /testbed/ || { log "restore failed"; exit 2; }
if [ -s "$MASK" ]; then
  ( cd /testbed && git apply --whitespace=fix "$MASK" ) > "$OUT/mask_apply.txt" 2>&1 || log "WARNING mask patch did not apply cleanly (benchmark warns, continues)"
fi
case "$F2P" in /testbed/*) F2PP="$F2P";; *) F2PP="/testbed/$F2P";; esac
rm -f "$F2PP"
if [ "$REPO" = "mlflow/mlflow" ]; then
  for path in /testbed/libs/skinny/mlflow /testbed/libs/tracing/mlflow; do
    if [ -e "$path" ] || [ -L "$path" ]; then rm -rf -- "$path" || { log "env fix failed"; exit 2; }; fi
  done
fi
# harness docstring arm: the same stripper on the same masked tree, so the agent's patch
# applies to exactly the tree it was made against (unset = the benchmark's evaluator)
if [ -n "${DOCSTRIP:-}" ]; then
  python3 -I "$DOCSTRIP" /testbed > "$OUT/docstrip.txt" 2>&1 || { log "docstring strip failed"; exit 2; }
fi
( cd /testbed && rm -rf .git && git init -q && git config user.email "fb@bench.com" && git config user.name "FeatureBench" \
  && git add -A && git commit -qm "Initial commit for FeatureBench evaluation" --allow-empty ) || log "WARNING git re-init reported failure (benchmark warns, continues)"
APPLIED=0
if [ ! -s "$AGENT" ]; then
  echo "ACCEPT SUMMARY f2p=FAIL p2p=FAIL patch_applied=0 error=empty_patch"; exit 1
fi
if ( cd /testbed && git apply --whitespace=fix --verbose "$AGENT" ) > "$OUT/patch_apply.txt" 2>&1; then APPLIED=1
else echo "ACCEPT SUMMARY f2p=FAIL p2p=FAIL patch_applied=0 error=patch_apply_failed"; exit 1; fi
rm -f "$F2PP"
if [ -s "$TESTP" ]; then
  ( cd /testbed && git apply --reverse --whitespace=fix "$TESTP" ) > "$OUT/test_restore.txt" 2>&1 || log "WARNING reverse-apply of test_patch failed (benchmark warns, continues)"
fi
CMD="$TEST_CMD"; if [ "${T_ONE:-0}" -gt 0 ] 2>/dev/null; then CMD="$CMD --timeout=$T_ONE"; fi
run_one () {  # run_one <abs test path> <out file> -> exit code on stdout
  ( source /opt/miniconda3/etc/profile.d/conda.sh && conda activate testbed && cd /testbed \
    && timeout -k 10 "$T_RUN" bash -c "$CMD $1" ) > "$2" 2>&1; echo $? ; }
F2P_RC=$(run_one "$F2PP" "$OUT/test_output.txt"); echo "$F2P_RC" > "$OUT/f2p_exit"
F2P_RES=FAIL; [ "$F2P_RC" = 0 ] && F2P_RES=PASS
P2P_RES=PASS
for p in "${P2P[@]}"; do
  case "$p" in /testbed/*) pp="$p";; *) pp="/testbed/$p";; esac
  name=$(basename "$pp" .py)
  rc=$(run_one "$pp" "$OUT/test_output_p2p_${name}.txt"); echo "$pp $rc" >> "$OUT/p2p_exits"
  [ "$rc" = 0 ] || P2P_RES=FAIL
done
echo "ACCEPT SUMMARY f2p=$F2P_RES p2p=$P2P_RES patch_applied=$APPLIED"
[ "$F2P_RES" = PASS ] && [ "$P2P_RES" = PASS ] && exit 0 || exit 1
