#!/usr/bin/env python3
"""callgraph.py -- call-graph distances between the functions a gold patch changes -> callgraph.csv.

Tree: repo at the task's base, in the POST-gold state. FeatureBench lv1 gold patches re-add code removed from upstream
base_commit, so upstream base_commit IS the post-gold tree (checked: `git apply -R --check gold.patch` must succeed).
SWE-Pro: base commit (from the instance id) + gold.patch applied.
Changed functions: innermost function/method enclosing each gold-changed line (new-side line numbers) in production code.
Graph: static, name-based. Nodes = every function/method defined in non-test production files of the language.
Edge f-g (undirected) when f's body calls a name g is defined under, if that name has <= AMBIG definitions repo-wide.
Distances: BFS hops between changed functions. Over-approximates edges (name collisions) and misses dynamic calls.
Usage: callgraph.py [cell-substring ...]"""
import ast, csv, json, os, re, subprocess, sys
from collections import defaultdict, deque
from itertools import combinations
from statistics import median

F = '/home/niruthi/features'; REPOS = '/home/niruthi/cg-repos'; AMBIG = 15
HERE = os.path.dirname(os.path.abspath(__file__))


def is_test(p):
    s = p.split('/'); b = s[-1]
    return bool(any(x in ('tests', 'test', '__tests__', 'testing', 'spec', 'specs', 'fixtures', '__mocks__') for x in s[:-1])
                or b == 'conftest.py' or re.search(r'(_test\.(go|py|[jt]sx?)$)|(^test_.*\.py$)|(\.(test|spec)\.[jt]sx?$)', b))


def git(d, *a, check=True):
    r = subprocess.run(['git', '-C', d, *a], capture_output=True, text=True)
    if check and r.returncode: raise RuntimeError(f'git {a}: {r.stderr[-400:]}')
    return r


def changed_lines(patch, ext):
    """file -> set of new-side line numbers touched (added lines; deletions mapped to the following new line)."""
    out = defaultdict(set); cur = None; n = 0
    for l in open(patch, errors='replace'):
        if l.startswith('diff --git'):
            p = l.split(' b/')[-1].strip(); cur = p if p.endswith(ext) and not is_test(p) else None
        elif cur is None or l.startswith(('+++', '---')): continue
        elif l.startswith('@@'): n = int(re.search(r'\+(\d+)', l).group(1))
        elif l.startswith('+'): out[cur].add(n); n += 1
        elif l.startswith('-'): out[cur].add(n)
        elif l.startswith(' '): n += 1
    return out


# ---------------------------------------------------------------- python front end (stdlib ast)
def py_defs(path, rel):
    """[(id, name, start, end, called_names)]"""
    try: tree = ast.parse(open(path, 'rb').read())
    except (SyntaxError, ValueError): return []
    res = []
    def visit(node, prefix):
        for ch in ast.iter_child_nodes(node):
            if isinstance(ch, (ast.FunctionDef, ast.AsyncFunctionDef)):
                q = f'{prefix}{ch.name}'; calls = set(); stack = list(ast.iter_child_nodes(ch))
                while stack:
                    x = stack.pop()
                    if isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)): continue
                    if isinstance(x, ast.Call):
                        f = x.func
                        if isinstance(f, ast.Name): calls.add(f.id)
                        elif isinstance(f, ast.Attribute): calls.add(f.attr)
                    stack.extend(ast.iter_child_nodes(x))
                res.append((f'{rel}::{q}', ch.name, ch.lineno, ch.end_lineno, calls))
                visit(ch, q + '.')
            elif isinstance(ch, ast.ClassDef):
                # a call to the class name reaches its __init__: record the class as an alias name of __init__
                res.append((f'{rel}::{prefix}{ch.name}', ch.name, ch.lineno, ch.end_lineno, set()))
                visit(ch, f'{prefix}{ch.name}.')
            else:
                visit(ch, prefix)
    visit(tree, '')
    return res


FRONT = {'.py': py_defs}

# ---------------------------------------------------------------- go / ts / js front ends (regex + brace matching; no parser available)
KW = set('if for while switch return catch function typeof new await yield super import export case else do try throw delete void in of instanceof func go defer select range make len cap append panic recover map chan struct interface type var const let'.split())
CALL = re.compile(r'(?<![\w$.])(?:[\w$]+\.)*([A-Za-z_$][\w$]*)\s*(?:<[^<>()]*>)?\s*\(')
JSX = re.compile(r'<([A-Z][\w$]*)[\s/>]')


def _strip(src):
    """blank out strings/comments, keep length and newlines."""
    out = []; i = 0; n = len(src)
    while i < n:
        c = src[i]
        if src.startswith('//', i):
            j = src.find('\n', i); j = n if j < 0 else j; out.append(' ' * (j - i)); i = j
        elif src.startswith('/*', i):
            j = src.find('*/', i + 2); j = n if j < 0 else j + 2; out.append(re.sub(r'[^\n]', ' ', src[i:j])); i = j
        elif c in '"\'`':
            j = i + 1
            while j < n and src[j] != c:
                if src[j] == '\\': j += 1
                elif c != '`' and src[j] == '\n': break
                j += 1
            j = min(j + 1, n); out.append(c + re.sub(r'[^\n]', ' ', src[i + 1:j - 1]) + (c if j - i > 1 else '')); i = j
        else:
            out.append(c); i += 1
    return ''.join(out)


