#!/usr/bin/env python3
"""patchshape.py -- extra gold-patch shape variables per cell -> patchshape.csv.
functions = distinct (file, enclosing def/class/func) touched by a hunk + newly defined ones; packages = top-two path
components; dos_file / dos_pkg = 1-HHI of changed lines over files / packages. Production code files only."""
import csv, json, re, os
from collections import Counter, defaultdict
F = '/home/niruthi/features'
CODE = re.compile(r'\.(py|go|js|jsx|ts|tsx|pyx|pxd)$')
def is_test(p):
    s = p.split('/'); b = s[-1]
    return (any(x in ('tests', 'test', '__tests__', 'testing', 'spec', 'specs') for x in s[:-1]) or b == 'conftest.py'
            or re.search(r'(_test\.(go|py|[jt]sx?)$)|(^test_.*\.py$)|(\.(test|spec)\.[jt]sx?$)', b))
DEF = re.compile(r'^\s*(?:async\s+)?(?:def|class)\s+(\w+)|^\s*func\s+(?:\([^)]*\)\s*)?(\w+)|^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s*(\w+)|^\s*(?:export\s+)?(?:const|let)\s+(\w+)\s*=\s*(?:async\s*)?(?:\([^)]*\)|\w+)\s*=>|^\s*(?:export\s+)?(?:abstract\s+)?(?:class|interface)\s+(\w+)')
def name(line):
    m = DEF.search(line)
    return next((g for g in m.groups() if g), None) if m else None
def shape(patch):
    files = {}; cur = None
    for l in open(patch, errors='replace'):
        if l.startswith('diff --git'):
            p = l.split(' b/')[-1].strip(); cur = p if CODE.search(p) and not is_test(p) else None
            if cur: files[cur] = dict(lines=0, hunks=0, funcs=set(), new=set(), created=False)
        elif cur is None: continue
        elif l.startswith('--- /dev/null'): files[cur]['created'] = True
        elif l.startswith('@@'):
            files[cur]['hunks'] += 1; h = l.split('@@')[-1]; n = name(h)
            if n: files[cur]['funcs'].add(n)
        elif l[:1] in '+-' and not l.startswith(('+++', '---')):
            if l[1:].strip(): files[cur]['lines'] += 1
            n = name(l[1:])
            if n:
                files[cur]['funcs'].add(n)
                if l[0] == '+': files[cur]['new'].add(n)
    pk = Counter(); tot = sum(v['lines'] for v in files.values()) or 1
    for p, v in files.items(): pk['/'.join(p.split('/')[:2]) if '/' in p else '.'] += v['lines']
    hhi = lambda c: 1 - sum((x / tot) ** 2 for x in c.values())
    fl = {p: v['lines'] for p, v in files.items()}
    return dict(n_files=len(files), n_lines=sum(fl.values()), focus_top_file=round(max(fl.values()) / tot, 3) if fl else '',
                n_functions=sum(len(v['funcs']) for v in files.values()),
                n_new_functions=sum(len(v['new']) for v in files.values()),
                n_hunks=sum(v['hunks'] for v in files.values()), n_packages=len(pk),
                n_files_created=sum(v['created'] for v in files.values()),
                dos_file=round(hhi({p: v['lines'] for p, v in files.items()}), 3), dos_pkg=round(hhi(pk), 3),
                lang='/'.join(sorted({os.path.splitext(p)[1][1:] for p in files})))
if __name__ == '__main__':
  rows = []
  for r in csv.DictReader(open(f'{F}/analysis/crossbench/cells.csv')):
      ex = 'experiment-featurebench' if r['bench'] == 'FeatureBench' else 'experiment-swebench-pro'
      m = json.load(open(f'{F}/{ex}/runs/{r["cell"]}/manifest.json'))
      iid = m.get('instance_id') or m.get('iid') or m.get('task')
      rows.append(dict(cell=r['cell'], **shape(f'{F}/{ex}/tasks/{iid}/gold.patch')))
  w = csv.DictWriter(open(f'{F}/analysis/crossbench/patchshape.csv', 'w', newline=''), fieldnames=list(rows[0]))
  w.writeheader(); w.writerows(rows)
  for x in rows: print(x)
