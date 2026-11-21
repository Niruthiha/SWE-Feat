"""scatterfig.py -- scattering-vs-effort figures/tables for make_page.py (agent's own diff = agentshape.csv)."""
import csv, math, random, html
from pathlib import Path
HERE = Path(__file__).resolve().parent
E = lambda s: html.escape(str(s), quote=True)
AS = {r['cell']: r for r in csv.DictReader(open(HERE / 'agentshape.csv'))}
XS = [('a_n_files', 'Files changed', True), ('a_n_packages', 'Packages changed', True), ('a_dos_pkg', 'Package dispersion (1−HHI)', False)]
XMORE = [('a_n_functions', 'Functions touched', True), ('a_focus_top_file', 'Focus: share of lines in the largest file', False)]
YS = [('tool_calls', 'Tool calls'), ('cost_usd', 'Cost (USD)'), ('searches', 'Searches')]
YMORE = [('api_turns', 'API turns'), ('wall_s', 'Wall time (s)'), ('r0_pass', 'Passed round 0')]
SIZE = 'a_n_lines'
LIN = {'navshare_not_found', 'gold_found_pre_edit', 'navshare_search', 'navshare_following_code', 'navshare_recall'}
NAVY = [('navshare_not_found', 'Gold files never located'), ('gold_found_pre_edit', 'Gold files found before first edit'),
        ('navshare_search', 'Gold files first found by search'), ('navshare_following_code', 'Gold files first found by following code')]
LOWREC = .8


def lowrec(rows):
    return [r for r in rows if fl(r, 'recall_all') is not None and fl(r, 'recall_all') < LOWREC and (fl(r, 'n_required') or 0) > 0]


def attach(rows):
    for r in rows:
        r.update({'a_' + k: v for k, v in AS[r['cell']].items() if k not in ('cell', 'bench', 'repo')})


def fl(r, k):
    v = r.get(k)
    if v in ('True', 'False'): return float(v == 'True')
    try: return float(v)
    except (ValueError, TypeError, KeyError): return None


def ols(x, y):
    n = len(x); mx, my = sum(x) / n, sum(y) / n
    sxx = sum((a - mx) ** 2 for a in x)
    b = sum((a - mx) * (c - my) for a, c in zip(x, y)) / sxx if sxx else 0
    return my - b * mx, b


def rank(v):
    o = sorted(range(len(v)), key=lambda i: v[i]); r = [0.0] * len(v); i = 0
    while i < len(o):
        j = i
        while j + 1 < len(o) and v[o[j + 1]] == v[o[i]]: j += 1
        for k in range(i, j + 1): r[o[k]] = (i + j) / 2
        i = j + 1
    return r


def pear(a, b):
    n = len(a); ma, mb = sum(a) / n, sum(b) / n
    sa = math.sqrt(sum((x - ma) ** 2 for x in a)); sb = math.sqrt(sum((x - mb) ** 2 for x in b))
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (sa * sb) if sa and sb else float('nan')


def spear(a, b, B=4000, seed=20261118):
    if len(a) < 4: return float('nan'), float('nan')
    ra, rb = rank(a), rank(b); r = pear(ra, rb)
    if r != r: return r, float('nan')
    rnd = random.Random(seed); hit = 0; rb2 = rb[:]
    for _ in range(B):
        rnd.shuffle(rb2); hit += abs(pear(ra, rb2)) >= abs(r) - 1e-12
    return r, (hit + 1) / (B + 1)


def yval(r, yk, adj, fit):
    """raw: log10(y). adjusted: residual of log10(y) on log10(lines) fitted within the cell's benchmark."""
    y = fl(r, yk); s = fl(r, SIZE)
    if y is None: return None
    if yk in LIN: return y
    if yk == 'r0_pass': return y if not adj else (y - (fit[r['bench']][0] + fit[r['bench']][1] * math.log10(max(s, 1))))
    ly = math.log10(max(y, 1e-3))
    if not adj: return ly
    a, b = fit[r['bench']]; return ly - (a + b * math.log10(max(s, 1)))


def size_fits(rows, yk):
    fit = {}
    for bn in ('FeatureBench', 'SWE-bench Pro'):
        g = [r for r in rows if r['bench'] == bn and fl(r, yk) is not None and fl(r, SIZE) is not None]
        ys = [fl(r, yk) if yk in LIN or yk == 'r0_pass' else math.log10(max(fl(r, yk), 1e-3)) for r in g]
        if g: fit[bn] = ols([math.log10(max(fl(r, SIZE), 1)) for r in g], ys)
    return fit


def xval(r, xk, logx):
    x = fl(r, xk)
    if x is None: return None
    return math.log10(x) if logx else x


