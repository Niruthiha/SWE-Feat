#!/usr/bin/env bash
# build_image.sh <task_id> -> dsexp-agent:<id>: the DeepSWE task image (task.toml environment.docker_image) UNCHANGED
# + vendored CLI 2.1.310 (instruments/claude-cli or instruments/musl, sha256 recorded). Port of swebench-pro build_image.sh.
set -euo pipefail
export DOCKER_CONFIG="$(realpath "$(dirname "$0")")/instruments/docker-anon"
HERE=$(realpath "$(dirname "$0")"); IID="$1"
BASE=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['image'])" "$HERE/tasks/$IID/meta.json")
TAG="dsexp-agent:$(echo "$IID" | cut -c1-120)"
docker image inspect "$BASE" >/dev/null 2>&1 || docker pull -q "$BASE" || { sleep 30; docker pull -q "$BASE"; }
CTX="$HERE/instruments"
if docker run --rm --network none --entrypoint sh "$BASE" -c 'test -f /etc/alpine-release' >/dev/null 2>&1; then CTX="$HERE/instruments/musl"; fi
echo "cli variant: $([ "$CTX" = "$HERE/instruments" ] && echo glibc || echo musl) (context $CTX)"
for t in 1 2; do docker build -q -f "$CTX/Dockerfile.agent" --build-arg BASE="$BASE" -t "$TAG" "$CTX" && break; [ $t = 2 ] && exit 1; sleep 30; done
echo "built $TAG"
docker run --rm --network none -e HOME=/agent-home -e IS_SANDBOX=1 "$TAG" claude --version
