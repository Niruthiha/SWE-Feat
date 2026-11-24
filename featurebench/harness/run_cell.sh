#!/usr/bin/env bash
# run_cell.sh - ONE CELL on a FeatureBench task: one agent, one fresh tree prepared
# exactly as the benchmark prepares it, the benchmark's own problem statement as the
# only prompt, run until the HIDDEN tests pass.  Harness v6.0 (2026-10-26), the
# FeatureBench variant of experiment-hotcrp/run_cell.sh v5.2.
#
# Usage: ./run_cell.sh <instance_id> [seed]
#
#   round 0        the dataset problem_statement, byte-for-byte (tasks/<id>/prompt.txt)
#   round n>0      blind_msg.txt and nothing else ("This is not done correctly. Keep
#                  working on it until it is.")  -- FEEDBACK=blind is the only mode
#
# After EVERY round the acceptance check runs in a FRESH container from the same
# image, as the benchmark's evaluator does (instruments/accept_in_container.sh =
# harness/runtime.py run_instance_level1): the agent's diff is applied to a clean
# masked tree, the hidden FAIL_TO_PASS file is restored, and it plus every
# PASS_TO_PASS file must exit 0. Nothing from that run ever reaches the agent.
# The count of rounds to the first PASS is the primary outcome.
#
# What v6.0 keeps from v5.2 (HARNESS.md section 3): one session id resumed every
# round, one container, empty HOME, no MCP, read-only credential outside HOME,
# internal network + allowlist egress proxy (hcexp-egress:2, incl. the OAuth refresh
# host, Fault 12/13), refused rounds -> agent_unavailable exit 3 (never a verdict),
# session_broken on a lost session, last-wins cost rule (roundcost.py, Fault 2),
# per-round snapshots, test_integrity, stall futility stop, isolation attestation
# before the agent runs, manifest first.
# What it drops: the repo self-suite and fix rounds (the agent gets NO test
# feedback of any kind), the symptom vocabulary, the PHP database (Fault 11's fix
# becomes "everything is provisioned by the benchmark image at build time").
# What it adds: the benchmark's tree preparation as root before the agent exists
# (instruments/prepare_tree.sh), the session store copied out at the end so the
# model's THINKING text is kept (stream-json redacts it), and a post-convergence
# existing-feature regression check (run_regress.sh).
set -euo pipefail
HARNESS_VERSION="6.0"
MODEL="${MODEL:-claude-opus-5-5}"
MAX_ROUNDS="${MAX_ROUNDS:-0}"          # blind rounds after round 0; 0 = unlimited
MAX_USD="${MAX_USD:-0}"                # 0 = unlimited
STALL_ROUNDS="${STALL_ROUNDS:-10}"     # tree byte-identical N rounds in a row -> stop
FEEDBACK="blind"
REGRESS="${REGRESS:-1}"                # run run_regress.sh after convergence
EFFORT="${EFFORT:-}"                   # empty = CLI default (recorded in manifest)

IID="$1"; SEED="${2:-1}"
HERE=$(realpath "$(dirname "$0")")
TASK_DIR="$HERE/tasks/$IID"
[ -d "$TASK_DIR" ] || { echo "no such task: $TASK_DIR (run make_task.py)" >&2; exit 1; }
for f in prompt.txt mask.patch test.patch meta.json; do
  [ -f "$TASK_DIR/$f" ] || { echo "missing $TASK_DIR/$f" >&2; exit 1; }; done
meta () { python3 -c "import json,sys;v=json.load(open(sys.argv[1]))$1;print(v if not isinstance(v,list) else ' '.join(v))" "$TASK_DIR/meta.json" "$1"; }
REPO=$(meta "['repository']" "")
IMAGE_NAME=$(meta "['image_name']" "")
F2P=$(meta "['FAIL_TO_PASS'][0]" "")
P2P=$(meta "['PASS_TO_PASS']" "")
TEST_CMD=$(meta "['test_cmd']" "")
T_ONE=$(meta "['timeout_one']" ""); T_RUN=$(meta "['timeout_run']" "")
IMAGE="fbexp-agent:$(echo "$IMAGE_NAME" | sed -E 's#.*featurebench-specs_##; s#-instance_#-#')"
[ -s "$TASK_DIR/image_tag" ] && IMAGE="fbexp-agent:$(tr -d "[:space:]" < "$TASK_DIR/image_tag")"  # per-task image override (environment repair, see instruments/Dockerfile.iers)
docker image inspect "$IMAGE" >/dev/null 2>&1 || {
  echo "no such image: $IMAGE (run ./build_image.sh $IID)" >&2; exit 1; }
if [ -z "${ANTHROPIC_API_KEY:-}" ] && [ -z "${CLAUDE_CREDS:-}" ]; then
  echo "set ANTHROPIC_API_KEY, or CLAUDE_CREDS=/path/to/.credentials.json" >&2; exit 1; fi
# ---- PREFLIGHT (exit 4): the oracle must have been shown to discriminate -------
# preflight_task.sh records, per task, that the acceptance passes on the GOLD tree
# and fails on a no-op patch, on THIS image. v4.4 learned the hard way what an
# unvalidated oracle costs (a void $9.68 cell); a cell never starts without it.
PF="$TASK_DIR/preflight.json"
if ! python3 - "$PF" "$IMAGE" <<'PY' 2>/dev/null
import json, sys
p = json.load(open(sys.argv[1]))
assert p["gold"] == "PASS" and p["noop"] == "FAIL" and p["image"] == sys.argv[2], p
PY
then
  echo "CELL REFUSED TO START: $PF missing or not gold=PASS/noop=FAIL on $IMAGE." >&2
  echo "  run ./preflight_task.sh $IID first." >&2; exit 4
fi
# docstring arm: its own oracle check (stripped gold PASS, noop FAIL, no leak, identical
# agent/acceptance trees) made with THIS stripper on THIS image
if [ "${DOCSTRIP:-0}" = "1" ] && ! python3 - "$TASK_DIR/docstrip/preflight.json" "$IMAGE" "$(sha256sum "$HERE/instruments/strip_docstrings.py" | cut -d' ' -f1)" <<'PY' 2>/dev/null
import json, sys
p = json.load(open(sys.argv[1]))
assert p["gold"] == "PASS" and p["noop"] == "FAIL" and p["leak_files_found"] == 0 and p.get("answerkey_files_found") == 0 and p.get("answerkey_phrases_checked", 0) > 0 and p["trees_identical"] \
    and p["image"] == sys.argv[2] and p["stripper_sha256"] == sys.argv[3], p
PY
then
  echo "CELL REFUSED TO START: docstring-arm preflight missing/failed or stale; run ./preflight_docstrip.sh $IID" >&2; exit 4
fi
# change-impact arm: the offline leak gate (instruments/impact_gate.py) must have PASSED
# for THIS hook; its graph sha is compared with the graph built in the container
IMPACT_GATE="$HERE/instruments/impact_gate/$IID.json"
if [ "${IMPACT:-0}" = "1" ] && ! python3 - "$IMPACT_GATE" "$(sha256sum "$HERE/instruments/impact_hook.py" | cut -d' ' -f1)" <<'PY' 2>/dev/null
import json, sys
g = json.load(open(sys.argv[1]))
assert g["gate_verdict"] == "PASS" and g["gate_A_untouched_note_empty"] and g["hook_sha256"] == sys.argv[2], g.get("gate_verdict")
PY
then
  echo "CELL REFUSED TO START: change-impact gate missing/failed or stale hook; run instruments/impact_gate.py $IID <base-cell>" >&2; exit 4
