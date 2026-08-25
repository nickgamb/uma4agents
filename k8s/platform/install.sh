#!/usr/bin/env bash
# Install the platform: everything under the lab, none of the lab itself.
#
# Helm for third-party, kustomize for ours. These components all ship as
# charts and all manage their own CRD lifecycle; hand-copying their manifests
# into this repo would mean owning an upgrade path nobody asked for. What
# stays hand-written, and readable, is the part that is the actual content —
# the namespaces, the policies, and the workloads under k8s/base.
#
# Idempotent: `helm upgrade --install` throughout, so running it twice is a
# no-op and running it after a version bump is the upgrade.
set -euo pipefail

# Every chart below is public, and none of them needs a credential. Helm's OCI
# client does not know that: it consults ~/.docker/config.json, finds
# `credsStore: desktop`, and shells out to `docker-credential-desktop get`.
# When that helper hangs — and under Docker Desktop it sometimes does, with no
# error, no timeout and no network connection — the install hangs with it, at
# the kgateway step, for as long as anyone is willing to wait.
#
# So these pulls get a registry config of their own, with nothing in it. It
# costs one directory and removes the only step here that can stall
# indefinitely. A private chart would need the real config back, and would
# need to say so.
HELM_ISOLATED_CONFIG="$(mktemp -d)"
printf '{}' > "$HELM_ISOLATED_CONFIG/config.json"
export DOCKER_CONFIG="$HELM_ISOLATED_CONFIG"
trap 'rm -rf "$HELM_ISOLATED_CONFIG"' EXIT

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$HERE/versions.env"

step() { printf '\n\033[1m==> %s\033[0m\n' "$1"; }

step "Gateway API $GATEWAY_API_VERSION"
kubectl apply --server-side -f \
  "https://github.com/kubernetes-sigs/gateway-api/releases/download/${GATEWAY_API_VERSION}/standard-install.yaml" \
  >/dev/null
echo "  applied"

step "cert-manager $CERT_MANAGER_VERSION + trust-manager $TRUST_MANAGER_VERSION"
helm repo add jetstack https://charts.jetstack.io >/dev/null 2>&1 || true
helm repo update jetstack >/dev/null 2>&1
helm upgrade --install cert-manager jetstack/cert-manager \
  --namespace cert-manager --create-namespace \
  --version "$CERT_MANAGER_VERSION" \
  --set crds.enabled=true \
  -f "$HERE/values/cert-manager.yaml" \
  --wait --timeout 5m >/dev/null
# trust-manager distributes the lab CA into every namespace that needs it,
# which is what lets each workload keep the same UMA4A_CA_BUNDLE path it uses
# under compose. Zero application change.
helm upgrade --install trust-manager jetstack/trust-manager \
  --namespace cert-manager \
  --version "$TRUST_MANAGER_VERSION" \
  --set app.trust.namespace=cert-manager \
  --wait --timeout 5m >/dev/null
echo "  ready"

step "Istio $ISTIO_VERSION (ambient)"
helm repo add istio https://istio-release.storage.googleapis.com/charts >/dev/null 2>&1 || true
helm repo update istio >/dev/null 2>&1
helm upgrade --install istio-base istio/base \
  --namespace istio-system --create-namespace \
  --version "$ISTIO_VERSION" --wait --timeout 5m >/dev/null
helm upgrade --install istiod istio/istiod \
  --namespace istio-system --version "$ISTIO_VERSION" \
  -f "$HERE/values/istiod.yaml" --wait --timeout 8m >/dev/null
# The CNI plugin is what enrols a pod into the mesh without a sidecar; on
# kind it has to be told where the kubelet keeps its plugin directories.
helm upgrade --install istio-cni istio/cni \
  --namespace istio-system --version "$ISTIO_VERSION" \
  -f "$HERE/values/istio-cni.yaml" --wait --timeout 5m >/dev/null
helm upgrade --install ztunnel istio/ztunnel \
  --namespace istio-system --version "$ISTIO_VERSION" \
  -f "$HERE/values/ztunnel.yaml" --wait --timeout 5m >/dev/null
echo "  ready"

step "kgateway $KGATEWAY_VERSION (the north-south edge)"
helm upgrade --install kgateway-crds \
  oci://cr.kgateway.dev/kgateway-dev/charts/kgateway-crds \
  --namespace kgateway-system --create-namespace \
  --version "$KGATEWAY_VERSION" --wait --timeout 5m >/dev/null
helm upgrade --install kgateway \
  oci://cr.kgateway.dev/kgateway-dev/charts/kgateway \
  --namespace kgateway-system --version "$KGATEWAY_VERSION" \
  --wait --timeout 5m >/dev/null
echo "  ready"

step "agentgateway $AGENTGATEWAY_VERSION (the agent-facing gateway)"
helm upgrade --install agentgateway-crds \
  oci://cr.agentgateway.dev/charts/agentgateway-crds \
  --namespace agentgateway-system --create-namespace \
  --version "$AGENTGATEWAY_VERSION" --wait --timeout 5m >/dev/null
helm upgrade --install agentgateway \
  oci://cr.agentgateway.dev/charts/agentgateway \
  --namespace agentgateway-system --version "$AGENTGATEWAY_VERSION" \
  --wait --timeout 5m >/dev/null
echo "  ready"

step "CloudNativePG $CNPG_VERSION"
helm repo add cnpg https://cloudnative-pg.github.io/charts >/dev/null 2>&1 || true
helm repo update cnpg >/dev/null 2>&1
helm upgrade --install cnpg cnpg/cloudnative-pg \
  --namespace cnpg-system --create-namespace \
  --version "$CNPG_VERSION" --wait --timeout 5m >/dev/null
echo "  ready"

step "kmcp $KMCP_VERSION (Alice's vault as a Kubernetes resource)"
# The MCPServer type comes from kagent's CRD chart; the controller that acts
# on it is a separate chart. kagent's own controller is opt-in — `make kagent`
# installs it and applies k8s/components/kagent, because it brings a model with
# it and that is a cost nobody should pay for a lab they only wanted to read.
helm upgrade --install kagent-crds \
  oci://ghcr.io/kagent-dev/kagent/helm/kagent-crds \
  --namespace kagent --create-namespace \
  --version "$KAGENT_VERSION" --wait --timeout 5m >/dev/null
# The controller, without which an MCPServer is accepted and then ignored.
helm upgrade --install kmcp oci://ghcr.io/kagent-dev/kmcp/helm/kmcp \
  --namespace kagent --version "$KMCP_VERSION" \
  --wait --timeout 5m >/dev/null
echo "  ready"

printf '\n\033[1mPlatform ready.\033[0m\n'
