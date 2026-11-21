#!/usr/bin/env python3
"""agentshape.py -- scattering of the AGENT'S final change (runs/<cell>/diff.patch), not the reference patch -> agentshape.csv.
Tree: pre-gold source (FB: upstream base with gold reversed; SWE-Pro: instance commit, gold reversed if already applied),
then the agent's diff.patch applied on top. Shape (files, packages, dispersion, functions, lines, focus) from the diff text;
call-graph distances and module independence from the post-agent tree. Gold is only used to rebuild the pre-task tree."""
import csv, os, subprocess, sys
import callgraph as cg, patchshape as ps

HERE = os.path.dirname(os.path.abspath(__file__)); F = cg.F
out_p = f'{HERE}/agentshape.csv'
want = sys.argv[1:]
old = {r['cell']: r for r in csv.DictReader(open(out_p))} if os.path.exists(out_p) else {}
for r in csv.DictReader(open(f'{HERE}/cells.csv')):
    if want and not any(w in r['cell'] for w in want): continue
    ex, iid, repo, base, gold = cg.task_of(r)
    diff = f'{F}/{ex}/runs/{r["cell"]}/diff.patch'
    d = f'{cg.REPOS}/{repo.replace("/", "__")}'
    row = dict(cell=r['cell'], bench=r['bench'], repo=repo)
    try:
        row.update(ps.shape(diff))
        cg.git(d, 'checkout', '-q', '-f', cg.git(d, 'rev-parse', base).stdout.strip()); cg.git(d, 'clean', '-qfdx')
        if cg.git(d, 'apply', '-R', '--check', gold, check=False).returncode == 0:
            cg.git(d, 'apply', '-R', gold)  # tree already contains gold -> back to pre-task
        # apply only production-code hunks (tests are not measured; masked/hidden test files may conflict)
        keep, blocks, cur = [], [], None
        for l in open(diff, errors='replace'):
            if l.startswith('diff --git'):
                p = l.split(' b/')[-1].strip(); cur = ps.CODE.search(p) and not ps.is_test(p)
            if cur: keep.append(l)
        diff = f'{HERE}/.agentdiff.tmp'; open(diff, 'w').write(''.join(keep))
        if cg.git(d, 'apply', '--whitespace=nowarn', diff, check=False).returncode:
            p = subprocess.run(['patch', '-p1', '--fuzz=3', '-s', '-d', d, '-i', diff], capture_output=True, text=True)
            if p.returncode: raise RuntimeError('agent diff does not apply: ' + p.stdout[-200:])
            row['apply'] = 'patch --fuzz'
        else: row['apply'] = 'git apply'
        exts = sorted({os.path.splitext(l.split(' b/')[-1].strip())[1] for l in open(diff, errors='replace')
                       if l.startswith('diff --git')} & set(cg.FRONT))
        if not exts: raise RuntimeError('no code files in agent diff')
        fam = ['.ts', '.tsx', '.js', '.jsx'] if set(exts) & {'.ts', '.tsx', '.js', '.jsx'} else exts
        row.update(cg.analyse(d, fam, diff)); row['status'] = 'ok'
    except Exception as e:
        row['status'] = f'error: {e}'[:300]
    old[r['cell']] = row
    print(r['cell'][:55], row.get('n_files'), row.get('n_packages'), row.get('dos_pkg'), row.get('cg_median_nn_dist'),
          row.get('mod_share_pairs_no_dep'), row['status'][:80], flush=True)
keys = list(dict.fromkeys(k for v in old.values() for k in v))
with open(out_p, 'w', newline='') as fh:
    w = csv.DictWriter(fh, fieldnames=keys); w.writeheader(); w.writerows(old.values())