fi
PROMPT_SHA=$(sha256sum "$TASK_DIR/prompt.txt" | cut -d' ' -f1)
MASK_SHA=$(sha256sum "$TASK_DIR/mask.patch" | cut -d' ' -f1)
SESSION_ID=$(python3 -c 'import uuid;print(uuid.uuid4())')

SHORT=$(echo "$IID" | sed -E 's/^([a-z-]+)__[^.]+\.[0-9a-f]+\.(test_[A-Za-z0-9_]+)\..*/\1-\2/')
RUN_ID="$(date +%Y%m%d-%H%M%S)-${SHORT}-s${SEED}"
# INDEX=1: index arm (DOCS-ARM-PLAN.md). Same task, prompt, image, oracle; the prepared
# tree additionally carries a mechanical single-file function map (CODE_MAP.md) in
# its base commit. INDEX_ONLY=1 stops after the index audit (dry run, no agent).
ARM=baseline
# one arm per cell: combining arm flags would silently prepare the tree for only one of them
[ $(( ${INDEX:-0} + ${DOCSTRIP:-0} + ${IMPACT:-0} + ${VAGUE:-0} + ${GOAL:-0} + ${GOALRW:-0} + $([ -n "${PROMPT_ARM:-}" ] && echo 1 || echo 0) )) -le 1 ] || { echo "CELL REFUSED TO START: more than one of INDEX/DOCSTRIP/IMPACT/VAGUE/GOAL/GOALRW/PROMPT_ARM set" >&2; exit 4; }
if [ "${INDEX:-0}" = "1" ]; then ARM=index; RUN_ID="$RUN_ID-map"; fi
# DOCSTRIP=1: docstring arm (DOCSTRING-ARM.md). Same task, prompt (no preamble), image,
# oracle; every docstring in the repo's non-test source is "" in the base commit, and the
# acceptance tree is stripped by the same script before the agent's patch is applied.
if [ "${DOCSTRIP:-0}" = "1" ]; then ARM=docstrip; RUN_ID="$RUN_ID-doc"; fi
# IMPACT=1: change-impact feedback arm (CHANGE-IMPACT-ARM.md). Same task, image, tree
# (the image's own prepare_tree), oracle; a PostToolUse hook (--settings, root-owned
# /opt/impact) adds a [change-impact] note after any tool call that changed production
# .py files; round 0 = the problem_statement + blank line + impact_preamble.txt (appended since 2026-10-31).
if [ "${IMPACT:-0}" = "1" ]; then ARM=impact; RUN_ID="$RUN_ID-imp"; fi
# VAGUE=1: vague-prompt stress test (user, 2026-11-02). Baseline in every respect (image, tree, oracle,
# blind retry message) except round 0 sends tasks/<id>/prompt_vague.txt (make_vague_prompt.py:
# Clarification example removed, tested Path: lines -> import lines, internal Path: lines removed).
# prompt_vague.json/.diff stay harness-side (they name tested symbols); nothing but mask.patch enters the container.
if [ "${VAGUE:-0}" = "1" ]; then
  [ -s "$TASK_DIR/prompt_vague.txt" ] || { echo "CELL REFUSED TO START: no prompt_vague.txt (run make_vague_prompt.py)" >&2; exit 4; }
  ARM=vague; RUN_ID="$RUN_ID-vague"; PROMPT_SHA=$(sha256sum "$TASK_DIR/prompt_vague.txt" | cut -d" " -f1); fi
# GOAL=1: goal-only prompt stress test (user, 2026-11-03: "no hints for any path ... hide information as much as
# possible, only the goal"). Baseline in every respect except round 0 sends tasks/<id>/prompt_goal.txt
# (make_goal_prompt.py: the dataset's "## Task" statement only, verbatim; NOTE, file-structure block and the whole
# Interface Descriptions section - every path, signature and docstring - removed).
if [ "${GOAL:-0}" = "1" ]; then
  [ -s "$TASK_DIR/prompt_goal.txt" ] || { echo "CELL REFUSED TO START: no prompt_goal.txt (run make_goal_prompt.py)" >&2; exit 4; }
  ARM=goal; RUN_ID="$RUN_ID-goal"; PROMPT_SHA=$(sha256sum "$TASK_DIR/prompt_goal.txt" | cut -d" " -f1); fi
# GOALRW=1: rewritten goal prompt (user, 2026-11-11: "rewrite the prompt with the goal, not too many details where to
# implement, the agent has to find them"). Baseline in every respect except round 0 sends tasks/<id>/prompt_goalrw.txt,
# hand-written by the analyst from the dataset prompt only (never from test.patch): a feature-level goal with no path,
# file, module, class or function name of the masked code. Not a verbatim prefix (unlike GOAL=1).
if [ "${GOALRW:-0}" = "1" ]; then
  [ -s "$TASK_DIR/prompt_goalrw.txt" ] || { echo "CELL REFUSED TO START: no prompt_goalrw.txt" >&2; exit 4; }
  ARM=goalrw; RUN_ID="$RUN_ID-goalrw"; PROMPT_SHA=$(sha256sum "$TASK_DIR/prompt_goalrw.txt" | cut -d" " -f1); fi
# PROMPT_ARM=<name>: generic custom-prompt arm (added 2026-11-24 for prompt reruns, see RUN_NEW_PROMPT.md).
# Baseline in every respect (image, tree, oracle, blind retry message) except round 0 sends
# tasks/<id>/prompt_<name>.txt raw. <name>: lowercase letters, digits, '-'; not an existing arm name.
if [ -n "${PROMPT_ARM:-}" ]; then
  echo "$PROMPT_ARM" | grep -qE '^[a-z0-9][a-z0-9-]{0,23}$' || { echo "CELL REFUSED TO START: PROMPT_ARM must match [a-z0-9][a-z0-9-]*" >&2; exit 4; }
  case "$PROMPT_ARM" in baseline|index|map|docstrip|doc|impact|imp|vague|goal|goalrw) echo "CELL REFUSED TO START: PROMPT_ARM=$PROMPT_ARM is an existing arm name" >&2; exit 4;; esac
  [ -s "$TASK_DIR/prompt_$PROMPT_ARM.txt" ] || { echo "CELL REFUSED TO START: no $TASK_DIR/prompt_$PROMPT_ARM.txt" >&2; exit 4; }
  ARM="$PROMPT_ARM"; RUN_ID="$RUN_ID-$PROMPT_ARM"; PROMPT_SHA=$(sha256sum "$TASK_DIR/prompt_$PROMPT_ARM.txt" | cut -d" " -f1); fi
