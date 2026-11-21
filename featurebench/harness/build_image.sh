#!/usr/bin/env bash
# build_image.sh <instance_id> [cli_version] - build fbexp-agent:<repo-hash> from the
# task's FeatureBench instance image (pulled from docker.io/libercoders) + pinned CLI.
set -euo pipefail
HERE=$(realpath "$(dirname "$0")"); IID="$1"; CLI="${2:-2.1.310}"
IMAGE_NAME=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['image_name'])" "$HERE/tasks/$IID/meta.json")
TAG="fbexp-agent:$(echo "$IMAGE_NAME" | sed -E 's#.*featurebench-specs_##; s#-instance_#-#')"
docker image inspect "docker.io/$IMAGE_NAME" >/dev/null 2>&1 || docker pull "docker.io/$IMAGE_NAME"
docker build -f "$HERE/instruments/Dockerfile.agent" --build-arg BASE="docker.io/$IMAGE_NAME" \
  --build-arg CLI_VERSION="$CLI" -t "$TAG" "$HERE/instruments"
echo "built $TAG"
docker run --rm --user 1000:1000 -e HOME=/agent-home "$TAG" claude --version
