#!/usr/bin/env python3
"""techniques_xb.py -- SlopCodeBench technique codebook (scbench/analysis/qual/techniques.py labels(), validated 57/60 on
Python traces) applied to the 33 crossbench traces -> techniques_xb.csv. Multi-label per tool call.
Extension for Go/TS (NOT in the validated classifier, disclosed): own_test_run also matches go test / jest / vitest /
yarn|npm|npx test / run_script.sh; probe_run also matches go run / node / npx ts-node / tsx.
Hand validation of all 101 Go/TS Bash calls: GOTS_VALIDATION.md (v1 90/101; timeout-prefix + stylelint/prettier fix -> v2)."""
import csv, json, re, os, collections
SRC = open('/home/niruthi/features/scbench/analysis/qual/techniques.py').read()
ns = {}; exec(SRC[:SRC.index('def classify')], ns)  # labels() and regexes only; skip its main block
labels0 = ns['labels']
PFX = r'(^|[;&|(\n]\s*|timeout \d+\s+|\bdo\s+)'
GOTS_TEST = re.compile(PFX + r'(go test\b|(npx |yarn |npm (run )?)?(jest|vitest)\b|yarn (run )?test\b|npm (run )?test\b|npx (jest|vitest)\b|bash [\w./-]*run_script\.sh)')
GOTS_PROBE = re.compile(PFX + r'(go run\b|node\b|npx (ts-node|tsx)\b|tsx\b)')
GOTS_STATIC = re.compile(PFX + r'(npx stylelint\b|npx prettier --check\b|go (build|vet)\b|gofmt\b|npx tsc\b|tsc\b|yarn tsc\b|npx eslint\b)')


def labels(name, a):
    L = set(labels0(name, a))
    if name == 'Bash':
        c = a.get('command', '')
        if GOTS_TEST.search(c): L.add('own_test_run')
        if GOTS_STATIC.search(c): L.add('static_check')
        if GOTS_PROBE.search(c) and 'probe_tmp' not in L: L.add('probe_run')
        if len(L) > 1: L -= {'bash_other', 'read', 'locate'} if L & {'own_test_run', 'static_check', 'probe_run'} and L <= {'own_test_run', 'static_check', 'probe_run', 'bash_other', 'read', 'locate'} else set()
    return L


KEYS = ['read', 'locate', 'edit_tool', 'edit_script', 'probe_run', 'probe_tmp', 'own_test_run', 'static_check', 'install_or_ref_lib', 'git', 'todo', 'bash_other']
F = '/home/niruthi/features'; rows = []
for r in csv.DictReader(open('cells.csv')):
    ex = 'experiment-featurebench' if r['bench'] == 'FeatureBench' else 'experiment-swebench-pro'
    cnt = collections.Counter(); n = 0
    for l in open(f'{F}/{ex}/runs/{r["cell"]}/transcript.jsonl', errors='replace'):
        try: m = json.loads(l)
        except ValueError: continue
        if m.get('type') != 'assistant': continue
        for x in m.get('message', {}).get('content', []) or []:
            if isinstance(x, dict) and x.get('type') == 'tool_use':
                n += 1
                for k in labels(x['name'], x.get('input', {}) or {}): cnt[k.split(':')[0] if k.startswith('other:') else k] += 1
    row = dict(cell=r['cell'], bench=r['bench'], calls=n, **{k: cnt.get(k, 0) for k in KEYS})
    row.update({f'tshare_{k}': round(cnt.get(k, 0) / n, 3) if n else '' for k in KEYS})
    rows.append(row)
w = csv.DictWriter(open('techniques_xb.csv', 'w', newline=''), fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
for x in rows: print(x['bench'][:3], x['calls'], {k: x[k] for k in KEYS if x[k]})
