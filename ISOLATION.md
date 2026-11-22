# Isolation: what we turned off, and how

This file explains every mechanism that controls what the agent can see and reach. It covers both benchmarks: SWE-bench Pro (61 runs) and FeatureBench (21 runs). It also lists what we did **not** turn off.

Each claim names the code that does it. File paths are relative to the repo root:
- SWE-bench Pro: `swebench-pro/harness/run_cell.sh`
- FeatureBench: `featurebench/harness/run_cell.sh`

The two harnesses use the same mechanisms unless a section says otherwise.

---

## 1. Summary

| What | Turned off? | How | Checked per run? |
|---|---|---|---|
| Internet (pip, npm, git, Go proxy, web) | yes | the agent container sits on an `--internal` Docker network; its only way out is a tinyproxy allowlist | yes, `isolation.txt` probes |
| WebSearch / WebFetch tools | yes | `--disallowedTools WebSearch WebFetch` | yes, from the command line in the transcript |
| MCP servers (incl. claude.ai connectors such as Gmail and Drive) | yes | `--strict-mcp-config --mcp-config '{"mcpServers":{}}'` | yes, `mcp_servers: []` in the transcript's `init` event |
| User memory, settings, CLAUDE.md, plugins, project history | yes | `HOME=/agent-home`, a new empty directory inside the container | yes, `find $HOME` in `isolation.txt` |
| Host files | yes | no bind mounts except the read-only credentials file | yes, the `mounts` section of `isolation.txt` |
| Hidden tests, gold patch, verifier | yes | never copied into the agent container; acceptance runs in a separate container | yes, path checks in `isolation.txt` |
| Test results reaching the agent | yes | later rounds send a fixed text (`blind_msg.txt`) | by construction |
| Root access | yes | the agent runs as uid 1000 | yes, `id` in `isolation.txt` |
| **Account skills** (`anthropic-skills:*`) | **no** | not turned off; see section 9 | listed in each transcript's `init` event |
| **Git identity (SWE-bench Pro)** | **no** | FeatureBench sets a neutral one; SWE-bench Pro doesn't; see section 10 | — |
| Permission prompts | turned off on purpose | `--dangerously-skip-permissions` (headless runs) | — |

---

## 2. Network: an internal network plus an allowlist proxy