# Index arm v2 (user decision 2026-10-27 12:36): (appended after the prompt since 2026-10-31, user decision) round 0 = index_preamble.txt + blank
# line + the verbatim problem_statement. The preamble is task-independent; the blind
# message is unchanged. Baseline round 0 stays the problem_statement alone.
PREAMBLE_SHA=""; [ "$ARM" = "index" ] && PREAMBLE_SHA=$(sha256sum "$HERE/index_preamble.txt" | cut -d" " -f1)
IMPACT_PREAMBLE_SHA=""; [ "$ARM" = "impact" ] && IMPACT_PREAMBLE_SHA=$(sha256sum "$HERE/impact_preamble.txt" | cut -d" " -f1)
[ "${INDEX_ONLY:-0}" = "1" ] && RUN_ID="idxdry-$RUN_ID"
# SMOKE_PROMPT=<file>: harness self-test. Round 0 sends that file instead of the task
# prompt and the run lands under runs/smoke-*; never an experiment record.
[ -n "${SMOKE_PROMPT:-}" ] && RUN_ID="smoke-$RUN_ID"
RUN_DIR="$HERE/runs/$RUN_ID"; mkdir -p "$RUN_DIR/rounds" "$RUN_DIR/snapshots"
CONTAINER="fbcell-$(echo "$RUN_ID" | tr -cd 'a-zA-Z0-9_.-' | tail -c 40 | sed 's/^[^a-zA-Z0-9]*//')"

# ---- 1. Fresh container on the internal network, egress through the allowlist ----
docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
CRED_MOUNT=()
[ -n "${CLAUDE_CREDS:-}" ] && CRED_MOUNT=(-v "$(realpath "$CLAUDE_CREDS")":/creds/credentials.json:ro)
docker network inspect hcexp-cellnet   >/dev/null 2>&1 || docker network create --internal hcexp-cellnet >/dev/null
docker network inspect hcexp-egressnet >/dev/null 2>&1 || docker network create hcexp-egressnet >/dev/null
EGRESS_IMAGE="hcexp-egress:2"
if [ "$(docker inspect -f '{{.State.Running}} {{.Config.Image}}' hcexp-egress 2>/dev/null)" != "true $EGRESS_IMAGE" ]; then
  docker rm -f hcexp-egress >/dev/null 2>&1 || true
  docker run -d --name hcexp-egress --network hcexp-cellnet "$EGRESS_IMAGE" >/dev/null
  docker network connect hcexp-egressnet hcexp-egress
  sleep 2
fi
PROXY="http://hcexp-egress:8888"
docker run -d --name "$CONTAINER" \
  --network hcexp-cellnet \
  "${CRED_MOUNT[@]+"${CRED_MOUNT[@]}"}" \
  ${ANTHROPIC_API_KEY:+-e ANTHROPIC_API_KEY} \
  -e HOME=/agent-home \
  -e HTTPS_PROXY="$PROXY" -e HTTP_PROXY="$PROXY" \
  -e https_proxy="$PROXY" -e http_proxy="$PROXY" \
  -e NO_PROXY=localhost,127.0.0.1 -e no_proxy=localhost,127.0.0.1 \
  --workdir /testbed \
  ${AGENT_MEM:+--memory "$AGENT_MEM" --memory-swap "$AGENT_MEM"} \
  "$IMAGE" sleep infinity >/dev/null
trap 'docker rm -f "$CONTAINER" "acc-$CONTAINER" >/dev/null 2>&1 || true' EXIT

AGENT_SHELL='source /opt/miniconda3/etc/profile.d/conda.sh && conda activate testbed && cd /testbed && '

# ---- 2. The benchmark's tree preparation, as root, BEFORE the agent exists -------
docker cp "$TASK_DIR/mask.patch" "$CONTAINER:/tmp/mask.patch"
NAV_SHA=""; NAV_GEN_SHA=""; PREP_SRC="image:/usr/local/bin/prepare_tree"; DOC_SHA=""; DOC_GEN_SHA=""
if [ "$ARM" = docstrip ]; then
  docker cp "$HERE/instruments/prepare_tree.sh" "$CONTAINER:/tmp/prepare_tree"
  docker cp "$HERE/instruments/strip_docstrings.py" "$CONTAINER:/tmp/strip_docstrings.py"
  DOC_GEN_SHA=$(sha256sum "$HERE/instruments/strip_docstrings.py" | cut -d' ' -f1)
  PREP_SRC="host:instruments/prepare_tree.sh@$(sha256sum "$HERE/instruments/prepare_tree.sh" | cut -d' ' -f1)"
  docker exec --user 0:0 -e DOCSTRIP=/tmp/strip_docstrings.py "$CONTAINER" bash /tmp/prepare_tree /tmp/mask.patch "$F2P" "$REPO" \
    > "$RUN_DIR/prepare_tree.log" 2>&1 || {
    echo "prepare_tree (docstring arm) failed (exit $?); see $RUN_DIR/prepare_tree.log" >&2; exit 5; }
  docker exec --user 0:0 "$CONTAINER" rm -f /tmp/prepare_tree /tmp/strip_docstrings.py
  DOC_SHA=$(sed -n 's/^DOCSTRIP_SHA256 //p' "$RUN_DIR/prepare_tree.log" | tail -1)
  [ -n "$DOC_SHA" ] || { echo "docstring arm: stripper printed no DOCSTRIP_SHA256" >&2; exit 5; }
  { grep -q 'equivalence_fail=0' "$RUN_DIR/prepare_tree.log" && ! grep -qE 'equivalence_fail=[1-9]' "$RUN_DIR/prepare_tree.log"; } || { echo "docstring arm: equivalence check failed" >&2; exit 6; }
  [ "${DOCSTRIP_ONLY:-0}" = "1" ] && { echo "DOCSTRIP_ONLY dry run done: $RUN_DIR" >&2; exit 0; }
elif [ "$ARM" = index ]; then
  # the image's prepare_tree predates the index step: use the host copy of the same
  # script (identical apart from the NAV_INDEX block) plus the generator, both copied
  # in and run as root before the agent exists; the generator deletes itself.
  docker cp "$HERE/instruments/prepare_tree.sh" "$CONTAINER:/tmp/prepare_tree"
  docker cp "$HERE/instruments/make_nav_index.py" "$CONTAINER:/tmp/make_nav_index.py"
  NAV_GEN_SHA=$(sha256sum "$HERE/instruments/make_nav_index.py" | cut -d' ' -f1)
  PREP_SRC="host:instruments/prepare_tree.sh@$(sha256sum "$HERE/instruments/prepare_tree.sh" | cut -d' ' -f1)"
  docker exec --user 0:0 -e NAV_INDEX=/tmp/make_nav_index.py "$CONTAINER" bash /tmp/prepare_tree /tmp/mask.patch "$F2P" "$REPO" \
    > "$RUN_DIR/prepare_tree.log" 2>&1 || {
    echo "prepare_tree (index arm) failed (exit $?); see $RUN_DIR/prepare_tree.log" >&2; exit 5; }
  docker exec --user 0:0 "$CONTAINER" rm -f /tmp/prepare_tree /tmp/make_nav_index.py
  NAV_SHA=$(sed -n 's/^NAV_INDEX_SHA256 //p' "$RUN_DIR/prepare_tree.log" | tail -1)
  [ -n "$NAV_SHA" ] || { echo "index arm: generator printed no NAV_INDEX_SHA256" >&2; exit 5; }
else
  docker exec --user 0:0 "$CONTAINER" prepare_tree /tmp/mask.patch "$F2P" "$REPO" \
    > "$RUN_DIR/prepare_tree.log" 2>&1 || {
    echo "prepare_tree failed (exit $?); see $RUN_DIR/prepare_tree.log" >&2; exit 5; }