def panel(rows, xk, xlab, logx, yk, ylab, adj, W=330, h=250, pooled=False):
    L, R, T, B = 46, 10, 26, 38; fit = size_fits(rows, yk)
    pts = [(xval(r, xk, logx), yval(r, yk, adj, fit), r) for r in rows]
    pts = [p for p in pts if p[0] is not None and p[1] is not None]
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    xlo, xhi = min(xs), max(xs); ylo, yhi = min(ys), max(ys)
    px = (xhi - xlo) * .06 or .5; py = (yhi - ylo) * .08 or .5; xlo -= px; xhi += px; ylo -= py; yhi += py
    X = lambda v: L + (v - xlo) / (xhi - xlo) * (W - L - R); Y = lambda v: T + (1 - (v - ylo) / (yhi - ylo)) * (h - T - B)
    o = [f'<svg viewBox="0 0 {W} {h}" role="img" aria-label="{E(ylab)} by {E(xlab)}{" adjusted for size" if adj else ""}">']
    # x ticks
    if logx:
        for t in [1, 2, 5, 10, 20, 50]:
            v = math.log10(t)
            if xlo <= v <= xhi: o.append(f'<line class="grid" x1="{X(v):.1f}" x2="{X(v):.1f}" y1="{T}" y2="{h-B}"/><text class="tick" x="{X(v):.1f}" y="{h-B+14}" text-anchor="middle">{t}</text>')
    else:
        for t in [0, .2, .4, .6, .8, 1, 2, 3, 4, 5, 6, 8]:
            if xlo <= t <= xhi and (xhi - xlo < 1.5 or t >= 1 or t == 0): o.append(f'<line class="grid" x1="{X(t):.1f}" x2="{X(t):.1f}" y1="{T}" y2="{h-B}"/><text class="tick" x="{X(t):.1f}" y="{h-B+14}" text-anchor="middle">{t:g}</text>')
    # y ticks
    if yk in LIN:
        ylo, yhi = -.06, 1.06
        for t in [0, .25, .5, .75, 1]:
            o.append(f'<line class="grid" x1="{L}" x2="{W-R}" y1="{Y(t):.1f}" y2="{Y(t):.1f}"/><text class="tick" x="{L-6}" y="{Y(t)+4:.1f}" text-anchor="end">{t:.0%}</text>')
    elif adj and yk != 'r0_pass':
        for m in [.25, .5, 1, 2, 4]:
            v = math.log10(m)
            if ylo <= v <= yhi: o.append(f'<line class="grid{" zero" if m == 1 else ""}" x1="{L}" x2="{W-R}" y1="{Y(v):.1f}" y2="{Y(v):.1f}"/><text class="tick" x="{L-6}" y="{Y(v)+4:.1f}" text-anchor="end">{m:g}×</text>')
    elif yk == 'r0_pass':
        for t in ([0, 1] if not adj else [-.5, 0, .5]):
            if ylo <= t <= yhi: o.append(f'<line class="grid" x1="{L}" x2="{W-R}" y1="{Y(t):.1f}" y2="{Y(t):.1f}"/><text class="tick" x="{L-6}" y="{Y(t)+4:.1f}" text-anchor="end">{t:g}</text>')
    else:
        for t in [.1, .2, .5, 1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000]:
            v = math.log10(t)
            if ylo <= v <= yhi: o.append(f'<line class="grid" x1="{L}" x2="{W-R}" y1="{Y(v):.1f}" y2="{Y(v):.1f}"/><text class="tick" x="{L-6}" y="{Y(v)+4:.1f}" text-anchor="end">{t:g}</text>')
    o.append(f'<text class="axl" x="{(L+W-R)/2}" y="{h-4}" text-anchor="middle">{E(xlab)}</text>')
    stats = []
    for bn, cls in (('FeatureBench', 's1'), ('SWE-bench Pro', 's2')):
        g = [p for p in pts if p[2]['bench'] == bn]
        if len(g) >= 3 and len({p[0] for p in g}) > 1:
            a, b = ols([p[0] for p in g], [p[1] for p in g]); x0, x1 = min(p[0] for p in g), max(p[0] for p in g)
            o.append(f'<line class="trend {cls}l" x1="{X(x0):.1f}" y1="{Y(a+b*x0):.1f}" x2="{X(x1):.1f}" y2="{Y(a+b*x1):.1f}"/>')
        rho, p = spear([p[0] for p in g], [p[1] for p in g]); stats.append((bn, rho, p, len(g)))
    for xv, yv, r in pts:
        cls = 's1' if r['bench'] == 'FeatureBench' else 's2'
        tip = f'{r["task"]} ({r["repo"]}) · {xlab} {fl(r, xk):g} · {ylab} {fl(r, yk):.3g} · {int(fl(r, SIZE) or 0)} lines changed · recall {fl(r, "recall_all"):.0%}'
        o.append(f'<circle class="{cls} dot" cx="{X(xv):.1f}" cy="{Y(yv):.1f}" r="5" data-tip="{E(tip)}"/>')
    if pooled:
        rho, p = spear([p[0] for p in pts], [p[1] for p in pts]); stats.append(('both', rho, p, len(pts)))
    lab = ' · '.join(f'<tspan class="{ {"FeatureBench": "s1t", "SWE-bench Pro": "s2t"}.get(bn, "")}">{ {"FeatureBench": "FB", "SWE-bench Pro": "SWE"}.get(bn, "all")} ρ {"n/a" if rho != rho else f"{rho:+.2f}"}{"*" if p == p and p < .05 else ""}</tspan>' for bn, rho, p, n in stats)
    o.append(f'<text class="lab sm" x="{L}" y="14">{lab}</text></svg>')
    return ''.join(o), stats


def grid(rows, adj):
    cells = []
    for yk, ylab in YS:
        for xk, xlab, logx in XS:
            svg, _ = panel(rows, xk, xlab, logx, yk, ylab, adj)
            cells.append(f'<div class="sm"><div class="smh">{E(ylab)}{" ÷ size-expected" if adj else ""}</div>{svg}</div>')
    return '<div class="smgrid">' + ''.join(cells) + '</div>'


def bh(ps):
    """Benjamini-Hochberg q for a list of p (nan kept as nan)."""
    idx = [i for i, p in enumerate(ps) if p == p]; m = len(idx); q = [float('nan')] * len(ps)
    order = sorted(idx, key=lambda i: ps[i]); prev = 1.0
    for k, i in reversed(list(enumerate(order, 1))):
        prev = min(prev, ps[i] * m / k); q[i] = prev
    return q


def _ph(recs, col, rho, p):
    recs.append((col, rho, p)); return f'\x00{len(recs) - 1}\x00'


QSTATS = {}


