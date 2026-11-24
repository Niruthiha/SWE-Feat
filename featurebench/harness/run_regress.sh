#!/usr/bin/env bash
# run_regress.sh <run_dir> - existing-feature regression check, run ONCE after the
# cell converged (the feature is fully in: hidden F2P passes). Harness-only, not
# part of the benchmark's verdict.
#
# Question it answers: did the agent's change break tests that the ORIGINAL
# (pristine, gold) tree passes?  Method: the same test files are run under pytest
# -rA on two trees prepared in fresh containers from the same image,
#     gold   = /root/my_repo as shipped (implementation + original tests)
#     agent  = masked tree + agent diff + F2P test restored (= the accepted tree)
# and compared per test id. A test PASSED on gold and FAILED/ERROR on agent, or
# gone from the agent run's collection, is a regression candidate. Tests the agent
# added itself (absent on gold) are ignored.
#
# Scope (REGRESS_SCOPE):
#   touched  (default) every test directory under, beside or one level above any
#            source file touched by the agent's diff OR by the mask patch, plus
#            the P2P and F2P files. The wider the agent reached, the wider the net.
#   all      every test directory in the tree (sympy: hours; use deliberately)
#   users    (v2, 2026-11-02; same rule on every task) the "touched" set PLUS every test file in the
#            pristine tree whose text names a changed module (import, from-import, or a dotted string
#            such as a mock.patch target) - changed = any .py source in the agent diff or the mask patch.
#            Found inside a --network none container over /root/my_repo. Writes to regress_users/ (its
#            own regression.json there), never over regress/ or the cell's regression.json. Test files
#            that fail to COLLECT on gold are listed (gold_uncollectable), not silently passed.
# Writes <run_dir>/regress/{gold,agent}/results.tsv, regression.json, regression.md
set -euo pipefail
RUN_DIR=$(realpath "$1"); HERE=$(realpath "$(dirname "$0")")
SCOPE="${REGRESS_SCOPE:-touched}"; T_RUN="${REGRESS_TIMEOUT:-3600}"
META="$RUN_DIR/task_meta.json"
IID=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['instance_id'])" "$META")
TD="$HERE/tasks/$IID"
meta () { python3 -c "import json,sys;v=json.load(open(sys.argv[1]))$1;print(v if not isinstance(v,list) else ' '.join(v))" "$META" "$1"; }
REPO=$(meta "['repository']" ""); IMAGE_NAME=$(meta "['image_name']" "")
F2P=$(meta "['FAIL_TO_PASS'][0]" ""); P2P=$(meta "['PASS_TO_PASS']" "")
TEST_CMD=$(meta "['test_cmd']" ""); T_ONE=$(meta "['timeout_one']" "")
IMAGE="fbexp-agent:$(echo "$IMAGE_NAME" | sed -E 's#.*featurebench-specs_##; s#-instance_#-#')"
[ -s "$TD/image_tag" ] && IMAGE="fbexp-agent:$(tr -d "[:space:]" < "$TD/image_tag")"  # per-task image override (environment repair, see instruments/Dockerfile.iers)
if [ "$SCOPE" = users ] || [ "$SCOPE" = all ]; then OUT="$RUN_DIR/regress_$SCOPE"; JSON_DIR="$OUT"; else OUT="$RUN_DIR/regress"; JSON_DIR="$RUN_DIR"; fi
[ "${REPARSE:-0}" = 1 ] || rm -rf "$OUT"; mkdir -p "$OUT"
[ -s "$RUN_DIR/diff.patch" ] || { echo "no final diff.patch in $RUN_DIR" >&2; exit 1; }
[ -s "$TD/test_dirs.txt" ] || { echo "no $TD/test_dirs.txt (run preflight_task.sh)" >&2; exit 1; }

