#!/usr/bin/env python3
"""make_page.py -- builds page/index.html (shareable report) from cells.csv + stats_out.json + verify/verify_out.txt.
Regressions deliberately left out (user decision 2026-11-18)."""
import csv, json, math, html
from statistics import median
from pathlib import Path

HERE = Path(__file__).resolve().parent
rows = list(csv.DictReader(open(HERE / 'cells.csv')))
_ps = {r['cell']: r for r in csv.DictReader(open(HERE / 'patchshape.csv'))}
for _r in rows:
    _r.update({k: v for k, v in _ps[_r['cell']].items() if k != 'cell'})
_beh = {r['cell']: r for r in csv.DictReader(open(HERE / 'behaviour.csv'))}
for _r in rows:
    _r.update({k: v for k, v in _beh[_r['cell']].items() if k not in ('cell', 'bench')})
import scatterfig as SF
SF.attach(rows)
SF.attach_attempt1(rows)
_PS, _PGRID, _PTBL, _PFAIL = SF.pass_section(rows)
SF.attach_tech(rows); SF.attach_tasktype(rows); _TTR, _TTG, _TTB = SF.tasktype_section(rows); _TC = SF.tech_corr(rows)[1]; _CT = SF.corr_table(rows); _NC = SF.navcorr(rows); _QC, _QCt = SF.qsummary('corr'); _QN, _QNt = SF.qsummary('nav'); _QT, _QTt = SF.qsummary('tech'); _TM = SF.tech_medians(rows)
S = json.load(open(HERE / 'stats_out.json'))
FB = [r for r in rows if r['bench'] == 'FeatureBench']
SB = [r for r in rows if r['bench'] != 'FeatureBench']
import os
if not os.environ.get('DRY'): assert S['n_fb'] == len(FB) and S['n_sbp'] == len(SB), 'stats_out.json is stale'


def f(r, k):
    try:
        return float(r[k])
    except (ValueError, TypeError, KeyError):
        return None


def vals(g, k):
    return [v for v in (f(r, k) for r in g) if v is not None]


def med(g, k):
    v = vals(g, k)
    return median(v) if v else None


def fmt(x, d=2):
    if x is None:
        return '–'
    if isinstance(x, str):
        return x
    if abs(x) >= 100:
        return f'{x:,.0f}'
    return f'{x:.{d}f}'


def pf(p):
    if p is None:
        return '–'
    return '<.001' if p < 0.001 else f'{p:.3f}'


E = html.escape
LABEL = {'cost_usd': 'Cost (USD)', 'api_turns': 'API turns', 'tool_calls': 'Tool calls', 'searches': 'Searches (grep/glob/find)',
         'test_runs': 'Test runs', 'files_opened': 'Files opened', 'files_read_full': 'Files read in full',
         'orient_calls': 'Calls before first edit', 'orient_searches': 'Searches before first edit',
         'gold_found_pre_edit': 'Gold files found before first edit (share)', 'gold_found_by_done': 'Gold files found by end (share)',
         'navshare_search': 'Gold files first found by search', 'navshare_following_code': 'Gold files first found by following code',
         'navshare_recall': 'Gold files edited without being looked up', 'navshare_not_found': 'Gold files never located',
         'navshare_benchmark_clue': 'Gold files found from a benchmark clue', 'rework': 'Rework (re-edits)', 'wall_s': 'Wall time (s)',
         'recall_all': 'Gold lines reproduced verbatim', 'recall_long': 'Long gold lines reproduced', 'recall_comments': 'Gold comment lines reproduced',
         'precision': 'Agent lines that are gold lines', 'n_files': 'Gold files touched', 'dos_dir': 'Directory dispersion (1−HHI)',
         'log_impl': 'Gold patch size (log lines)', 'cue_files': 'Gold files named in prompt', 'cue_tokens': 'Code-shaped tokens in prompt',
         'log_cost': 'Cost (log)'}

# ---------------------------------------------------------------- charts (inline SVG, tokens via CSS classes)
W = 640