def _fill(html_, recs, name=''):
    """replace placeholders with ρ / p / BH q; q computed per column (one family = one benchmark × raw/adj column)."""
    qs = {}
    for col in {c for c, _, _ in recs}:
        ii = [i for i, r in enumerate(recs) if r[0] == col]
        for i, q in zip(ii, bh([recs[i][2] for i in ii])): qs[i] = q
    def cell(i):
        _, rho, p = recs[i]; q = qs[i]
        f = lambda v: '–' if v != v else ('<.001' if v < .001 else f'{v:.3f}')
        return (f'<td class="{"sig" if q == q and q < .05 else ""}">{"n/a" if rho != rho else f"{rho:+.2f}"} '
                f'<small>p {f(p)} · q {f(q)}</small></td>')
    ok = [i for i in range(len(recs)) if recs[i][2] == recs[i][2]]
    st = {}
    for i in ok:
        c = recs[i][0]; c = c if isinstance(c, str) else f"{c[0]} {'size-adj.' if c[1] else 'raw'}"
        a = st.setdefault(c, [0, 0, 0]); a[0] += 1; a[1] += recs[i][2] < .05; a[2] += qs[i] < .05
    QSTATS[name] = st
    for i in range(len(recs)): html_ = html_.replace(f'\x00{i}\x00', cell(i))
    return html_


def corr_table(rows):
    recs = []
    h = ['<table class="big"><thead><tr><th>Scattering measure (agent diff)</th><th>Outcome</th>'
         '<th>FB ρ raw</th><th>FB ρ size-adj.</th><th>SWE ρ raw</th><th>SWE ρ size-adj.</th></tr></thead><tbody>']
    for xk, xlab, logx in XS + XMORE:
        for yk, ylab in YS + YMORE:
            c = []
            for bn in ('FeatureBench', 'SWE-bench Pro'):
                for adj in (False, True):
                    fit = size_fits(rows, yk)
                    g = [(fl(r, xk), yval(r, yk, adj, fit)) for r in rows if r['bench'] == bn]
                    g = [p for p in g if p[0] is not None and p[1] is not None]
                    rho, p = spear([a for a, _ in g], [b for _, b in g])
                    c.append(_ph(recs, (bn, adj), rho, p))
            h.append(f'<tr><td>{E(xlab)}</td><td style="font-family:inherit">{E(ylab)}</td>{"".join(c)}</tr>')
    return _fill(''.join(h) + '</tbody></table>', recs, 'corr')


def task_table(rows):
    key = lambda r: (fl(r, 'a_dos_pkg') or 0, fl(r, 'a_n_packages') or 0, fl(r, 'a_n_files') or 0)
    cols = [('bench', 'Benchmark'), ('repo', 'Repo'), ('task', 'Task'), ('a_n_files', 'Files'), ('a_n_packages', 'Packages'),
            ('a_dos_pkg', 'Pkg dispersion'), ('a_n_functions', 'Functions'), ('a_n_lines', 'Lines'),
                        ('cost_usd', 'Cost $'), ('wall_s', 'Time s'), ('tool_calls', 'Tool calls'), ('searches', 'Searches'),
            ('api_turns', 'Turns'), ('r0_pass', 'Pass r0'), ('accept_final', 'Pass final')]
    h = ['<table class="cells"><thead><tr><th>#</th>' + ''.join(f'<th>{E(l)}</th>' for _, l in cols) + '</tr></thead><tbody>']
    for i, r in enumerate(sorted(rows, key=key, reverse=True), 1):
        tds = []
        for k, _ in cols:
            v = r.get(k, '')
            if k == 'bench': v = 'FB' if v == 'FeatureBench' else 'SWE-Pro'
            elif k == 'task' and len(v) > 34: v = v[:32] + '…'
            elif k in ('r0_pass', 'accept_final'): v = {'1.0': 'yes', '0.0': 'no', '1': 'yes', 'True': 'yes', '0': 'no', 'False': 'no'}.get(str(v), v)
            elif fl(r, k) is not None and k not in ('repo', 'task'):
                x = fl(r, k); v = f'{x:.0f}' if x == int(x) and k != 'cost_usd' else (f'{x:.2f}' if k in ('cost_usd',) or x < 10 else f'{x:.0f}')
            tds.append(f'<td>{E(v)}</td>')
        h.append(f'<tr><td>{i}</td>{"".join(tds)}</tr>')
    return ''.join(h) + '</tbody></table>'


def navgrid(rows):
    g = lowrec(rows); cells = []
    for yk, ylab in NAVY:
        for xk, xlab, logx in XS:
            svg, _ = panel(g, xk, xlab, logx, yk, ylab, False, pooled=True)
            cells.append(f'<div class="sm"><div class="smh">{E(ylab)}</div>{svg}</div>')
    return '<div class="smgrid">' + ''.join(cells) + '</div>'


def navcorr(rows):
    recs = []
    groups = [('Low-recall runs, both benchmarks', lowrec(rows)), ('All runs · FeatureBench', [r for r in rows if r['bench'] == 'FeatureBench']),
              ('All runs · SWE-bench Pro', [r for r in rows if r['bench'] != 'FeatureBench' and (fl(r, 'n_required') or 0) > 0])]
    h = ['<table class="big"><thead><tr><th>Scattering measure (agent diff)</th><th>Navigation outcome</th>' +
         ''.join(f'<th>{E(n)} <small>n={len(g)}</small></th>' for n, g in groups) + '</tr></thead><tbody>']
    ys = NAVY + [('navshare_recall', 'Gold files edited without lookup'), ('searches', 'Searches'), ('files_opened', 'Files opened')]
    for xk, xlab, _ in XS + XMORE:
        for yk, ylab in ys:
            c = []
            for gn, g in groups:
                pr = [(fl(r, xk), fl(r, yk)) for r in g]; pr = [p for p in pr if None not in p]
                rho, p = spear([a for a, _ in pr], [b for _, b in pr])
                c.append(_ph(recs, gn, rho, p))
            h.append(f'<tr><td>{E(xlab)}</td><td style="font-family:inherit">{E(ylab)}</td>{"".join(c)}</tr>')
    return _fill(''.join(h) + '</tbody></table>', recs, 'nav')


