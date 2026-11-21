#!/usr/bin/env python3
"""stats.py -- FeatureBench goal-only vs SWE-bench Pro V2: tests on cells.csv. Associational only; one seed per task.

Families (each BH-FDR corrected within family; all p-values are two-sided permutation p: 20 000 draws for A/B, 5 000 for the Spearman tests in C/D):
 A  benchmark difference per DV: Mann-Whitney (permutation of labels), Cliff's delta, bootstrap 95% CI of median diff
 B  benchmark difference controlled for memorisation: Freedman-Lane permutation of the benchmark coefficient in
    rank(DV) ~ bench + rank(control), control in {recall_all, recall_long}; plus + rank(log impl_lines)
 C  within-benchmark IV -> DV Spearman (n_files, dos_dir, log impl_lines, cue_files), plain and partial given
    log impl_lines, and partial given recall_all (memorisation control)
 D  memorisation -> effort: Spearman recall_all / recall_comments vs searches, tool_calls, gold_found_pre_edit,
    navshare_search, within FeatureBench (where recall varies) and pooled
 E  rates: Fisher exact for r0 pass and measured regressions
 Robustness: FeatureBench fresh-only subset; leave-one-repo-out (sign stability of the C/D estimates);
 SWE-Pro without protonmail.
Power: minimum |rho| detectable at alpha .05 / power .8 for each n (Fisher z).
Writes stats_out.json and prints a readable report.
"""
import csv, json, math, random, sys
from pathlib import Path
import numpy as np
from scipy import stats as S

HERE = Path(__file__).resolve().parent
R = 20000
rng = np.random.default_rng(20261117)

rows = list(csv.DictReader(open(HERE / 'cells.csv')))


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return np.nan


for r in rows:
    r['log_impl'] = math.log(num(r['impl_lines'])) if num(r['impl_lines']) > 0 else np.nan
    r['log_cost'] = math.log(num(r['cost_usd']))
    r['r0'] = 1.0 if r['r0_pass'] == 'True' else 0.0
    r['is_fb'] = 1.0 if r['bench'] == 'FeatureBench' else 0.0

DVS = ['cost_usd', 'api_turns', 'tool_calls', 'searches', 'test_runs', 'files_opened', 'files_read_full', 'orient_calls',
       'orient_searches', 'gold_found_pre_edit', 'gold_found_by_done', 'navshare_search', 'navshare_following_code',
       'navshare_recall', 'navshare_not_found', 'navshare_benchmark_clue', 'rework', 'wall_s']
MEM = ['recall_all', 'recall_long', 'recall_comments', 'precision']
IVS = ['n_files', 'dos_dir', 'log_impl', 'cue_files', 'cue_tokens']


def col(rs, k):
    return np.array([num(r[k]) for r in rs], float)


def bh(ps):
    ps = np.array(ps, float); n = len(ps); o = np.argsort(ps); q = np.empty(n)
    run = 1.0
    for i in range(n - 1, -1, -1):
        run = min(run, ps[o[i]] * n / (i + 1)); q[o[i]] = run
    return q


def perm_mw(a, b):
    a, b = a[~np.isnan(a)], b[~np.isnan(b)]
    if len(a) < 3 or len(b) < 3:
        return None
    allv = np.concatenate([a, b]); ranks = S.rankdata(allv); na = len(a)
    obs = ranks[:na].mean() - ranks[na:].mean(); cnt = 0
    for _ in range(R):
        p = rng.permutation(ranks); d = p[:na].mean() - p[na:].mean()
        cnt += abs(d) >= abs(obs) - 1e-12
    cliff = float(np.sign(a[:, None] - b[None, :]).sum()) / (len(a) * len(b))
    boots = [np.median(rng.choice(a, len(a))) - np.median(rng.choice(b, len(b))) for _ in range(4000)]
    return dict(n_fb=len(a), n_sbp=len(b), median_fb=float(np.median(a)), median_sbp=float(np.median(b)),
                median_diff=float(np.median(a) - np.median(b)), ci95=[float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))],
                cliffs_delta=round(cliff, 3), p=(cnt + 1) / (R + 1))


def rank_resid(y, X):
    X = np.column_stack([np.ones(len(y))] + [S.rankdata(x) for x in X])
    beta, *_ = np.linalg.lstsq(X, S.rankdata(y), rcond=None)
    return S.rankdata(y) - X @ beta


