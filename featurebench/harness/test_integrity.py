#!/usr/bin/env python3
"""test_integrity.py <diff.patch> - lines the agent REMOVED from or CHANGED IN tests
that already existed (experiment-hotcrp/test_integrity.py, path rule adapted to
Python repos: any file under a tests/ or test/ directory, or named test_*.py /
*_test.py). Run every round; a place a regression can hide behind an intended
behaviour change, flagged for human eyes, never a gate."""
import json, re, sys

TEST_RE = re.compile(r"(^|/)(tests?)/|(^|/)test_[^/]*\.py$|_test\.py$")


def audit(diff_text):
    cur, removed = None, {}
    for line in diff_text.splitlines():
        if line.startswith("+++ b/"):
            cur = line[6:]
        elif line.startswith("+++ /dev/null"):
            cur = None          # a deleted test file is reported from its --- header
        elif line.startswith("--- a/"):
            cur_old = line[6:]
            if TEST_RE.search(cur_old):
                cur = cur_old
        elif line.startswith("-") and not line.startswith("---") and cur:
            if TEST_RE.search(cur) and line[1:].strip():
                removed.setdefault(cur, []).append(line[1:].strip())
    return {"existing_test_lines_removed_or_changed": {k: len(v) for k, v in sorted(removed.items())},
            "total": sum(len(v) for v in removed.values()),
            "samples": {k: v[:5] for k, v in sorted(removed.items())},
            "note": "each removed/changed line in a pre-existing test is a place a regression can hide; review"}


if __name__ == "__main__":
    try:
        txt = open(sys.argv[1], encoding="utf-8", errors="replace").read()
    except OSError:
        txt = ""
    print(json.dumps(audit(txt), indent=2))