def by_scatter(rows):
    """rows sorted most-scattered first, with a label carrying benchmark, files and recall"""
    out = []
    for r in sorted(rows, key=lambda r: (fl(r, 'a_dos_pkg') or 0, fl(r, 'a_n_packages') or 0, fl(r, 'a_n_files') or 0), reverse=True):
        q = dict(r); low = (fl(r, 'recall_all') or 1) < LOWREC
        q['task'] = f'{"FB" if r["bench"] == "FeatureBench" else "SW"}{"·low" if low else ""} {int(fl(r, "a_n_files") or 0)}f {r["task"].replace("protonmail-", "")}'
        out.append(q)
    return out


# ---------------------------------------------------------------- first-attempt scattering vs first-attempt pass
import os as _os, patchshape as _ps
_F = '/home/niruthi/features'
PASSX = [('n_files', 'Files changed', True), ('n_packages', 'Packages changed', True), ('dos_pkg', 'Package dispersion', False),
         ('n_functions', 'Functions touched', True), ('focus_top_file', 'Share of lines in largest file', False), ('n_lines', 'Lines changed', True)]


def attach_attempt1(rows):
    for r in rows:
        ex = 'experiment-featurebench' if r['bench'] == 'FeatureBench' else 'experiment-swebench-pro'
        d = f'{_F}/{ex}/runs/{r["cell"]}'; p = f'{d}/attempt1.diff.patch'
        src = p if _os.path.exists(p) else f'{d}/diff.patch'
        r['a1_src'] = 'attempt1.diff.patch' if _os.path.exists(p) else 'diff.patch (single round)'
        r.update({'a1_' + k: v for k, v in _ps.shape(src).items()})


def rb_perm(x_pass, x_fail, B=5000, seed=20261118):
    """rank-biserial (P(fail > pass) − P(fail < pass)) and two-sided permutation p"""
    def rb(a, b):
        g = sum((y > x) - (y < x) for x in a for y in b); return g / (len(a) * len(b))
    obs = rb(x_pass, x_fail); allv = x_pass + x_fail; n = len(x_pass); rnd = random.Random(seed); hit = 0
    for _ in range(B):
        rnd.shuffle(allv); hit += abs(rb(allv[:n], allv[n:])) >= abs(obs) - 1e-12
    return obs, (hit + 1) / (B + 1)


def pass_stats(rows):
    g = [r for r in rows if r['bench'] == 'FeatureBench']; out = []
    for k, lab, logx in PASSX:
        xs = [(float(r['a1_' + k]), fl(r, 'r0_pass'), math.log10(max(float(r['a1_n_lines']), 1))) for r in g if r.get('a1_' + k) not in ('', None)]
        rbr, p = rb_perm([x for x, y, _ in xs if y == 1], [x for x, y, _ in xs if y == 0])
        if k != 'n_lines':  # size-adjusted: residual of (log) measure on log lines
            t = [(math.log10(max(x, 1e-3)) if logx else x) for x, _, _ in xs]
            a, b = ols([s for *_, s in xs], t); res = [ti - (a + b * s) for ti, (_, _, s) in zip(t, xs)]
            ra, pa = rb_perm([v for v, (_, y, _) in zip(res, xs) if y == 1], [v for v, (_, y, _) in zip(res, xs) if y == 0])
        else: ra, pa = float('nan'), float('nan'); res = None
        out.append(dict(k=k, lab=lab, logx=logx, rb=rbr, p=p, rba=ra, pa=pa, xs=xs, res=res,
                        mp=median([x for x, y, _ in xs if y == 1]), mf=median([x for x, y, _ in xs if y == 0])))
    return out


from statistics import median


def pass_strip(st, adj, W=330, h=120):
    L, R = 70, 14; o = []
    vals = st['res'] if adj else [(math.log10(max(x, 1e-3)) if st['logx'] else x) for x, _, _ in st['xs']]
    lo, hi = min(vals), max(vals); pad = (hi - lo) * .06 or .5; lo -= pad; hi += pad
    X = lambda v: L + (v - lo) / (hi - lo) * (W - L - R)
    o.append(f'<svg viewBox="0 0 {W} {h}" role="img" aria-label="{E(st["lab"])} by first-attempt pass">')
    for row, (y, lab, cls) in enumerate([(1, 'passed (17)', 's1'), (0, 'failed (4)', 's7')]):
        cy = 30 + row * 42
        o.append(f'<text class="lab sm" x="{L-8}" y="{cy+4}" text-anchor="end">{lab}</text><line class="grid" x1="{L}" x2="{W-R}" y1="{cy}" y2="{cy}"/>')
        for v, (x, yy, _), r_ in zip(vals, st['xs'], range(99)):
            if yy == y:
                o.append(f'<circle class="{cls} dot" cx="{X(v):.1f}" cy="{cy + ((r_ % 3) - 1) * 5}" r="5" data-tip="{E(st["lab"])} {x:g}"/>')
    o.append(f'<text class="tick" x="{L}" y="{h-6}">{"lower than size predicts" if adj else "low"}</text><text class="tick" x="{W-R}" y="{h-6}" text-anchor="end">{"higher than size predicts" if adj else "high"}</text></svg>')
    return ''.join(o)


