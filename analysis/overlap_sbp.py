#!/usr/bin/env python3
"""overlap_sbp.py -- gold line overlap (memorisation check) for the SWE-bench Pro V2 cells.

Same metrics as analysis/goalrw/behaviour/overlap.py (FeatureBench), made language-aware for Go / JS / TS / Python:
  recall_all       share of gold added lines (non-blank, stripped, multiset) the agent also added
  recall_long      same over gold lines >= 40 chars
  recall_comments  same over gold comment lines (#, //, /*, * ; bare markers and lint pragmas excluded)
  precision_all    share of agent added lines, in files gold touches, that are gold lines
Inputs: runs/<cell>/diff.patch (final), rounds/r00/diff.patch, manifest.json, tasks/<iid>/gold.patch.
Never reads tests or the accept/ dir. Test files are dropped from both sides.
Output: overlap_sbp.csv next to this script.
"""
import csv, json, re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNS, TASKS, HERE = ROOT / 'runs', ROOT / 'tasks', Path(__file__).resolve().parent


def is_test(path):
    p = path.split('/'); n = p[-1]
    return (bool({'tests', 'test', '__tests__', 'testdata', '__mocks__'} & set(p[:-1]))
            or n.startswith('test_') or n == 'conftest.py' or n.endswith('_test.go')
            or re.search(r'\.(test|spec)\.[jt]sx?$', n) is not None)


def added(patch):
    out, cur = {}, None
    if not patch.exists():
        return None
    for line in patch.read_text(errors='replace').splitlines():
        if line.startswith('+++ '):
            f = line[4:]; f = f[2:] if f.startswith('b/') else f
            cur = None if f == '/dev/null' or is_test(f) else f
            if cur: out.setdefault(cur, Counter())
        elif line.startswith('+') and cur:
            s = line[1:].strip()
            if s: out[cur][s] += 1
    return out


def is_comment(s):
    if s in ('#', '//', '/*', '*/', '*', '/**'): return False
    if re.match(r'(#|//)\s*(type:|noqa|pragma|fmt:|pylint|eslint|@ts-|nolint|go:)', s): return False
    return s.startswith(('#', '//', '/*', '* '))


def overlap(gold, agent):
    def inter(pred):
        g, a = Counter(), Counter()
        for c in gold.values(): g.update({s: n for s, n in c.items() if pred(s)})
        for c in agent.values(): a.update({s: n for s, n in c.items() if pred(s)})
        return sum(g.values()), sum((g & a).values())
    ga, ma = inter(lambda s: True); gl, ml = inter(lambda s: len(s) >= 40); gc, mc = inter(is_comment)
    g_all, a_all = Counter(), Counter()
    for c in gold.values(): g_all.update(c)
    for f, c in agent.items():
        if f in gold: a_all.update(c)
    a_in = sum(a_all.values())
    r = lambda m, g: round(m / g, 3) if g else ''
    return dict(gold_lines=ga, recall_all=r(ma, ga), gold_long=gl, recall_long=r(ml, gl),
                gold_comments=gc, recall_comments=r(mc, gc), agent_lines_in_gold_files=a_in,
                precision_all=r(sum((g_all & a_all).values()), a_in), gold_files=len(gold),
                agent_files=len(agent), agent_files_outside_gold=len(set(agent) - set(gold)))


def main():
    rows = []
    for run in sorted(RUNS.glob('2026*-s1')):
        iid = json.load(open(run / 'manifest.json'))['instance_id']
        gold = added(TASKS / iid / 'gold.patch')
        repo = iid.split('__')[0].removeprefix('instance_')
        for label, p in (('final', run / 'diff.patch'), ('r00', run / 'rounds/r00/diff.patch')):
            a = added(p)
            row = dict(repo=repo, task=iid.split('-')[-1][:8] if 'webclients' in iid else iid.split('__')[1][:30],
                       cell=run.name, diff=label, complete=(run / 'accept_final.txt').exists())
            row.update(overlap(gold, a) if a is not None else {})
            rows.append(row)
    keys = list(max(rows, key=len))
    with open(HERE / 'overlap_sbp.csv', 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=keys); w.writeheader(); w.writerows(rows)
    for r in rows:
        if r['diff'] == 'final':
            print(f"{r['repo']:22} {r['task']:30} done={r['complete']!s:5} gold={r.get('gold_lines','-')!s:>5} "
                  f"rec={r.get('recall_all','-')!s:6} long={r.get('recall_long','-')!s:6} "
                  f"cmt={r.get('gold_comments','-')!s:>3}/{r.get('recall_comments','-')!s:6} "
                  f"prec={r.get('precision_all','-')!s:6} out={r.get('agent_files_outside_gold','-')}")


if __name__ == '__main__':
    main()