fi
BASE_TREE=$(sed -n 's/^BASE_TREE //p' "$RUN_DIR/prepare_tree.log" | tail -1)
IMPACT_GRAPH_SHA=""; IMPACT_HOOK_SHA=""; IMPACT_SETTINGS_SHA=""
if [ "$ARM" = impact ]; then
  # ---- 2a. change-impact hook, installed as root BEFORE the agent exists (exit 6) -----
  # /opt/impact (root-owned, read-only to uid 1000) holds the hook, the call graph of the
  # masked tree and the settings file passed with --settings; HOME stays empty.
  IMPACT_HOOK_SHA=$(sha256sum "$HERE/instruments/impact_hook.py" | cut -d' ' -f1)
  printf '%s\n' '{"hooks":{"PostToolUse":[{"matcher":"Edit|Write|MultiEdit|NotebookEdit|Bash","hooks":[{"type":"command","command":"python3 -I /opt/impact/hook.py hook","timeout":60}]}],"PostToolUseFailure":[{"matcher":"Edit|Write|MultiEdit|NotebookEdit|Bash","hooks":[{"type":"command","command":"python3 -I /opt/impact/hook.py hook","timeout":60}]}]}}' > "$RUN_DIR/impact_settings.json"
  IMPACT_SETTINGS_SHA=$(sha256sum "$RUN_DIR/impact_settings.json" | cut -d' ' -f1)
  docker exec --user 0:0 "$CONTAINER" mkdir -p /opt/impact
  docker cp "$HERE/instruments/impact_hook.py" "$CONTAINER:/opt/impact/hook.py"
  docker cp "$RUN_DIR/impact_settings.json" "$CONTAINER:/opt/impact/settings.json"
  docker exec --user 0:0 "$CONTAINER" bash -c "$AGENT_SHELL"'python3 -I /opt/impact/hook.py build /testbed /opt/impact/graph.json && chown -R 0:0 /opt/impact && chmod 755 /opt/impact && chmod 644 /opt/impact/*' \
    > "$RUN_DIR/impact_build.log" 2>&1 || { echo "change-impact graph build failed; see $RUN_DIR/impact_build.log" >&2; exit 6; }
  IMPACT_GRAPH_SHA=$(sed -n 's/^IMPACT_GRAPH_SHA256 //p' "$RUN_DIR/impact_build.log" | tail -1)
  WANT=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['graph_sha256'])" "$IMPACT_GATE")
  [ "$IMPACT_GRAPH_SHA" = "$WANT" ] || { echo "change-impact graph sha $IMPACT_GRAPH_SHA != gated $WANT (tree differs from the gated masked tree)" >&2; exit 6; }
  # in-container gate A: no edit yet -> the hook must say nothing; its scratch state is discarded
  GA=$(docker exec --user 1000:1000 "$CONTAINER" bash -c "$AGENT_SHELL"'python3 -I /opt/impact/hook.py note /testbed /opt/impact/graph.json /tmp/.impact-gateA; rm -rf /tmp/.impact-gateA')
  [ -z "$GA" ] || { echo "change-impact gate A FAIL: note on the untouched tree: $GA" >&2; exit 6; }
  echo "  impact arm: graph $IMPACT_GRAPH_SHA (= gated), $(sed -n 's/^IMPACT_GRAPH_SUMMARY //p' "$RUN_DIR/impact_build.log"); gate A empty" >&2
fi
BASE_COMMIT=$(docker exec --user 1000:1000 "$CONTAINER" git -C /testbed rev-parse HEAD)
if [ "$ARM" = index ]; then
  # ---- 2b. index-arm leak audit, BEFORE the agent exists (exit 6 on FAIL) ----------
  # The index as the agent will see it is copied out (runs/<id>/nav_index/) and checked
  # against mask.patch and test.patch: no mask-removed def/class listed for its file,
  # no hidden test name, no hidden test path; and it must be tracked in the base commit.
  mkdir -p "$RUN_DIR/nav_index"
  docker cp "$CONTAINER:/testbed/CODE_MAP.md" "$RUN_DIR/nav_index/CODE_MAP.md"
  # every def/class line still in the MASKED tree, for the files the mask touched (audit input)
  sed -n 's#^--- a/##p' "$TASK_DIR/mask.patch" | sort -u | docker exec -i --user 1000:1000 "$CONTAINER" bash -c '
    cd /testbed && while read -r f; do [ -f "$f" ] || continue
      grep -nE "^\s*(async\s+)?(def|class)\s+[A-Za-z_][A-Za-z0-9_]*" "$f" | sed -E "s/^([0-9]+):\s*(async\s+)?(def|class)\s+([A-Za-z_][A-Za-z0-9_]*).*/$(printf "%s" "$f" | sed "s#/#\\\\/#g")\t\1\t\4/"; done' \
    > "$RUN_DIR/nav_index/masked_defs.txt"
  docker exec --user 1000:1000 "$CONTAINER" bash -c 'cd /testbed && echo "tracked_in_base_commit $(git ls-tree -r --name-only HEAD -- CODE_MAP.md | wc -l) files; status: $(git status --porcelain | wc -l) lines"' \
    > "$RUN_DIR/nav_index/git_check.txt"
  if ! python3 "$HERE/nav_audit.py" "$RUN_DIR/nav_index" "$TASK_DIR/mask.patch" "$TASK_DIR/test.patch" "$F2P" > "$RUN_DIR/nav_audit.json"; then
    echo "CELL REFUSED TO START: index leak audit FAIL, see $RUN_DIR/nav_audit.json" >&2; exit 6; fi
  grep -q 'status: 0 lines' "$RUN_DIR/nav_index/git_check.txt" || { echo "index not clean in base commit: $(cat "$RUN_DIR/nav_index/git_check.txt")" >&2; exit 6; }
  NAV_N=$(sed -n 's/^NAV_INDEX_FILES \([0-9]*\).*/\1/p' "$RUN_DIR/prepare_tree.log" | tail -1)
  grep -q "tracked_in_base_commit $NAV_N files" "$RUN_DIR/nav_index/git_check.txt" || { echo "index files tracked != generated ($NAV_N): $(cat "$RUN_DIR/nav_index/git_check.txt") -- gitignored?" >&2; exit 6; }
  echo "  index arm: $(cat "$RUN_DIR/nav_index/git_check.txt"); audit PASS; sha $NAV_SHA" >&2
  if [ "${INDEX_ONLY:-0}" = "1" ]; then   # verifier 4 finding 4: dry runs record the generator sha too
    echo "nav_generator_sha256 $(sha256sum "$HERE/instruments/make_nav_index.py" | cut -d' ' -f1)" > "$RUN_DIR/dryrun_generator.txt"
    echo "INDEX_ONLY dry run done: $RUN_DIR" >&2; exit 0; fi
fi
if [ -n "${CLAUDE_CREDS:-}" ]; then
  docker exec --user 1000:1000 "$CONTAINER" bash -c \
    'mkdir -p "$HOME/.claude" && cp /creds/credentials.json "$HOME/.claude/.credentials.json" && chmod 600 "$HOME/.claude/.credentials.json"'
fi
CLI_VERSION=$(docker exec --user 1000:1000 "$CONTAINER" claude --version 2>/dev/null | tr -d '\r')
[ -n "$CLI_VERSION" ] || { echo "claude not runnable in $IMAGE" >&2; exit 1; }

# The agent is launched the way the benchmark's own runner launches it: conda env
# `testbed` active, cwd /testbed. AGENT_SHELL is the one launch path used for the
# attestation and for every round, so what is attested is what ran.
# (AGENT_SHELL is defined before step 2: the change-impact graph is built with the same python)

