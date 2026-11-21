#!/usr/bin/env python3
"""behaviour.py -- per-cell behaviour/technique counts from auto/<bench>/<cell>.json (trace extracts) -> behaviour.csv.
Search technique is classified from each Bash call's command text (one call can hold several techniques)."""
import csv, glob, json, os, re
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
SEG = ['search', 'grep_on_file', 'read_part', 'read_full', 'list', 'edit', 'test_run', 'probe', 'git_diff', 'git_log']
SEARCH = {'grep_recursive': r'\bgrep\b[^|;&\n]*\s-\w*[rR]', 'grep_pipe_or_file': r'\bgrep\b', 'ripgrep': r'(^|[\s;&|(])rg\s',
          'find': r'(^|[\s;&|(])find\s', 'git_grep': r'\bgit\s+grep\b', 'git_ls_files': r'\bgit\s+ls-files\b'}


def search_tech(cmd):
    hits = Counter()
    for seg in re.split(r'\n|;|&&|\|\|', cmd):
        s = seg.strip()
        if re.search(SEARCH['git_grep'], s): hits['git_grep'] += 1
        elif re.search(SEARCH['git_ls_files'], s): hits['git_ls_files'] += 1
        elif re.search(SEARCH['ripgrep'], ' ' + s): hits['ripgrep'] += 1
        elif re.search(SEARCH['grep_recursive'], s): hits['grep_recursive'] += 1
        elif re.search(SEARCH['find'], ' ' + s): hits['find'] += 1
        elif re.search(SEARCH['grep_pipe_or_file'], s): hits['grep_pipe_or_file'] += 1
    return hits


def edit_tech(call):
    if call['tool'] in ('Edit', 'MultiEdit'): return 'edit_tool'
    if call['tool'] == 'Write': return 'write_tool'
    c = call.get('cmd') or ''
    if re.search(r'python3?\s+-\s*<<|python3?\s+<<|python3? -c', c): return 'python_script'
    if re.search(r'\bsed\s+-i|perl\s+-pi', c): return 'sed_perl_inplace'
    if re.search(r'cat\s*>|tee\s|>>?\s*\S', c): return 'shell_redirect'
    return 'other'


rows = []
for bench in ('featurebench', 'swebench_pro'):
    for p in sorted(glob.glob(f'{HERE}/auto/{bench}/*.json')):
        o = json.load(open(p))
        a = o['activity']; segs = Counter(a.get('segments_by_kind') or {})
        nseg = sum(segs.values()) or 1
        r = dict(cell=o['run'], bench='FeatureBench' if bench == 'featurebench' else 'SWE-bench Pro')
        for k in SEG:
            r[f'seg_{k}'] = segs.get(k, 0)
            r[f'segshare_{k}'] = round(segs.get(k, 0) / nseg, 3)
        st, et = Counter(), Counter()
        for c in o['calls']:
            if c['tool'] == 'Bash' and any(e[0] == 'search' for e in c['events']):
                st += search_tech(c.get('cmd') or '')
            if any(e[0] == 'edit' for e in c['events']):
                et[edit_tech(c)] += 1
        ns = sum(st.values()) or 1; ne = sum(et.values()) or 1
        for k in SEARCH:
            r[f'srch_{k}'] = st.get(k, 0); r[f'srchshare_{k}'] = round(st.get(k, 0) / ns, 3) if st else ''
        for k in ('edit_tool', 'write_tool', 'python_script', 'sed_perl_inplace', 'shell_redirect', 'other'):
            r[f'editshare_{k}'] = round(et.get(k, 0) / ne, 3) if et else ''
        r['bash_share'] = round(a['tools'].get('Bash', 0) / (a['tool_calls'] or 1), 3)
        r['dedicated_tool_calls'] = sum(v for k, v in a['tools'].items() if k in ('Read', 'Grep', 'Glob', 'Edit', 'Write'))
        r['files_read_part'] = a.get('files_read_part'); r['files_grep_only'] = a.get('files_grep_only')
        r['files_seen_in_output'] = a.get('files_seen_in_output'); r['files_edited_any'] = a.get('files_edited_any')
        r['read_part_per_full'] = round(segs.get('read_part', 0) / max(segs.get('read_full', 0), 1), 2)
        r['searches_per_edit'] = round(segs.get('search', 0) / max(segs.get('edit', 0), 1), 2)
        orr = o['orientation']
        r['ctx_tokens_before_first_edit'] = orr.get('ctx_tokens_before_first_edit')
        r['share_ctx_before_first_edit'] = orr.get('share_ctx_before_first_edit')
        r['files_opened_before_first_edit'] = orr.get('files_opened_before_first_edit')
        stt = o['self_testing']
        r['ran_tests_before_first_edit'] = int(bool(stt.get('ran_tests_before_first_edit')))
        r['test_cases_added'] = stt.get('test_cases_added', 0)
        r['probes'] = len(o['probing'].get('probe_segments') or [])
        tk = o['outcome']['tokens_total']
        r['output_tokens'] = tk['output_tokens']; r['cache_read_tokens'] = tk['cache_read_input_tokens']
        rows.append(r)

keys = list(dict.fromkeys(k for r in rows for k in r))
with open(f'{HERE}/behaviour.csv', 'w', newline='') as fh:
    w = csv.DictWriter(fh, fieldnames=keys); w.writeheader(); w.writerows(rows)
print(len(rows), 'cells')
for r in rows:
    print(r['bench'][:4], r['cell'][:40], {k[5:]: r[k] for k in r if k.startswith('srch_') and r[k]})
