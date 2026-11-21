#!/usr/bin/env python3
"""build_table.py -- one row per cell, FeatureBench goal-only (21) + SWE-bench Pro V2 (12).

Same definitions for both benchmarks wherever possible (sources in brackets):
 IVs, task side (gold.patch, production files only):
   n_files      gold production files touched
   impl_lines   gold added+removed production lines
   n_dirs       distinct parent directories of those files
   dos_dir      1 - HHI of changed lines over parent directories (0 = all in one directory)
   cue_files    share of gold files whose path, or file stem (>=4 chars, exact case, whole word), the agent's prompt names
   cue_tokens   distinct code-shaped tokens in the prompt (cue_recall.code_tokens)
 Memorisation (gold line overlap, final diff): recall_all, recall_long, recall_comments, gold_comments
   (FB: analysis/goalrw/behaviour/overlap.py; SWE-Pro: experiment-swebench-pro/analysis/overlap/overlap_sbp.py --
    identical metric, comment syntax extended to // /* *)
 DVs (crossbench/extract_all.py = experiment-swebench-pro dv_extract.py, repo root parameterised, one indexing bug fixed):
   tool_calls, api_turns, searches, test_runs, files_opened, files_read_full, orient_calls, gold_found_pre_edit,
   gold_found_by_done, nav_* counts and shares, rework
 Outcomes: accept_final, r0_pass, rounds, cost_usd, wall_s; regression (FB: run_regress verdict on touched-module tests,
   raw and after the documented flaky/timeout reruns; SWE-Pro: benchmark P2P only -- no broader check exists).
Writes cells.csv.
"""
import csv, glob, json, os, re, sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
FB = Path('/home/niruthi/features/experiment-featurebench')
SBP = Path('/home/niruthi/features/experiment-swebench-pro')
sys.path.insert(0, '/home/niruthi/features/analysis/goalrw')
from cue_recall import code_tokens  # noqa: E402
sys.path.insert(0, str(SBP / 'analysis/overlap'))
import overlap_sbp as OS  # noqa: E402  (language-aware added()/overlap(); same metric as FB)

# documented reruns: flagged regressions attributed to timeouts / flaky tests
REG_ADJUST = {'20261112-091735-pandas-dev-test_describe-s1-goalrw': 'regress/EXT_RERUN.md',
              '20261112-173352-pandas-dev-test_formats-s1-goalrw': 'regress/ONLINE_RERUN.md'}


def gold_shape(patch):
    per_file = Counter(); cur = None
    for line in patch.read_text(errors='replace').splitlines():
        if line.startswith('diff --git'):
            m = re.match(r'diff --git a/(\S+) b/(\S+)', line); cur = m.group(2) if m else None
            if cur and (OS.is_test(cur) or re.search(r'\.(md|mdx|rst|txt|json|lock|snap|ya?ml)$', cur) or '/docs/' in '/' + cur):
                cur = None
        elif cur and line[:1] in '+-' and not line.startswith(('+++', '---')) and line[1:].strip():
            per_file[cur] += 1
    dirs = Counter()
    for f, n in per_file.items():
        dirs[os.path.dirname(f)] += n
    tot = sum(per_file.values())
    return per_file, dict(n_files=len(per_file), impl_lines=tot, n_dirs=len(dirs),
                          dos_dir=round(1 - sum((n / tot) ** 2 for n in dirs.values()), 3) if tot else '')


def cue_files(files, text):
    hit = 0
    for f in files:
        stem = Path(f).stem
        mod = f.rsplit('.', 1)[0].replace('/', '.')
        if f in text or mod in text or (len(stem) >= 4 and re.search(r'(?<![\w.])' + re.escape(stem) + r'(?!\w)', text)):
            hit += 1
    return round(hit / len(files), 3) if files else ''


def nav_row(bench, cell):
    o = json.load(open(HERE / 'auto' / bench / f'{cell}.json'))
    a, d, orr = o['activity'], o['discovery'], o['orientation']
    nm = Counter(d.get('nav_methods') or {})
    nreq = sum(nm.values())
    r = dict(tool_calls=a['tool_calls'], api_turns=a['api_turns'], searches=a['searches'], test_runs=a['test_runs'],
             files_opened=a['files_opened'], files_read_full=a['files_read_full'], listings=a['listings'],
             orient_calls=orr['calls_before_first_edit'], orient_searches=orr['searches_before_first_edit'],
             gold_found_pre_edit=d['share_gold_found_before_first_edit'], gold_found_by_done=d['share_gold_found_by_done'],
             n_required=nreq, rework=o['rework']['n'])
    for k in ('search', 'following_code', 'following_code+search', 'listing', 'tests', 'benchmark_clue', 'recall',
              'other_output', 'not_found'):
        r[f'nav_{k}'] = nm.get(k, 0)
        r[f'navshare_{k}'] = round(nm.get(k, 0) / nreq, 3) if nreq else ''
    return r


