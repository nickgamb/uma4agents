#!/usr/bin/env bash
# Build the lab's own images and push them to the local registry.
#
# The same Dockerfiles the compose stack uses — one source, two deployment
# shapes, which is the point. person-server needs `make fetch-upstream` to
# have populated its build context first; that is the same dependency compose
# has, and the Makefile target orders it.
set -euo pipefail

REG=localhost:5001
TAG="${TAG:-dev}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

build() {
  local name="$1" dockerfile="$2" context="$3"
  printf '  %-20s' "$name"
  docker build -q -t "${REG}/u4a/${name}:${TAG}" -f "$dockerfile" "$context" >/dev/null
  docker push -q "${REG}/u4a/${name}:${TAG}" >/dev/null
  echo "built and pushed"
}

build uma-as           services/uma-as/Dockerfile        .
build paios            kwaai/Dockerfile                  .
build uma-pep          services/uma-pep/Dockerfile       .
build alice-vault-mcp  mcp/alice-vault/Dockerfile        .
build portal           services/alice-portal/Dockerfile  ./services/alice-portal
build agent-operator   clients/agent-operator/Dockerfile ./clients/agent-operator
build org-authority    services/org-authority/Dockerfile .
build org-console      services/org-console/Dockerfile   ./services/org-console

if [ -d aauth/upstream/aauth-person-server/.git ]; then
  build person-server  aauth/person-server.Dockerfile    ./aauth
else
  echo "  person-server        skipped (run 'make fetch-upstream' first)"
fi
