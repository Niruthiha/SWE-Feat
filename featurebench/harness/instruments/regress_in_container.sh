#!/usr/bin/env bash
# regress_in_container <mask.patch> <test.patch> <agent.patch|GOLD> <f2p-file> <repository> <test_cmd> <timeout_one> <timeout_run> <out-dir> <test-path>...
# Harness-only (not part of the benchmark): the WIDER existing-feature regression
# check, run once after the cell converges. Same tree preparation as the
# acceptance, then pytest -rA over every given test path, with per-test outcomes
# written to <out-dir>/results.tsv (nodeid<TAB>PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS).
# With agent patch = GOLD the tree is the pristine one (mask reverse-applied), so
# the two runs can be diffed per test: PASSED on gold, not PASSED on agent = a
# regression the agent introduced in an existing feature.
set -uo pipefail
MASK="$1"; TESTP="$2"; AGENT="$3"; F2P="$4"; REPO="$5"; TEST_CMD="$6"; T_ONE="$7"; T_RUN="$8"; OUT="$9"; shift 9
PATHS=("$@"); mkdir -p "$OUT"
source /opt/miniconda3/etc/profile.d/conda.sh && conda activate testbed && rm -rf /testbed/* && cp -r /root/my_repo/* /testbed/ || exit 2
if [ "$AGENT" != GOLD ]; then
  [ -s "$MASK" ] && ( cd /testbed && git apply --whitespace=fix "$MASK" ) > "$OUT/mask_apply.txt" 2>&1
  case "$F2P" in /testbed/*) F2PP="$F2P";; *) F2PP="/testbed/$F2P";; esac
  rm -f "$F2PP"
fi
if [ "$REPO" = "mlflow/mlflow" ]; then
  for path in /testbed/libs/skinny/mlflow /testbed/libs/tracing/mlflow; do
    { [ -e "$path" ] || [ -L "$path" ]; } && rm -rf -- "$path"
  done
fi
# docstring arm (2026-10-29): DOCSTRIP=<stripper path> strips BOTH trees (gold = pristine,
# agent = masked) with the same stripper as the cell's prepare_tree/acceptance, so the
# agent's diff applies to the tree it was made against and gold is compared like for like
if [ -n "${DOCSTRIP:-}" ]; then
  python3 -I "$DOCSTRIP" /testbed > "$OUT/docstrip.txt" 2>&1 || { echo "REGRESS SUMMARY error=docstrip_failed"; exit 2; }
fi
( cd /testbed && rm -rf .git && git init -q && git config user.email "fb@bench.com" && git config user.name "FeatureBench" \
  && git add -A && git commit -qm "Initial commit for FeatureBench evaluation" --allow-empty ) >/dev/null 2>&1
( cd /testbed && git rev-parse "HEAD^{tree}" ) > "$OUT/base_tree.txt" 2>&1
if [ "$AGENT" != GOLD ]; then
  ( cd /testbed && git apply --whitespace=fix --verbose "$AGENT" ) > "$OUT/patch_apply.txt" 2>&1 || { echo "REGRESS SUMMARY error=patch_apply_failed"; exit 2; }
  rm -f "$F2PP"
  [ -s "$TESTP" ] && ( cd /testbed && git apply --reverse --whitespace=fix "$TESTP" ) > "$OUT/test_restore.txt" 2>&1
fi
CMD="$TEST_CMD"; if [ "${T_ONE:-0}" -gt 0 ] 2>/dev/null; then CMD="$CMD --timeout=$T_ONE"; fi
: > "$OUT/results.tsv"
i=0
for p in "${PATHS[@]}"; do
  case "$p" in /testbed/*) pp="$p";; *) pp="/testbed/$p";; esac
  i=$((i+1)); of="$OUT/out_$(printf '%03d' $i).txt"
  ( source /opt/miniconda3/etc/profile.d/conda.sh && conda activate testbed && cd /testbed \
    && timeout -k 10 "$T_RUN" bash -c "$CMD $pp" ) > "$of" 2>&1; rc=$?
  echo "$pp $rc" >> "$OUT/exits"
  # pytest -rA short summary lines: "PASSED path::test", "FAILED path::test - msg", "ERROR path::test", "SKIPPED [n] path:line: reason", "XFAIL path::test", "XPASS path::test"
  python3 - "$of" >> "$OUT/results.tsv" <<'PY'
import re, sys
NOISE = re.compile(r"^\| MEM [^|]*\| DISK [^ ]* GB ")
# fallback for plugins that suppress the -rA summary (pytest-pretty in pydantic):
# verbose per-test lines "path::test OUTCOME [ nn%]", used only when a file has no -rA lines
VERBOSE = re.compile(r"^(\S+::\S.*?) (PASSED|FAILED|ERROR|XFAIL|XPASS|SKIPPED)(?: \(.*\))?\s+\[\s*\d+%\]$")
lines = open(sys.argv[1], errors="replace").read().splitlines(); got = {}
for line in lines:
    m = re.match(r"^(PASSED|FAILED|ERROR|XFAIL|XPASS) (\S.*?)(?: - .*)?$", line)
    if m: got[NOISE.sub("", m.group(2))] = m.group(1); continue
    m = re.match(r"^SKIPPED (?:\[\d+\] )?(\S+?:\d+):", line)
    if m: got[m.group(1)] = "SKIPPED"
if not got:
    for line in lines:
        m = VERBOSE.match(NOISE.sub("", line))
        if m: got[m.group(1)] = m.group(2)
for k, v in got.items(): print(k + "\t" + v)
PY
done
echo "REGRESS SUMMARY paths=${#PATHS[@]} tests=$(wc -l < "$OUT/results.tsv" | tr -d ' ') passed=$(grep -c $'\tPASSED$' "$OUT/results.tsv")"