def strip(key, title, unit='', log=False, pct=False, h=150):
    """dot strip per benchmark, median tick."""
    groups = [('FeatureBench', FB, 's1'), ('SWE-bench Pro', SB, 's2')]
    allv = [v for _, g, _ in groups for v in vals(g, key)]
    lo, hi = min(allv), max(allv)
    if log:
        lo, hi = max(lo, 1e-3), hi
        tr = lambda v: (math.log10(max(v, lo)) - math.log10(lo)) / ((math.log10(hi) - math.log10(lo)) or 1)
    else:
        lo = 0 if lo >= 0 else lo
        hi = 1 if pct else hi
        tr = lambda v: (v - lo) / ((hi - lo) or 1)
    L, R = 120, 24
    x = lambda v: L + tr(v) * (W - L - R)
    out = [f'<svg viewBox="0 0 {W} {h}" role="img" aria-label="{E(title)}">']
    # ticks
    if log:
        t = 10 ** math.floor(math.log10(lo))
        ticks = []
        while t <= hi * 1.001:
            for m in (1, 2, 5):
                if lo <= t * m <= hi:
                    ticks.append(t * m)
            t *= 10
    else:
        n = 5
        ticks = [lo + (hi - lo) * i / n for i in range(n + 1)]
    for t in ticks:
        lab = f'{t:.0%}' if pct else (f'{t:g}' if log else (f'{t:.2g}' if hi - lo < 10 else f'{t:.0f}'))
        out.append(f'<line class="grid" x1="{x(t):.1f}" x2="{x(t):.1f}" y1="14" y2="{h-26}"/>'
                   f'<text class="tick" x="{x(t):.1f}" y="{h-10}" text-anchor="middle">{unit if unit=="$" else ""}{lab}</text>')
    band = (h - 40) / 2
    for i, (name, g, cls) in enumerate(groups):
        cy = 14 + band * i + band / 2
        out.append(f'<text class="lab" x="{L-12}" y="{cy+4:.1f}" text-anchor="end">{name}</text>')
        pts = sorted(((f(r, key), r) for r in g if f(r, key) is not None), key=lambda p: p[0])
        # jitter: simple beeswarm by stacking near-equal values
        placed = []
        for v, r in pts:
            px = x(v); off = 0; k = 0
            while any(abs(px - qx) < 9 and abs(off - qo) < 9 for qx, qo in placed):
                k += 1; off = ((k + 1) // 2) * 8 * (1 if k % 2 else -1)
            placed.append((px, off))
            vv = f'{v:.0%}' if pct else (f'${v:.2f}' if unit == '$' else fmt(v))
            tip = f'{r["task"]} ({r["repo"]}) · {vv}'
            out.append(f'<circle class="{cls} dot" cx="{px:.1f}" cy="{cy+off:.1f}" r="5" data-tip="{E(tip)}"/>')
        m = median([v for v, _ in pts])
        out.append(f'<line class="medtick" x1="{x(m):.1f}" x2="{x(m):.1f}" y1="{cy-band/2+6:.1f}" y2="{cy+band/2-6:.1f}"/>')
    out.append('</svg>')
    return ''.join(out)


def scatter(xk, yk, xlab, ylab, logy=True, h=320):
    L, R, T, B = 56, 20, 16, 44
    pts = [(f(r, xk), f(r, yk), r) for r in rows if f(r, xk) is not None and f(r, yk) is not None]
    ys = [p[1] for p in pts]
    ylo, yhi = (min(ys), max(ys))
    ty = (lambda v: (math.log10(v) - math.log10(ylo)) / (math.log10(yhi) - math.log10(ylo))) if logy else (lambda v: (v - ylo) / (yhi - ylo))
    X = lambda v: L + v * (W - L - R)
    Y = lambda v: T + (1 - ty(v)) * (h - T - B)
    out = [f'<svg viewBox="0 0 {W} {h}" role="img" aria-label="{E(ylab)} by {E(xlab)}">']
    for t in [0, .25, .5, .75, 1]:
        out.append(f'<line class="grid" x1="{X(t):.1f}" x2="{X(t):.1f}" y1="{T}" y2="{h-B}"/><text class="tick" x="{X(t):.1f}" y="{h-B+16}" text-anchor="middle">{t:.0%}</text>')
    for t in [1, 2, 5, 10, 20, 50, 100, 200]:
        if ylo <= t <= yhi:
            out.append(f'<line class="grid" x1="{L}" x2="{W-R}" y1="{Y(t):.1f}" y2="{Y(t):.1f}"/><text class="tick" x="{L-8}" y="{Y(t)+4:.1f}" text-anchor="end">{t}</text>')
    out.append(f'<text class="axl" x="{(L+W-R)/2}" y="{h-6}" text-anchor="middle">{E(xlab)}</text>'
               f'<text class="axl" transform="translate(14 {(T+h-B)/2}) rotate(-90)" text-anchor="middle">{E(ylab)}</text>')
    for xv, yv, r in pts:
        cls = 's1' if r['bench'] == 'FeatureBench' else 's2'
        tip = f'{r["task"]} ({r["repo"]}) · recall {xv:.0%} · {int(yv)} tool calls'
        out.append(f'<circle class="{cls} dot ring" cx="{X(xv):.1f}" cy="{Y(yv):.1f}" r="6" data-tip="{E(tip)}"/>')
    out.append('</svg>')
    return ''.join(out)


NAV = [('search', ['search', 'following_code+search'], 's1', 'Search'), ('code', ['following_code'], 's3', 'Following code'),
       ('other', ['listing', 'tests', 'other_output', 'benchmark_clue'], 's4', 'Listing / tests / clue'),
       ('recall', ['recall'], 's5', 'Edited without lookup'), ('nf', ['not_found'], 's7', 'Never located')]


def navbars():
    h, L, R = 130, 120, 70
    out = [f'<svg viewBox="0 0 {W} {h}" role="img" aria-label="How gold files were first found">']
    for i, (name, g) in enumerate([('FeatureBench', FB), ('SWE-bench Pro', SB)]):
        tot = {c: sum(int(r[f'nav_{k}'] or 0) for r in g for k in ks) for c, ks, _, _ in NAV}
        n = sum(tot.values()); y = 16 + i * 52; xx = L
        out.append(f'<text class="lab" x="{L-12}" y="{y+19}" text-anchor="end">{name}</text>')
        for c, ks, cls, lab in NAV:
            w = (W - L - R) * tot[c] / n
            if w > 0:
                out.append(f'<rect class="{cls} dot" x="{xx:.1f}" y="{y}" width="{max(w-2,1):.1f}" height="28" rx="3" '
                           f'data-tip="{E(name)} · {E(lab)}: {tot[c]} of {n} files ({tot[c]/n:.0%})"/>')
                if w > 34:
                    out.append(f'<text class="inbar" x="{xx+w/2-1:.1f}" y="{y+18}" text-anchor="middle">{tot[c]/n:.0%}</text>')
            xx += w
        out.append(f'<text class="tick" x="{W-R+8}" y="{y+19}">n={n} files</text>')
    out.append('</svg>')
    leg = ''.join(f'<span class="key"><i class="{cls}"></i>{lab}</span>' for _, _, cls, lab in NAV)
    return ''.join(out), leg


def cmtbars():
    rs = sorted([r for r in rows if f(r, 'recall_comments') is not None], key=lambda r: (r['bench'] != 'FeatureBench', -f(r, 'recall_comments')))
    bh, gap, L = 16, 4, 190
    h = len(rs) * (bh + gap) + 34
    X = lambda v: L + v * (W - L - 50)
    out = [f'<svg viewBox="0 0 {W} {h}" role="img" aria-label="Comment-line match per cell">']
    for t in [0, .25, .5, .75, 1]:
        out.append(f'<line class="grid" x1="{X(t):.1f}" x2="{X(t):.1f}" y1="4" y2="{h-26}"/><text class="tick" x="{X(t):.1f}" y="{h-10}" text-anchor="middle">{t:.0%}</text>')
    for i, r in enumerate(rs):
        y = 4 + i * (bh + gap); v = f(r, 'recall_comments'); cls = 's1' if r['bench'] == 'FeatureBench' else 's2'
        nm = r['task'] if r['bench'] == 'FeatureBench' else r['task'].replace('protonmail-', 'proton-')
        out.append(f'<text class="lab sm" x="{L-8}" y="{y+12}" text-anchor="end">{E(nm[:26])}</text>')
        out.append(f'<rect class="{cls} dot" x="{L}" y="{y}" width="{max(X(v)-L,2):.1f}" height="{bh}" rx="3" '
                   f'data-tip="{E(r["task"])}: {v:.0%} of {r["gold_comments"]} gold comment lines"/>')
        out.append(f'<text class="tick" x="{max(X(v),L+2)+6:.1f}" y="{y+12}">{v:.0%} <tspan class="muted">/{r["gold_comments"]}</tspan></text>')
    out.append('</svg>')
    return ''.join(out)


# ---------------------------------------------------------------- tables
A = S['A_benchmark_difference']; B = S['B_benchmark_diff_controlling_memorisation']; C = S['C_iv_dv_within_benchmark']
D = S['D_memorisation_vs_effort']; ER = S['E_rates']


def sig(q):
    return ' class="sig"' if q is not None and q < 0.05 else ''


def tA(keys):
    t = ['<table><thead><tr><th>Variable</th><th>FB median</th><th>SWE-Pro median</th><th>Diff (FB−SWE) 95% CI</th><th>Cliff’s δ</th><th>p</th><th>q (BH)</th></tr></thead><tbody>']
    for k in keys:
        v = A.get(k)
        if not v:
            continue
        ci = v.get('ci95') or [None, None]
        t.append(f'<tr{sig(v["q"])}><td>{LABEL.get(k,k)}</td><td>{fmt(v["median_fb"])}</td><td>{fmt(v["median_sbp"])}</td>'
                 f'<td>{fmt(ci[0])} to {fmt(ci[1])}</td><td>{v["cliffs_delta"]:+.2f}</td><td>{pf(v["p"])}</td><td>{pf(v["q"])}</td></tr>')
    return ''.join(t) + '</tbody></table>'


def tB():
    dvs = list(dict.fromkeys(k.split(' | ')[0] for k in B))
    t = ['<table><thead><tr><th>Outcome</th><th>controls: recall (all lines)</th><th>recall (long lines)</th><th>recall + patch size</th></tr></thead><tbody>']
    for d in dvs:
        cells = []
        for c in ('recall_all', 'recall_long', 'recall_all+log_impl'):
            v = B.get(f'{d} | {c}')
            cells.append(f'<td{sig(v["q"])}>β {v["coef_bench_rank"]:+.1f} · q {pf(v["q"])}</td>' if v else '<td>–</td>')
        t.append(f'<tr><td>{LABEL.get(d,d)}</td>{"".join(cells)}</tr>')
    return ''.join(t) + '</tbody></table>'


def tC(prefix, ivs, dvs):
    t = ['<table class="matrix"><thead><tr><th>Task property ↓ / outcome →</th>' + ''.join(f'<th>{LABEL.get(d,d)}</th>' for d in dvs) + '</tr></thead><tbody>']
    for iv in ivs:
        row = [f'<td>{LABEL.get(iv,iv)}</td>']
        for d in dvs:
            v = C.get(f'{prefix}: {iv} ~ {d}')
            if not v:
                row.append('<td>–</td>'); continue
            p, pr = v['plain'], (v.get('partial_recall') or {'rho': float('nan'), 'q': None})
            if not p or p.get('rho') is None or p['rho'] != p['rho']:
                row.append('<td>–</td>'); continue
            if pr.get('rho') is None: pr = {'rho': float('nan'), 'q': None}
            a = min(abs(p['rho']), 1)
            tone = 'pos' if p['rho'] > 0 else 'neg'
            row.append(f'<td class="heat {tone}{" sig" if (p["q"] or 1) < .05 else ""}" style="--a:{a:.2f}" title="partial on recall ρ={"–" if pr["rho"]!=pr["rho"] else format(pr["rho"],"+.2f")}, q={pf(pr["q"])}">'
                       f'{p["rho"]:+.2f}<small>q {pf(p["q"])} · |rec {"–" if pr["rho"]!=pr["rho"] else format(pr["rho"],"+.2f")}</small></td>')
        t.append('<tr>' + ''.join(row) + '</tr>')
    return ''.join(t) + '</tbody></table>'


def tD():
    t = ['<table><thead><tr><th>Within</th><th>Memorisation ~ effort</th><th>ρ</th><th>p</th><th>q</th><th>partial on size ρ</th></tr></thead><tbody>']
    for k, v in D.items():
        if not isinstance(v, dict) or 'rho' not in v:
            continue
        w, rel = k.split(': ', 1)
        a, b = rel.split(' ~ ')
        ps = v.get('partial_size', {}).get('rho')
        t.append(f'<tr{sig(v.get("q"))}><td>{ {"fb":"FeatureBench","sbp":"SWE-bench Pro","pooled":"Both (pooled)"}.get(w,w)}</td>'
                 f'<td>{LABEL.get(a,a)} ~ {LABEL.get(b,b)}</td><td>{v["rho"]:+.2f}</td><td>{pf(v["p"])}</td><td>{pf(v.get("q"))}</td><td>{fmt(ps)}</td></tr>')
    return ''.join(t) + '</tbody></table>'


def tLORO():
    L = S['robust_leave_one_repo_out']
    t = ['<table><thead><tr><th>Within FeatureBench ρ, dropping one repo at a time</th>' + ''.join(f'<th>−{E(r)}</th>' for r in next(iter(L.values()))) + '</tr></thead><tbody>']
    for k, v in L.items():
        w, rel = k.split(': ', 1); a, b = rel.split(' ~ ')
        t.append(f'<tr><td>{LABEL.get(a,a)} ~ {LABEL.get(b,b)}</td>' + ''.join(f'<td>{x:+.2f}</td>' for x in v.values()) + '</tr>')
    return ''.join(t) + '</tbody></table>'


def cell_table():
    cols = [('bench', 'Benchmark'), ('repo', 'Repo'), ('task', 'Task'), ('n_files', 'Gold files'), ('impl_lines', 'Gold lines'),
            ('dos_dir', 'Dispersion'), ('cue_files', 'Files named'), ('recall_all', 'Line recall'), ('recall_comments', 'Comment match'),
            ('gold_comments', 'Gold comments'), ('tool_calls', 'Tool calls'), ('searches', 'Searches'), ('test_runs', 'Test runs'),
            ('gold_found_pre_edit', 'Found pre-edit'), ('navshare_not_found', 'Never located'), ('r0_pass', 'Pass round 0'),
            ('rounds', 'Rounds'), ('cost_usd', 'Cost $')]
    t = ['<table class="cells"><thead><tr>' + ''.join(f'<th data-k="{k}">{l}</th>' for k, l in cols) + '</tr></thead><tbody>']
    for r in rows:
        tds = []
        for k, _ in cols:
            v = r[k]
            if k in ('recall_all', 'recall_comments', 'cue_files', 'gold_found_pre_edit', 'navshare_not_found') and v not in ('', None):
                v = f'{float(v):.0%}'
            elif k == 'bench':
                v = 'FB' if v == 'FeatureBench' else 'SWE-Pro'
            elif k == 'r0_pass':
                v = 'yes' if v == 'True' else 'no'
            tds.append(f'<td>{E(str(v)) if v != "" else "–"}</td>')
        t.append('<tr>' + ''.join(tds) + '</tr>')
    return ''.join(t) + '</tbody></table>'


# ---------------------------------------------------------------- numbers for prose
mFBc, mSBc = med(FB, 'tool_calls'), med(SB, 'tool_calls')
mFBr, mSBr = med(FB, 'recall_all'), med(SB, 'recall_all')
mFBcm, mSBcm = med(FB, 'recall_comments'), med(SB, 'recall_comments')
nSBcm = len(vals(SB, 'recall_comments'))
cost_fb, cost_sb = med(FB, 'cost_usd'), med(SB, 'cost_usd')
r0 = ER['r0_pass']
mr = S['power_min_rho']
navsvg, navleg = navbars()
repos_fb = sorted({r['repo'] for r in FB}); repos_sb = sorted({r['repo'] for r in SB})
verify_txt = (HERE / 'verify/verify_out.txt').read_text() if (HERE / 'verify/verify_out.txt').exists() else ''

KEY_A = ['tool_calls', 'searches', 'test_runs', 'files_opened', 'files_read_full', 'orient_calls', 'gold_found_pre_edit', 'gold_found_by_done',
         'navshare_search', 'navshare_following_code', 'navshare_recall', 'navshare_not_found', 'rework', 'cost_usd', 'wall_s']
KEY_M = ['recall_all', 'recall_long', 'recall_comments', 'precision', 'n_files', 'log_impl', 'dos_dir', 'cue_files', 'cue_tokens']

# ---------------------------------------------------------------- per-benchmark sections (added 2026-11-18)
from scipy.stats import mannwhitneyu
LABEL.update({'segshare_search': 'Actions that are searches', 'segshare_grep_on_file': 'Actions grepping a named file',
              'segshare_read_part': 'Actions reading part of a file', 'segshare_read_full': 'Actions reading a whole file',
              'segshare_list': 'Actions listing dirs', 'segshare_edit': 'Actions that edit', 'segshare_test_run': 'Actions running tests',
              'segshare_probe': 'Actions running probe scripts', 'segshare_git_diff': 'Actions viewing git diff',
              'srchshare_grep_recursive': 'Searches: recursive grep -r', 'srchshare_grep_pipe_or_file': 'Searches: grep on file / pipe',
              'srchshare_find': 'Searches: find', 'srchshare_git_ls_files': 'Searches: git ls-files', 'srchshare_git_grep': 'Searches: git grep',
              'editshare_python_script': 'Edits via python script', 'editshare_shell_redirect': 'Edits via heredoc / redirect',
              'editshare_sed_perl_inplace': 'Edits via sed -i', 'editshare_edit_tool': 'Edits via Edit tool',
              'read_part_per_full': 'Partial reads per whole-file read', 'searches_per_edit': 'Searches per edit',
              'share_ctx_before_first_edit': 'Share of context read before first edit', 'files_opened_before_first_edit': 'Files opened before first edit',
              'probes': 'Probe scripts run', 'files_grep_only': 'Files seen only via grep lines', 'files_read_part': 'Files read partially',
              'output_tokens': 'Output tokens', 'cache_read_tokens': 'Context tokens re-read (cache)', 'rounds': 'Rounds used',
              'files_outside_gold': 'Files edited outside gold', 'gold_lines_added': 'Gold lines added', 'impl_lines': 'Gold lines changed',
              'n_dirs': 'Gold directories', 'listings': 'Directory listings', 'api_turns': 'API turns', 'gold_comments': 'Gold comment lines',
              'files_edited_any': 'Files edited', 'test_cases_added': 'Test cases added', 'r0_pass': 'Passed round 0 (share)'})
GROUPS = [
    ('Task properties (IVs)', ['n_files', 'impl_lines', 'n_dirs', 'dos_dir', 'cue_files', 'cue_tokens']),
    ('Memorisation', ['recall_all', 'recall_long', 'recall_comments', 'gold_comments', 'precision', 'files_outside_gold']),
    ('Navigation', ['searches', 'orient_calls', 'orient_searches', 'files_opened', 'files_read_full', 'files_read_part', 'files_grep_only',
                    'listings', 'gold_found_pre_edit', 'gold_found_by_done', 'navshare_search', 'navshare_following_code',
                    'navshare_recall', 'navshare_not_found', 'share_ctx_before_first_edit', 'files_opened_before_first_edit']),
    ('Behaviour / technique', ['segshare_search', 'segshare_grep_on_file', 'segshare_read_part', 'segshare_read_full', 'segshare_edit',
                               'segshare_test_run', 'segshare_probe', 'srchshare_grep_recursive', 'srchshare_grep_pipe_or_file',
                               'srchshare_find', 'editshare_python_script', 'editshare_shell_redirect', 'editshare_sed_perl_inplace',
                               'read_part_per_full', 'searches_per_edit', 'probes', 'rework']),
    ('Effort & outcome', ['tool_calls', 'api_turns', 'test_runs', 'output_tokens', 'cache_read_tokens', 'cost_usd', 'wall_s', 'rounds', 'r0_pass']),
]
SHARE = lambda k: k.startswith(('recall', 'navshare', 'segshare', 'srchshare', 'editshare', 'gold_found', 'share_', 'cue_files')) or k in ('precision', 'dos_dir', 'r0_pass')


def num(r, k):
    if k == 'r0_pass':
        return 1.0 if r['r0_pass'] == 'True' else 0.0
    return f(r, k)


def gv(g, k):
    return [v for v in (num(r, k) for r in g) if v is not None]


def q4(v):
    import numpy as np
    return np.percentile(v, 25), np.percentile(v, 75)


def fv(k, x):
    if x is None:
        return '–'
    if k == 'r0_pass' or (SHARE(k) and k != 'dos_dir'):
        return f'{x:.0%}'
    if k == 'cost_usd':
        return f'${x:.2f}'
    if abs(x) >= 1e5:
        return f'{x/1e6:.2f}M'
    if float(x).is_integer():
        return f'{x:,.0f}'
    return fmt(x)


def desc_table(g):
    t = ['<table><thead><tr><th>Dependent / independent variable</th><th>n</th><th>median</th><th>IQR</th><th>min</th><th>max</th><th>mean</th></tr></thead><tbody>']
    for gname, ks in GROUPS:
        t.append(f'<tr class="grp"><td colspan="7">{gname}</td></tr>')
        for k in ks:
            v = gv(g, k)
            if not v:
                t.append(f'<tr><td>{LABEL.get(k,k)}</td><td>0</td><td colspan="5">undefined</td></tr>'); continue
            a, b = q4(v)
            t.append(f'<tr><td>{LABEL.get(k,k)}</td><td>{len(v)}</td><td>{fv(k,median(v))}</td><td>{fv(k,a)} – {fv(k,b)}</td>'
                     f'<td>{fv(k,min(v))}</td><td>{fv(k,max(v))}</td><td>{fv(k,sum(v)/len(v))}</td></tr>')
    return ''.join(t) + '</tbody></table>'


def bh(ps):
    n = len(ps); order = sorted(range(n), key=lambda i: ps[i]); q = [0] * n; m = 1
    for rank, i in reversed(list(enumerate(order, 1))):
        m = min(m, ps[i] * n / rank); q[i] = m
    return q


def cliff(a, b):
    return sum((x > y) - (x < y) for x in a for y in b) / (len(a) * len(b))


def compare_table():
    """Mann-Whitney (two-sided) + Cliff's delta for EVERY variable; BH within each variable group."""
    t = ['<table><thead><tr><th>Variable</th><th>FB median</th><th>SWE-Pro median</th><th>Cliff’s δ (FB vs SWE)</th><th>U</th><th>p</th><th>q (BH, group)</th></tr></thead><tbody>']
    for gname, ks in GROUPS:
        res = []
        for k in ks:
            a, b = gv(FB, k), gv(SB, k)
            if len(a) < 3 or len(b) < 3 or (len(set(a + b)) == 1):
                res.append((k, a, b, None, None, None)); continue
            u = mannwhitneyu(a, b, alternative='two-sided')
            res.append((k, a, b, cliff(a, b), u.statistic, u.pvalue))
        qs = bh([r[5] for r in res if r[5] is not None]); qi = iter(qs)
        t.append(f'<tr class="grp"><td colspan="7">{gname}</td></tr>')
        for k, a, b, d, U, p in res:
            q = next(qi) if p is not None else None
            t.append(f'<tr{sig(q)}><td>{LABEL.get(k,k)}</td><td>{fv(k,median(a)) if a else "–"}</td><td>{fv(k,median(b)) if b else "–"}</td>'
                     f'<td>{"–" if d is None else f"{d:+.2f}"}</td><td>{"–" if U is None else f"{U:.0f}"}</td><td>{pf(p)}</td><td>{pf(q)}</td></tr>')
    return ''.join(t) + '</tbody></table>'


TECHP = [(l, ['t_' + k], c) for k, l, c in SF.TECH]


def split_stack(parts, title):
    out = []
    for bn, short in (('FeatureBench', 'FeatureBench'), ('SWE-bench Pro', 'SWE-bench Pro')):
        g = SF.by_scatter([r for r in rows if r['bench'] == bn])
        out.append(f'<div style="min-width:0"><h5 style="margin:.4em 0">{short} (n = {len(g)})</h5>{stack(g, parts, f"{title} · {short}", pooled_bar=False)}</div>')
    return '<div class="grid2">' + ''.join(out) + '</div>'


def stack(g, parts, title, h=None, pooled_bar=True):
    """one 100% bar per cell + pooled bar. parts = [(label, [cols], cls)]; counts from columns (raw counts)."""
    rs = [r for r in g if sum(float(r[c] or 0) for _, cs, _ in parts for c in cs) > 0]
    bh_, gap, L, R = 15, 4, 170, 46
    h = (len(rs) + pooled_bar) * (bh_ + gap) + 30
    out = [f'<svg viewBox="0 0 {W} {h}" role="img" aria-label="{E(title)}">']
    def bar(y, label, vals_, bold=False):
        n = sum(v for _, v, _ in vals_); xx = L
        out.append(f'<text class="lab sm" x="{L-8}" y="{y+11}" text-anchor="end"{" font-weight=\"600\"" if bold else ""}>{E(label[:26])}</text>')
        for lab, v, cls in vals_:
            w = (W - L - R) * v / n if n else 0
            if w > 0:
                out.append(f'<rect class="{cls} dot" x="{xx:.1f}" y="{y}" width="{max(w-2,0.8):.1f}" height="{bh_}" rx="2" data-tip="{E(label)} · {E(lab)}: {v:g} ({v/n:.0%})"/>')
            xx += w
        out.append(f'<text class="tick" x="{W-R+6}" y="{y+11}">{n:g}</text>')
    pooled = [(lab, sum(float(r[c] or 0) for r in rs for c in cs), cls) for lab, cs, cls in parts]
    if pooled_bar: bar(4, 'All cells pooled', pooled, True)
    for i, r in enumerate(rs):
        bar(4 + (i + pooled_bar) * (bh_ + gap) + 4, r['task'].replace('protonmail-', 'proton-'), [(lab, sum(float(r[c] or 0) for c in cs), cls) for lab, cs, cls in parts])
    out.append('</svg>')
    leg = ''.join(f'<span class="key"><i class="{cls}"></i>{lab}</span>' for lab, _, cls in parts)
    return ''.join(out) + f'<div class="legend">{leg}</div>'


SEGP = [('Search', ['seg_search'], 's1'), ('Grep in a file', ['seg_grep_on_file'], 's3'), ('Read part of file', ['seg_read_part'], 's4'),
        ('Read whole file', ['seg_read_full'], 's2'), ('Edit', ['seg_edit'], 's5'), ('Run tests', ['seg_test_run'], 's7'),
        ('Probe / list / git', ['seg_probe', 'seg_list', 'seg_git_diff', 'seg_git_log'], 's8')]
SRCHP = [('grep -r over a tree', ['srch_grep_recursive'], 's1'), ('grep on a file or pipe', ['srch_grep_pipe_or_file'], 's3'),
         ('find', ['srch_find'], 's4'), ('git ls-files / git grep', ['srch_git_ls_files', 'srch_git_grep'], 's5')]
NAVP = [('Search', ['nav_search', 'nav_following_code+search'], 's1'), ('Following code', ['nav_following_code'], 's3'),
        ('Listing / tests / other output', ['nav_listing', 'nav_tests', 'nav_other_output'], 's4'), ('Benchmark clue', ['nav_benchmark_clue'], 's8'),
        ('Edited without lookup', ['nav_recall'], 's5'), ('Never located', ['nav_not_found'], 's7')]


def bench_section(tag, name, g, prefix, color):
    n = len(g); other_ok = prefix == 'fb'
    Dk = {k: v for k, v in D.items() if k.startswith(prefix + ':') and isinstance(v, dict) and 'rho' in v}
    dt = ['<table><thead><tr><th>Memorisation ~ effort</th><th>ρ</th><th>p</th><th>q</th><th>partial on size ρ</th></tr></thead><tbody>']
    for k, v in Dk.items():
        a, b = k.split(': ', 1)[1].split(' ~ ')
        dt.append(f'<tr{sig(v.get("q"))}><td>{LABEL.get(a,a)} ~ {LABEL.get(b,b)}</td><td>{v["rho"]:+.2f}</td><td>{pf(v["p"])}</td><td>{pf(v.get("q"))}</td><td>{fmt(v.get("partial_size",{}).get("rho"))}</td></tr>')
    dt = ''.join(dt) + '</tbody></table>'
    return f'''
<h2 id="{tag}" class="part"><span class="sw big" style="background:var(--{color})"></span>{name}</h2>
<p class="lede">{n} cells · repos: {", ".join(sorted({r["repo"] for r in g}))}. Median gold patch: {med(g,"n_files"):.0f} files, {med(g,"impl_lines"):.0f} lines. Round-0 pass {sum(r["r0_pass"]=="True" for r in g)}/{n}; all passed by the last round.</p>
<h3>Where the actions went</h3>
<p class="sub">Every Bash call is split into commands; each command is classified. One bar per cell, plus all cells pooled. The number at the right is the total commands.</p>
<div class="fig">{stack(g, SEGP, name + " action mix")}</div>
<div class="grid2">
<div class="fig"><h4>Search technique</h4><p class="sub">Which search command the agent used, share of search commands.</p>{stack(g, SRCHP, name + " search technique")}</div>
<div class="fig"><h4>How each gold file was first found</h4><p class="sub">Per required gold file, from the trace.</p>{stack(g, NAVP, name + " navigation")}</div>
</div>
<h3>All variables: descriptive statistics</h3>
<div class="tw">{desc_table(g)}</div>
<h3>Statistical tests within {name}</h3>
<p>Spearman ρ between task properties and outcomes; permutation p (20,000 resamples); q = Benjamini-Hochberg across the family. The small line in each cell is ρ partialled on line recall, i.e. the same association holding memorisation fixed. Smallest |ρ| detectable at 80% power with n={n}: <b>{mr[prefix]:.2f}</b>.</p>
<div class="tw">{tC(prefix,["n_files","dos_dir","log_impl","cue_files"],["log_cost","tool_calls","searches","test_runs","files_opened","gold_found_pre_edit","navshare_search","recall_all"])}</div>
<h4>Does verbatim recall go with effort?</h4>
<div class="tw">{dt}</div>
'''

# ---------------------------------------------------------------- v3: one big comparison (2026-11-18)
import random
LABEL.update({'n_functions': 'Functions / classes touched', 'n_new_functions': 'New functions / classes', 'n_hunks': 'Hunks',
              'n_packages': 'Packages (top-2 path dirs)', 'dos_file': 'Dispersion over files (1−HHI)', 'dos_pkg': 'Dispersion over packages (1−HHI)',
              'n_files_created': 'Files created', 'files_opened': 'Files opened', 'n_required': 'Gold files required'})
GROUPS3 = [
    ('Task: prompt cues', ['cue_files', 'cue_tokens']),
    ('Memorisation (verbatim overlap with gold)', ['recall_all', 'recall_long', 'recall_comments', 'gold_comments', 'precision', 'files_outside_gold']),
    ('Navigation', ['searches', 'orient_calls', 'orient_searches', 'files_opened', 'files_read_full', 'files_read_part', 'listings',
                    'gold_found_pre_edit', 'gold_found_by_done', 'navshare_search', 'navshare_following_code', 'navshare_recall', 'navshare_not_found']),
    ('Effort, cost and time', ['tool_calls', 'api_turns', 'test_runs', 'probes', 'rework', 'output_tokens', 'cache_read_tokens', 'cost_usd', 'wall_s']),
    ('Outcome', ['r0_pass', 'rounds']),
]
_rng = random.Random(20261118)


def boot_delta(a, b, B=2000):
    ds = sorted(cliff([_rng.choice(a) for _ in a], [_rng.choice(b) for _ in b]) for _ in range(B))
    return ds[int(.025 * B)], ds[int(.975 * B) - 1]


def perm_p(a, b, B=5000):
    d0 = abs(cliff(a, b)); pool = a + b; n = len(a); k = 0
    for _ in range(B):
        _rng.shuffle(pool)
        if abs(cliff(pool[:n], pool[n:])) >= d0 - 1e-12: k += 1
    return (k + 1) / (B + 1)


def mag(d):
    a = abs(d)
    return 'negligible' if a < .147 else 'small' if a < .33 else 'medium' if a < .474 else 'large'


RES = []
for gname, ks in GROUPS3:
    gr = []
    for k in ks:
        a, b = gv(FB, k), gv(SB, k)
        if len(a) < 3 or len(b) < 3 or len(set(a + b)) == 1:
            gr.append(dict(k=k, a=a, b=b, d=None, p=None)); continue
        if k == 'r0_pass':
            from scipy.stats import fisher_exact
            p = fisher_exact([[sum(a), len(a) - sum(a)], [sum(b), len(b) - sum(b)]])[1]
        else:
            p = perm_p(a, b)
        gr.append(dict(k=k, a=a, b=b, d=cliff(a, b), ci=boot_delta(a, b), p=p))
    qs = iter(bh([x['p'] for x in gr if x['p'] is not None]))
    for x in gr:
        x['q'] = next(qs) if x['p'] is not None else None
    RES.append((gname, gr))


def iqr(k, v):
    a, b = q4(v); return f'{fv(k,a)}–{fv(k,b)}'


def big_table():
    t = ['<table class="big"><thead><tr><th>Variable</th><th>FeatureBench<br><small>median (IQR)</small></th><th>SWE-bench Pro<br><small>median (IQR)</small></th>'
         '<th>Cliff’s δ<br><small>95% CI</small></th><th>Size</th><th>p</th><th>q</th><th>Reading</th></tr></thead><tbody>']
    for gname, gr in RES:
        t.append(f'<tr class="grp"><td colspan="8">{gname}</td></tr>')
        for x in gr:
            k, a, b, d = x['k'], x['a'], x['b'], x['d']
            fa = f'{fv(k,median(a))} <small>({iqr(k,a)})</small>' if a else 'n/a'
            fb = f'{fv(k,median(b))} <small>({iqr(k,b)})</small>' if b else 'n/a'
            if k == 'r0_pass':
                fa = f'{int(sum(a))}/{len(a)}'; fb = f'{int(sum(b))}/{len(b)}'
            if d is None:
                t.append(f'<tr><td>{LABEL.get(k,k)}</td><td>{fa}</td><td>{fb}</td><td colspan="5">no variation, not tested</td></tr>'); continue
            sigq = x['q'] < .05
            read = ('FB higher' if d > 0 else 'SWE-Pro higher') if sigq else 'no clear difference'
            t.append(f'<tr{" class=sig" if sigq else ""}><td>{LABEL.get(k,k)}</td><td>{fa}</td><td>{fb}</td>'
                     f'<td>{d:+.2f} <small>[{x["ci"][0]:+.2f}, {x["ci"][1]:+.2f}]</small></td><td>{mag(d)}</td><td>{pf(x["p"])}</td><td>{pf(x["q"])}</td><td>{read}</td></tr>')
    return ''.join(t) + '</tbody></table>'


def forest():
    items = [(g, x) for g, gr in RES for x in gr if x['d'] is not None]
    rh, L, R, T = 19, 250, 20, 26
    h = T + len(items) * rh + len(RES) * 22 + 30
    X = lambda v: L + (v + 1) / 2 * (W - L - R)
    out = [f'<svg viewBox="0 0 {W} {h}" role="img" aria-label="Effect size for every variable">']
    for t in (-1, -.474, 0, .474, 1):
        out.append(f'<line class="grid{" zero" if t == 0 else ""}" x1="{X(t):.1f}" x2="{X(t):.1f}" y1="{T-6}" y2="{h-28}"/><text class="tick" x="{X(t):.1f}" y="{h-12}" text-anchor="middle">{t:+.2f}'.replace('+0.00', '0') + '</text>')
    out.append(f'<text class="tick" x="{X(-1)}" y="12">← SWE-Pro higher</text><text class="tick" x="{X(1)}" y="12" text-anchor="end">FeatureBench higher →</text>')
    y = T; last = None
    for g, x in items:
        if g != last:
            y += 6; out.append(f'<text class="lab" x="4" y="{y+10}" font-weight="600">{E(g)}</text>'); y += 16; last = g
        cls = 's1' if x['d'] > 0 else 's2'; op = '1' if x['q'] < .05 else '.35'
        lo, hi = x['ci']
        out.append(f'<text class="lab sm" x="{L-10}" y="{y+12}" text-anchor="end">{E(LABEL.get(x["k"],x["k"])[:38])}</text>'
                   f'<line class="ci" x1="{X(lo):.1f}" x2="{X(hi):.1f}" y1="{y+8}" y2="{y+8}" style="opacity:{op}"/>'
                   f'<circle class="{cls} dot" cx="{X(x["d"]):.1f}" cy="{y+8}" r="5" style="fill-opacity:{op}" '
                   f'data-tip="{E(LABEL.get(x["k"],x["k"]))}: δ {x["d"]:+.2f} [{lo:+.2f}, {hi:+.2f}], q {pf(x["q"])}"/>')
        y += rh
    out.append('</svg>')
    return ''.join(out)


def cell_table3():
    cols = [('bench', 'Bench'), ('repo', 'Repo'), ('task', 'Task'), ('cue_files', 'Files named'),
            ('recall_all', 'Line recall'), ('recall_comments', 'Comment match'), ('gold_comments', 'Gold cmts'), ('precision', 'Precision'),
            ('tool_calls', 'Calls'), ('api_turns', 'Turns'), ('searches', 'Searches'), ('test_runs', 'Tests'), ('files_opened', 'Opened'),
            ('gold_found_pre_edit', 'Found pre-edit'), ('navshare_not_found', 'Never located'), ('cost_usd', 'Cost $'), ('wall_s', 'Time s'),
            ('r0_pass', 'Pass r0'), ('rounds', 'Rounds')]
    P = {'recall_all', 'recall_comments', 'cue_files', 'gold_found_pre_edit', 'navshare_not_found', 'precision'}
    t = ['<table class="cells"><thead><tr>' + ''.join(f'<th>{l}</th>' for _, l in cols) + '</tr></thead><tbody>']
    for r in rows:
        tds = []
        for k, _ in cols:
            v = r.get(k, '')
            if k in P and v not in ('', None): v = f'{float(v):.0%}'
            elif k == 'bench': v = 'FB' if v == 'FeatureBench' else 'SWE-Pro'
            elif k == 'r0_pass': v = 'yes' if v == 'True' else 'no'
            elif k == 'cost_usd' and v: v = f'{float(v):.2f}'
            tds.append(f'<td>{E(str(v)) if v != "" else "–"}</td>')
        t.append('<tr>' + ''.join(tds) + '</tr>')
    return ''.join(t) + '</tbody></table>'


nsig = sum(1 for _, gr in RES for x in gr if x['q'] is not None and x['q'] < .05)
ntest = sum(1 for _, gr in RES for x in gr if x['q'] is not None)


_adj = {(yk, xk): SF.panel(rows, xk, xl, lg, yk, yl, True)[1] for yk, yl in SF.YS for xk, xl, lg in SF.XS}
_fbs = sum(1 for v in _adj.values() if v[0][2] < .05); _sbs = sum(1 for v in _adj.values() if v[1][2] < .05)
adjnote = (f'After the size adjustment, {_fbs} of 9 FeatureBench panels and {_sbs} of 9 SWE-Pro panels still show p &lt; .05. '
           'Within FeatureBench, more scattered diffs go with more tool calls, cost and searches than their size predicts (ρ about .5–.65). '
           'On SWE-Pro (61 runs) the raw links hold after correction (ρ about .3–.5) but shrink to ρ ≈ .1–.35 after the size adjustment and no longer survive correction (best q = .11): there, scattering adds little beyond size. '
           'This is associational: effort could scatter the change (more exploration, more files touched) as easily as the reverse.')
ncorr = len(SF.XS + SF.XMORE) * len(SF.YS + SF.YMORE)
page = f'''<title>Scattering vs Agent Effort</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&family=Source+Serif+4:opsz,wght@8..60,500;8..60,600&display=swap">
<style>
:root{{--bg:#f9f9f7;--surface:#fcfcfb;--panel:#f1f0ec;--fg:#0b0b0b;--fg2:#52514e;--muted:#7b7a74;--rule:#dedcd5;--grid:#e9e7e1;
 --s1:#2a78d6;--s2:#eb6834;--s3:#1baf7a;--s4:#eda100;--s5:#e87ba4;--s7:#6250d6;--s8:#8a8880;--sig:#fff3d6;--pos:42,120,214;--neg:235,104,52;color-scheme:light}}
@media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{--bg:#0d0d0d;--surface:#1a1a19;--panel:#222220;--fg:#f0efec;--fg2:#c3c2b7;--muted:#8d8c84;--rule:#383835;--grid:#2a2a28;
 --s1:#3987e5;--s2:#d95926;--s3:#199e70;--s4:#c98500;--s5:#d55181;--s7:#9085e9;--s8:#77766f;--sig:#3a3220;--pos:57,135,229;--neg:217,89,38;color-scheme:dark}}}}
:root[data-theme="dark"]{{--bg:#0d0d0d;--surface:#1a1a19;--panel:#222220;--fg:#f0efec;--fg2:#c3c2b7;--muted:#8d8c84;--rule:#383835;--grid:#2a2a28;
 --s1:#3987e5;--s2:#d95926;--s3:#199e70;--s4:#c98500;--s5:#d55181;--s7:#9085e9;--s8:#77766f;--sig:#3a3220;--pos:57,135,229;--neg:217,89,38;color-scheme:dark}}
body{{background:var(--bg);color:var(--fg);font:15px/1.6 "IBM Plex Sans",system-ui,sans-serif}}
.wrap{{max-width:1060px;margin:0 auto;padding-block:40px 80px;padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px))}}
h1,h2{{font-family:"Source Serif 4",Georgia,serif;font-weight:600;text-wrap:balance;letter-spacing:-.01em}}
h1{{font-size:2.1rem;line-height:1.15;margin:.2em 0 .4em}} h2{{font-size:1.45rem;margin:2.6em 0 .5em;padding-top:.8em;border-top:1px solid var(--rule)}}
h3{{font-size:1rem;margin:1.6em 0 .4em;font-weight:600}}
p,li{{max-width:68ch;color:var(--fg)}} .lede{{font-size:1.08rem;color:var(--fg2)}}
.eyebrow{{font:500 .74rem "IBM Plex Mono",monospace;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}}
nav.toc{{display:flex;flex-wrap:wrap;gap:6px 14px;font-size:.85rem;margin:1.2em 0}} nav.toc a{{color:var(--fg2)}}
.tiles{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin:1.6em 0}}
.tile{{background:var(--surface);border:1px solid var(--rule);border-radius:10px;padding:14px 16px;min-width:0}}
.tile .k{{font-size:.8rem;color:var(--fg2)}} .tile .v{{font:500 1.5rem "IBM Plex Mono",monospace;margin:.2em 0}}
.tile .v b{{font-weight:500}} .tile .v .a{{color:var(--fg)}} .tile small{{color:var(--muted);font-size:.78rem}}
.sw{{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:5px;vertical-align:middle}}
.fig{{background:var(--surface);border:1px solid var(--rule);border-radius:10px;padding:16px;margin:1em 0 .4em;min-width:0}}
.fig h4{{margin:0 0 .2em;font-size:.95rem}} .fig .sub{{color:var(--fg2);font-size:.83rem;margin:0 0 .6em}}
.grid2{{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px}}
svg{{width:100%;height:auto;display:block;overflow:visible}}
svg .grid{{stroke:var(--grid);stroke-width:1}} svg .tick{{fill:var(--muted);font:11px "IBM Plex Mono",monospace}}
svg .lab{{fill:var(--fg2);font:12px "IBM Plex Sans",sans-serif}} svg .lab.sm{{font-size:11px}} svg .axl{{fill:var(--fg2);font:12px "IBM Plex Sans"}}
svg .muted{{fill:var(--muted)}} svg .inbar{{fill:#fff;font:600 11px "IBM Plex Mono",monospace;pointer-events:none}}
svg .s1{{fill:var(--s1)}} svg .s2{{fill:var(--s2)}} svg .s3{{fill:var(--s3)}} svg .s4{{fill:var(--s4)}} svg .s5{{fill:var(--s5)}} svg .s7{{fill:var(--s7)}} svg .s8{{fill:var(--s8)}}
svg circle.dot{{stroke:var(--surface);stroke-width:2;fill-opacity:.9}} svg .dot{{cursor:default}} svg .dot:hover{{fill-opacity:1;stroke:var(--fg)}}
svg .ci{{stroke:var(--fg2);stroke-width:2}} svg .grid.zero{{stroke:var(--fg2)}} table.big td small{{color:var(--muted)}} svg .medtick{{stroke:var(--fg);stroke-width:2}}
.legend{{display:flex;flex-wrap:wrap;gap:6px 16px;font-size:.82rem;color:var(--fg2);margin:.4em 0}}
.key i{{display:inline-block;width:11px;height:11px;border-radius:3px;margin-right:6px;vertical-align:-1px}}
.key i.s1{{background:var(--s1)}} .key i.s2{{background:var(--s2)}} .key i.s3{{background:var(--s3)}} .key i.s4{{background:var(--s4)}} .key i.s5{{background:var(--s5)}} .key i.s7{{background:var(--s7)}} .key i.s8{{background:var(--s8)}}
tr.grp td{{background:var(--panel);font-weight:600;font-family:inherit!important;color:var(--fg2)}} h2.part{{font-size:1.8rem}} .sw.big{{width:14px;height:14px}}
.tw{{overflow-x:auto;margin:.6em 0 1em;border:1px solid var(--rule);border-radius:10px;background:var(--surface)}}
table{{border-collapse:collapse;width:100%;font-size:.84rem}}
th,td{{padding:6px 10px;text-align:left;border-bottom:1px solid var(--grid);white-space:nowrap}}
th{{font-weight:600;color:var(--fg2);background:var(--panel);position:sticky;top:0}}
td:not(:first-child){{font-family:"IBM Plex Mono",monospace;font-size:.8rem}}
tr.sig td,td.sig{{background:var(--sig)}}
.matrix td.heat{{background:rgba(var(--pos),calc(var(--a)*.35))}} .matrix td.heat.neg{{background:rgba(var(--neg),calc(var(--a)*.35))}}
.matrix td.sig{{font-weight:600}} .matrix small{{display:block;color:var(--fg2);font-size:.7rem;font-weight:400}}
table.cells th{{cursor:pointer}}
.note{{border-left:3px solid var(--s4);background:var(--surface);padding:10px 14px;border-radius:0 8px 8px 0;margin:1em 0;max-width:80ch}}
.verdict{{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:12px}}
.verdict div{{background:var(--surface);border:1px solid var(--rule);border-radius:10px;padding:12px 16px;min-width:0}}
.verdict h4{{margin:.2em 0 .4em}} .verdict ul{{margin:0;padding-left:1.1em}}
details{{margin:.8em 0}} summary{{cursor:pointer;color:var(--fg2)}} pre{{white-space:pre;overflow-x:auto;font:12px/1.45 "IBM Plex Mono",monospace;background:var(--surface);border:1px solid var(--rule);padding:12px;border-radius:8px}}
code{{font:.86em "IBM Plex Mono",monospace}}
.smgrid{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}} @media (max-width:760px){{.smgrid{{grid-template-columns:1fr}}}}
.sm{{background:var(--surface);border:1px solid var(--rule);border-radius:8px;padding:8px;min-width:0}} .smh{{font-size:.8rem;font-weight:600;color:var(--fg2)}}
svg .trend{{stroke-width:2}} svg .s1l{{stroke:var(--s1)}} svg .s2l{{stroke:var(--s2)}} svg .s1t{{fill:var(--s1)}} svg .s2t{{fill:var(--s2)}}
.warn{{border-left:3px solid var(--s2);background:var(--surface);padding:10px 14px;border-radius:0 8px 8px 0;margin:1em 0;max-width:80ch}}
#tip{{position:fixed;pointer-events:none;background:var(--fg);color:var(--bg);font:12px "IBM Plex Sans";padding:5px 9px;border-radius:6px;z-index:20;max-width:280px}}
.bdk{{background:none;border:0;padding:0;cursor:pointer;font:inherit;color:inherit}}
</style>
<div class="wrap">
<div class="eyebrow">Claude Code 2.1.310 · Opus 5.5 · seed 1 · {len(FB)} + {len(SB)} runs</div>
<h1>Does scattering of the change relate to the agent’s effort, navigation and success?</h1>
<p class="lede"><b>Question.</b> When the agent’s change is spread over more files, packages and loosely connected code, does it spend more tool calls, cost and searches, and does it still pass? <b>Scattering is measured on the agent’s own final diff</b>, not on the reference patch, since a reference commit can contain unrelated changes.</p>
<div class="note"><b>What “effort” means here.</b> The measures of how much work the agent did in a run:
<div class="tw"><table class="big" style="margin-top:.4em"><thead><tr><th>Measure</th><th>What it counts</th></tr></thead><tbody>
<tr><td>Tool calls</td><td>every action: a shell command, a file read, an edit, a test run</td></tr>
<tr><td>API turns</td><td>how many times the model was called (one turn = the model thinks and replies once, usually with a tool call)</td></tr>
<tr><td>Cost (USD)</td><td>the run’s cost as reported by Claude Code: output, new input, cache writes and re-read context</td></tr>
<tr><td>Searches</td><td>search commands: grep, rg, find, git grep, and the Grep/Glob tools</td></tr>
<tr><td>Wall time</td><td>seconds from start to finish</td></tr>
</tbody></table></div>
The appendix’s benchmark comparison adds output tokens, re-read context tokens, test runs, probe scripts and re-edits.
<br><b>These are mostly one thing measured several ways.</b> Tool calls and API turns are almost identical (ρ ≈ 1.0 in both benchmarks); cost tracks them at ≈ .9 on FeatureBench and ≈ .8 on SWE-Pro. Read “scattering relates to tool calls, turns and cost” as one finding. On FeatureBench searches also move with tool calls (ρ .96), so they add little separate evidence there; on SWE-Pro they are more distinct (ρ .74).</div>
<div class="verdict" style="margin:1.2em 0">
<div><h4>Key findings</h4><p style="margin:0 0 .5em"><small>Only results that hold after correcting for multiple tests. SWE-Pro (61 runs): raw links between scattering and effort survive correction; none survive after the size adjustment.</small></p><p style="margin:.6em 0 .2em"><b>Do scattered changes cost the agent more?</b><br>Yes, beyond their size.</p>
<ul style="margin:0;padding-left:1.2em">
<li>Runs whose change spans more files or packages use more tool calls, cost and searches, even after adjusting for size (FeatureBench ρ ≈ +0.5 to +0.65, surviving correction).</li>
<li>SWE-Pro (61 runs): the same direction before the size adjustment (ρ ≈ +0.3 to +0.5, surviving correction), but not after it (ρ ≈ +0.1 to +0.35, q ≥ .11). On SWE-Pro, scattering mostly tracks size. Adding 11 multi-file tasks (batch 4) did not change this.</li>
<li>Focus: when most of the change sits in one file, the run is cheaper (ρ ≈ −0.55).</li>
<li>Functions touched don’t matter once size is removed. Effort tracks how many places the change lands, not how much code is written.</li>
</ul>
<p style="margin:.8em 0 .2em"><b>How does the agent navigate scattered changes?</b><br>It searches more and starts editing before it has found everything.</p>
<ul style="margin:0;padding-left:1.2em">
<li>More scattered → more searches and more files opened (ρ up to +0.89, surviving correction).</li>
<li>It finds files by grep, almost never by following calls or imports.</li>
<li>Scattered runs start editing earlier, having found 9% of the needed files vs 40% on localized runs, and discover the rest along the way.</li>
<li>More of their actions are reading (47% vs 32%) and fewer are git (4% vs 14%). Splitting by packages or dispersion instead shows no difference (<a href="#app-split">table</a>).</li>
</ul>
<p style="margin:.8em 0 .2em"><b>Can FeatureBench effort be read as search effort?</b><br>Only with care.</p>
<ul style="margin:0;padding-left:1.2em">
<li>The agent reproduces code it was never shown (median {mFBr:.0%} of reference lines verbatim; SWE-Pro {mSBr:.0%}), so effort may reflect recall more than search.</li>
</ul><p style="margin:.5em 0 0"><small>Weaker results that don’t hold after correction: <a href="#leads">bottom of the page</a>.</small></p></div>
<div><h4>Read with care</h4><ul style="margin:0;padding-left:1.1em">
<li>All links are correlations, and the direction is open. More exploring can produce a more scattered diff, just as a scattered change can need more exploring.</li>
<li>Scattering is measured on the agent’s own diff, which can only include files it found.</li>
<li>Small samples: 21 + 61 runs, one seed each; the 61 SWE-Pro runs come from 10 repos (15 protonmail). 11 of them (batch 4) were picked because their reference patch changes ≥ 3 files.</li>
<li>Chart p-values are uncorrected; the appendix tables show corrected q.</li>
</ul></div>
</div>
<div class="note"><b>How many correlations survive multiple-test correction?</b> Benjamini–Hochberg q, applied separately to each table column (one benchmark × raw or size-adjusted).
<div class="tw"><table class="big" style="max-width:40em;margin-top:.4em"><thead><tr><th>Table (appendix)</th><th>Tests</th><th>p &lt; .05</th><th>q &lt; .05</th></tr></thead><tbody>
<tr><td><a href="#corr">Scattering × effort and outcome</a></td><td>{_QC[0]}</td><td>{_QC[1]}</td><td>{_QC[2]}</td></tr>
<tr><td><a href="#navcorr">Scattering × navigation</a></td><td>{_QN[0]}</td><td>{_QN[1]}</td><td>{_QN[2]}</td></tr>
<tr><td><a href="#app-tech">Scattering × technique</a></td><td>{_QT[0]}</td><td>{_QT[1]}</td><td>{_QT[2]}</td></tr>
<tr><td><b>Total</b></td><td><b>{_QC[0]+_QN[0]+_QT[0]}</b></td><td><b>{_QC[1]+_QN[1]+_QT[1]}</b></td><td><b>{_QC[2]+_QN[2]+_QT[2]}</b></td></tr>
</tbody></table></div>Per-column counts are under each appendix table. The main-page charts show uncorrected p.</div>
<p><b>Data.</b> One agent (Claude Code 2.1.310, Opus 5.5), one run per task: {len(FB)} FeatureBench tasks across {len(repos_fb)} Python repos, using a hand-written goal-only prompt, and {len(SB)} SWE-bench Pro V2 tasks across {len(repos_sb)} repos in Python, Go and TypeScript, using the issue text. Each chart’s trend line is fitted <b>within</b> each benchmark, never across both.</p>
<div class="warn"><b>Memorisation warning.</b> On FeatureBench the agent’s diff reproduces a median {mFBr:.0%} of reference lines verbatim, including {mFBcm:.0%} of comment lines, even though the prompt names no code. Those repos are very likely in training data, so effort there may reflect recall rather than navigation. SWE-Pro shows {mSBr:.0%}. Read the two benchmarks separately.</div>
<nav class="toc"><a href="#main">Scattering vs effort</a><a href="#adj">Size-adjusted</a><a href="#navres">Scattering vs navigation</a><a href="#tech">Techniques</a><a href="#tasktype">Task type</a><a href="#pass">Pass rate</a><a href="#tasks">Tasks by scattering</a><a href="#appendix">Appendix: full tables, benchmark vs benchmark</a><a href="#leads">Leads not surviving correction</a></nav>

<h2 id="main">Scattering vs effort</h2>
<p class="sub">Columns: files changed, packages changed and package dispersion, all from the agent’s diff (production code only). Rows: tool calls, cost and searches, on log scales. Header label = Spearman ρ within each benchmark (* p &lt; .05, 4,000-shuffle permutation). Hover a dot for the task.</p>
<div class="legend"><span class="key"><i class="s1"></i>FeatureBench (n = {len(FB)})</span><span class="key"><i class="s2"></i>SWE-bench Pro (n = {len(SB)})</span></div>
{SF.grid(rows, False)}
<div class="note"><b>Package dispersion (1 − HHI)</b> has no unit; it runs from 0 to 1. HHI (Herfindahl–Hirschman Index) measures how concentrated the agent’s changed lines are across packages: take each package’s share of the changed lines, square each share and add them up. 1 − HHI flips it, so higher means more spread out.
<div class="tw"><table class="big" style="margin-top:.5em"><thead><tr><th>How the changed lines are split</th><th>HHI</th><th>1 − HHI</th></tr></thead><tbody>
<tr><td>All in 1 package</td><td>1.0² = 1.0</td><td>0</td></tr>
<tr><td>90% / 10% over 2 packages</td><td>0.81 + 0.01 = 0.82</td><td>0.18</td></tr>
<tr><td>50% / 50% over 2 packages</td><td>0.25 + 0.25 = 0.5</td><td>0.5</td></tr>
<tr><td>Evenly over 4 packages</td><td>4 × 0.0625 = 0.25</td><td>0.75</td></tr>
</tbody></table></div>
<small>A package is the top two path components of a changed file.</small></div>
<div class="note"><b>How to read “FB ρ +0.60*”.</b> Spearman rank correlation within one benchmark (−1 to +1; ≈ .3 weak, .5 moderate, ≥ .7 strong); * = permutation p &lt; .05, uncorrected.<br>No star is not “no link”: FeatureBench has 21 runs, so ρ below about .45 often misses p &lt; .05; SWE-Pro has 61, which detects about ρ ≥ .35. Correlation only, direction open.</div>

<h2 id="bigdos-h">All 82 runs: effort measures by package dispersion</h2>
<p class="sub">Each colour is one effort measure. Measures have different units, so each is shown as a percentile rank among the 82 runs (0% = lowest, 100% = highest). Lines are straight-line fits. <b>Size-adjusted</b> shows each run relative to what its lines changed predict, fitted within each benchmark (same method as the size-adjusted charts below). ρ = Spearman over all 82 runs pooled, uncorrected; the benchmarks differ in size, so read the within-benchmark results above for inference. Click a legend item to hide it; hover a dot for the run.</p>
<div class="fig">{SF.bigdos(rows)}</div>
<h2 id="adj">The same, adjusted for size: is there anything beyond lines changed?</h2>
<p>File count mostly measures size. Here each outcome is shown <b>relative to what its number of changed lines predicts</b>. Within each benchmark, log(outcome) is regressed on log(lines changed in the agent’s diff), and the plot shows the residual as a ratio, where 1× means exactly as expected for its size. A trend that remains here is association beyond size.</p>
{SF.grid(rows, True)}
<div class="note"><b>Reading.</b> {adjnote}</div>

<h2 id="navres">Scattering vs navigation</h2>
<div class="verdict">
<div><h4>Key findings (FeatureBench, 21 runs)</h4><p style="margin:0 0 .5em"><small>Only results that hold after correcting for multiple tests.</small></p><ul>
<li><b>Scattered diffs go with more exploring.</b> The more files the diff changes, the more the agent searched (ρ +.89) and the more files it opened (+.71). More packages and wider spread across packages also go with more files opened (+.54, +.56).</li>
<li><b>Focused diffs go with less exploring.</b> The more of the diff sits in one file, the fewer searches (ρ −.82) and files opened (−.65), and the more needed files the agent had found before its first edit (+.63).</li>
<li><b>Wide diffs start editing earlier.</b> Runs changing more files or functions had found fewer of the needed files before the first edit (ρ −.70, −.60).</li>
</ul></div>
<div><h4>Read with care</h4><ul>
<li>Scattering is measured on the agent’s own diff, and the agent can only change files it found, so navigation and scattering partly measure the same thing. Neither is shown to cause the other.</li>
<li>The findings above are FeatureBench only. On SWE-Pro (61 runs) the raw links also hold after correction: more files changed go with more files opened (ρ +.74) and more searches (+.48), and focused diffs with fewer (ρ −.68, −.43). Across low-recall runs of both benchmarks, more scattered diffs had more needed files first found by search (ρ ≈ +.4 to +.54, q &lt; .05). See the <a href="#navcorr">appendix table</a>.</li>
</ul></div>
</div>
<p class="sub">FeatureBench, all 21 runs. Each dot is one run. These four charts back the findings above.</p>
{SF.navkey(rows)}
<div class="verdict" style="margin-top:2em">
<div><h4>Key findings (SWE-bench Pro, 61 runs)</h4><p style="margin:0 0 .5em"><small>Only results that hold after correcting for multiple tests.</small></p><ul>
<li><b>Scattered diffs go with more exploring here too.</b> The more files the diff changes, the more files the agent opened (ρ +.71) and the more it searched (+.47). More packages and wider spread also go with more files opened (+.58, +.58 in the <a href="#navcorr">appendix table</a>, which leaves out 2 runs with no needed files).</li>
<li><b>Focused diffs go with less exploring.</b> The more of the diff sits in one file, the fewer searches (ρ −.42) and files opened (−.68).</li>
<li><b>Split at the median:</b> runs changing more than 1 file (28 of 61) opened a median 6 files vs 2 (r +.73), searched 7 vs 4 times (r +.42) and cost $0.38 vs $0.28 (r +.37). Runs touching more than one package opened 6 vs 3 (r +.66) and searched 8 vs 5 (r +.48). <a href="#app-split-swe">table</a></li>
</ul></div>
<div><h4>Different from FeatureBench</h4><ul>
<li><b>No “start editing earlier” effect.</b> On FeatureBench, wide diffs had found fewer needed files before the first edit (ρ −.70). On SWE-Pro there is no such link (files changed ρ +.16, p = .22; median split 67% vs 33%, p = .21), possibly because the issue text often names the code to change. Functions touched even go the other way (ρ +.35, q = .02).</li>
<li><b>The action mix does not shift.</b> On FeatureBench scattered runs read more and use git less. On SWE-Pro, no share of actions differs between scattered and localized runs (all q &gt; .19).</li>
<li>Effects are smaller than on FeatureBench (median 9 tool calls per run, against 50), and correlations only.</li>
</ul></div>
</div>
<p class="sub">SWE-bench Pro, all 61 runs. The same four charts.</p>
{SF.navkey(rows, 'SWE-bench Pro')}
<h3>How each gold file was first found, per run, most scattered first</h3>
<p class="sub">One panel per benchmark. Label = benchmark (FB / SW), “·low” = low-recall run, number of files in the agent’s diff, task. Ordered by package dispersion of the agent’s diff. Hover for counts.</p>
<div class="fig">{split_stack(NAVP, "Navigation method by scattering")}</div>
<div>
<div class="fig"><h4>Search technique, most scattered first</h4><p class="sub">Share of search commands. Number = total searches.</p>{split_stack(SRCHP, "Search technique by scattering")}</div>
<div class="fig"><h4>Action mix, most scattered first</h4><p class="sub">Share of all agent actions. Number = total actions.</p>{split_stack(SEGP, "Action mix by scattering")}</div>
</div>

<h2 id="tech">Scattering vs technique</h2>
<p><b>Probing does not rise with scattering</b>: once size is removed, FeatureBench shows no link, and on SWE-Pro more scattered runs probe somewhat less (ρ ≈ −.28 to −.35, p &lt; .05 but not surviving correction, q = .13). Codebook, validation and the full technique tables are in the <a href="#app-tech">appendix</a>.</p>

<h2 id="tasktype">Task type vs scattering and effort</h2>
<p>Each task was labelled from its <b>prompt text only</b>, before looking at any outcome (<code>tasktype.csv</code>, with a one-line reason per task). There are two labels. <b>Nature</b> has five groups: data/compute library core (10, all FeatureBench), plotting (4, FeatureBench), tool pipeline/integration such as CLIs, builders, clients and platform support (7 FeatureBench + 19 SWE-Pro), UI component/behaviour (12, SWE-Pro) and small fix/rename (30, SWE-Pro). <b>Bundled</b> marks a prompt that asks for several unrelated features at once (10 of the 21 FeatureBench tasks, no SWE-Pro task). Most groups exist in only one benchmark, so groups are compared <b>within</b> each benchmark (Kruskal–Wallis, permutation p): FeatureBench library/plotting/pipeline and SWE-Pro pipeline/UI/fix.</p>
<div class="note"><b>Findings.</b> (1) Task nature goes with <b>how</b> a change is spread, not with how much effort it takes. On FeatureBench, package dispersion differs by nature (p = .01): library-core tasks stay inside one package (median dispersion .16), while plotting (.59) and pipeline tasks (.57) spread across packages. (2) On FeatureBench, effort (tool calls, cost) does not differ by nature, raw or size-adjusted. The closest is size-adjusted (p ≈ .07), where pipeline tasks run highest. On SWE-Pro it differs raw only, see (4). (3) Bundled multi-feature prompts lean bigger (median files 11.5 vs 6, tool calls 50 vs 28, cost $2.11 vs $1.28), but nothing is significant (p ≥ .39), and the gap disappears after the size adjustment. (4) On SWE-Pro (61 tasks: 30 fix, 19 pipeline, 12 UI), raw cost and tool calls differ by nature (cost p = .001, q = .005, median $0.23 fix, $0.33 pipeline, $0.40 UI; tool calls p = .012, q = .04, median 7.5, 9, 12.5; BH over the 6 SWE-Pro tests), but neither after the size adjustment (p = .08, .25): fixes are smaller changes. Labels are my reading of each prompt, so this is descriptive.</div>
<div class="legend"><span class="key"><i class="s1"></i>FeatureBench</span><span class="key"><i class="s2"></i>SWE-bench Pro</span><span class="key"><i style="background:var(--fg);width:2px"></i>group median</span></div>
<div class="fig">{_TTG}</div>
<div class="fig"><h4>Bundled vs single-feature prompts (FeatureBench)</h4>{_TTB}</div>

<h2 id="pass">Scattering vs passing at the first attempt</h2>
<p>Final diffs include what the agent changed after failure feedback, so here scattering is measured on the <b>first-attempt diff</b> (<code>attempt1.diff.patch</code>; for single-round runs the first attempt is the final diff). Only FeatureBench can be tested: all {len(SB)} SWE-Pro runs passed at the first attempt, so there is nothing to compare.</p>
<div class="note"><b>Finding.</b> No scattering measure separates the 4 first-attempt failures from the 17 passes, raw or size-adjusted (all p &gt; .4). The failures lean towards <em>smaller</em> first attempts: fewer lines and functions (r ≈ −.56, p ≈ .10). That looks more like under-doing the task than being lost in a scattered change. With 4 failures, only a very large effect could show up.</div>
<p class="sub"><b>How to read r:</b> rank-biserial correlation, from −1 to +1. Positive means failed runs tend to have <em>higher</em> values than passed runs. p = two-sided permutation test (5,000 shuffles of pass/fail labels). Size-adjusted = the measure’s residual after regressing it on log lines changed (FeatureBench only).</p>
<div class="tw">{_PTBL}</div>
{_PGRID}
<h3>The 4 runs that failed the first attempt: first-attempt vs final diff</h3>
<p class="sub">relational’s scattering appeared only in round 2, after feedback. The other three barely changed.</p>
<div class="tw">{_PFAIL}</div>

<h2 id="tasks">All {len(rows)} tasks, ordered by scattering</h2>
<p class="sub">Ordered by package dispersion of the agent’s diff, then packages, then files; most scattered first. Click a header to re-sort.</p>
<div class="tw">{SF.task_table(rows)}</div>

<h2 id="appendix" class="part">Appendix</h2>
<p>Full tables behind the main page, then the benchmark-vs-benchmark comparison.</p>
<h2 id="corr">All scattering measures × all outcomes</h2>
<p class="sub">Spearman ρ within each benchmark, raw and size-adjusted, with permutation p with Benjamini–Hochberg q per column (up to {ncorr} tests per column; SWE-Pro has 25 because pass rate is constant there; shaded where q &lt; .05). Pass rate is binary, so its ρ is a point-biserial correlation on ranks.</p>
<div class="tw">{_CT}</div>
<h4>Surviving correction</h4>{_QCt}

<h2 id="navcorr">Navigation measures × scattering</h2>
<p class="sub">Spearman ρ, permutation p and Benjamini–Hochberg q per column (shaded where q &lt; .05).</p>

<div class="tw">{_NC}</div>
<h4>Surviving correction</h4>{_QNt}

<h2 id="app-tech">Scattering vs technique (SlopCodeBench codebook)</h2>
<p>Every tool call is labelled with the same codebook used for SlopCodeBench (<code>scbench/analysis/qual/techniques.py</code>, hand-validated 57/60 on Python traces): read, edit tool, edit via script, probe (run code in the repo / scratch script in <code>/tmp</code>), run tests, static check. One call can carry several labels. For the Go/TS SWE-Pro tasks I added <code>go test</code>/jest/vitest, <code>go run</code>/node and <code>go build</code>/tsc/stylelint patterns. I hand-checked all 101 Go/TS Bash calls: 98/101 have the right label set; the 3 errors come from the unchanged base classifier (<code>GOTS_VALIDATION.md</code>).</p>
<div class="note"><b>Findings.</b> (1) In FeatureBench almost every technique count rises with the number of files the agent changed; after the size adjustment the ones that stay at p &lt; .05 are <b>reads, script edits and test runs</b> (ρ ≈ .5–.57), though none survives correction (q ≥ .08). (2) On SWE-Pro (61 runs) script edits and static checks (tsc, go build/vet) rise with scattering before size adjustment (ρ ≈ .32–.38), but none survive correction (q ≥ .056); after size adjustment only static checks vs packages / dispersion stay at p &lt; .05 among them (ρ +.28, +.25, q = .13). The 12-run version of this page showed much stronger SWE-Pro technique links (ρ .7); they did not hold at 50 or 61. (3) Probing: in FeatureBench it rises with files only before size adjustment; in SWE-Pro, size-adjusted probing goes slightly <em>down</em> as scattering goes up (ρ ≈ −.28 to −.35, q = .13). (4) A focused change (most lines in one file) goes with fewer reads and script edits. 56 tests per benchmark (28 per column), with q per column — treat single cells as leads, not results; correlations only.</div>
<div class="fig"><h4>Median technique use per run</h4>{_TM}</div>
<div class="fig"><h4>Technique count vs scattering, within benchmark</h4><p class="sub">Spearman ρ on log(count+1); size-adj. = residual after regressing on log lines changed. Benjamini–Hochberg q per column; shaded where q &lt; .05.</p><div style="overflow-x:auto">{_TC}</div></div>
<div class="fig"><h4>Surviving correction</h4>{_QTt}</div>
<div class="fig"><h4>Technique mix, most scattered first</h4><p class="sub">Share of labelled calls. Number = total labels.</p>{split_stack(TECHP, "Technique mix by scattering")}</div>

<h2 id="app-split">Scattered vs localized runs (FeatureBench)</h2>
<p class="sub">Each split cuts the 21 FeatureBench runs at the median of one scattering measure. Rank-biserial r: +1 = every scattered run is higher, −1 = every localized run is higher. Permutation p (5,000 shuffles); Benjamini–Hochberg q within each split. Shaded = q &lt; .05. Shares of actions use the technique labels above.</p>
{SF.split_table(rows)}
<h2 id="app-split-swe">Scattered vs localized runs (SWE-bench Pro)</h2>
<p class="sub">Same method on the 61 SWE-bench Pro runs. Most SWE-Pro diffs touch one package, so the median package count is 1 and dispersion 0: the package and dispersion splits put the same runs on each side and give identical tables.</p>
{SF.split_table(rows, 'SWE-bench Pro')}
<h2 id="bvb" class="part">Benchmark vs benchmark</h2>
<p>This comparison mixes prompt style, repository, language, size and memorisation, so it is kept for reference only. Shape variables in this appendix come from the <em>reference</em> patch.</p>
<div class="tiles">
<div class="tile"><div class="k">Variables compared</div><div class="v">{ntest}</div><small>{nsig} differ at q &lt; .05</small></div>
<div class="tile"><div class="k">Gold lines reproduced (median)</div><div class="v"><span class="sw" style="background:var(--s1)"></span>{mFBr:.0%} <span style="color:var(--muted)">vs</span> <span class="sw" style="background:var(--s2)"></span>{mSBr:.0%}</div></div>
<div class="tile"><div class="k">Gold comment lines reproduced</div><div class="v"><span class="sw" style="background:var(--s1)"></span>{mFBcm:.0%} <span style="color:var(--muted)">vs</span> <span class="sw" style="background:var(--s2)"></span>{mSBcm:.0%}</div></div>
<div class="tile"><div class="k">Tool calls (median)</div><div class="v"><span class="sw" style="background:var(--s1)"></span>{mFBc:.0f} <span style="color:var(--muted)">vs</span> <span class="sw" style="background:var(--s2)"></span>{mSBc:.1f}</div></div>
<div class="tile"><div class="k">Passed in round 0</div><div class="v"><span class="sw" style="background:var(--s1)"></span>{r0["fb"]} <span style="color:var(--muted)">vs</span> <span class="sw" style="background:var(--s2)"></span>{r0["sbp"]}</div><small>Fisher p = {r0["fisher_p"]:.2f}</small></div>
</div>
<div class="legend"><span class="key"><i class="s1"></i>FeatureBench, goal-only</span><span class="key"><i class="s2"></i>SWE-bench Pro, issue text</span></div>

<h2 id="how">How to compare the two benchmarks</h2>
<p>Each benchmark is a group of cells (one run per task). For every variable we ask: <em>if you pick one FeatureBench cell and one SWE-Pro cell at random, which is likely to be higher?</em></p>
<ul>
<li><b>Cliff’s δ</b> answers that directly. It runs from −1 (every SWE-Pro cell is higher) to +1 (every FeatureBench cell is higher), with 0 meaning no difference. |δ| below .15 is negligible, below .33 small, below .47 medium, and anything above is large. It uses ranks only, so a few extreme cells cannot drive it.</li>
<li><b>95% CI</b> comes from resampling cells (2,000 bootstraps). A CI that crosses 0 means the direction is not settled.</li>
<li><b>p</b> is a permutation test (5,000 shuffles of the benchmark labels): how often a δ this large appears by chance. Pass rate uses Fisher’s exact test.</li>
<li><b>q</b> is p after Benjamini-Hochberg correction within each variable group, because many variables are tested at once. Rows with q &lt; .05 are shaded.</li>
<li>A difference here is <b>associational</b>. Benchmark, prompt style, repository, language and task size all change together.</li>
</ul>

<h2 id="effects">Effect size for every variable</h2>
<div class="fig"><h4>Cliff’s δ with 95% CI, FeatureBench vs SWE-bench Pro</h4><p class="sub">Solid = q &lt; .05; faded = not significant. Dashed guides at ±.47 mark a “large” effect. Hover for numbers.</p>{forest()}</div>

<h2 id="table">All variables, both benchmarks</h2>
<p class="sub">Reference-patch shape is not compared here; scattering is measured on the agent’s diff on the main page.</p>
<div class="tw">{big_table()}</div>

<h2 id="recall">Gold lines reproduced verbatim</h2>
<p>The FeatureBench prompts name no code, yet the agent’s diff contains most reference lines character for character. That pattern is consistent with the reference being in training data. SWE-Pro, whose issue text does name code, shows much less overlap.</p>
<div class="fig"><h4>Gold lines reproduced verbatim, per cell</h4><p class="sub">Each dot is one cell; the black tick is the median. Hover for task.</p>{strip("recall_all","Gold lines reproduced verbatim",pct=True)}</div>

<h2 id="comments">Comment-line matching</h2>
<p>Comment wording is free, so a verbatim comment match is a sharper signal than matching code. Median match: <b>{mFBcm:.0%}</b> on FeatureBench against <b>{mSBcm:.0%}</b> on SWE-Pro. Only {nSBcm} of {len(SB)} SWE-Pro gold patches contain any comments; the {len(SB)-nSBcm} without any are left out.</p>
<div class="fig"><h4>Gold comment lines reproduced, per cell</h4><p class="sub">Bar = share reproduced verbatim; “/n” = number of gold comment lines.</p>{cmtbars()}<div class="legend"><span class="key"><i class="s1"></i>FeatureBench</span><span class="key"><i class="s2"></i>SWE-bench Pro</span></div></div>
<p>Comment match tracks line recall closely (ρ ≈ .8). The effort gaps (tool calls, searches, cost) hold when it is used as the control instead (n = 61 runs with gold comments, p &lt; .001).</p>

<h2 id="nav">Navigation</h2>
<div class="fig"><h4>How gold files were first found, all cells pooled</h4><p class="sub">Share of required gold files by discovery method. Hover for counts.</p>{navsvg}<div class="legend">{navleg}</div></div>
<div class="grid2">
<div class="fig"><h4>Search technique · FeatureBench</h4><p class="sub">Which search command the agent used, share of search commands. Number = total searches.</p>{stack(FB, SRCHP, "FeatureBench search technique")}</div>
<div class="fig"><h4>Search technique · SWE-bench Pro</h4><p class="sub">Which search command the agent used, share of search commands. Number = total searches.</p>{stack(SB, SRCHP, "SWE-bench Pro search technique")}</div>
<div class="fig"><h4>How each gold file was first found · FeatureBench</h4><p class="sub">Per required gold file, from the trace.</p>{stack(FB, NAVP, "FeatureBench navigation")}</div>
<div class="fig"><h4>How each gold file was first found · SWE-bench Pro</h4><p class="sub">Per required gold file, from the trace.</p>{stack(SB, NAVP, "SWE-bench Pro navigation")}</div>
</div>
<div class="fig"><h4>Searches per run</h4><p class="sub">grep / glob / find calls; log scale.</p>{strip("searches","Searches",log=True,h=140)}</div>

<h2 id="caveats">Caveats</h2>
<ol>
<li><b>Entangled factors.</b> Benchmark, prompt style, repositories, language and task size change together.</li>
<li><b>Verbatim recall is not proof of memorisation.</b> It is used as a control, not a diagnosis.</li>
<li><b>One seed per task.</b> Run-to-run variance is unknown.</li>
<li><b>SWE-Pro is spread over 10 repos</b> (15 protonmail, 9 flipt, 7 each navidrome and vuls, 6 ansible, 5 qutebrowser, …); 12 runs come from earlier batches, 38 from batch 3 and 11 from batch 4. Batch 4 was selected for reference patches changing ≥ 3 files, so it is not a random draw. All use the issue text verbatim, except two prompts where one function or class name the tests don’t use was replaced.</li>
<li><b>Small n.</b> With 21 vs 61 cells, only |δ| above about .4 is reliably detectable. A non-significant row is not evidence of no difference.</li>
<li><b>Function counts</b> are parsed from patch text (def/class/func/function declarations and hunk headers), not from a parser.</li>
<li>Regression checks on existing features are out of scope here.</li>
</ol>

<h2 id="cells">All {len(rows)} cells</h2>
<p class="sub">Click a column header to sort.</p>
<div class="tw">{cell_table3()}</div>
<p class="eyebrow" style="margin-top:3em">Sources: cells.csv · agentshape.csv (agentshape.py) · patchshape.csv · behaviour.csv · stats_out.json</p>
<h2 id="leads" class="part">Leads that do not survive correction</h2>
<p>Each of these had uncorrected p &lt; .05 but q ≥ .05 after Benjamini–Hochberg correction (task type: 6 Kruskal–Wallis tests per benchmark; p = .01 gives q = .06). They are directions to re-test with more runs, not results.</p>
<ol>
<li><b>Files vs effort on SWE-Pro.</b> Size-adjusted, more files changed went with more searches and longer wall time (ρ +.34, p = .01, q = .11; wall time +.25, p = .06). Tool calls: ρ +.25, p = .06.</li>
<li><b>Focus on SWE-Pro.</b> Size-adjusted, more focused diffs went with fewer searches and shorter wall time (ρ −.32, −.31; p = .015, q = .11). Tool calls: ρ −.26, p = .05.</li>
<li><b>Probing does not rise with scattering.</b> On FeatureBench, the link between probes and files changed vanishes after the size adjustment. On SWE-Pro, more scattered runs probe slightly <em>less</em> than their size predicts (ρ ≈ −.28 to −.35). These come from 56 tests per benchmark, none surviving correction, so treat them as leads.</li>
<li><b>Task type shapes the spread, not the effort.</b> On FeatureBench, library-core tasks stay in one package (dispersion .16), while plotting and pipeline tasks spread across packages (.57–.59; p = .01). Tool calls and cost do not differ by task type on FeatureBench, and prompts that bundle several features are not significantly costlier. On SWE-Pro they differ raw (fixes are cheapest) but not after the size adjustment. <a href="#tasktype">Task type</a></li>
</ol>
</div>
<div id="tip" hidden></div>
<script>
const tip=document.getElementById('tip');
document.addEventListener('pointerover',e=>{{const t=e.target.closest('[data-tip]');if(!t){{tip.hidden=true;return}}tip.textContent=t.dataset.tip;tip.hidden=false}});
document.addEventListener('pointermove',e=>{{if(tip.hidden)return;const x=Math.min(e.clientX+14,innerWidth-tip.offsetWidth-8);tip.style.left=x+'px';tip.style.top=(e.clientY+14)+'px'}});
document.querySelectorAll('table.cells th').forEach((th,i)=>th.addEventListener('click',()=>{{
 const tb=th.closest('table').tBodies[0];const asc=th.dataset.dir!=='asc';th.dataset.dir=asc?'asc':'desc';
 const num=s=>{{const v=parseFloat(s.replace('%',''));return isNaN(v)?null:v}};
 [...tb.rows].sort((a,b)=>{{const x=a.cells[i].textContent,y=b.cells[i].textContent,nx=num(x),ny=num(y);
  const c=(nx!==null&&ny!==null)?nx-ny:x.localeCompare(y);return asc?c:-c}}).forEach(r=>tb.appendChild(r))}}));
</script>
'''
out = HERE / 'page'; out.mkdir(exist_ok=True)
(out / 'index.html').write_text(page)
print('wrote', out / 'index.html', len(page))
