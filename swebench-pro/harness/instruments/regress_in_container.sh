#!/bin/bash
# regress_in_container.sh <label> - runs as root in a FRESH --network none container from the PRISTINE V2 image.
# Builds one tree and runs the existing tests of the touched modules on it, parsed by the task's UNCHANGED parser.py.
#   tree:  base commit + /tmp/tree.patch (gold.patch or the agent's final diff, applied as accept_in_container does)
#          -> test-code reset to HEAD (exactly the verifier's rule: tracked test code checked out, untracked removed)
#          -> /tests/test_patch.patch applied. Identical test files on both trees; only production code differs.
#   scope: /tmp/scope_src.txt = production files changed by gold OR agent (host computes). Tests chosen here:
#          go      every package dir of a changed .go file that has *_test.go -> go test -v ./<dir>
#          python  test/units/<mirror of lib/ansible/...> dir and the test_<stem>.py file, if they exist -> run_script.sh
#          js/ts   tracked test files (*.test.*, *.spec.*, *-test.*, __tests__/, test/) whose stem equals a changed
#                  file's stem, or that sit in the changed file's directory or its __tests__ -> run_script.sh (jest/yarn)
#          plus the task's own selected_test_files_to_run (the F2P files) on both trees.
# Writes /out/<label>/{scope_tests.txt,stdout.txt,stderr.txt,output.json}
L="$1"; mkdir -p /out/$L; cd /app 2>/dev/null || cd /testbed || exit 3
git apply /tmp/tree.patch 2>/dev/null || git apply --3way /tmp/tree.patch 2>/dev/null || patch --fuzz=3 -p1 -i /tmp/tree.patch >/dev/null \
  || { echo "APPLY_FAIL" > /out/$L/apply.txt; exit 2; }
python3 - <<'PY' > /tmp/reset.txt
import subprocess, re
CODE = {'tests','test','__tests__','spec','specs'}; DATA = {'testdata','test_data','fixtures','fixture','mocks','mock','__snapshots__'}
def t(p):
    s = p.split('/'); par, b = s[:-1], s[-1]
    if any(x in DATA for x in par): return False
    if any(x in CODE for x in par) or b == 'conftest.py': return True
    return bool(re.search(r'_test\.(go|py|js|jsx|ts|tsx)$', b) or re.search(r'^test_.*\.py$', b) or re.search(r'\.(test|spec)\.(js|jsx|ts|tsx)$', b))
g = lambda a: subprocess.run(['git'] + a, capture_output=True, text=True).stdout.splitlines()
for p in g(['ls-files']):
    if t(p): print('T ' + p)
for p in g(['ls-files', '--others', '--exclude-standard']):
    if t(p): print('U ' + p)
PY
while read -r k p; do case "$k" in T) git checkout HEAD -- "$p" 2>/dev/null;; U) rm -f -- "$p";; esac; done < /tmp/reset.txt
# files the test patch itself adds/changes: back to base (tracked) or removed, so it applies identically on both trees
for p in $(grep -oP '^diff --git a/\S+ b/\K\S+' /tests/test_patch.patch); do git checkout HEAD -- "$p" 2>/dev/null || rm -f -- "$p"; done
git apply /tests/test_patch.patch || { echo "TESTPATCH_FAIL" > /out/$L/apply.txt; exit 2; }
echo OK > /out/$L/apply.txt
LANG_=$(python3 -c "import json;print(json.load(open('/tmp/lang.json'))['lang'])")
python3 - "$LANG_" > /out/$L/scope_tests.txt <<'PY'
import json, os, re, subprocess, sys
lang = sys.argv[1]
src = [l.strip() for l in open('/tmp/scope_src.txt') if l.strip()]
cfg = json.load(open('/tests/config.json')); sel = cfg.get('selected_test_files_to_run') or []
sel = json.loads(sel) if isinstance(sel, str) else sel
files = subprocess.run(['git', 'ls-files'], capture_output=True, text=True).stdout.split()
out = []
if lang == 'go':
    for d in sorted({os.path.dirname(f) or '.' for f in src if f.endswith('.go')}):
        if os.path.isdir(d) and any(n.endswith('_test.go') for n in os.listdir(d)): out.append('./' + d)
elif lang == 'python':
    for f in src:
        if not f.endswith('.py'): continue
        rel = f[len('lib/ansible/'):] if f.startswith('lib/ansible/') else f
        d, stem = os.path.dirname(rel), os.path.splitext(os.path.basename(rel))[0]
        for c in (f'test/units/{d}/test_{stem}.py', f'test/units/{d}/{stem}'):
            if os.path.exists(c): out.append(c)
        if not any(o.startswith(f'test/units/{d}/') for o in out) and os.path.isdir(f'test/units/{d}'):
            out.append(f'test/units/{d}')
    out += [s for s in sel if s.endswith('.py')]
else:
    T = re.compile(r'(\.(test|spec)\.[jt]sx?$)|(-test\.[jt]sx?$)')
    tests = [f for f in files if T.search(f)]
    for f in src:
        if not re.search(r'\.[jt]sx?$', f): continue
        d, stem = os.path.dirname(f), re.sub(r'\.[jt]sx?$', '', os.path.basename(f))
        for t in tests:
            ts = re.sub(r'(\.(test|spec)|-test)\.[jt]sx?$', '', os.path.basename(t))
            if ts == stem or os.path.dirname(t) in (d, f'{d}/__tests__'): out.append(t)
    out += [s.split('|')[0].strip() for s in sel if re.search(r'\.[jt]sx?$', s.split('|')[0].strip()) and os.path.exists(s.split('|')[0].strip())]
print('\n'.join(dict.fromkeys(out)))
PY
mapfile -t TS < /out/$L/scope_tests.txt
[ ${#TS[@]} -eq 0 ] && { echo '{"tests": []}' > /out/$L/output.json; exit 0; }
if [ "$LANG_" = go ]; then
  ( go test -v "${TS[@]}" 2>&1 ) > /out/$L/stdout.txt 2> /out/$L/stderr.txt
else
  # one test-runner process per file: a suite that crashes the runner (environment) cannot hide the others
  : > /out/$L/stdout.txt; : > /out/$L/stderr.txt
  for t in "${TS[@]}"; do bash /tests/run_script.sh "$t" >> /out/$L/stdout.txt 2>> /out/$L/stderr.txt; done
fi
echo "run_exit=$?" > /out/$L/run_exit.txt
python3 /tests/parser.py /out/$L/stdout.txt /out/$L/stderr.txt /out/$L/output.json
