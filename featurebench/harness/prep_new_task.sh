#!/usr/bin/env bash
# prep_new_task.sh <instance_id> <pristine-dir-name>: everything a task needs before run_four_arms,
# one Docker step at a time. Rerun after a crash; finished steps are skipped. Stops at the first failure.
set -euo pipefail
cd "$(dirname "$0")"; IID="$1"; P="../analysis/traces/pristine/$2"
[ -s "tasks/$IID/meta.json" ] || python3 make_task.py "$IID"
python3 - "$IID" <<'PY'
import csv,json,sys
iid=sys.argv[1]; f=f"tasks/{iid}/meta.json"; m=json.load(open(f))
src="eligible.csv"; rows={x["instance_id"]:x for x in csv.DictReader(open("../featurebench/inventory/eligible.csv"))}
if iid not in rows: src="tasks.csv"; rows={x["instance_id"]:x for x in csv.DictReader(open("../featurebench/inventory/tasks.csv"))}
r=rows[iid]
m["covariates"]={k:r.get(k) for k in ("dos_pkg","dos_file","n_files","n_packages","eff_packages","impl_loc","n_ops","hidden_tests")}
m["covariates"]["source"]=src; json.dump(m,open(f,"w"),indent=2)
PY
TAG="fbexp-agent:$(python3 -c "import json;print(json.load(open('tasks/$IID/meta.json'))['image_name'])" | sed -E 's#.*featurebench-specs_##; s#-instance_#-#')"
docker image inspect "$TAG" >/dev/null 2>&1 || ./build_image.sh "$IID"
if [ ! -d "$P/.done" ]; then rm -rf "$P"; mkdir -p "$P"
  docker run --rm --user 0:0 --entrypoint tar "$TAG" -C /root/my_repo --exclude=.git -cf - . | tar -xf - -C "$P"; mkdir "$P/.done"; fi
python3 -c "import json,sys;sys.exit(0 if json.load(open('tasks/$IID/preflight.json'))['gold']=='PASS' else 1)" 2>/dev/null || ./preflight_task.sh "$IID"
python3 -c "import json;d=json.load(open('tasks/$IID/preflight.json'));print('PREFLIGHT',d['gold'],d['noop']);assert d['gold']=='PASS' and d['noop']=='FAIL'"
[ -s "tasks/$IID/docstrip/preflight.json" ] || ./preflight_docstrip.sh "$IID"
python3 -c "import json;d=json.load(open('tasks/$IID/docstrip/preflight.json'));print('DOCSTRIP',{k:v for k,v in d.items() if isinstance(v,(str,int,bool))});assert d['gold']=='PASS' and d['noop']=='FAIL' and d['leak_files_found']==0 and d['answerkey_files_found']==0"
python3 instruments/doc_dose.py "$IID" | tail -1
echo PREP_DONE