def pass_section(rows):
    S = pass_stats(rows); cells = []; trs = []
    for st in S:
        for adj in (False, True):
            if adj and st['res'] is None: continue
            r_, p_ = (st['rba'], st['pa']) if adj else (st['rb'], st['p'])
            cells.append(f'<div class="sm"><div class="smh">{E(st["lab"])}{" · size-adjusted" if adj else ""}</div><div class="sub" style="font-size:.78rem;color:var(--fg2)">r = {r_:+.2f}, p = {p_:.3f}{" *" if p_ < .05 else ""}</div>{pass_strip(st, adj)}</div>')
        trs.append(f'<tr><td>{E(st["lab"])}</td><td>{st["mp"]:g}</td><td>{st["mf"]:g}</td><td class="{"sig" if st["p"] < .05 else ""}">{st["rb"]:+.2f} <small>p {st["p"]:.3f}</small></td>'
                   f'<td class="{"sig" if st["pa"] < .05 else ""}">{"–" if st["rba"] != st["rba"] else f"{st[chr(114)+chr(98)+chr(97)]:+.2f}"} <small>p {"–" if st["pa"] != st["pa"] else f"{st[chr(112)+chr(97)]:.3f}"}</small></td></tr>')
    tbl = ('<table class="big"><thead><tr><th>First-attempt diff measure</th><th>Median, passed r0</th><th>Median, failed r0</th><th>r raw</th><th>r size-adj.</th></tr></thead><tbody>'
           + ''.join(trs) + '</tbody></table>')
    fails = [r for r in rows if r['bench'] == 'FeatureBench' and fl(r, 'r0_pass') == 0]
    ft = ['<table class="big"><thead><tr><th>Task (failed r0)</th><th>Files a1 → final</th><th>Packages a1 → final</th><th>Dispersion a1 → final</th><th>Largest-file share a1 → final</th><th>Lines a1 → final</th></tr></thead><tbody>']
    for r in fails:
        ft.append(f'<tr><td>{E(r["task"])}</td>' + ''.join(f'<td>{r["a1_" + k]} → {r["a_" + k]}</td>' for k in ('n_files', 'n_packages', 'dos_pkg', 'focus_top_file', 'n_lines')) + '</tr>')
    return S, '<div class="smgrid">' + ''.join(cells) + '</div>', tbl, ''.join(ft) + '</tbody></table>'


# ---------------------------------------------------------------- SlopCodeBench technique codebook vs scattering
TECH = [('probe_run', 'Probe: run code in the repo', 's1'), ('probe_tmp', 'Probe: scratch script in /tmp', 's3'),
        ('own_test_run', 'Run tests', 's4'), ('static_check', 'Static check / compile', 's5'),
        ('edit_script', 'Edit via script (sed/python/heredoc)', 's2'), ('edit_tool', 'Edit tool', 's7'),
        ('read', 'Read / view (incl. grep | head)', 's8')]


def attach_tech(rows):
    T = {r['cell']: r for r in csv.DictReader(open(HERE / 'techniques_xb.csv'))}
    for r in rows: r.update({'t_' + k: v for k, v in T[r['cell']].items() if k not in ('cell', 'bench')})


def tech_corr(rows):
    groups = [(bn, [r for r in rows if r['bench'] == bn]) for bn in ('FeatureBench', 'SWE-bench Pro')]
    h = ['<table class="big"><thead><tr><th>Technique (calls)</th><th>Scattering (agent diff)</th>'
         '<th>FB ρ raw</th><th>FB ρ size-adj.</th><th>SWE ρ raw</th><th>SWE ρ size-adj.</th></tr></thead><tbody>']
    out = {}; recs = []
    for tk, tl, _ in TECH:
        for xk, xl, _ in XS + [('a_focus_top_file', 'Share of lines in largest file', False)]:
            c = []
            for bn, g in groups:
                ys = [math.log10(fl(r, 't_' + tk) + 1) for r in g]; s = [math.log10(max(fl(r, SIZE), 1)) for r in g]
                a, b = ols(s, ys); res = [y - (a + b * si) for y, si in zip(ys, s)]
                xs = [fl(r, xk) for r in g]
                for adj, yy in ((0, ys), (1, res)):
                    rho, p = spear(xs, yy); out[(tk, xk, bn, adj)] = (rho, p)
                    c.append(_ph(recs, (bn, adj), rho, p))
            h.append(f'<tr><td style="font-family:inherit">{E(tl)}</td><td style="font-family:inherit">{E(xl)}</td>{"".join(c)}</tr>')
    return out, _fill(''.join(h) + '</tbody></table>', recs, 'tech')


def tech_medians(rows):
    h = ['<table class="big"><thead><tr><th>Technique</th><th>FB median calls</th><th>FB median share</th><th>SWE median calls</th><th>SWE median share</th></tr></thead><tbody>']
    for tk, tl, _ in TECH:
        c = ''
        for bn in ('FeatureBench', 'SWE-bench Pro'):
            g = [r for r in rows if r['bench'] == bn]
            c += f'<td>{median(fl(r, "t_" + tk) for r in g):g}</td><td>{median(fl(r, "t_tshare_" + tk) for r in g):.0%}</td>'
        h.append(f'<tr><td style="font-family:inherit">{E(tl)}</td>{c}</tr>')
    return ''.join(h) + '</tbody></table>'


# ---------------------------------------------------------------- task nature (a-priori labels from prompt text only)
NATURE = [('library', 'Data/compute library core'), ('plotting', 'Plotting'), ('pipeline', 'Tool pipeline / integration'),
          ('ui', 'UI component / behaviour'), ('fix', 'Small fix / rename')]
TT_Y = [('a_n_files', 'Files changed', False, True), ('a_dos_pkg', 'Package dispersion', False, False),
        ('tool_calls', 'Tool calls', True, True), ('cost_usd', 'Cost (USD)', True, True)]


