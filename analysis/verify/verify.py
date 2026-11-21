import numpy as np, pandas as pd
from scipy import stats
rng=np.random.default_rng(0)
d=pd.read_csv('../cells.csv'); d['sw']=(d.bench!='FeatureBench').astype(int)
d['logsize']=np.log(d.impl_lines)
IV=['n_files','impl_lines','n_dirs','dos_dir','cue_files','cue_tokens']
MEM=['recall_all','recall_long','gold_comments','recall_comments','precision','files_outside_gold']
NAV=['tool_calls','api_turns','searches','test_runs','files_opened','files_read_full','listings','orient_calls','orient_searches','gold_found_pre_edit','gold_found_by_done','rework','navshare_search','navshare_following_code','navshare_recall','navshare_benchmark_clue','navshare_not_found']
OUT=['r0_pass','accept_final','rounds','cost_usd','wall_s']
ALL=IV+MEM+NAV+OUT
def cliff(a,b):
    a,b=np.asarray(a,float),np.asarray(b,float); return (np.sign(a[:,None]-b[None,:])).mean()
def perm_p(a,b,B=20000):
    x=np.r_[a,b]; n=len(a); obs=abs(np.mean(a)-np.mean(b)); c=0
    for _ in range(B):
        p=rng.permutation(x); c+=abs(p[:n].mean()-p[n:].mean())>=obs-1e-12
    return (c+1)/(B+1)
def bh(p):
    p=np.asarray(p); n=len(p); o=np.argsort(p); q=p[o]*n/np.arange(1,n+1)
    q=np.minimum.accumulate(q[::-1])[::-1]; r=np.empty(n); r[o]=np.minimum(q,1); return r
print("N",d.groupby('bench').size().to_dict())
print("\n== T1 descriptives median [Q1,Q3] ==")
for c in ALL:
    s=[]
    for b,g in d.groupby('bench'):
        x=g[c].astype(float).dropna(); s.append(f"{b[:5]} {x.median():.3g} [{x.quantile(.25):.3g},{x.quantile(.75):.3g}] n={len(x)}")
    print(f"{c:26s}"," | ".join(s))
print("\n== T2 MWU / Cliff / perm / BH ==")
rows=[]
for c in IV+MEM+NAV+['rounds','cost_usd','wall_s']:
    a=d.loc[d.sw==0,c].astype(float).dropna(); b=d.loc[d.sw==1,c].astype(float).dropna()
    rows.append([c,stats.mannwhitneyu(a,b).pvalue,cliff(b,a),perm_p(a.values,b.values,5000)])
r=pd.DataFrame(rows,columns=['var','p_mwu','cliff_SW_vs_FB','p_perm']); r['q_bh']=bh(r.p_mwu)
print(r.round(4).to_string())
print(pd.crosstab(d.bench,d.r0_pass));print("Fisher r0_pass", stats.fisher_exact(pd.crosstab(d.sw,d.r0_pass)))
print("\nRecall overlap: FB min",d[d.sw==0].recall_all.min(),"SW max",d[d.sw==1].recall_all.max(),
      "| SW cells with recall>=FB min:",(d[d.sw==1].recall_all>=d[d.sw==0].recall_all.min()).sum())
print("\n== T2b rank regression: rank(DV) ~ sw + rank(recall) + rank(logsize); permutation of sw (Freedman-Lane) ==")
def rk(x): return stats.rankdata(x)
def fl(y,X,cov,B=5000):
    Z=np.column_stack([np.ones(len(y))]+cov); full=np.column_stack([Z,X])
    beta=np.linalg.lstsq(full,y,rcond=None)[0][-1]
    bz=np.linalg.lstsq(Z,y,rcond=None)[0]; fit=Z@bz; res=y-fit; c=0
    for _ in range(B):
        yp=fit+rng.permutation(res); c+=abs(np.linalg.lstsq(full,yp,rcond=None)[0][-1])>=abs(beta)
    return beta,(c+1)/(B+1)
for c in ['tool_calls','api_turns','searches','files_opened','test_runs','gold_found_pre_edit','navshare_search','navshare_recall','cost_usd','wall_s']:
    e=d[d[c].notna()]; y=rk(e[c]); out=[]
    for name,cov in [('none',[]),('+size',[rk(e.logsize),rk(e.n_files)]),('+recall',[rk(e.recall_all)]),('+recall+size',[rk(e.recall_all),rk(e.logsize),rk(e.n_files)])]:
        b,p=fl(y,e.sw.values.astype(float),cov); out.append(f"{name}: b={b:+.1f} p={p:.3f}")
    print(f"{c:20s}",' | '.join(out))
