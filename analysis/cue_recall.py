#!/usr/bin/env python3
"""cue_recall.py -- how much of the required code each goal-only prompt points to (prompt-cue control).

Required units come from gold.patch (production files only; never test.patch):
  files  files gold adds lines to
  names  def/class names gold adds (dunders like __init__ excluded: they cue nothing)
Prompt = the exact round-0 prompt of the cell (runs/<cell>/rounds/r00/prompt.txt) when the cell has run,
else tasks/<iid>/prompt_goalrw.txt.
Per prompt:
  name_exact   share of required names written verbatim in the prompt (whole word, case-sensitive)
  name_code    share of required names written verbatim AND code-shaped (underscore or inner capital): drops
               plain-word names like insert/label/view that prose uses anyway. Recommended covariate.
  name_loose   share whose words appear as a phrase (snake/camel split, case-insensitive), e.g.
               missing_dims -> "missing dims"; superset of name_exact
  file_exact   share of required files whose path or dotted module is written in the prompt
  file_stem    also counting the file stem (>=4 chars) as a whole word, case-insensitive -- NOISY: prose words
               like "common", "frame", "series" match; upper bound only
  code_tokens  number of distinct code-shaped tokens in the prompt (dotted names, snake_case, CamelCase
               with an inner capital, name( calls, backticked spans): specificity regardless of target
The file-level grep variant of benchmark-audit CUE_STRENGTH (which files the prompt's identifiers hit in the
masked tree) needs the masked tree, i.e. a container; not computed here.
Output: cue_recall.csv, printed table.
"""
import csv, json, re, sys
from pathlib import Path

FB = Path('/home/niruthi/features/experiment-featurebench')
HERE = Path(__file__).resolve().parent
XARRAY = {'backends_chunks': 'pydata__xarray.97f3a746.test_backends_chunks.fa55f68a.lv1',
          'treenode': 'pydata__xarray.97f3a746.test_treenode.aa8ba777.lv1',
          'range_index': 'pydata__xarray.97f3a746.test_range_index.7b95ba66.lv1'}


def is_test(path):
    p = path.split('/')
    return 'tests' in p or p[-1].startswith('test_') or p[-1] == 'conftest.py'


def gold_units(patch):
    files, names, cur = set(), set(), None
    for line in patch.read_text(errors='replace').splitlines():
        if line.startswith('+++ '):
            f = line[4:]; f = f[2:] if f.startswith('b/') else f
            cur = None if f == '/dev/null' or is_test(f) else f
        elif line.startswith('+') and cur:
            if line[1:].strip():
                files.add(cur)
            m = re.match(r'\+\s*(?:async\s+)?(?:def|class)\s+(\w+)', line)
            if m and not (m.group(1).startswith('__') and m.group(1).endswith('__')):
                names.add(m.group(1))
    return files, names


def words(name):
    s = re.sub(r'([a-z0-9])([A-Z])', r'\1 \2', name.strip('_'))
    return [w.lower() for w in re.split(r'[_\s]+', s) if w]


def code_tokens(text):
    toks = set()
    toks |= set(re.findall(r'`([^`]+)`', text))
    toks |= set(re.findall(r'\b[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+\b', text))       # dotted
    toks |= set(re.findall(r'\b[a-z0-9]+(?:_[a-z0-9]+)+\b', text))              # snake_case
    toks |= set(re.findall(r'\b[A-Z][a-z0-9]+[A-Z]\w*\b', text))                # CamelCase
    toks |= {m + '(' for m in re.findall(r'\b([A-Za-z_]\w*)\(', text)}          # call(
    toks = {t for t in toks if not t.startswith(('http', 'github.com', 'www.'))}
    return toks


def main():
    cells = {r['task']: r['cell'] for r in csv.DictReader(open(HERE / 'goalrw_cells.csv'))}
    tasks = {t: json.load(open(FB / 'runs' / c / 'manifest.json'))['instance_id'] for t, c in cells.items()}
    tasks.update(XARRAY)
    for p in FB.glob('runs/*-goalrw'):           # xarray cells that have run
        for t, iid in XARRAY.items():
            if f'test_{t}-s1' in p.name and (p / 'rounds/r00/prompt.txt').exists():
                cells[t] = p.name
    rows = []
    for t, iid in tasks.items():
        td = FB / 'tasks' / iid
        if not (td / 'gold.patch').exists():
            print(f'{t:22} pending: no gold.patch until preflight'); continue
        src = FB / 'runs' / cells[t] / 'rounds/r00/prompt.txt' if t in cells else td / 'prompt_goalrw.txt'
        text = src.read_text()
        low = ' ' + re.sub(r'[^a-z0-9]+', ' ', text.lower()) + ' '
        files, names = gold_units(td / 'gold.patch')
        exact = sorted(n for n in names if re.search(r'(?<![\w.])' + re.escape(n) + r'(?!\w)', text))
        shaped = lambda n: '_' in n.strip('_') or re.search(r'[a-z][A-Z]', n)
        code_names = {n for n in names if shaped(n)}
        exact_code = [n for n in exact if shaped(n)]
        loose = sorted(n for n in names if ' ' + ' '.join(words(n)) + ' ' in low)
        fhit, fstem = [], []
        for f in files:
            mod = f[:-3].replace('/', '.') if f.endswith('.py') else f
            stem = Path(f).stem
            if f in text or mod in text:
                fhit.append(f)
            if f in text or mod in text or (len(stem) >= 4 and ' ' + ' '.join(words(stem)) + ' ' in low):
                fstem.append(f)
        ct = code_tokens(text)
        r = lambda a, b: round(len(a) / len(b), 3) if b else ''
        rows.append(dict(task=t, repo=iid.split('__')[0], prompt_source='cell r00' if t in cells else 'task file',
                         n_files=len(files), n_names=len(names),
                         name_exact=r(exact, names), name_code=r(exact_code, names), name_loose=r(loose, names), file_exact=r(fhit, files), file_stem=r(fstem, files),
                         code_tokens=len(ct), names_exact_hit=' '.join(exact), names_loose_hit=' '.join(loose),
                         files_stem_hit=' '.join(sorted(fstem)), code_token_list=' '.join(sorted(ct))))
    with open(HERE / 'cue_recall.csv', 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    print(f"{'task':22} {'files':>5} {'names':>5} {'exact':>6} {'code':>6} {'loose':>6} {'f_exact':>7} {'f_stem':>6} {'tokens':>6}")
    for x in rows:
        print(f"{x['task']:22} {x['n_files']:5} {x['n_names']:5} {x['name_exact']!s:>6} {x['name_code']!s:>6} {x['name_loose']!s:>6} "
              f"{x['file_exact']!s:>7} {x['file_stem']!s:>6} {x['code_tokens']:6}")


if __name__ == '__main__':
    main()