# ---- scope -------------------------------------------------------------------
python3 - "$RUN_DIR/diff.patch" "$TD/mask.patch" "$TD/test_dirs.txt" "$SCOPE" "$F2P" $P2P > "$OUT/scope.txt" <<'PY'
import re, sys, pathlib
agent, mask, dirs_f, scope, f2p, *p2p = sys.argv[1:]
TEST_RE = re.compile(r"(^|/)(tests?)/|(^|/)test_[^/]*\.py$|_test\.py$")
def files(p):
    out = set()
    for l in pathlib.Path(p).read_text(errors="replace").splitlines():
        if l.startswith("+++ b/") or l.startswith("--- a/"):
            out.add(l[6:])
    return out
test_dirs = [d for d in pathlib.Path(dirs_f).read_text().split() if d]
src = {f for f in files(agent) | files(mask) if not TEST_RE.search(f) and f.endswith(".py")}
chosen = set()
if scope == "all":
    chosen = set(test_dirs)
if scope != "all":
    for f in src:
        d = str(pathlib.PurePosixPath(f).parent)
        parent = str(pathlib.PurePosixPath(d).parent)
        for td in test_dirs:
            if td == d or td.startswith(d + "/") or td in (f"{d}/tests", f"{d}/test", f"{parent}/tests", f"{parent}/test"):
                chosen.add(td)
paths = sorted(chosen) + [p for p in [f2p] + p2p if not any(p.startswith(c + "/") for c in chosen)]
print("\n".join(paths))
print("\n".join(f"# source: {s}" for s in sorted(src)), file=sys.stderr)
PY
if [ "$SCOPE" = users ] && [ "${REPARSE:-0}" != 1 ]; then  # add test FILES that name a changed module
  sc="fbreg-scope-$$"; docker rm -f "$sc" >/dev/null 2>&1 || true
  docker run -d --name "$sc" --network none "$IMAGE" sleep infinity >/dev/null
  python3 - "$RUN_DIR/diff.patch" "$TD/mask.patch" > "$OUT/changed_modules.txt" <<'PY'
import re, sys, pathlib
TEST_RE = re.compile(r"(^|/)(tests?)/|(^|/)test_[^/]*\.py$|_test\.py$")
fs = set()
for p in sys.argv[1:]:
    for l in pathlib.Path(p).read_text(errors="replace").splitlines():
        if l.startswith("+++ b/") or l.startswith("--- a/"): fs.add(l[6:])
for f in sorted(fs):
    if f.endswith(".py") and not TEST_RE.search(f):
        m = f[:-3].replace("/", ".")
        print(m[:-9] if m.endswith(".__init__") else m)
PY
  docker cp "$OUT/changed_modules.txt" "$sc:/tmp/changed_modules.txt"
  docker exec -i --user 0:0 "$sc" bash -c 'cd /root/my_repo && python3 - "'"$REPO"'"' > "$OUT/users.txt" 2> "$OUT/users.err" <<'PY'
import re, os, sys
mods = [m for m in open("/tmp/changed_modules.txt").read().split() if m]
# strip the src-layout prefix (src/ or libs/x/) so "src/pkg/mod" matches "pkg.mod" in imports
alts = set()
for m in mods:
    parts = m.split(".")
    for i in range(len(parts)):
        if len(parts) - i >= 2 or i == 0: alts.add(".".join(parts[i:]))
pats = []
for m in sorted(alts):
    if "." not in m: continue                        # never match a bare top-level package name
    pkg, last = m.rsplit(".", 1)
    pats.append(re.compile(r"\b" + re.escape(m) + r"\b"))
    pats.append(re.compile(r"from\s+" + re.escape(pkg) + r"\s+import\s+(\([^)]*|[^\n]*)\b" + re.escape(last) + r"\b"))
TEST_RE = re.compile(r"(^|/)(tests?)/|(^|/)test_[^/]*\.py$|_test\.py$")
for root, ds, fs in os.walk("."):
    ds[:] = [d for d in ds if d not in (".git", "node_modules", "__pycache__")]
    for f in fs:
        p = os.path.join(root, f)[2:]
        if not (f.endswith(".py") and (f.startswith("test_") or f.endswith("_test.py")) and TEST_RE.search(p)): continue
        try: t = open(p, errors="replace").read()
        except OSError: continue
        if any(x.search(t) for x in pats): print(p)