# ---- 2b. Isolation attestation, recorded BEFORE the agent runs -------------------
docker exec --user 1000:1000 "$CONTAINER" bash -c "$AGENT_SHELL"'
  echo "== whoami ==";        id
  echo "== HOME ==";          echo "$HOME"
  echo "== find \$HOME ==";   find "$HOME" -maxdepth 3 2>/dev/null | sort
  echo "== python/pytest on PATH =="; command -v python; python --version 2>&1; command -v pytest
  echo "== env (claude/anthropic/conda names; HOME and proxy values) =="
  env | grep -iE "claude|anthropic|conda" | sed "s/=.*/=<redacted>/" | sort
  env | grep -E "^(HOME|HTTPS_PROXY|HTTP_PROXY|NO_PROXY|https_proxy|http_proxy|no_proxy)=" | sort
  echo "== instruction files on the search path (a repo-shipped one is part of the as-is codebase, recorded not removed) =="
  for d in / /testbed /agent-home; do for f in CLAUDE.md AGENTS.md .mcp.json; do [ -e "$d/$f" ] && echo "PRESENT $d/$f" || echo "absent  $d/$f"; done; done
  find /testbed \( -iname "CLAUDE.md" -o -iname "AGENTS.md" -o -iname ".claude" -o -iname ".mcp.json" -o -iname ".claude.json" \) 2>/dev/null | sed "s/^/  repo-shipped: /"
  echo "  (find done)"
  echo "== hidden test file absent =="
  [ -e "/testbed/'"$F2P"'" ] && echo "PRESENT /testbed/'"$F2P"'" || echo "absent  /testbed/'"$F2P"'"
  echo "== mask patch / pristine copy absent =="
  ls -la /tmp/mask.patch /root/my_repo 2>&1 | head -3
  echo "== git history visible to the agent =="
  git -C /testbed log --oneline | head -3; git -C /testbed status --porcelain | head -3
  echo "== mounts =="
  grep -E " /testbed| /creds| /agent-home" /proc/self/mountinfo | awk "{print \$5, \$6}"
  echo "== egress (only the model API may answer) =="
  for h in api.anthropic.com platform.claude.com github.com pypi.org raw.githubusercontent.com; do
    c=$(timeout 12 curl -s -o /dev/null -w "%{http_code}" "https://$h/" 2>/dev/null); [ -n "$c" ] || c=000
    echo "  $h -> $c"
  done