**Setup** (`run_cell.sh` makes it on the first run; it's also listed in the README):

```bash
docker network create --internal hcexp-cellnet   # no route to the internet
docker network create hcexp-egressnet            # normal bridge
docker run -d --name hcexp-egress --network hcexp-cellnet hcexp-egress:2
docker network connect hcexp-egressnet hcexp-egress
```

- **The agent container** is started with `--network hcexp-cellnet`. Docker gives an `--internal` network no gateway, so the container has no direct route out at all.
- **The proxy container `hcexp-egress`** is the only one attached to both networks. The agent's environment points at it:
  ```
  -e HTTPS_PROXY=http://hcexp-egress:8888 -e HTTP_PROXY=... -e https_proxy=... -e http_proxy=...
  -e NO_PROXY=localhost,127.0.0.1
  ```
- **The proxy** is built from `swebench-pro/harness/instruments/docker-egress/`: alpine 3.20 with tinyproxy. Its config, `tinyproxy.conf`:
  ```
  ConnectPort 443
  Filter "/etc/tinyproxy/filter"
  FilterExtended On
  FilterDefaultDeny Yes
  ```
  and the `filter` file, which is the whole allowlist:
  ```
  ^api\.anthropic\.com$
  ^statsig\.anthropic\.com$
  ^console\.anthropic\.com$
  ^platform\.claude\.com$
  ```
  `FilterDefaultDeny Yes` means every other host is refused. `platform.claude.com` is needed for OAuth token refresh. Without it, long runs died when the token expired; that's why the image is version `:2`.
- **Even if a program ignored the proxy variables,** it still couldn't get out, because the internal network has no route.
- **Acceptance and regression containers** run with `--network none`.

**Per-run check.** Before the agent starts, `run_cell.sh` curls a set of hosts from inside the agent container and writes the HTTP codes to `runs/<run>/isolation.txt`. Totals across all runs:

| Host | SWE-bench Pro (61) | FeatureBench (21) |
|---|---|---|
| github.com | 000 (refused) ×61 | 000 ×21 |
| pypi.org | 000 ×61 | 000 ×21 |
| registry.npmjs.org | 000 ×61 | — |
| proxy.golang.org | 000 ×61 | — |
| raw.githubusercontent.com | — | 000 ×21 |
| api.anthropic.com | 404 ×40, 000 ×21 | 404 ×21 |
| platform.claude.com | 200 ×37, 000 ×24 | 200 ×21 |

- A 404 or 200 from an Anthropic host means the proxy let the request through (`/` on the API host returns 404).
- In 21–24 SWE-bench Pro runs the probe of the allowed hosts also returned 000. The probe has a 12-second timeout, and those were all runs where the agent then ran normally through the same proxy, so the 000 there is a probe timeout, not a block.
- **No disallowed host ever answered.**

---

## 3. Web tools

The agent command line (identical in both harnesses) is:

```bash
claude -p "<prompt>" --model <model> --session-id <uuid>        # round 0; later rounds: --resume <uuid>
  --strict-mcp-config --mcp-config '{"mcpServers":{}}'
  --output-format stream-json --verbose
  --disallowedTools WebSearch WebFetch
  --dangerously-skip-permissions
```

- **`--disallowedTools WebSearch WebFetch`** removes both web tools from the agent's toolset. The network allowlist (section 2) would block them anyway; the flag means the agent never sees them as available.
- **Result:** across the 82 runs, there were no WebSearch or WebFetch calls.

---

## 4. MCP servers and connectors

- **What the flags do:** `--strict-mcp-config` tells Claude Code to use only the MCP config given on the command line and ignore every other source (user, project and account/claude.ai connectors). That config is empty: `{"mcpServers":{}}`.
- **Why:** without this, a signed-in account can bring claude.ai connectors (Gmail, Drive, Calendar…) into the session. We saw that leak in an earlier study on 2026-09-03, which is why this flag is checked by `featurebench/harness/audit_isolation.sh`.
- **Check:** each transcript's first `system/init` event lists `mcp_servers`, and it is empty in all 82 runs.

---

## 5. Empty HOME: no memory, settings, CLAUDE.md or plugins

- **How:** the container is started with `-e HOME=/agent-home`, a directory created fresh inside the container and owned by uid 1000.
- **What that leaves out:** Claude Code reads user state from `$HOME/.claude/`: memory, `settings.json`, the global `CLAUDE.md`, installed plugins, project history and todos. None of it exists in the agent's HOME, so none of it loads.
- **What is in HOME:** only the credentials file (section 6). `isolation.txt` records `find $HOME`:
  ```
  /agent-home
  /agent-home/.claude
  /agent-home/.claude/.credentials.json
  ```
- **Instruction files:** `isolation.txt` also checks for `CLAUDE.md`, `AGENTS.md` and `.mcp.json` at `/`, in the work tree and in HOME, and lists any shipped inside the repo itself.
  - Repo-shipped files (e.g. mlflow's `CLAUDE.md`) are part of the task as the benchmark ships it. We recorded them and did not remove them.
- **FeatureBench change-impact arm only:** that arm (not part of the 21 analysed runs) passes one extra `--settings /opt/impact/settings.json`. The file is root-owned and read-only to the agent. The analysed goal-only runs pass no `--settings`.

---

## 6. Credentials

- **How they get in:** the credentials file is the only host file mounted, read-only and outside HOME:
  ```bash
  -v "$(realpath "$CLAUDE_CREDS")":/creds/credentials.json:ro
  ```
  As uid 1000, the harness copies it to `$HOME/.claude/.credentials.json` with mode 600, because the CLI refreshes the token in place and can't write to a read-only mount.
- **Mount check:** `isolation.txt` records the mount table. `audit_isolation.sh` fails if there is more than one `-v` mount.
- **API key alternative:** if `ANTHROPIC_API_KEY` is set instead, it is passed as an environment variable and no file is mounted. All 82 runs used the OAuth credentials file.
- **Environment variables** whose names contain `claude` or `anthropic` are logged with their values replaced by `<redacted>`.

---

## 7. Hidden tests, gold patch and verifier

- **What the agent container holds:** only the task's repo at its base commit and the prompt.
- **Path check:** `isolation.txt` records that `/tests`, `/solution`, `/logs/verifier` and `/oracle` are absent.
- **Hidden test files:** for every file the hidden test patch touches, `isolation.txt` records that it is still the `HEAD` version (or absent), i.e. the test patch was not applied.
- **Git history:** `isolation.txt` records the commit count and that there are no refs ahead of `HEAD` and no stash, so the solution can't be reached through git history.
- **FeatureBench:** each run starts from the image's pristine copy (`prepare_tree.sh` does `cp -r /root/my_repo/* /testbed/`). The masked feature is removed there before the agent starts.
- **Acceptance** runs after every round in a separate container from the **pristine** image with `--network none`:
  - the agent's diff is applied there, then the benchmark's own tests run;
  - nothing from that container is sent back to the agent.

---

## 8. No test feedback

- **Round 0** sends the task prompt.
- **Every later round** sends the fixed text in `blind_msg.txt`: "This is not done correctly. Keep working on it until it is."
- **Audit:** `audit_isolation.sh` checks that `blind_msg.txt` doesn't reference acceptance output and that no acceptance output is routed into a prompt.

---

## 9. NOT turned off: account skills

- **What happened:** we turned off MCP, the web tools and user state, but not Claude Code **skills**. Skills come with the signed-in account and the CLI, not from files in HOME, so the empty HOME didn't remove them.
- **Two setups appear** in the `skills` list of each transcript's `init` event:
  - **built-in only:** the CLI's own skills (`dataviz`, `code-review`, `simplify`, `debug`, `loop`, `schedule`, `claude-api`, …);
  - **built-in plus the account set:** the same, plus `anthropic-skills:docs`, `:pdf`, `:xlsx`, `:pptx`, `:docx`, `:computer-use`, `:chrome-browser`, `:built-in-browser`, `:deep-research`, `:import-memory`, `:morning`, `:skill-creator`, `:google-workspace`.

| | account set loaded | built-in only |
|---|---|---|
| SWE-bench Pro (61) | 40 | 21 |
| FeatureBench (21) | 9 | 12 |

- **Effect:** no agent called the Skill tool in any of the 82 runs (0 `"name":"Skill"` tool uses across all rounds), so the extra skills were never exercised. It is still a difference in the starting setup between runs, and it is disclosed in `analysis/STATISTICS.md` §7.
- **For new runs:**
  - turn account skills off, or pin one fixed set, so every run starts identically;
  - keep recording the `init` skills list per run;
  - check before analysis that it's the same in every run.

---

## 10. NOT turned off: git identity (SWE-bench Pro)

- **FeatureBench** sets a neutral, repo-local identity inside the agent container (`featurebench/harness/instruments/prepare_tree.sh`):
  ```bash
  git config user.email "fb@bench.com" && git config user.name "FeatureBench"
  ```
- **SWE-bench Pro** doesn't set one, so an agent commit there could pick up identity details from the account.
- **In our 82 runs no agent made a commit,** so no commit carries an identity. The one transcript containing "git commit" is git's own `git status` hint text.
- **Account email in transcripts:** the account email and organization id appear in transcript metadata regardless. They are replaced with `<redacted-email>` / `<redacted-org>` in every file in this repo.
- **For new runs:** set a neutral `user.name` / `user.email` in every container, in both harnesses.

---

## 11. What is graded

- **How the diff is taken:** after every round, the harness snapshots the agent's work as a diff from the **base commit** through a temporary git index (`GIT_INDEX_FILE=/tmp/.sbpsnap.index`, or `.fbsnap.index` for FeatureBench). It runs `git add -A` into that index (binaries dropped) and then `git diff --cached <base>`.
- **What that captures:** uncommitted working-tree edits *and* anything committed, without touching the agent's own index.
- **The one exclusion:** a commit followed by reverting the working tree would show only the final tree state. That is the intended behavior, since the final tree is what gets tested.
- **Comparison with DeepSWE:** DeepSWE's official harness grades committed changes only. For new runs on that benchmark, record both and report both.

---

## 12. Where to look in each run

| File | What it shows |
|---|---|
| `runs/<run>/isolation.txt` | whoami, HOME contents, env (redacted), absent verifier paths, hidden-test files at HEAD, instruction files, git history, mounts, egress probe codes |
| `runs/<run>/manifest.json` | CLI version, model, image, egress image and allowlist, base commit, agent uid |
| `runs/<run>/transcript.jsonl`, first line | the `init` event: tools, `mcp_servers` (empty), `skills` (section 9) |
| `runs/<run>/rounds/rNN/prompt.txt` | exactly what the agent received in each round |
| `featurebench/harness/audit_isolation.sh` | a static audit of `run_cell.sh` that fails if any of the above mechanisms is missing |