def attach_tasktype(rows):
    T = list(csv.DictReader(open(HERE / 'tasktype.csv')))
    for r in rows:
        m = [t for t in T if t['key'] in r['cell'] or t['key'] in r.get('task', '')]
        assert len(m) == 1, (r['cell'], [t['key'] for t in m])
        r['nature'] = m[0]['nature']; r['bundled'] = int(m[0]['bundled'])


def _kw(groups, B=4000, seed=20261118):
    """Kruskal-Wallis H on ranks with permutation p."""
    allv = [v for g in groups for v in g]; rk = rank(allv); n = len(allv)
    def H(lbl):
        s = {};
        for l, r_ in zip(lbl, rk): s.setdefault(l, []).append(r_)
        return 12 / (n * (n + 1)) * sum(len(v) * (sum(v) / len(v) - (n + 1) / 2) ** 2 for v in s.values())
    lbl = [i for i, g in enumerate(groups) for _ in g]; h0 = H(lbl); rnd = random.Random(seed); c = 0
    for _ in range(B):
        rnd.shuffle(lbl); c += H(lbl) >= h0 - 1e-12
    return h0, (c + 1) / (B + 1)


def tt_values(rows, key, logy, adj):
    out = {}
    for bn in ('FeatureBench', 'SWE-bench Pro'):
        g = [r for r in rows if r['bench'] == bn]
        ys = [math.log10(max(fl(r, key), 1e-3)) if logy else fl(r, key) for r in g]
        if adj:
            s = [math.log10(max(fl(r, SIZE), 1)) for r in g]; a, b = ols(s, ys); ys = [y - (a + b * si) for y, si in zip(ys, s)]
        for r, y in zip(g, ys): out[r['cell']] = y
    return out


def tt_strip(rows, key, lab, logy, adj, W=340):
    V = tt_values(rows, key, logy, adj); L, R = 150, 12; rowh = 26; h = 24 + rowh * len(NATURE) + 18
    vals = list(V.values()); lo, hi = min(vals), max(vals); pad = (hi - lo) * .06 or .5; lo -= pad; hi += pad
    X = lambda v: L + (v - lo) / (hi - lo) * (W - L - R)
    o = [f'<svg viewBox="0 0 {W} {h}" role="img" aria-label="{E(lab)} by task nature">']
    for i, (nk, nl) in enumerate(NATURE):
        cy = 22 + i * rowh; g = [r for r in rows if r['nature'] == nk]
        o.append(f'<text class="lab sm" x="{L-8}" y="{cy+4}" text-anchor="end">{E(nl)} ({len(g)})</text><line class="grid" x1="{L}" x2="{W-R}" y1="{cy}" y2="{cy}"/>')
        md = median(V[r['cell']] for r in g)
        o.append(f'<line x1="{X(md):.1f}" x2="{X(md):.1f}" y1="{cy-9}" y2="{cy+9}" stroke="var(--fg)" stroke-width="2"/>')
        for j, r in enumerate(g):
            raw = fl(r, key)
            o.append(f'<circle class="{"s1" if r["bench"] == "FeatureBench" else "s2"} dot" cx="{X(V[r["cell"]]):.1f}" cy="{cy + ((j % 3) - 1) * 5}" r="4.5"'
                     f' data-tip="{E(r["task"][:40])} · {E(lab)} {raw:g}{" · bundled" if r["bundled"] else ""}"/>')
    o.append(f'<text class="tick" x="{L}" y="{h-4}">{"lower than size predicts" if adj else ("low (log)" if logy else "low")}</text>'
             f'<text class="tick" x="{W-R}" y="{h-4}" text-anchor="end">{"higher than size predicts" if adj else "high"}</text></svg>')
    return ''.join(o)


def tasktype_section(rows):
    cells, trs = [], []; res = {}
    for key, lab, logy, sizeadj in TT_Y:
        for adj in ((False, True) if sizeadj and key != 'a_n_files' else (False,)):
            V = tt_values(rows, key, logy, adj); stat = []
            for bn, ks in (('FeatureBench', ('library', 'plotting', 'pipeline')), ('SWE-bench Pro', ('pipeline', 'ui', 'fix'))):
                gs = [[V[r['cell']] for r in rows if r['bench'] == bn and r['nature'] == k] for k in ks]
                h_, p_ = _kw(gs); res[(key, adj, bn, 'nature')] = p_
                stat.append(f'{bn[:3] if bn[0]=="F" else "SWE"} KW p {p_:.3f}{" *" if p_ < .05 else ""}')
            fb = [r for r in rows if r['bench'] == 'FeatureBench']
            b1 = [V[r['cell']] for r in fb if r['bundled']]; b0 = [V[r['cell']] for r in fb if not r['bundled']]
            rb, pb = rb_perm(b1, b0); res[(key, adj, 'FeatureBench', 'bundled')] = (rb, pb)
            cells.append(f'<div class="sm"><div class="smh">{E(lab)}{" · size-adjusted" if adj else ""}</div>'
                         f'<div class="sub" style="font-size:.78rem;color:var(--fg2)">{" · ".join(stat)}</div>{tt_strip(rows, key, lab, logy, adj)}</div>')
            m1 = median(fl(r, key) for r in fb if r['bundled']); m0 = median(fl(r, key) for r in fb if not r['bundled'])
            trs.append(f'<tr><td>{E(lab)}{" (size-adj.)" if adj else ""}</td><td>{"–" if adj else f"{m1:.3g}"}</td><td>{"–" if adj else f"{m0:.3g}"}</td>'
                       f'<td class="{"sig" if pb < .05 else ""}">{abs(rb):.2f} <small>p {pb:.3f}</small></td></tr>')
    tbl = ('<table class="big"><thead><tr><th>FeatureBench: bundled (n = %d) vs single feature (n = %d)</th><th>Median bundled</th><th>Median single</th><th>|r| rank-biserial, permutation p</th></tr></thead><tbody>'
           % (sum(r['bundled'] for r in rows if r['bench'] == 'FeatureBench'), sum(1 - r['bundled'] for r in rows if r['bench'] == 'FeatureBench')) + ''.join(trs) + '</tbody></table>')
    return res, '<div class="smgrid">' + ''.join(cells) + '</div>', tbl


