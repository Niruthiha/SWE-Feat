#!/usr/bin/env python3
"""extract_all.py -- identical navigation measures for both benchmarks.

FeatureBench: goal-only (goalrw) cells; repo at /testbed; prompt = prompt_goalrw.txt.
SWE-bench Pro V2: every finished s1 cell (batch 1 + no-hint); repo at /app; prompt = prompt.txt (benchmark text verbatim).
Writes auto/<bench>/<cell>.json and nav.csv (one row per cell).
"""
import csv, glob, json, os, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import dv_extract_common as X

FB = '/home/niruthi/features/experiment-featurebench'
SBP = '/home/niruthi/features/experiment-swebench-pro'


def fb_cells():
    cells = [r['cell'] for r in csv.DictReader(open('/home/niruthi/features/analysis/goalrw/goalrw_cells.csv'))]
    cells += sorted(os.path.basename(p) for p in glob.glob(f'{FB}/runs/2026111[7-9]-*-pydata-*-s1-goalrw'))
    return [c for c in dict.fromkeys(cells) if os.path.exists(f'{FB}/runs/{c}/accept_final.txt')]


def sbp_cells():
    return sorted(os.path.basename(p) for p in glob.glob(f'{SBP}/runs/2026*-s1')+glob.glob(f'{SBP}/runs/2026*-s1-verb') if os.path.exists(f'{p}/accept_final.txt'))


def run(bench, root, repo, prompt, cells):
    X.ROOT, X.REPO, X.PROMPT = root, repo, prompt
    out = HERE / 'auto' / bench; out.mkdir(parents=True, exist_ok=True)
    rows = []
    for c in cells:
        rd = f'{root}/runs/{c}'
        iid = json.load(open(f'{rd}/manifest.json'))['instance_id']
        o = X.analyse(rd, iid)
        json.dump(o, open(out / f'{c}.json', 'w'), indent=1, default=list)
        a, d, orr = o['activity'], o['discovery'], o['orientation']
        nm = d.get('nav_methods') or {}
        rows.append(dict(bench=bench, cell=c, iid=iid, tool_calls=a['tool_calls'], api_turns=a.get('api_turns'),
                         searches=a['searches'], files_read_full=a['files_read_full'], files_read_part=a['files_read_part'],
                         files_grep_only=a['files_grep_only'],
                         gold_found_pre_edit=d['share_gold_found_before_first_edit'],
                         gold_found_by_done=d['share_gold_found_by_done'],
                         orient_calls=orr['calls_before_first_edit'], orient_ctx=orr['ctx_tokens_before_first_edit'],
                         rework=o['rework']['n'], **{f'nav_{k}': v for k, v in nm.items()}))
    return rows


if __name__ == '__main__':
    rows = run('featurebench', FB, '/testbed', 'prompt_goalrw.txt', fb_cells())
    rows += run('swebench_pro', SBP, '/app', 'prompt.txt', sbp_cells())
    keys = list(dict.fromkeys(k for r in rows for k in r))
    with open(HERE / 'nav.csv', 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=keys, restval=0); w.writeheader(); w.writerows(rows)
    for r in rows:
        print(r['bench'][:3], r['cell'][16:60], r['tool_calls'], r['searches'], r['gold_found_pre_edit'], r['gold_found_by_done'],
              {k[4:]: v for k, v in r.items() if k.startswith('nav_')})
