#!/bin/bash
# prep_agent.sh - root, inside the AGENT container, before the agent exists. Makes the task image usable by the
# non-root agent (the CLI refuses --dangerously-skip-permissions as root) without changing what the code/tests see:
#   * the repo tree -> owned by uid 1000;  /root -> 755 so image-wide tools under it resolve
#   * the toolchain caches the image warmed as root (go build/mod cache, pip/npm caches) -> writable by uid 1000,
#     and their locations pinned in /etc/sbpexp-agent.env (HOME changes to /agent-home, which would move them)
# Prints WORKDIR <dir>. Fails if any harness/verifier/solution path exists in the image.
set -e
W=$(cd /app 2>/dev/null && pwd || (cd /testbed && pwd))
for p in /tests /solution /logs/verifier /oracle; do [ -e "$p" ] && { echo "LEAK: $p present in image"; exit 7; }; done
chown -R 1000:1000 "$W"
chmod 755 /root
: > /etc/sbpexp-agent.env
if command -v go >/dev/null 2>&1; then
  GC=$(HOME=/root go env GOCACHE); GM=$(HOME=/root go env GOMODCACHE); GP=$(HOME=/root go env GOPATH)
  echo "export GOCACHE=$GC GOMODCACHE=$GM GOPATH=$GP GOFLAGS=$(HOME=/root go env GOFLAGS)" >> /etc/sbpexp-agent.env
  for d in "$GC" "$GM" "$GP"; do [ -d "$d" ] && chmod -R a+rwX "$d"; done
fi
for d in /root/.cache /root/.npm /root/.yarn /root/.local /root/.config; do [ -d "$d" ] && chmod -R a+rwX "$d"; done
[ -d /root/.cache/pip ] && echo "export PIP_CACHE_DIR=/root/.cache/pip" >> /etc/sbpexp-agent.env
[ -d /root/.npm ] && echo "export npm_config_cache=/root/.npm" >> /etc/sbpexp-agent.env
chmod 644 /etc/sbpexp-agent.env
echo "WORKDIR $W"
echo "ENVFILE $(tr '\n' ';' < /etc/sbpexp-agent.env)"