def freedman_lane(y, g, covs):
    """rank(y) ~ g + rank(covs); permutation p for g's coefficient (Freedman-Lane)."""
    m = ~np.isnan(y) & ~np.isnan(g)
    for c in covs: m &= ~np.isnan(c)
    y, g, covs = y[m], g[m], [c[m] for c in covs]
    ry = S.rankdata(y)
    Z = np.column_stack([np.ones(len(y))] + [S.rankdata(c) for c in covs])
    X = np.column_stack([Z, g])
    def coef(yy):
        b, *_ = np.linalg.lstsq(X, yy, rcond=None); return b[-1]
    obs = coef(ry)
    bz, *_ = np.linalg.lstsq(Z, ry, rcond=None); fit = Z @ bz; res = ry - fit
    cnt = sum(abs(coef(fit + rng.permutation(res))) >= abs(obs) - 1e-12 for _ in range(R))
    return dict(n=int(m.sum()), coef_bench_rank=round(float(obs), 3), p=(cnt + 1) / (R + 1))


def perm_spear(x, y, z=None):
    m = ~np.isnan(x) & ~np.isnan(y)
    if z is not None:
        for c in z: m &= ~np.isnan(c)
    x, y = x[m], y[m]
    if len(x) < 5 or np.ptp(x) == 0 or np.ptp(y) == 0:
        return None
    if z is not None:
        zz = [c[m] for c in z]; x, y = rank_resid(x, zz), rank_resid(y, zz)
        f = lambda a, b: np.corrcoef(a, b)[0, 1]
    else:
        f = lambda a, b: S.spearmanr(a, b)[0]
    obs = f(x, y); cnt = sum(abs(f(x, rng.permutation(y))) >= abs(obs) - 1e-12 for _ in range(R // 4))
    return dict(n=int(len(x)), rho=round(float(obs), 3), p=(cnt + 1) / (R // 4 + 1))


def min_rho(n):
    if n < 5: return None
    z = (S.norm.ppf(.975) + S.norm.ppf(.8)) / math.sqrt(n - 3)
    return round(math.tanh(z), 3)


def main():
    fb = [r for r in rows if r['bench'] == 'FeatureBench']; sb = [r for r in rows if r['bench'] != 'FeatureBench']
    out = dict(n_fb=len(fb), n_sbp=len(sb), power_min_rho=dict(fb=min_rho(len(fb)), sbp=min_rho(len(sb)), pooled=min_rho(len(rows))))

    # A
    A = {}
    for k in DVS + MEM + IVS:
        t = perm_mw(col(fb, k), col(sb, k))
        if t: A[k] = t
    q = bh([v['p'] for v in A.values()])
    for (k, v), qq in zip(A.items(), q): v['q'] = round(float(qq), 4)
    out['A_benchmark_difference'] = A

    # B
    B = {}
    g = col(rows, 'is_fb')
    for k in DVS:
        for ctl in (['recall_all'], ['recall_long'], ['recall_all', 'log_impl']):
            B[f'{k} | {"+".join(ctl)}'] = freedman_lane(col(rows, k), g, [col(rows, c) for c in ctl])
    q = bh([v['p'] for v in B.values()])
    for (k, v), qq in zip(B.items(), q): v['q'] = round(float(qq), 4)
    out['B_benchmark_diff_controlling_memorisation'] = B

    # C
    C = {}
    for name, rs in (('fb', fb), ('sbp', sb), ('fb_fresh', [r for r in fb if r['subset'] == 'fresh'])):
        for iv in ['n_files', 'dos_dir', 'log_impl', 'cue_files']:
            for dv in ['log_cost', 'tool_calls', 'searches', 'test_runs', 'files_opened', 'gold_found_pre_edit', 'navshare_search', 'recall_all']:
                key = f'{name}: {iv} ~ {dv}'
                C[key] = dict(plain=perm_spear(col(rs, iv), col(rs, dv)),
                              partial_size=perm_spear(col(rs, iv), col(rs, dv), [col(rs, 'log_impl')]) if iv != 'log_impl' else None,
                              partial_recall=perm_spear(col(rs, iv), col(rs, dv), [col(rs, 'recall_all')]) if dv != 'recall_all' else None)
    for kind in ('plain', 'partial_size', 'partial_recall'):
        ks = [k for k in C if C[k][kind]]
        for k, qq in zip(ks, bh([C[k][kind]['p'] for k in ks])): C[k][kind]['q'] = round(float(qq), 4)
    out['C_iv_dv_within_benchmark'] = C

    # D
    D = {}
    for name, rs in (('fb', fb), ('sbp', sb), ('pooled', rows)):
        for mv in ['recall_all', 'recall_comments', 'recall_long']:
            for dv in ['log_cost', 'tool_calls', 'searches', 'files_opened', 'gold_found_pre_edit', 'navshare_search', 'orient_calls']:
                t = perm_spear(col(rs, mv), col(rs, dv))
                if t:
                    t['partial_size'] = perm_spear(col(rs, mv), col(rs, dv), [col(rs, 'log_impl')])
                    D[f'{name}: {mv} ~ {dv}'] = t
    for k, qq in zip(D, bh([v['p'] for v in D.values()])): D[k]['q'] = round(float(qq), 4)
    out['D_memorisation_vs_effort'] = D

    # E
    fb_r0 = sum(r['r0'] for r in fb); sb_r0 = sum(r['r0'] for r in sb)
    E = dict(r0_pass=dict(fb=f'{int(fb_r0)}/{len(fb)}', sbp=f'{int(sb_r0)}/{len(sb)}',
                          fisher_p=S.fisher_exact([[fb_r0, len(fb) - fb_r0], [sb_r0, len(sb) - sb_r0]])[1]),
             accepted_final=dict(fb=sum(r['accept_final'] == 'True' for r in fb), sbp=sum(r['accept_final'] == 'True' for r in sb)))
    reg = {}
    for name, rs in (('fb', fb), ('sbp', sb)):
        meas = [r for r in rs if not r['regression_adj'].startswith(('not_measured', 'missing'))]
        reg[name] = dict(measured=len(meas), regressions_raw=sum(r['regression_raw'] == 'REGRESSION' or r['regression_raw'] == 'P2P_FAIL' for r in meas),
                         regressions_adjusted=sum(r['regression_adj'] in ('REGRESSION', 'P2P_FAIL') for r in meas),
                         not_measured=len(rs) - len(meas))
    E['regression'] = reg
    out['E_rates'] = E

    # robustness: leave-one-repo-out sign stability for the D estimates within fb
    LORO = {}
    repos = sorted({r['repo'] for r in fb})
    for mv, dv in [('recall_all', 'searches'), ('recall_all', 'tool_calls'), ('recall_comments', 'searches'), ('recall_all', 'gold_found_pre_edit')]:
        rhos = {}
        for rp in repos:
            rs = [r for r in fb if r['repo'] != rp]; x, y = col(rs, mv), col(rs, dv); m = ~np.isnan(x) & ~np.isnan(y)
            rhos[rp] = round(float(S.spearmanr(x[m], y[m])[0]), 3)
        LORO[f'fb: {mv} ~ {dv}'] = rhos
    out['robust_leave_one_repo_out'] = LORO
    sb_np = [r for r in sb if 'protonmail' not in r['repo']]
    out['robust_sbp_without_protonmail'] = {k: dict(median=float(np.nanmedian(col(sb_np, k))), n=len(sb_np)) for k in ['recall_all', 'searches', 'tool_calls', 'cost_usd']}

    json.dump(out, open(HERE / 'stats_out.json', 'w'), indent=1, default=float)

    print(f"n FB={len(fb)} SWE-Pro={len(sb)}; min detectable |rho|: {out['power_min_rho']}")
    print('\nA. benchmark difference (FB vs SWE-Pro), BH within family')
    for k, v in A.items():
        print(f"  {k:26} med {v['median_fb']:9.3f} vs {v['median_sbp']:9.3f}  diff CI [{v['ci95'][0]:.2f},{v['ci95'][1]:.2f}]  delta={v['cliffs_delta']:+.2f} p={v['p']:.4f} q={v['q']:.4f}")
    print('\nB. benchmark coefficient after controlling memorisation (rank regression, Freedman-Lane)')
    for k, v in B.items():
        print(f"  {k:44} n={v['n']} coef={v['coef_bench_rank']:+.2f} p={v['p']:.4f} q={v['q']:.4f}")
    print('\nC. within-benchmark IV~DV (survivors q<.10 any kind)')
    for k, v in C.items():
        hits = {kk: vv for kk, vv in v.items() if vv and vv.get('q', 1) < .10}
        if hits: print(f"  {k:45} " + '  '.join(f"{kk} rho={vv['rho']:+.2f} q={vv['q']:.3f}" for kk, vv in hits.items()))
    print('\nD. memorisation vs effort')
    for k, v in D.items():
        print(f"  {k:45} rho={v['rho']:+.2f} p={v['p']:.4f} q={v['q']:.4f}  partial|size rho={v['partial_size']['rho'] if v['partial_size'] else '-'}")
    print('\nE.', json.dumps(E, default=float))
    print('\nLORO', json.dumps(LORO))


if __name__ == '__main__':
    main()