' > "$RUN_DIR/isolation.txt" 2>&1 || true
# the pristine copy lives under /root, unreadable to uid 1000; its absence is attested as root
docker exec --user 0:0 "$CONTAINER" bash -c '
  echo "== as root: pristine copy and mask patch gone =="
  [ -e /root/my_repo ] && echo "PRESENT /root/my_repo" || echo "absent  /root/my_repo"
  [ -e /tmp/mask.patch ] && echo "PRESENT /tmp/mask.patch" || echo "absent  /tmp/mask.patch"
  echo "== as root: nothing claude-related under /root =="; ls -a /root | tr "\n" " "; echo
  echo "== as root: package caches (cleared by prepare_tree) =="; du -sh /opt/miniconda3/pkgs /root/.cache/pip /root/.cache/uv 2>&1 | head -4' >> "$RUN_DIR/isolation.txt" 2>&1 || true
{ echo "== arm =="; echo "arm $ARM"
  if [ "$ARM" = index ]; then
    echo "navigation index in base commit: NAV_INDEX_SHA256 $NAV_SHA (generator sha256 $NAV_GEN_SHA, $(cat "$RUN_DIR/nav_index/git_check.txt"))"
    echo "leak audit: $(python3 -c "import json,sys;j=json.load(open(sys.argv[1]));print(j['verdict'],'removed_defs_checked',j['removed_defs_checked'],'found',len(j['removed_defs_found_in_index']),'hidden_test_names_checked',j['hidden_test_names_checked'],'found',len(j['hidden_test_names_found']),'f2p_path_found',j['f2p_path_found'])" "$RUN_DIR/nav_audit.json")"
    echo "generator and prepare script removed from container: $(docker exec --user 0:0 "$CONTAINER" bash -c '[ -e /tmp/make_nav_index.py ] || [ -e /tmp/prepare_tree ] && echo PRESENT || echo absent')"
  fi
  if [ "$ARM" = impact ]; then
    echo "change-impact hook: settings $IMPACT_SETTINGS_SHA (--settings /opt/impact/settings.json; the only settings file), hook $IMPACT_HOOK_SHA, graph $IMPACT_GRAPH_SHA (= offline gate), preamble $IMPACT_PREAMBLE_SHA"
    echo "offline gate: $(python3 -c "import json,sys;g=json.load(open(sys.argv[1]));print(g['gate_verdict'],'hidden_test_names_checked',g['gate_B_hidden_test_names_checked'],'found',len(g['gate_B_hidden_test_names_found']),'f2p_path_found',g['gate_B_f2p_path_found'])" "$IMPACT_GATE")"
    echo "/opt/impact as the agent sees it: $(docker exec --user 1000:1000 "$CONTAINER" bash -c 'ls -ln /opt/impact | tail -n +2 | awk "{print \$1, \$3, \$9}" | tr "\n" ";"; touch /opt/impact/x 2>/dev/null && echo WRITABLE || echo read-only')"
  fi
  if [ "$ARM" = docstrip ]; then
    echo "docstrings stripped in base commit: $(grep '^DOCSTRIP_SUMMARY' "$RUN_DIR/prepare_tree.log") DOCSTRIP_SHA256 $DOC_SHA (stripper sha256 $DOC_GEN_SHA)"
    echo "stripper and prepare script removed from container: $(docker exec --user 0:0 "$CONTAINER" bash -c '[ -e /tmp/strip_docstrings.py ] || [ -e /tmp/prepare_tree ] && echo PRESENT || echo absent')"
    echo "no unstripped source copy reachable: $(docker exec --user 0:0 "$CONTAINER" bash -c 'ls -d /root/my_repo /testbed/libs/skinny/mlflow /testbed/libs/tracing/mlflow 2>/dev/null | tr "\n" " "; find /testbed -xdev -name "*.pyc" 2>/dev/null | head -1; ls -d /opt/miniconda3/envs/*/lib/python3*/site-packages/'"${REPO#*/}"' 2>/dev/null | grep -v /envs/testbed/; echo "(empty = none)"')"
  fi; } >> "$RUN_DIR/isolation.txt" 2>&1 || true

cp "$TASK_DIR/prompt.txt" "$RUN_DIR/task.md"
if [ "$ARM" = vague ]; then cp "$TASK_DIR/prompt_vague.txt" "$RUN_DIR/task.md"; fi
if [ "$ARM" = goal ]; then cp "$TASK_DIR/prompt_goal.txt" "$RUN_DIR/task.md"; fi
if [ -n "${PROMPT_ARM:-}" ]; then cp "$TASK_DIR/prompt_$PROMPT_ARM.txt" "$RUN_DIR/task.md"; fi
cp "$TASK_DIR/meta.json" "$RUN_DIR/task_meta.json"
python3 - "$RUN_DIR/manifest.json" <<PY
import json, sys
json.dump({"run_id": "$RUN_ID", "instance_id": "$IID", "task": "$SHORT", "seed": "$SEED",
           "repo": "$REPO", "image": "$IMAGE", "base_image": "$IMAGE_NAME",
           "cli_version": "$CLI_VERSION", "model_requested": "$MODEL", "effort": "${EFFORT:-default}",
           "harness_version": "$HARNESS_VERSION", "protocol": "run-to-acceptance",
           "feedback": "$FEEDBACK", "session_id": "$SESSION_ID",
           "prompt_sha256": "$PROMPT_SHA", "index_preamble_sha256": "$PREAMBLE_SHA", "mask_sha256": "$MASK_SHA",
           "acceptance": "F2P file exit 0 in a fresh container decides (stop rule 2026-10-31); every P2P file also run and reported",
           "f2p": "$F2P", "p2p": "$P2P".split(),
           "max_rounds": $MAX_ROUNDS, "max_usd": $MAX_USD, "stall_rounds": $STALL_ROUNDS,
           "agent_uid": 1000, "egress": "allowlist:api.anthropic.com,statsig.anthropic.com,console.anthropic.com,platform.claude.com",
           "egress_image": "$EGRESS_IMAGE", "base_tree": "$BASE_TREE", "base_commit": "$BASE_COMMIT",
           "image_id": "$(docker image inspect --format '{{.Id}}' "$IMAGE")",
           "arm": "$ARM", "agent_mem_cap": "${AGENT_MEM:-none}", "docstrip_sha256": "$DOC_SHA", "docstrip_script_sha256": "$DOC_GEN_SHA", "nav_index_sha256": "$NAV_SHA", "nav_generator_sha256": "$NAV_GEN_SHA", "prepare_tree_source": "$PREP_SRC",
           "impact_preamble_sha256": "$IMPACT_PREAMBLE_SHA", "impact_hook_sha256": "$IMPACT_HOOK_SHA", "impact_graph_sha256": "$IMPACT_GRAPH_SHA", "impact_settings_sha256": "$IMPACT_SETTINGS_SHA",
           "started": "$(date -Iseconds)"}, open(sys.argv[1], "w"), indent=2)
PY

# ---- helpers -----------------------------------------------------------------------
# snapshot: the agent's deliverable is its DIFF, built the way the benchmark builds it
# (complete_runtime: git add -A, diff --cached against the baseline commit, binary
# diffs dropped) -- but on a TEMPORARY index so the agent's own index and status are
# never touched between rounds.
snapshot () {   # snapshot <round-dir>
  docker exec --user 1000:1000 -e BASE_COMMIT="$BASE_COMMIT" -e ARM="$ARM" "$CONTAINER" bash -c '
    cd /testbed && export GIT_INDEX_FILE=/tmp/.fbsnap.index && rm -f "$GIT_INDEX_FILE"
    git read-tree "$BASE_COMMIT" && git add -A
    # index arm: the navigation index is not part of the deliverable (the acceptance tree
    # has none), so edits/deletions of it are excluded from the diff and recorded instead
    EXCL=(); if [ "$ARM" = index ]; then EXCL=(-- . ":(exclude)CODE_MAP.md")
      git diff --cached --no-color --name-status "$BASE_COMMIT" -- CODE_MAP.md > /tmp/.fbsnap.index_touched; fi
    git diff --cached --no-color --stat "$BASE_COMMIT" "${EXCL[@]}" > /tmp/.fbsnap.stat
    git diff --cached --no-color --name-status "$BASE_COMMIT" "${EXCL[@]}" > /tmp/.fbsnap.names
    git diff --cached --no-color "$BASE_COMMIT" "${EXCL[@]}"; echo "@@TREE $(git write-tree)" >&2' \
    > "$1/diff.raw" 2> "$1/snapshot.stderr" || true
  python3 - "$1" <<'PY'
import pathlib, sys
rd = pathlib.Path(sys.argv[1]); raw = (rd / "diff.raw").read_text(errors="replace")
# featurebench/infer/runtime.py _remove_binary_diffs, verbatim logic
had_nl = raw.endswith("\n"); out = []; skip = False
for line in raw.split("\n"):
    if line.startswith("diff --git"): skip = False
    if "Binary files" in line or "GIT binary patch" in line:
        while out and not out[-1].startswith("diff --git"): out.pop()
        if out and out[-1].startswith("diff --git"): out.pop()
        skip = True; continue
    if not skip: out.append(line)
txt = "\n".join(out)
if had_nl and not txt.endswith("\n"): txt += "\n"
(rd / "diff.patch").write_text(txt)
PY
  docker exec --user 1000:1000 "$CONTAINER" bash -c 'cat /tmp/.fbsnap.stat; echo ---; cat /tmp/.fbsnap.names' \
    | awk -v rd="$1" 'BEGIN{f=rd"/diff.stat"} /^---$/{f=rd"/files_touched.txt"; next} {print > f}' || true
  touch "$1/diff.stat" "$1/files_touched.txt"
  [ "$ARM" = index ] && docker exec --user 1000:1000 "$CONTAINER" cat /tmp/.fbsnap.index_touched > "$1/index_touched.txt" 2>/dev/null
  sed -n 's/^@@TREE //p' "$1/snapshot.stderr" | tail -1 > "$1/tree"
}
integrity () { # integrity <round-dir> -> count on stdout
  python3 "$HERE/test_integrity.py" "$1/diff.patch" > "$1/test_integrity.json"
  python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['total'])" "$1/test_integrity.json"
}
run_accept () { # run_accept <round-dir> -> PASS|FAIL|ERROR ; outputs in <round-dir>/accept
  local rd="$1" acc="acc-$CONTAINER"
  docker rm -f "$acc" >/dev/null 2>&1 || true
  docker run -d --name "$acc" --network none "$IMAGE" sleep infinity >/dev/null
  docker cp "$TASK_DIR/mask.patch" "$acc:/tmp/mask.patch"
  docker cp "$TASK_DIR/test.patch" "$acc:/tmp/test.patch"
  docker cp "$rd/diff.patch"       "$acc:/tmp/agent.patch"
  local ACC_BIN=accept_in_container ACC_ENV=()
  if [ "$ARM" = docstrip ]; then
    docker cp "$HERE/instruments/accept_in_container.sh" "$acc:/tmp/accept_in_container"
    docker cp "$HERE/instruments/strip_docstrings.py" "$acc:/tmp/strip_docstrings.py"
    ACC_BIN="bash /tmp/accept_in_container"; ACC_ENV=(-e DOCSTRIP=/tmp/strip_docstrings.py)
  fi
  set +e
  docker exec --user 0:0 "${ACC_ENV[@]+"${ACC_ENV[@]}"}" "$acc" $ACC_BIN /tmp/mask.patch /tmp/test.patch /tmp/agent.patch \
      "$F2P" "$REPO" "$TEST_CMD" "$T_ONE" "$T_RUN" /tmp/accept_out $P2P > "$rd/accept.stdout" 2>&1
  local rc=$?
  set -e
  docker cp "$acc:/tmp/accept_out" "$rd/accept" >/dev/null 2>&1 || true
  docker rm -f "$acc" >/dev/null 2>&1 || true
  echo "$rc" > "$rd/accept_exit"
  grep -a '^ACCEPT SUMMARY' "$rd/accept.stdout" | tail -1 > "$rd/accept/VERDICT.txt" 2>/dev/null || true
  case "$rc" in 0) echo PASS ;; 1) echo FAIL ;; *) echo ERROR ;; esac
}
usd_so_far () { python3 "$HERE/cell_cost.py" "$RUN_DIR" 2>/dev/null || echo 0; }
over_cap () { python3 -c "import sys;sys.exit(0 if float('$MAX_USD')>0 and float('$1')>=float('$MAX_USD') else 1)"; }

