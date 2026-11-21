#!/usr/bin/env bash
# build_image.sh <instance_id> -> sbpexp-agent:<short>: the V2 image + vendored CLI 2.1.310 (instruments/claude-cli, sha256 recorded)
set -euo pipefail
# public ghcr pulls without the Windows credential helper (desktop.exe over WSL vsock times out intermittently)
export DOCKER_CONFIG="$(realpath "$(dirname "$0")")/instruments/docker-anon"
HERE=$(realpath "$(dirname "$0")"); IID="$1"
BASE="ghcr.io/scaleapi/swe-bench_pro-v2:$IID"
TAG="sbpexp-agent:$(echo "$IID" | sed -E 's/^instance_//' | cut -c1-120)"
docker image inspect "$BASE" >/dev/null 2>&1 || docker pull -q "$BASE" || { sleep 30; docker pull -q "$BASE"; }
# libc of the task image decides the CLI build: glibc (default) or musl (Alpine V2 images, added 2026-11-04)
CTX="$HERE/instruments"
if docker run --rm --network none --entrypoint sh "$BASE" -c 'test -f /etc/alpine-release' >/dev/null 2>&1; then CTX="$HERE/instruments/musl"; fi
echo "cli variant: $([ "$CTX" = "$HERE/instruments" ] && echo glibc || echo musl) (context $CTX)"
for t in 1 2; do docker build -q -f "$CTX/Dockerfile.agent" --build-arg BASE="$BASE" -t "$TAG" "$CTX" && break; [ $t = 2 ] && exit 1; sleep 30; done
echo "built $TAG"
docker run --rm --network none -e HOME=/agent-home -e IS_SANDBOX=1 "$TAG" claude --version