def qsummary(name):
    st = QSTATS[name]; T = [sum(v[i] for v in st.values()) for i in range(3)]
    rows_ = ''.join(f'<tr><td>{E(c)}</td><td>{v[0]}</td><td>{v[1]}</td><td>{v[2]}</td></tr>' for c, v in st.items())
    return T, ('<table class="big" style="max-width:36em"><thead><tr><th>Column</th><th>Tests</th><th>p &lt; .05</th><th>q &lt; .05</th></tr></thead><tbody>'
               + rows_ + f'<tr><td><b>Total</b></td><td><b>{T[0]}</b></td><td><b>{T[1]}</b></td><td><b>{T[2]}</b></td></tr></tbody></table>')


NAVKEY = [('a_n_files', 'Files changed', True, 'searches', 'Searches', 'More files changed, more searching.'),
          ('a_n_files', 'Files changed', True, 'files_opened', 'Files opened', 'More files changed, more files opened.'),
          ('a_focus_top_file', 'Focus: share of lines in the largest file', False, 'searches', 'Searches', 'Focused diffs need fewer searches.'),
          ('a_n_files', 'Files changed', True, 'gold_found_pre_edit', 'Gold files found before first edit', 'Wide diffs start editing before finding all needed files.')]


def navkey(rows, bench='FeatureBench'):
    g = [r for r in rows if r['bench'] == bench]; cells = []
    for xk, xlab, logx, yk, ylab, why in NAVKEY:
        svg, _ = panel(g, xk, xlab, logx, yk, ylab, False)
        cells.append(f'<div class="sm"><div class="smh">{E(ylab)}</div>{svg}<p class="sub" style="margin:.3em 0 0">{E(why)}</p></div>')
    return '<div class="smgrid">' + ''.join(cells) + '</div>'


SPLITY = [('searches', 'Searches', 0), ('files_opened', 'Files opened', 0), ('gold_found_pre_edit', 'Needed files found before first edit', 1),
          ('tool_calls', 'Tool calls', 0), ('cost_usd', 'Cost (USD)', 2), ('a_n_lines', 'Lines changed', 0)] + \
         [(f't_tshare_{k}', f'Share of actions: {lab}', 1) for k, lab in [('read', 'reading'), ('locate', 'locating'), ('edit_tool', 'Edit tool'),
          ('edit_script', 'script edits'), ('probe_run', 'probing in repo'), ('probe_tmp', 'scratch scripts'), ('own_test_run', 'running tests'),
          ('static_check', 'static checks'), ('git', 'git'), ('bash_other', 'other shell')]]


def split_table(rows, bench='FeatureBench', ret=False):
    import random, statistics as st
    g = [r for r in rows if r['bench'] == bench]; allres = {}
    rb = lambda a, b: sum((x > y) - (x < y) for x in a for y in b) / (len(a) * len(b))
    def fmt(v, kind): return f'{v:.0%}' if kind == 1 else (f'${v:.2f}' if kind == 2 else f'{v:.0f}')
    out = []
    for sk, slab in (('a_n_files', 'files changed'), ('a_n_packages', 'packages changed'), ('a_dos_pkg', 'package dispersion')):
        m = st.median(fl(r, sk) for r in g); sc = [r for r in g if fl(r, sk) > m]; lo = [r for r in g if fl(r, sk) <= m]
        random.seed(20261118); res = []
        for yk, ylab, kind in SPLITY:
            a = [fl(r, yk) for r in sc if fl(r, yk) is not None]; b = [fl(r, yk) for r in lo if fl(r, yk) is not None]
            obs = rb(a, b); v = a + b; c = 0
            for _ in range(5000):
                random.shuffle(v); c += abs(rb(v[:len(a)], v[len(a):])) >= abs(obs) - 1e-12
            res.append((ylab, fmt(st.median(a), kind), fmt(st.median(b), kind), obs, (c + 1) / 5001))
        qs = bh([x[4] for x in res]); allres[sk] = list(zip(res, qs))
        h = [f'<h4>Split by {slab}: above {m:g} ({len(sc)} runs) vs at or below ({len(lo)} runs)</h4><div class="tw"><table class="big"><thead><tr><th>Measure</th><th>Scattered (median)</th><th>Localized (median)</th><th>Rank-biserial r</th><th>p · q</th></tr></thead><tbody>']
        for (ylab, a, b, r_, p_), q in zip(res, qs):
            h.append(f'<tr><td>{E(ylab)}</td><td>{a}</td><td>{b}</td><td>{r_:+.2f}</td><td{" class=\"sig\"" if q < .05 else ""}>{p_:.3f} · {q:.3f}</td></tr>')
        out.append(''.join(h) + '</tbody></table></div>')
    return (''.join(out), allres) if ret else ''.join(out)


BIGY = [('tool_calls', 'Tool calls', 's1'), ('cost_usd', 'Cost', 's2'), ('searches', 'Searches', 's3'),
        ('files_opened', 'Files opened', 's4'), ('api_turns', 'API turns', 's7'), ('wall_s', 'Wall time', 's5')]