print("\nVIF-ish: corr(sw, rank recall)=%.2f corr(sw,rank logsize)=%.2f"%(stats.spearmanr(d.sw,d.recall_all)[0],stats.spearmanr(d.sw,d.logsize)[0]))
print("\n== T2c comment-line matching ==")
for b,g in d.groupby('bench'):
    print(b,"gold_comments==0:",(g.gold_comments==0).sum(),"recall_comments median",g.recall_comments.median())
print("rho(recall_all, recall_comments) all:",stats.spearmanr(d.recall_all,d.recall_comments,nan_policy='omit'))
for c in ['tool_calls','searches','cost_usd','gold_found_pre_edit']:
    e=d[d.recall_comments.notna()&d[c].notna()]; m=np.ones(len(e),bool)
    b,p=fl(rk(e[c]),e.sw.values.astype(float),[rk(e.recall_comments)]); print(f"{c}: sw|recall_comments (n={m.sum()}) b={b:+.1f} p={p:.3f}")
print("\n== T2d stratum: recall in overlap [0.6,0.9] ==")
s=d[(d.recall_all>=.6)&(d.recall_all<=.9)]; print(s[['bench','task','recall_all','tool_calls','searches','cost_usd']].to_string())
print("\n== T3 within-bench Spearman (and partial on recall) ==")
def partial(x,y,z):
    x,y,z=rk(x),rk(y),rk(z); rx=x-np.polyval(np.polyfit(z,x,1),z); ry=y-np.polyval(np.polyfit(z,y,1),z)
    return stats.pearsonr(rx,ry)[0]
for b,g in d.groupby('bench'):
    print('--',b,len(g)); ps=[];lines=[]
    for iv in ['n_files','impl_lines','n_dirs','dos_dir','recall_all']:
        for dv in ['cost_usd','tool_calls','searches','gold_found_pre_edit','wall_s']:
            h=g[list(dict.fromkeys([iv,dv,'recall_all']))].dropna(); rho,p=stats.spearmanr(h[iv],h[dv]); pr=partial(h[iv],h[dv],h.recall_all) if iv!='recall_all' else np.nan
            ps.append(p); lines.append((iv,dv,rho,p,pr))
    q=bh(ps)
    for (iv,dv,rho,p,pr),qq in zip(lines,q): print(f"  {iv:11s}~{dv:20s} rho={rho:+.2f} p={p:.3f} q={qq:.3f} partial|recall={pr:+.2f}")
print("\n== T4 robustness ==")
def mw(dd,c):
    a=dd.loc[dd.sw==0,c].dropna();b=dd.loc[dd.sw==1,c].dropna(); return cliff(b,a),stats.mannwhitneyu(a,b).pvalue
K=['tool_calls','searches','files_opened','cost_usd','gold_found_pre_edit','recall_all','impl_lines','n_files']
print("drop protonmail:",{c:tuple(np.round(mw(d[d.repo!='protonmail'],c),3)) for c in K})
for rp in d.repo.unique():
    dd=d[d.repo!=rp]; print(f" LORO -{rp:16s}",{c:round(mw(dd,c)[0],2) for c in K[:5]}, "max p",round(max(mw(dd,c)[1] for c in K[:5]),3))
print("bootstrap 95% CI of Cliff delta (SW vs FB) and median diff:")
for c in K:
    a=d.loc[d.sw==0,c].dropna().values;b=d.loc[d.sw==1,c].dropna().values; cd=[];md=[]
    for _ in range(4000):
        aa=rng.choice(a,len(a));bb=rng.choice(b,len(b)); cd.append(cliff(bb,aa)); md.append(np.median(bb)-np.median(aa))
    print(f"  {c:20s} delta={cliff(b,a):+.2f} CI[{np.percentile(cd,2.5):+.2f},{np.percentile(cd,97.5):+.2f}] meddiff CI[{np.percentile(md,2.5):.3g},{np.percentile(md,97.5):.3g}]")
nA,nB=int((d.sw==0).sum()),int((d.sw==1).sum())
print(f"Power: MWU {nA} vs {nB}, alpha .05, 80% power -> simulate min |Cliff delta| (normal shift)")
for shift in [0.4,0.5,0.6,0.8,1.0,1.2]:
    hits=sum(stats.mannwhitneyu(rng.normal(0,1,nA),rng.normal(shift,1,nB)).pvalue<.05 for _ in range(2000))
    print(f"  shift d={shift}: power={hits/2000:.2f}, Cliff~{2*stats.norm.cdf(shift/np.sqrt(2))-1:.2f}")
for n in [nA,nB]:
    for rho in [0.4,0.5,0.6,0.7]:
        z=np.arctanh(rho)*np.sqrt(n-3); print(f"  Spearman n={n} rho={rho}: approx power={stats.norm.cdf(z-1.96):.2f}")