# ---- 3. The run-to-acceptance loop ---------------------------------------------------
START_NS=$(date +%s%N)
ROUND=0; BLIND=0; AGENT_UNAVAILABLE=0; STALL=0; TREE_PREV=""
VERDICT="unknown"; STOP_REASON=""; ACCEPT_ROUND=""
: > "$RUN_DIR/rounds.tsv"
printf 'round\tkind\taccept\tf2p\tp2p\ttest_integrity\tcum_usd\twall_ms\n' >> "$RUN_DIR/rounds.tsv"
EFFORT_ARGS=(); [ -n "$EFFORT" ] && EFFORT_ARGS=(--effort "$EFFORT")
ARM_ARGS=""; [ "$ARM" = impact ] && ARM_ARGS="--settings /opt/impact/settings.json"

while : ; do
  RD="$RUN_DIR/rounds/$(printf 'r%02d' "$ROUND")"; mkdir -p "$RD"
  if [ "$ROUND" -eq 0 ]; then
    KIND=task; PROMPT_FILE="${SMOKE_PROMPT:-$TASK_DIR/prompt.txt}"; CLI_ARGS=(--session-id "$SESSION_ID")
    if [ "$ARM" = "index" ] && [ -z "${SMOKE_PROMPT:-}" ]; then
      { cat "$TASK_DIR/prompt.txt"; printf '\n'; cat "$HERE/index_preamble.txt"; } > "$RUN_DIR/prompt_r0.txt"
      PROMPT_FILE="$RUN_DIR/prompt_r0.txt"
      sha256sum "$RUN_DIR/prompt_r0.txt" | cut -d' ' -f1 > "$RUN_DIR/prompt_r0.sha256"  # hash of the bytes actually sent
    fi
    if [ "$ARM" = "vague" ] && [ -z "${SMOKE_PROMPT:-}" ]; then
      PROMPT_FILE="$TASK_DIR/prompt_vague.txt"
      sha256sum "$PROMPT_FILE" | cut -d' ' -f1 > "$RUN_DIR/prompt_r0.sha256"
    fi
    if [ "$ARM" = "goal" ] && [ -z "${SMOKE_PROMPT:-}" ]; then
      PROMPT_FILE="$TASK_DIR/prompt_goal.txt"
      sha256sum "$PROMPT_FILE" | cut -d' ' -f1 > "$RUN_DIR/prompt_r0.sha256"
    fi
    if [ "$ARM" = "goalrw" ] && [ -z "${SMOKE_PROMPT:-}" ]; then
      PROMPT_FILE="$TASK_DIR/prompt_goalrw.txt"
      sha256sum "$PROMPT_FILE" | cut -d' ' -f1 > "$RUN_DIR/prompt_r0.sha256"
    fi
    if [ -n "${PROMPT_ARM:-}" ] && [ -z "${SMOKE_PROMPT:-}" ]; then
      PROMPT_FILE="$TASK_DIR/prompt_$PROMPT_ARM.txt"
      sha256sum "$PROMPT_FILE" | cut -d' ' -f1 > "$RUN_DIR/prompt_r0.sha256"
    fi
    if [ "$ARM" = "impact" ] && [ -z "${SMOKE_PROMPT:-}" ]; then
      { cat "$TASK_DIR/prompt.txt"; printf '\n'; cat "$HERE/impact_preamble.txt"; } > "$RUN_DIR/prompt_r0.txt"
      PROMPT_FILE="$RUN_DIR/prompt_r0.txt"
      sha256sum "$RUN_DIR/prompt_r0.txt" | cut -d' ' -f1 > "$RUN_DIR/prompt_r0.sha256"
    fi
    if [ "$ARM" = "impact" ]; then                       # round number for the hook log (root-written, read-only to the agent)
      docker exec --user 0:0 "$CONTAINER" bash -c "echo $ROUND > /opt/impact/round && chmod 644 /opt/impact/round"
    fi
  else
    KIND=blind; PROMPT_FILE="$HERE/blind_msg.txt"; CLI_ARGS=(--resume "$SESSION_ID")
    if [ "$ARM" = "impact" ]; then docker exec --user 0:0 "$CONTAINER" bash -c "echo $ROUND > /opt/impact/round"; fi
  fi
  echo "$KIND" > "$RD/kind"; cp -f "$PROMPT_FILE" "$RD/prompt.txt"

  R_START=$(date +%s%N)
  set +e
  docker exec -i --user 1000:1000 "$CONTAINER" bash -c \
    "$AGENT_SHELL claude -p \"\$(cat /dev/stdin)\" \
       --model $MODEL ${CLI_ARGS[*]} ${EFFORT_ARGS[*]+${EFFORT_ARGS[*]}} \
       --strict-mcp-config --mcp-config '{\"mcpServers\":{}}' \
       --output-format stream-json --verbose \
       --disallowedTools WebSearch WebFetch $ARM_ARGS \
       --dangerously-skip-permissions" \
    < "$PROMPT_FILE" > "$RD/transcript.jsonl" 2> "$RD/agent.stderr"
  R_EXIT=$?
  set -e
  R_END=$(date +%s%N)
  echo "$R_EXIT" > "$RD/agent_exit"
  WALL=$(( (R_END - R_START) / 1000000 )); echo "$WALL" > "$RD/wall_ms"

  if ! grep -qa '"type":"result"' "$RD/transcript.jsonl" 2>/dev/null; then
    VERDICT="session_broken"; STOP_REASON="no result event in round $ROUND (session lost; cell invalid)"; break
  fi
  AERR=$(python3 -c "
import sys; sys.path.insert(0, '$HERE')
from roundcost import final_result
r = final_result('$RD/transcript.jsonl') or {}
print('1' if r.get('is_error') else '0')
print((str(r.get('result') or '')[:200]).replace(chr(10), ' '))
" 2>/dev/null || printf '0\n')
  if [ "$(printf '%s' "$AERR" | head -1)" = "1" ]; then
    printf '%s' "$AERR" | tail -n +2 > "$RD/agent_error.txt"
    VERDICT="agent_unavailable"; STOP_REASON="round $ROUND returned an error result: $(cat "$RD/agent_error.txt")"
    echo "AGENT UNAVAILABLE: $STOP_REASON" >&2; AGENT_UNAVAILABLE=1; break
  fi

  snapshot "$RD"
  TI=$(integrity "$RD" 2>/dev/null || echo -1)
  TREE_NOW=$(cat "$RD/tree" 2>/dev/null || echo none)
  if [ "$ROUND" -gt 0 ] && [ "$TREE_NOW" = "${TREE_PREV:-}" ]; then STALL=$((STALL+1)); else STALL=0; fi
  TREE_PREV="$TREE_NOW"
  cp -f "$RD/diff.patch" "$RUN_DIR/snapshots/$(printf 'r%02d' "$ROUND")-${KIND}.diff.patch"

  ACC=$(run_accept "$RD")
  echo "$ACC" > "$RD/accept_result"
  F2PR=$(sed -nE 's/.*f2p=([A-Z]+).*/\1/p' "$RD/accept/VERDICT.txt" 2>/dev/null | tail -1); F2PR="${F2PR:--}"
  P2PR=$(sed -nE 's/.*p2p=([A-Z]+).*/\1/p' "$RD/accept/VERDICT.txt" 2>/dev/null | tail -1); P2PR="${P2PR:--}"
  # stop rule (user decision 2026-10-31): the hidden feature tests (F2P) alone decide; the P2P
  # result stays in rounds.tsv and accept_final.txt, is reported, and does not extend the loop.
  [ "$ACC" = FAIL ] && [ "$F2PR" = PASS ] && { ACC=PASS; echo "$ACC" > "$RD/accept_result"; }
  SPENT=$(usd_so_far)
  printf '%d\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$ROUND" "$KIND" "$ACC" "$F2PR" "$P2PR" "$TI" "$SPENT" "$WALL" >> "$RUN_DIR/rounds.tsv"
  echo "round $ROUND ($KIND): accept=$ACC f2p=$F2PR p2p=$P2PR integrity=$TI cum=\$$SPENT wall=${WALL}ms  $(cat "$RD/accept/VERDICT.txt" 2>/dev/null)"

  if [ "$ACC" = PASS ]; then VERDICT="converged"; STOP_REASON="acceptance passed"; ACCEPT_ROUND="$ROUND"; break; fi
  if [ "$ACC" = ERROR ]; then VERDICT="acceptance_error"; STOP_REASON="acceptance check could not run (exit $(cat "$RD/accept_exit"))"; break; fi
  if over_cap "$SPENT"; then VERDICT="did_not_converge"; STOP_REASON="cost cap (\$$SPENT >= \$$MAX_USD)"; break; fi
  if [ "$STALL_ROUNDS" -gt 0 ] && [ "$STALL" -ge "$STALL_ROUNDS" ]; then
    VERDICT="did_not_converge"; STOP_REASON="stalled: tree unchanged for $STALL consecutive rounds"; break; fi
  if [ "$MAX_ROUNDS" -gt 0 ] && [ "$BLIND" -ge "$MAX_ROUNDS" ]; then
    VERDICT="did_not_converge"; STOP_REASON="blind-round cap ($MAX_ROUNDS)"; break; fi
  BLIND=$((BLIND+1)); ROUND=$((ROUND+1))
done
END_NS=$(date +%s%N)

# ---- 3a. The session store (the CLI's own record of the session) -------------------
# NOTE: in -p mode the CLI redacts thinking TEXT everywhere (stream-json, session
# store, partial deltas; verified on 2.1.310). Only thinking_tokens are measurable.
# The session file under $HOME/.claude/projects/ is still copied out BEFORE the
# container is removed (it holds the exact first user message = the prompt);
# only projects/ is taken, never the credential beside it.
docker cp "$CONTAINER:/agent-home/.claude/projects" "$RUN_DIR/session" >/dev/null 2>&1 \
  || echo "  note: no session store found in the container" >&2
# change-impact arm: the hook's own log (every trigger: tool, note shown, errors) and state
if [ "$ARM" = impact ]; then
  docker cp "$CONTAINER:/tmp/.impact" "$RUN_DIR/impact" >/dev/null 2>&1 || echo "  note: no change-impact log (hook never fired)" >&2
fi
find "$RUN_DIR/session" -name '*.jsonl' -exec sh -c 'grep -l "sk-ant\|accessToken" "$1" >/dev/null 2>&1 && echo "WARNING: credential-like string in $1"' _ {} \; 2>/dev/null || true

# ---- 3b. INVALID CELL: the agent was never reached ---------------------------------
if [ "$AGENT_UNAVAILABLE" = "1" ]; then
  python3 - "$RUN_DIR/manifest.json" <<PY
import json, sys
p = sys.argv[1]; m = json.load(open(p))
m.update(finished="$(date -Iseconds)", wall_ms=$(( (END_NS - START_NS) / 1000000 )),
         verdict="agent_unavailable", stop_reason="""$STOP_REASON""",
         rounds_used=$ROUND, blind_rounds=$BLIND, converged=False, accept=None, valid=False,
         cost_layers={"attempt1_oneshot": None, "to_acceptance": None},
         note="INVALID CELL: a round returned an error result (quota/session limit). "
              "Exclude from every analysis; do not restart as if continuous.")
json.dump(m, open(p, "w"), indent=2)
PY
  echo "  cell is INVALID (agent unavailable) -- not an outcome" >&2; exit 3
fi

# ---- 4. Cost layers + assembly ------------------------------------------------------
COST_ATTEMPT1=$(python3 "$HERE/cell_cost.py" "$RUN_DIR" 0)
COST_TOTAL=$(usd_so_far)
LAST="$RUN_DIR/rounds/$(printf 'r%02d' "$ROUND")"
cat "$RUN_DIR"/rounds/r*/transcript.jsonl > "$RUN_DIR/transcript.jsonl"
cp -f "$LAST/diff.patch" "$RUN_DIR/diff.patch"; cp -f "$LAST/diff.patch" "$RUN_DIR/snapshots/final.diff.patch"
cp -f "$LAST/diff.stat" "$RUN_DIR/diff.stat"; cp -f "$LAST/files_touched.txt" "$RUN_DIR/files_touched.txt"
cp -f "$RUN_DIR/rounds/r00/transcript.jsonl" "$RUN_DIR/attempt1.transcript.jsonl"
cp -f "$RUN_DIR/rounds/r00/diff.patch" "$RUN_DIR/attempt1.diff.patch"
[ -f "$LAST/accept/VERDICT.txt" ] && cp -f "$LAST/accept/VERDICT.txt" "$RUN_DIR/accept_final.txt"
[ -d "$LAST/accept" ] && rm -rf "$RUN_DIR/accept" && cp -r "$LAST/accept" "$RUN_DIR/accept"

python3 - "$RUN_DIR/manifest.json" <<PY
import json, sys
p = sys.argv[1]; m = json.load(open(p))
def f(x):
    try: return float(x)
    except Exception: return None
m.update(finished="$(date -Iseconds)", wall_ms=$(( (END_NS - START_NS) / 1000000 )),
         verdict="$VERDICT", stop_reason="""$STOP_REASON""",
         rounds_used=$((ROUND+1)), blind_rounds=$BLIND,
         acceptance_round=${ACCEPT_ROUND:-None},
         converged=("$VERDICT" == "converged"),
         accept=("PASS" if "$VERDICT" == "converged" else "FAIL"),
         valid=True,
         cost_layers={"attempt1_oneshot": f("$COST_ATTEMPT1"), "to_acceptance": f("$COST_TOTAL")})
try: m["prompt_r0_sha256"] = open("$RUN_DIR/prompt_r0.sha256").read().strip()   # index/impact arms: bytes actually sent
except OSError: pass
json.dump(m, open(p, "w"), indent=2)
PY
python3 "$HERE/collect_metrics.py" "$RUN_DIR" || true
echo "cell complete: $RUN_DIR"
echo "  verdict=$VERDICT  rounds=$((ROUND+1))  blind_rounds=$BLIND  \$$COST_TOTAL"

# ---- 5. Existing-feature regression, once, after the feature is fully in -------------
if [ "$VERDICT" = converged ] && [ "$REGRESS" = 1 ]; then
  "$HERE/run_regress.sh" "$RUN_DIR" || echo "  regression check failed to run; rerun ./run_regress.sh $RUN_DIR" >&2
fi