def _brace_end(s, start):
    k = s.find('{', start)
    if k < 0: return None, None
    depth = 0
    for j in range(k, len(s)):
        if s[j] == '{': depth += 1
        elif s[j] == '}':
            depth -= 1
            if depth == 0: return k, j
    return k, len(s) - 1


GO_DEF = re.compile(r'^func\s+(?:\([^)]*\)\s*)?([A-Za-z_]\w*)\s*[\[(]', re.M)
TS_DEF = re.compile(r'^[ \t]*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s*([A-Za-z_$][\w$]*)'
                    r'|^[ \t]*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*(?::[^=]+)?=\s*(?:async\s*)?(?:\([^)]*\)|[\w$]+)\s*(?::[^=>{]+)?=>'
                    r'|^[ \t]*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*(?::[^=]+)?=\s*(?:React\.)?(?:memo|forwardRef|useCallback|useMemo)\s*\('
                    r'|^[ \t]+(?:(?:public|private|protected|static|async|readonly|override|get|set)\s+)*([A-Za-z_$][\w$]*)\s*(?:<[^>]*>)?\s*\([^;{]*\)\s*(?::[^{;]+)?\{'
                    r'|^[ \t]*(?:export\s+)?(?:default\s+)?(?:abstract\s+)?class\s+([A-Za-z_$][\w$]*)', re.M)


def _regex_defs(path, rel, rx, jsx):
    try: src = open(path, errors='replace').read()
    except OSError: return []
    if len(src) > 400_000: return []
    s = _strip(src); line_at = lambda off: s.count('\n', 0, off) + 1; res = []
    for m in rx.finditer(s):
        name = next(g for g in m.groups() if g)
        if name in KW: continue
        k, e = _brace_end(s, m.end() - 1 if s[m.end() - 1] == '{' else m.end())
        if k is None: continue
        # arrow fn with expression body: end at line end
        if '=>' in m.group(0) and s[m.end():k].strip(): k, e = m.end(), s.find('\n', m.end())
        body = s[k:e + 1]
        calls = {c for c in CALL.findall(body) if c not in KW} | (set(JSX.findall(body)) if jsx else set())
        res.append((f'{rel}::{name}@{line_at(m.start())}', name, line_at(m.start()), line_at(e), calls))
    return res


FRONT.update({'.go': lambda p, r: _regex_defs(p, r, GO_DEF, False),
              '.ts': lambda p, r: _regex_defs(p, r, TS_DEF, False), '.tsx': lambda p, r: _regex_defs(p, r, TS_DEF, True),
              '.js': lambda p, r: _regex_defs(p, r, TS_DEF, False), '.jsx': lambda p, r: _regex_defs(p, r, TS_DEF, True)})


def analyse(repo, exts, patch):
    exts = tuple(exts); defs = []
    files = [p for p in git(repo, 'ls-files').stdout.split() if p.endswith(exts) and not is_test(p) and '/node_modules/' not in p]
    for rel in files:
        defs += FRONT[os.path.splitext(rel)[1]](os.path.join(repo, rel), rel)
    byname = defaultdict(list); by_file = defaultdict(list)
    for d in defs:
        byname[d[1]].append(d[0]); by_file[d[0].split('::')[0]].append(d)
    adj = defaultdict(set)
    for i, name, s, e, calls in defs:
        for c in calls:
            tg = byname.get(c, ())
            if 0 < len(tg) <= AMBIG:
                for t in tg:
                    if t != i: adj[i].add(t); adj[t].add(i)
    # class node <-> its methods (constructor call reaches __init__ and the class body)
    for d in defs:
        q = d[0]
        if '.' in q.split('::')[1]:
            parent = q.rsplit('.', 1)[0]
            if any(x[0] == parent for x in by_file[q.split('::')[0]]): adj[q].add(parent); adj[parent].add(q)
    changed = set(); module_level = 0
    for f, ls in changed_lines(patch, exts).items():
        fd = [d for d in by_file.get(f, []) if d[0].split('::')[1] and d[4] is not None]
        for ln in ls:
            enc = [d for d in fd if d[2] <= ln <= d[3]]
            if enc: changed.add(min(enc, key=lambda d: d[3] - d[2])[0])
            else: module_level += 1
    ch = sorted(changed); dist = {}
    for a in ch:
        seen = {a: 0}; q = deque([a]); want = set(ch) - {a}
        while q and want:
            x = q.popleft()
            for y in adj[x]:
                if y not in seen:
                    seen[y] = seen[x] + 1; want.discard(y); q.append(y)
        for b in ch:
            if b != a and b in seen: dist[(a, b)] = seen[b]
    pairs = list(combinations(ch, 2)); conn = [dist[p] for p in pairs if p in dist]
    nn = [min((dist[(a, b)] for b in ch if (a, b) in dist), default=None) for a in ch]
    nn = [x for x in nn if x is not None]
    # components among changed functions under reachability
    comp = 0; left = set(ch)
    while left:
        a = left.pop(); comp += 1
        left -= {b for b in ch if (a, b) in dist}
    # module (file) level: touched files, and pairs with no direct call edge either way
    fadj = defaultdict(set)
    for a, bs in adj.items():
        fa = a.split('::')[0]
        for b in bs:
            fb = b.split('::')[0]
            if fa != fb: fadj[fa].add(fb)
    tf = sorted({x.split('::')[0] for x in ch} | set(changed_lines(patch, exts)) & set(by_file))
    fp = list(combinations(tf, 2)); indep = [p for p in fp if p[1] not in fadj[p[0]]]
    return dict(mod_touched=len(tf), mod_pairs=len(fp), mod_share_pairs_no_dep=round(len(indep) / len(fp), 3) if fp else '',
                mod_isolated=sum(1 for f in tf if not any(g in fadj[f] for g in tf if g != f)) if len(tf) > 1 else 0,
                cg_nodes=len(defs), cg_edges=sum(len(v) for v in adj.values()) // 2, cg_changed_funcs=len(ch),
                cg_module_level_lines=module_level, cg_pairs=len(pairs),
                cg_share_pairs_connected=round(len(conn) / len(pairs), 3) if pairs else '',
                cg_mean_dist=round(sum(conn) / len(conn), 2) if conn else '', cg_median_dist=median(conn) if conn else '',
                cg_max_dist=max(conn) if conn else '', cg_median_nn_dist=median(nn) if nn else '',
                cg_share_isolated=round(1 - len(nn) / len(ch), 3) if ch else '', cg_components=comp)


