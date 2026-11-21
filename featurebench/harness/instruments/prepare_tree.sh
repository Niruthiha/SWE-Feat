#!/usr/bin/env bash
# prepare_tree <mask.patch> <f2p-file> <repository> -- run as ROOT inside the agent
# container BEFORE the agent exists. A line-for-line port of
# featurebench/infer/runtime.py InferenceRuntime._initialize_level1 (steps 1-6)
# + clear_package_caches, followed by one harness-only step (chown to the agent uid).
# Every command is the benchmark's; only the step comments are ours.
set -uo pipefail
MASK="$1"; F2P="$2"; REPO="$3"
echo "== step 1: restore /testbed from /root/my_repo =="
source /opt/miniconda3/etc/profile.d/conda.sh && conda activate testbed \
 && rm -rf /testbed/* && cp -r /root/my_repo/* /testbed/ && rm -rf /root/my_repo || exit 11
echo "== step 2: apply mask patch =="
if [ -s "$MASK" ]; then
  ( cd /testbed; git apply --whitespace=fix "$MASK"; status=$?; rm -f -- "$MASK"; exit "$status" ) || exit 12
else echo "no mask patch"; fi
echo "== step 3: delete F2P test file =="
case "$F2P" in /testbed/*) P="$F2P";; *) P="/testbed/$F2P";; esac
rm -f "$P"; [ -e "$P" ] && exit 13
echo "deleted $P"
echo "== step 4: repository-specific environment fixes =="
# featurebench/environment_fixes/mlflow.py MlflowParallelSourcesFix, verbatim
if [ "$REPO" = "mlflow/mlflow" ]; then
  paths=(/testbed/libs/skinny/mlflow /testbed/libs/tracing/mlflow)
  for path in "${paths[@]}"; do
    if [ -e "$path" ] || [ -L "$path" ]; then rm -rf -- "$path" || exit 14; echo "Removed MLflow parallel source: $path"; fi
    if [ -e "$path" ] || [ -L "$path" ]; then echo "MLflow parallel source still exists: $path" >&2; exit 14; fi
  done
fi
echo "== step 5: remove stale python bytecode =="
( set -e; cd /testbed || exit 1
  find . -type d -name __pycache__ -prune -exec rm -rf -- {} +
  find . -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete ) || exit 15
# harness index arm (DOCS-ARM-PLAN.md): NAV_INDEX=<generator path> -> a navigation-only
# symbol index is generated on the MASKED tree here, so it is part of the base commit
# (never in the agent's diff) and lists nothing the mask removed. Unset = byte-identical
# to the baseline arm. The generator is deleted afterwards.
if [ -n "${NAV_INDEX:-}" ]; then
  echo "== index arm: navigation index on the masked tree (before git init) =="
  python3 -I "$NAV_INDEX" /testbed || exit 18
  rm -f -- "$NAV_INDEX"
fi
# harness docstring arm (DOCSTRING-ARM.md): DOCSTRIP=<stripper path> -> every docstring
# in the repo's non-test .py files becomes "" on the MASKED tree here, so the stripped
# text is the base commit (never in the agent's diff). Unset = byte-identical to baseline.
if [ -n "${DOCSTRIP:-}" ]; then
  echo "== docstring arm: strip docstrings on the masked tree (before git init) =="
  python3 -I "$DOCSTRIP" /testbed || exit 19
  # other installed copies of the repo's own package in OTHER conda envs are REMOVED
  # (operator decision 2026-10-28): the sympy image ships sympy 1.13.1 in envs/pytorch_base
  # with full docstrings AND older versions of both sympy tasks' gold module and hidden test
  # file. No test imports that env. For repos without such a copy this loop does nothing.
  PKG="${REPO#*/}"
  for sp in /opt/miniconda3/envs/*/lib/python3*/site-packages/"$PKG"; do
    [ -d "$sp" ] || continue
    case "$sp" in /opt/miniconda3/envs/testbed/*) continue;; esac
    echo "EXTRA_COPY_REMOVED $sp ($(find "$sp" -name '*.py' | wc -l) .py files)"
    rm -rf -- "$sp" || exit 19
    # top-level modules the same distribution installs next to it (sympy: isympy.py + bytecode)
    for m in "$(dirname "$sp")"/isympy.py "$(dirname "$sp")"/__pycache__/isympy.*.pyc; do
      [ "$PKG" = sympy ] && [ -e "$m" ] && { echo "EXTRA_COPY_REMOVED $m"; rm -f -- "$m"; }
    done
  done
  rm -f -- "$DOCSTRIP"
fi
echo "== step 6: re-initialise git =="
( cd /testbed && rm -rf .git && git init -q \
  && git config user.email "fb@bench.com" && git config user.name "FeatureBench" \
  && git add -A && git commit -qm "Initial commit for FeatureBench evaluation" --allow-empty \
  && git rev-parse HEAD ) || exit 16
echo "== clear package caches (InferenceRuntime.clear_package_caches) =="
shopt -s nullglob
for cache_path in /download /opt/miniconda3/pkgs /opt/conda/pkgs /root/.cache/pip /root/.cache/uv /root/.conda/pkgs /home/*/.cache/pip /home/*/.cache/uv /home/*/.conda/pkgs; do
  [ -e "$cache_path" ] || continue
  size_kb="$(du -sk "$cache_path" 2>/dev/null | awk '{print $1}')"
  find "$cache_path" -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +
  echo "Cleared package cache: $cache_path (${size_kb:-unknown} KB)"
done
for temp_path in /tmp/pip-* /tmp/uv-*; do [ -e "$temp_path" ] || continue; rm -rf -- "$temp_path"; echo "Cleared package temporary path: $temp_path"; done
echo "== base tree =="
echo "BASE_TREE $(cd /testbed && git rev-parse HEAD^{tree})"
echo "== harness-only: hand the tree to the agent uid =="
chown -R 1000:1000 /testbed || exit 17
echo "prepare_tree done"