PY
  docker rm -f "$sc" >/dev/null 2>&1 || true
  cp "$OUT/scope.txt" "$OUT/scope_touched.txt"
  sort -u "$OUT/users.txt" | while read -r f; do
    if ! grep -qxF "$f" "$OUT/scope_touched.txt" && awk -v f="$f" 'BEGIN{s=0} !/^#/ && $0!="" {if (index(f, $0"/")==1) s=1} END{exit s}' "$OUT/scope_touched.txt"; then echo "$f"; fi
  done >> "$OUT/scope.txt"
  echo "users scope: $(wc -l < "$OUT/changed_modules.txt") changed modules -> $(sort -u "$OUT/users.txt" | wc -l) test files name them"
fi
mapfile -t PATHS < <(grep -v '^#' "$OUT/scope.txt" | sed '/^$/d')
# 2026-11-12: REGRESS_SPLIT=1 replaces a scope path that is a parent of other test dirs (pandas: the
# whole pandas/tests) by its direct child test dirs plus its own top-level test_*.py files, one pytest
# process each, so one hanging/aborting file loses one folder instead of the whole run. Same tests.
if [ -n "${REGRESS_SPLIT:-}" ]; then
  mapfile -t PATHS < <(python3 - "$TD/test_dirs.txt" "${PATHS[@]}" <<'PY'
import sys
dirs = [d for d in open(sys.argv[1]).read().split() if d]
for p in sys.argv[2:]:
    kids = sorted({d[len(p)+1:].split("/")[0] for d in dirs if d.startswith(p + "/")})
    if kids:
        print(f"{p}/test_*.py")
        for k in kids: print(f"{p}/{k}")
    else:
        print(p)
PY
)
  printf '%s\n' "${PATHS[@]}" > "$OUT/scope_split.txt"
fi
# 2026-11-17: REGRESS_SPLIT=file goes one step further for flat test dirs (xarray: xarray/tests has no
# child test dirs, and one whole-dir pytest process segfaulted on gold / stalled on agent for treenode and
# range_index). Every directory path becomes its test_*.py files, one pytest process each (file list read in
# a --network none container from the image, identical for both trees). Same tests, finer failure unit.
if [ "${REGRESS_SPLIT:-}" = file ]; then
  sf="fbreg-split-$$"; mapfile -t PATHS < <(docker run --rm --name "$sf" --network none "$IMAGE" bash -c \
    'cd /testbed 2>/dev/null || cd /root/my_repo; for p in "$@"; do p=${p%/test_\*.py}; if [ -d "$p" ]; then ls "$p"/test_*.py; else echo "$p"; fi; done' _ "${PATHS[@]}" | sort -u)
  printf '%s\n' "${PATHS[@]}" > "$OUT/scope_split.txt"
fi
echo "regression scope ($SCOPE): ${#PATHS[@]} paths"; printf '  %s\n' "${PATHS[@]}"

