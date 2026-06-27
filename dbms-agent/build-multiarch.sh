#!/usr/bin/env bash
set -euo pipefail

IMAGE="${IMAGE:-dbms-agent}"
TAG="${TAG:-latest}"
PLATFORMS="${PLATFORMS:-linux/amd64,linux/arm64}"
BUILDER="${BUILDER:-dbms-agent-builder}"
OUTPUT_MODE="${OUTPUT_MODE:-oci}"
OCI_FILE="${OCI_FILE:-dbms-agent-${TAG}.oci.tar}"

if ! docker buildx inspect "${BUILDER}" >/dev/null 2>&1; then
  docker buildx create --name "${BUILDER}" --driver docker-container --use
else
  docker buildx use "${BUILDER}"
fi
docker buildx inspect --bootstrap >/dev/null

output_args=()
case "${OUTPUT_MODE}" in
  push)
    output_args+=(--push)
    ;;
  oci)
    output_args+=(--output "type=oci,dest=${OCI_FILE}")
    ;;
  load)
    if [[ "${PLATFORMS}" == *,* ]]; then
      echo "OUTPUT_MODE=load only supports one platform; set PLATFORMS=linux/amd64 or linux/arm64" >&2
      exit 2
    fi
    output_args+=(--load)
    ;;
  *)
    echo "OUTPUT_MODE must be push, oci, or load" >&2
    exit 2
    ;;
esac

docker buildx build \
  --platform "${PLATFORMS}" \
  --tag "${IMAGE}:${TAG}" \
  "${output_args[@]}" \
  .