def task_of(r):
    ex = 'experiment-featurebench' if r['bench'] == 'FeatureBench' else 'experiment-swebench-pro'
    m = json.load(open(f'{F}/{ex}/runs/{r["cell"]}/manifest.json')); iid = m.get('instance_id') or m.get('iid')
    t = json.load(open(f'{F}/{ex}/tasks/{iid}/meta.json'))
    if r['bench'] == 'FeatureBench':
        repo, base = t['repo'], t['base_commit']
    else:
        mm = re.match(r'instance_([^_]+(?:-[^_]+)*)__([^-]+(?:-[a-z]+)*)-([0-9a-f]{12,40})', iid)
        repo, base = f'{mm.group(1)}/{mm.group(2)}', mm.group(3)
    return ex, iid, repo, base, f'{F}/{ex}/tasks/{iid}/gold.patch'


if __name__ == '__main__':
    want = sys.argv[1:]; out_p = f'{HERE}/callgraph.csv'
    old = {r['cell']: r for r in csv.DictReader(open(out_p))} if os.path.exists(out_p) else {}
    for r in csv.DictReader(open(f'{HERE}/cells.csv')):
        if want and not any(w in r['cell'] for w in want): continue
        ex, iid, repo, base, patch = task_of(r)
        exts = sorted({os.path.splitext(l.split(' b/')[-1].strip())[1] for l in open(patch, errors='replace') if l.startswith('diff --git')} & set(FRONT))
        d = f'{REPOS}/{repo.replace("/", "__")}'
        row = dict(cell=r['cell'], repo=repo, base=base[:12], lang='/'.join(exts) or 'unsupported')
        try:
            if not exts: raise RuntimeError('no supported language front end yet')
            full = git(d, 'rev-parse', base).stdout.strip()
            git(d, 'checkout', '-q', '-f', full); git(d, 'clean', '-qfdx')
            if r['bench'] == 'FeatureBench':
                if git(d, 'apply', '-R', '--check', patch, check=False).returncode:
                    raise RuntimeError('gold does not reverse-apply: upstream base != post-gold tree')
                row['tree'] = 'upstream base (== post-gold, reverse-apply checked)'
            else:
                if git(d, 'apply', patch, check=False).returncode == 0: row['tree'] = 'base + gold.patch'
                elif git(d, 'apply', '-R', '--check', patch, check=False).returncode == 0: row['tree'] = 'instance commit already == post-gold (reverse-apply checked)'
                else: raise RuntimeError('gold neither applies nor reverse-applies')
            fam = ['.ts', '.tsx', '.js', '.jsx'] if set(exts) & {'.ts', '.tsx', '.js', '.jsx'} else exts
            row.update(analyse(d, fam, patch))
            row['status'] = 'ok'
        except Exception as e:
            row['status'] = f'error: {e}'[:300]
        old[r['cell']] = row
        print(r['cell'][:60], {k: v for k, v in row.items() if k.startswith('cg_') or k == 'status'}, flush=True)
    keys = list(dict.fromkeys(k for v in old.values() for k in v))
    with open(out_p, 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=keys); w.writeheader(); w.writerows(old.values())