run_tree () { # run_tree <label> <agent.patch|GOLD>
  local label="$1" patch="$2"; local c="fbreg-$label-$$"
  docker rm -f "$c" >/dev/null 2>&1 || true
  docker run -d --name "$c" --network none "$IMAGE" sleep infinity >/dev/null
  docker cp "$TD/mask.patch" "$c:/tmp/mask.patch"; docker cp "$TD/test.patch" "$c:/tmp/test.patch"
  local parg=GOLD
  if [ "$patch" != GOLD ]; then docker cp "$patch" "$c:/tmp/agent.patch"; parg=/tmp/agent.patch; fi
  local ric=regress_in_container; local denv=()
  # 2026-11-12: pandas test_clipboard starts Qt; with no display Qt aborts the whole pytest process
  # (gold and agent alike). REGRESS_QT_OFFSCREEN=1 sets QT_QPA_PLATFORM=offscreen; no test is changed.
  [ -n "${REGRESS_QT_OFFSCREEN:-}" ] && denv+=(-e QT_QPA_PLATFORM=offscreen)
  if [ "${DOCSTRIP:-0}" = 1 ]; then  # docstring arm: strip both trees in the container (see regress_in_container.sh)
    docker cp "${DOCSTRIP_SCRIPT:-$HERE/instruments/strip_docstrings.py}" "$c:/tmp/strip_docstrings.py"
    docker cp "$HERE/instruments/regress_in_container.sh" "$c:/tmp/regress_in_container"; ric="bash /tmp/regress_in_container"
    denv=(-e DOCSTRIP=/tmp/strip_docstrings.py)
  fi
  set +e
  docker exec --user 0:0 "${denv[@]}" "$c" $ric /tmp/mask.patch /tmp/test.patch "$parg" "$F2P" "$REPO" "$TEST_CMD" "$T_ONE" "$T_RUN" /tmp/reg "${PATHS[@]}" > "$OUT/$label.stdout" 2>&1
  local rc=$?; set -e
  docker cp "$c:/tmp/reg" "$OUT/$label" >/dev/null 2>&1 || true
  docker rm -f "$c" >/dev/null 2>&1 || true
  echo "  $label: $(tail -1 "$OUT/$label.stdout") (exit $rc)"
}
if [ "${REPARSE:-0}" = 1 ]; then echo "REPARSE=1: reusing regress/{gold,agent}/results.tsv"; else
echo "== gold tree =="; run_tree gold GOLD
echo "== agent tree =="; run_tree agent "$RUN_DIR/diff.patch"
fi

python3 - "$OUT" "$IID" "$SCOPE" "$JSON_DIR" <<'PY'
import json, re, sys, pathlib
out = pathlib.Path(sys.argv[1]); iid = sys.argv[2]; scope = sys.argv[3]; jdir = pathlib.Path(sys.argv[4])
# mlflow's conftest decorates every result line with "| MEM x/y GB | DISK x/y GB ";
# it is run-specific noise, not part of the test id
NOISE = re.compile(r"^\| MEM [^|]*\| DISK [^ ]* GB ")
# fallback for plugins that suppress the -rA summary (pytest-pretty in pydantic):
# verbose per-test lines "path::test OUTCOME [ nn%]", used only when a file has no -rA lines
VERBOSE = re.compile(r"^(\S+::\S.*?) (PASSED|FAILED|ERROR|XFAIL|XPASS|SKIPPED)(?: \(.*\))?\s+\[\s*\d+%\]$")
def parse_raw(label):
    # same rules as regress_in_container's parser, applied host-side to the raw
    # pytest -rA outputs (fallback for a container whose parser produced nothing)
    res = {}
    for of in sorted((out / label).glob("out_*.txt")):
        lines = of.read_text(errors="replace").splitlines(); got = {}
        for line in lines:
            m = re.match(r"^(PASSED|FAILED|ERROR|XFAIL|XPASS) (\S.*?)(?: - .*)?$", line)
            if m: got[NOISE.sub("", m.group(2))] = m.group(1); continue
            m = re.match(r"^SKIPPED (?:\[\d+\] )?(\S+?:\d+):", line)
            if m: got[m.group(1)] = "SKIPPED"
        if not got:
            for line in lines:
                m = VERBOSE.match(NOISE.sub("", line))
                if m: got[m.group(1)] = m.group(2)
        res.update(got)
    return res
def load(label):
    res = {}
    f = out / label / "results.tsv"
    if not (out / label).exists(): return None
    if f.exists():
        for l in f.read_text(errors="replace").splitlines():
            if "\t" in l:
                k, v = l.rsplit("\t", 1); res[NOISE.sub("", k)] = v
    if not res:
        res = parse_raw(label)
        if res: print(f"  {label}: results.tsv empty; {len(res)} outcomes parsed host-side from out_*.txt")
    return res