def fb_rows():
    cells = [r['cell'] for r in csv.DictReader(open('/home/niruthi/features/analysis/goalrw/goalrw_cells.csv'))]
    cells += sorted(os.path.basename(p) for p in glob.glob(str(FB / 'runs/2026111[7-9]-*-pydata-*-s1-goalrw')))
    fresh13 = {'compression_failures', 'vo', 'line', 'regression', 'relational', 'scales', 'describe', 'formats',
               'groupby_shift_diff', 'build_gettext', 'ext_doctest', 'ext_math', 'ext_napoleon_docstring'}
    for c in dict.fromkeys(cells):
        rd = FB / 'runs' / c
        if not (rd / 'accept_final.txt').exists():
            continue
        iid = json.load(open(rd / 'manifest.json'))['instance_id']
        td = FB / 'tasks' / iid
        task = iid.split('.')[2].removeprefix('test_')
        prompt = (rd / 'rounds/r00/prompt.txt').read_text()
        per_file, shape = gold_shape(td / 'gold.patch')
        met = json.load(open(rd / 'metrics.json'))
        rounds = list(csv.DictReader(open(rd / 'rounds.tsv'), delimiter='\t'))
        reg = json.load(open(rd / 'regression.json')) if (rd / 'regression.json').exists() else {}
        raw = reg.get('verdict', 'missing')
        adj = 'no_regression (flaky/timeout rerun: %s)' % REG_ADJUST[c] if c in REG_ADJUST else raw
        yield dict(bench='FeatureBench', repo=iid.split('__')[0], task=task, cell=c, subset='fresh' if (task in fresh13 or 'pydata' in iid) else 'seen_other_arm',
                   prompt='goal-only rewrite', **shape, cue_files=cue_files(list(per_file), prompt),
                   cue_tokens=len(code_tokens(prompt)), _gold=td / 'gold.patch', _diff=rd / 'diff.patch',
                   accept_final='PASS' in (rd / 'accept_final.txt').read_text().split('f2p=')[1][:4] and 'p2p=PASS' in (rd / 'accept_final.txt').read_text(),
                   r0_pass=rounds[0]['accept'] == 'PASS', rounds=len(rounds), cost_usd=round(float(rounds[-1]['cum_usd']), 4),
                   wall_s=round(met.get('wall_ms', 0) / 1000), regression_raw=raw, regression_n=reg.get('n_regressions', ''),
                   regression_adj=adj, regression_scope='touched-module tests, gold vs agent tree', **nav_row('featurebench', c))


def sbp_rows():
    for rd in sorted(list(SBP.glob('runs/2026*-s1'))+list(SBP.glob('runs/2026*-s1-verb'))):
        if not (rd / 'accept_final.txt').exists():
            continue
        c = rd.name
        iid = json.load(open(rd / 'manifest.json'))['instance_id']
        td = SBP / 'tasks' / iid
        repo = iid.split('__')[0].removeprefix('instance_')
        task = (repo + '-' + re.search(r'-([0-9a-f]{8})', iid).group(1))
        prompt = (rd / 'rounds/r00/prompt.txt').read_text()
        per_file, shape = gold_shape(td / 'gold.patch')
        met = json.load(open(rd / 'metrics.json'))
        rounds = list(csv.DictReader(open(rd / 'rounds.tsv'), delimiter='\t'))
        acc = (rd / 'accept_final.txt').read_text()
        f2p_p, f2p_t = map(int, re.search(r'f2p=(\d+)/(\d+)', acc).groups())
        p2p_p, p2p_t = map(int, re.search(r'p2p=(\d+)/(\d+)', acc).groups())
        p2p = p2p_p == p2p_t
        reg = 'not_measured (0 P2P tests)' if p2p_t == 0 else ('no_regression' if p2p else 'P2P_FAIL')
        yield dict(bench='SWE-bench Pro', repo=repo, task=task, cell=c, subset='batch3' if c.endswith('-verb') else ('nohint' if 'protonmail' in iid else 'batch1'),
                   prompt='benchmark text verbatim', **shape, cue_files=cue_files(list(per_file), prompt),
                   cue_tokens=len(code_tokens(prompt)), _gold=td / 'gold.patch', _diff=rd / 'diff.patch',
                   accept_final=f2p_p == f2p_t and p2p, p2p_tests=p2p_t, r0_pass=rounds[0]['accept'] == 'PASS', rounds=len(rounds),
                   cost_usd=round(float(rounds[-1]['cum_usd']), 4), wall_s=round(met.get('wall_ms', 0) / 1000),
                   regression_raw=reg, regression_n='', regression_adj=reg,
                   regression_scope='benchmark P2P tests only (%d)' % p2p_t,
                   **nav_row('swebench_pro', c))


def main():
    rows = list(fb_rows()) + list(sbp_rows())
    for r in rows:
        g, a = OS.added(r.pop('_gold')), OS.added(r.pop('_diff'))
        ov = OS.overlap(g, a or {})
        r.update(gold_lines_added=ov['gold_lines'], recall_all=ov['recall_all'], recall_long=ov['recall_long'],
                 gold_comments=ov['gold_comments'], recall_comments=ov['recall_comments'], precision=ov['precision_all'],
                 files_outside_gold=ov['agent_files_outside_gold'])
    keys = list(dict.fromkeys(k for r in rows for k in r))
    with open(HERE / 'cells.csv', 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=keys); w.writeheader(); w.writerows(rows)
    for r in rows:
        print(f"{r['bench'][:4]} {r['task'][:24]:24} files={r['n_files']:3} dos={r['dos_dir']!s:5} cue={r['cue_files']!s:5} "
              f"rec={r['recall_all']!s:6} cmt={r['gold_comments']:3}/{r['recall_comments']!s:6} r0={r['r0_pass']!s:5} "
              f"cost={r['cost_usd']:7} calls={r['tool_calls']:4} srch={r['searches']:4} tests={r['test_runs']:3} "
              f"reg={r['regression_adj'][:14]}")


if __name__ == '__main__':
    main()
