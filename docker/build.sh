#!/bin/bash
# Strix — Kali Gold Image Build Script
# Builds the sectest/kali-sandbox:latest image from Dockerfile.kali
#
# Usage:
#   bash docker/build.sh
#
# Prerequisites:
#   Docker Engine running and accessible

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

IMAGE_NAME="sectest/kali-sandbox"
IMAGE_TAG="latest"
DOCKERFILE="$SCRIPT_DIR/Dockerfile.kali"

echo "=== Strix Kali Gold Image Build ==="
echo "Image:  $IMAGE_NAME:$IMAGE_TAG"
echo "Dockerfile: $DOCKERFILE"
echo "Context: $PROJECT_ROOT"
echo ""

# Build from project root so .dockerignore is picked up
docker build \
    -t "$IMAGE_NAME:$IMAGE_TAG" \
    -f "$DOCKERFILE" \
    "$PROJECT_ROOT"

echo ""
echo "Build complete: $IMAGE_NAME:$IMAGE_TAG"
echo ""
echo "Verify with:"
echo "  docker run --rm $IMAGE_NAME:$IMAGE_TAG nmap --version"
echo "  docker run --rm $IMAGE_NAME:$IMAGE_TAG semgrep --version"
echo "  docker run --rm $IMAGE_NAME:$IMAGE_TAG bandit --version"
