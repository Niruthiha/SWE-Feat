# Go/TS technique-label validation (hand-checked, 2026-11-18)

Population: ALL 101 Bash calls in the 7 non-Python SWE-Pro runs (navidrome, vuls = Go; element-web, protonmail ×4 = TS/TSX).
No sample — every call checked; full label set must be right to count as correct.
Call dump: labels + first 300 chars per call; truncated calls re-read via their shell lines.

| Version | Correct | Errors |
|---|---|---|
| v1 (first extension) | 90/101 (89%) | 11 |
| v2 (after fix) | 98/101 (97%) | 3 (base SlopCodeBench classifier, left unfixed) |

v1 errors from the Go/TS extension (8, all fixed in v2):
- `timeout 600 npx tsc` / `timeout 300 npx jest` not matched (prefix rule only allowed start-of-command / ; & | ( newline): #47 #48 #53 #63 #64 #66 (missed static_check or own_test_run)
- `npx stylelint`, `npx prettier --check` not counted as static checks: #52 #54
Fix: prefix also allows `timeout N ` and `do `; stylelint / prettier --check added to static_check.
Effect: protonmail runs 20261105-010938 static_check 0→5; 20261105-092014 own_test_run 0→1, static_check 0→2. No FeatureBench count changed.

Remaining errors (base classifier, same kinds as SlopCodeBench validation, not fixed to keep it identical):
- #20 `git diff` after a heredoc on a new line not labelled git
- #40 `for f in …; do sed -n …` file reads labelled locate, not read
- #44 python script in /tmp that edits repo files labelled probe_tmp, not edit_script

Judgement call (counted correct, consistent with the codebook): a throwaway test file written into the repo, run, then deleted
(#6 #23 #100) is labelled edit_script + own_test_run, not a probe.