def _bigdos_svg(rows, adj):
    W, H, L, R, T, B = 900, 460, 56, 20, 16, 46
    g = [r for r in rows if fl(r, 'a_dos_pkg') is not None]
    xs = [fl(r, 'a_dos_pkg') for r in g]; xhi = max(xs) * 1.05 or 1
    X = lambda v: L + v / xhi * (W - L - R); Y = lambda v: T + (1 - v) * (H - T - B)
    sid = 'bigdos-adj' if adj else 'bigdos-raw'
    o = [f'<svg id="{sid}" viewBox="0 0 {W} {H}" role="img" aria-label="Effort measures by package dispersion, all {len(rows)} runs{", adjusted for lines changed" if adj else ""}"{" hidden" if adj else ""}>']
    for t in [0, .25, .5, .75, 1]:
        o.append(f'<line class="grid" x1="{L}" x2="{W-R}" y1="{Y(t):.1f}" y2="{Y(t):.1f}"/><text class="tick" x="{L-6}" y="{Y(t)+4:.1f}" text-anchor="end">{t:.0%}</text>')
    t = 0
    while t <= xhi:
        o.append(f'<line class="grid" x1="{X(t):.1f}" x2="{X(t):.1f}" y1="{T}" y2="{H-B}"/><text class="tick" x="{X(t):.1f}" y="{H-B+16}" text-anchor="middle">{t:.1f}</text>'); t = round(t + .1, 2)
    o.append(f'<text class="tick" x="{(L+W-R)/2}" y="{H-8}" text-anchor="middle">Package dispersion (1 − HHI) of the agent’s diff → more spread out</text>')
    ylab_ax = 'Percentile rank of size-adjusted value' if adj else f'Percentile rank among the {len(rows)} runs'
    o.append(f'<text class="tick" transform="translate(14,{(T+H-B)/2}) rotate(-90)" text-anchor="middle">{ylab_ax}</text>')
    rhos = {}
    for yk, ylab, col in BIGY:
        fit = size_fits(g, yk) if adj else None
        pts = []
        for r in g:
            if fl(r, yk) is None: continue
            v = yval(r, yk, True, fit) if adj else fl(r, yk)
            if v is not None: pts.append((fl(r, 'a_dos_pkg'), v, fl(r, yk), r))
        vals = sorted(v for _, v, _, _ in pts); n = len(vals)
        pr = lambda v: (sum(x < v for x in vals) + (sum(x == v for x in vals) - 1) / 2) / (n - 1)
        P = [(x, pr(v), raw, r) for x, v, raw, r in pts]
        a, b = ols([x for x, *_ in P], [y for _, y, *_ in P])
        rhos[yk] = spear([x for x, *_ in P], [y for _, y, *_ in P])[0]
        o.append(f'<g class="bd" data-k="{yk}" style="color:var(--{col})">')
        o.append(f'<line x1="{X(0):.1f}" y1="{Y(a):.1f}" x2="{X(xhi):.1f}" y2="{Y(a+b*xhi):.1f}" stroke="currentColor" stroke-width="2.5"/>')
        for x, y, v, r in P:
            fb = r['bench'] == 'FeatureBench'
            sh = f'<circle cx="{X(x):.1f}" cy="{Y(y):.1f}" r="4.5"' if fb else f'<rect x="{X(x)-4:.1f}" y="{Y(y)-4:.1f}" width="8" height="8"'
            o.append(sh + f' fill="currentColor" fill-opacity=".75" stroke="var(--surface)" stroke-width="1.5"><title>{E(ylab)}: {v:g} (rank {y:.0%}{" after size" if adj else ""}) · dispersion {x:.2f} · {E(r["bench"])} · {E(r["cell"][:60])}</title>' + ('</circle>' if fb else '</rect>'))
        o.append('</g>')
    o.append('</svg>')
    return ''.join(o), rhos


def bigdos(rows):
    raw, rr = _bigdos_svg(rows, False); adj, ra = _bigdos_svg(rows, True)
    leg = ''.join(f'<button type="button" class="key bdk" data-k="{yk}" aria-pressed="true"><i class="{col}"></i>{E(ylab)} <small><span class="bdr">ρ {rr[yk]:+.2f}</span><span class="bda" hidden>ρ {ra[yk]:+.2f}</span></small></button>' for yk, ylab, col in BIGY)
    tog = ('<div class="legend" role="group" aria-label="Scale"><button type="button" class="key bdm" data-m="raw" aria-pressed="true"><b>Raw</b></button>'
           '<button type="button" class="key bdm" data-m="adj" aria-pressed="false" style="opacity:.5"><b>Size-adjusted</b> (lines changed removed, within benchmark)</button></div>')
    js = """<script>(()=>{const hid=new Set();const apply=()=>{document.querySelectorAll('#bigdos-raw g.bd,#bigdos-adj g.bd').forEach(g=>{g.style.display=hid.has(g.dataset.k)?'none':''});};
document.querySelectorAll('.bdk').forEach(b=>b.addEventListener('click',()=>{const k=b.dataset.k;hid.has(k)?hid.delete(k):hid.add(k);const on=!hid.has(k);b.setAttribute('aria-pressed',on);b.style.opacity=on?1:.4;apply();}));
document.querySelectorAll('.bdm').forEach(b=>b.addEventListener('click',()=>{const a=b.dataset.m==='adj';document.getElementById('bigdos-raw').hidden=a;document.getElementById('bigdos-adj').hidden=!a;
document.querySelectorAll('.bdr').forEach(e=>e.hidden=a);document.querySelectorAll('.bda').forEach(e=>e.hidden=!a);document.querySelectorAll('.bdm').forEach(x=>{const on=x===b;x.setAttribute('aria-pressed',on);x.style.opacity=on?1:.5;});}));})();</script>"""
    return tog + '<div class="legend">' + leg + '<span class="key">● FeatureBench ■ SWE-bench Pro</span></div><div class="tw">' + raw + adj + '</div>' + js
