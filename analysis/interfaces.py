#!/usr/bin/env python3
"""interfaces.py -- did the agent read/use the abstraction layer? -> interfaces.csv
Per run: every file the agent opened (read_full/read_part/grep_on_file) or edited, in call order, from auto/<bench>/<cell>.json.
Each file is classified as INTERFACE or implementation from its content in the PRE-TASK tree
(base commit, gold reversed if already applied -- same reconstruction as agentshape.py; gold used only for that).
Interface rules (static, decided before looking at outcomes):
  Python: class inheriting ABC/Protocol or metaclass=ABCMeta, or any @abstractmethod; __init__.py that only re-exports
          (imports/__all__, no top-level def/class); basename interface(s)/protocol(s)/typing/_typing/types/_types .py
  (v2: v1 counted every __init__.py with imports and every base.py/api.py -- too loose, e.g. sphinx/builders/html/__init__.py)
  TS/JS:  .d.ts; index.ts/js that only re-exports; file whose top-level exports are all `interface`/`type`
  Go:     declares `type X interface`
Files absent from the pre-task tree (created by the agent) count as 'new', not interface.
"""
import ast, csv, glob, json, os, re, subprocess
import callgraph as cg, patchshape as ps

HERE = os.path.dirname(os.path.abspath(__file__))
PY_NAMES = {'interface.py', 'interfaces.py', 'protocol.py', 'protocols.py', 'typing.py', '_typing.py', 'types.py', '_types.py'}
OPEN = {'read_full', 'read_part', 'grep_on_file'}
CODE = ('.py', '.ts', '.tsx', '.js', '.jsx', '.go', '.mjs')


def norm(p):
    p = p.strip().strip('"\'')
    for pre in ('/testbed/', '/app/', '/workspace/', '/repo/', './'):
        if p.startswith(pre): p = p[len(pre):]
    return p


def classify(d, path):
    f = os.path.join(d, path)
    if not path.endswith(CODE): return None
    if not os.path.isfile(f): return 'new'
    try: src = open(f, errors='replace').read()
    except Exception: return None
    b = os.path.basename(path)
    if path.endswith('.py'):
        if re.search(r'^\s*class\s+\w+\([^)]*\b(ABC|Protocol|ABCMeta)\b', src, re.M) or 'metaclass=ABCMeta' in src or re.search(r'@(abc\.)?abstractmethod', src):
            return 'interface'
        if b == '__init__.py' and (re.search(r'^\s*(from|import)\s', src, re.M) or '__all__' in src) \
                and not re.search(r'^(def|class|async def)\s', src, re.M): return 'interface'  # pure re-export package API
        if b in PY_NAMES: return 'interface'
        return 'impl'
    if path.endswith('.go'):
        return 'interface' if re.search(r'^\s*type\s+\w+\s+interface\s*\{', src, re.M) else 'impl'
    if path.endswith('.d.ts'): return 'interface'
    if re.match(r'index\.(ts|tsx|js|mjs)$', b):
        lines = [l for l in src.splitlines() if l.strip() and not l.strip().startswith(('//', '/*', '*'))]
        if lines and all(re.match(r'\s*(export\s+(\*|\{|type\s)|import\s)', l) or l.strip() in ('}', '};') or re.match(r'\s*[\w$]+,?$', l) for l in lines):
            return 'interface'
    exports = re.findall(r'^\s*export\s+(?:default\s+)?(?:declare\s+)?(\w+)', src, re.M)
    if exports and all(e in ('interface', 'type', 'enum') for e in exports): return 'interface'
    return 'impl'


def pretask(r):
    ex, iid, repo, base, gold = cg.task_of(r)
    d = f'{cg.REPOS}/{repo.replace("/", "__")}'
    cg.git(d, 'checkout', '-q', '-f', cg.git(d, 'rev-parse', base).stdout.strip()); cg.git(d, 'clean', '-qfdx')
    if cg.git(d, 'apply', '-R', '--check', gold, check=False).returncode == 0: cg.git(d, 'apply', '-R', gold)
    return d


def run(r):
    bench = 'featurebench' if r['bench'] == 'FeatureBench' else 'swebench_pro'
    o = json.load(open(f'{HERE}/auto/{bench}/{r["cell"]}.json'))
    d = pretask(r)
    opened, edited = {}, {}           # path -> first call index
    for c in o['calls']:
        ev = c['events']; ev = eval(ev) if isinstance(ev, str) else ev
        i = int(c['i'])
        for k, p in ev:
            if not p or '*' in p: continue
            p = norm(p)
            if ps.is_test(p): continue
            if k in OPEN: opened.setdefault(p, i)
            elif k == 'edit': edited.setdefault(p, i)
    cls = {p: classify(d, p) for p in set(opened) | set(edited)}
    op = [p for p in opened if cls[p] in ('interface', 'impl')]
    ed = [p for p in edited if cls[p] in ('interface', 'impl', 'new')]
    iface_open = [p for p in op if cls[p] == 'interface']
    # repo baseline: interface share among code files in the directories the agent opened files from
    dirs = {os.path.dirname(p) for p in op}; pool = []
    for dd in dirs:
        full = os.path.join(d, dd)
        if os.path.isdir(full):
            for fn in os.listdir(full):
                c_ = classify(d, os.path.join(dd, fn))
                if c_ in ('interface', 'impl') and not ps.is_test(os.path.join(dd, fn)): pool.append(c_)
    # interface-before-edit: edited impl/new files with an interface file in the same or parent dir opened earlier
    def near(p, q):
        a, b = os.path.dirname(p), os.path.dirname(q)
        return a == b or a == os.path.dirname(b) or b == os.path.dirname(a)
    ed_impl = [p for p in ed if cls[p] in ('impl', 'new')]
    before = [p for p in ed_impl if any(near(p, q) and opened[q] < edited[p] for q in iface_open)]
    nearby = [p for p in ed_impl if any(near(p, q) for q in iface_open)]
    ed_iface = [p for p in ed if cls[p] == 'interface']
    return dict(cell=r['cell'], bench=r['bench'], n_opened=len(op), n_iface_opened=len(iface_open),
                iface_open_share=round(len(iface_open) / len(op), 3) if op else '',
                iface_dir_base=round(pool.count('interface') / len(pool), 3) if pool else '',
                n_edited=len(ed), n_iface_edited=len(ed_iface), edited_iface_any=int(bool(ed_iface)),
                iface_edit_share=round(len(ed_iface) / len(ed), 3) if ed else '',
                n_impl_edited=len(ed_impl), iface_before_edit_share=round(len(before) / len(ed_impl), 3) if ed_impl else '',
                iface_seen_ever_share=round(len(nearby) / len(ed_impl), 3) if ed_impl else '',
                iface_files_opened=';'.join(sorted(iface_open))[:400], iface_files_edited=';'.join(sorted(ed_iface))[:400])


if __name__ == '__main__':
    out = []
    for r in csv.DictReader(open(f'{HERE}/cells.csv')):
        try: row = run(r); row['status'] = 'ok'
        except Exception as e: row = dict(cell=r['cell'], bench=r['bench'], status=f'error: {e}'[:200])
        out.append(row)
        print(r['bench'][:4], r['cell'][:45], row.get('n_opened'), row.get('n_iface_opened'), row.get('iface_open_share'), row.get('iface_dir_base'),
              row.get('edited_iface_any'), row.get('iface_before_edit_share'), row['status'][:60], flush=True)
    keys = list(dict.fromkeys(k for v in out for k in v))
    with open(f'{HERE}/interfaces.csv', 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=keys); w.writeheader(); w.writerows(out)