gold, agent = load("gold"), load("agent")
if gold is not None and agent is not None and (not gold or not agent):
    gold = agent = None  # a run that collected nothing must not yield a vacuous verdict
r = {"instance_id": iid, "scope": scope, "paths": (out / "scope.txt").read_text().split("\n") if (out / "scope.txt").exists() else []}
r["paths"] = [p for p in r["paths"] if p and not p.startswith("#")]
if gold is None or agent is None:
    r["status"] = "error"; r["note"] = "one of the runs produced no per-test results (no results.tsv and nothing parsable in out_*.txt)"
else:
    gp = {k for k, v in gold.items() if v == "PASSED"}
    regressions = sorted(k for k in gp if agent.get(k) not in ("PASSED", "XPASS", "SKIPPED"))
    r.update(status="ok",
             gold={"tests": len(gold), "passed": len(gp), "failed": sum(v in ("FAILED", "ERROR") for v in gold.values())},
             agent={"tests": len(agent), "passed": sum(v == "PASSED" for v in agent.values()),
                    "failed": sum(v in ("FAILED", "ERROR") for v in agent.values())},
             regressions=[{"test": k, "gold": "PASSED", "agent": agent.get(k, "MISSING")} for k in regressions],
             n_regressions=len(regressions),
             fixed_by_agent=sorted(k for k, v in gold.items() if v in ("FAILED", "ERROR") and agent.get(k) == "PASSED"),
             added_by_agent=sorted(k for k in agent if k not in gold),
             gold_exits=(out / "gold" / "exits").read_text().split("\n") if (out / "gold" / "exits").exists() else [],
             agent_exits=(out / "agent" / "exits").read_text().split("\n") if (out / "agent" / "exits").exists() else [])
    r["verdict"] = "no_regression" if not regressions else "REGRESSION"
if gold is not None:  # test files that error at collection on the pristine tree cannot show a regression: list them
    r["gold_uncollectable"] = sorted({re.sub(r"^ERROR ", "", l).split(" ")[0] for of in (out / "gold").glob("out_*.txt")
                                      for l in of.read_text(errors="replace").splitlines() if re.match(r"^ERROR \S+\.py( |$)", l)})
json.dump(r, open(jdir / "regression.json", "w"), indent=2)
md = [f"# Existing-feature regression check: {iid}", "",
      f"scope = {scope}, {len(r['paths'])} test paths, gold vs agent tree, pytest -rA per test id", ""]
if r.get("status") == "ok":
    md += [f"| tree | tests collected | passed | failed/error |", "|---|---|---|---|",
           f"| gold (pristine) | {r['gold']['tests']} | {r['gold']['passed']} | {r['gold']['failed']} |",
           f"| agent (accepted) | {r['agent']['tests']} | {r['agent']['passed']} | {r['agent']['failed']} |", "",
           f"**verdict: {r['verdict']}** ({r['n_regressions']} tests PASSED on gold and not on agent)", ""]
    md += [f"- `{x['test']}` gold PASSED -> agent {x['agent']}" for x in r["regressions"]]
    if r["added_by_agent"]: md += ["", f"{len(r['added_by_agent'])} test ids exist only on the agent tree (agent-added tests; not compared)."]
    if r["fixed_by_agent"]: md += ["", f"{len(r['fixed_by_agent'])} tests fail on gold and pass on agent (listed in regression.json)."]
else:
    md += [f"status: {r.get('status')} {r.get('note','')}"]
if r.get("gold_uncollectable"): md += ["", f"{len(r['gold_uncollectable'])} test files could not be collected on gold (not comparable): " + ", ".join(r["gold_uncollectable"][:20])]
(jdir / "regression.md").write_text("\n".join(md) + "\n")
print("\n".join(md))
PY
