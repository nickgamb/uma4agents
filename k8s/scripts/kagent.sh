#!/usr/bin/env bash
# The kagent path: an agent framework nobody modified, governed by Alice.
#
# Everything the lab shows elsewhere drives the grant from code in this repo.
# This installs kagent's controller, gives it a model, points it at the U4A
# adapter running in Bob's namespace, and asks it a question — so what proves
# the claim is a framework we did not write, calling tools it believes are
# ordinary, and being held to Alice's terms anyway.
#
# Opt-in, because a model is a real cost: either a container that pulls a
# couple of gigabytes, or an account somewhere.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
K8S="$ROOT/k8s"
# shellcheck disable=SC1091
source "$K8S/platform/versions.env"

bold() { printf '\n\033[1m==> %s\033[0m\n' "$1"; }

# The ModelConfig, per provider.
#
# Adding one is meant to be small, and it is: a case here that names the
# provider, the model, and whatever provider-specific block it requires. The
# U4A path does not change — the adapter holds Bob's key and runs the four
# beats whichever of these decides which tool to call.
#
# Written with a heredoc rather than a template plus envsubst, because
# envsubst is gettext and not present on a stock macOS, and because each
# provider needs a differently-shaped block rather than the same one with
# different words in it.
model_secret() {
  # From your shell into a Secret, and nowhere else. Not echoed, not written
  # to this repository, not passed on a command line.
  local key="$1"
  kubectl -n sterling-vance create secret generic u4a-model-key \
    --from-literal=api-key="$key" --dry-run=client -o yaml | kubectl apply -f - >/dev/null
}

require_env() {
  local var="$1"
  if [ -z "${!var:-}" ]; then
    echo "  $var is not set in your environment." >&2
    echo "  Either export it, or run 'make kagent' for the local model." >&2
    exit 1
  fi
}

model_config() {
  local model="$1" provider name extra=""

  case "$model" in
    ollama)
      bold "A model in the cluster (ollama, no account anywhere)"
      kubectl apply -f "$K8S/components/kagent/model-ollama.yaml" >/dev/null
      printf '  pulling the model, which takes a few minutes the first time'
      kubectl -n kagent rollout status deploy/ollama --timeout=900s >/dev/null
      echo "  ready"
      return ;;

    anthropic)
      require_env ANTHROPIC_API_KEY
      provider=Anthropic; name="${ANTHROPIC_MODEL:-claude-sonnet-4-5-20250929}"
      model_secret "$ANTHROPIC_API_KEY" ;;

    openai)
      require_env OPENAI_API_KEY
      provider=OpenAI; name="${OPENAI_MODEL:-gpt-4o-mini}"
      model_secret "$OPENAI_API_KEY" ;;

    bedrock)
      # A Bedrock API key is a bearer token like the others, so the secret
      # shape is unchanged. What Bedrock adds is its own block; region is
      # required within it, though the block itself may be omitted to fall
      # back to the AWS default chain. Naming it beats inheriting it.
      require_env AWS_BEDROCK_API_KEY
      provider=Bedrock; name="${BEDROCK_MODEL:-anthropic.claude-3-5-sonnet-20241022-v2:0}"
      extra=$(printf '  bedrock:\n    region: %s' "${AWS_REGION:-us-east-1}")
      model_secret "$AWS_BEDROCK_API_KEY" ;;

    *)
      echo "unknown MODEL=$model (want: ollama, anthropic, openai, bedrock)" >&2
      exit 1 ;;
  esac

  bold "A hosted model ($provider)"
  {
    cat <<YAML
apiVersion: kagent.dev/v1alpha2
kind: ModelConfig
metadata:
  name: u4a-model
  namespace: sterling-vance
spec:
  provider: $provider
  model: $name
  apiKeySecret: u4a-model-key
  apiKeySecretKey: api-key
YAML
    # `if` rather than `[ … ] && …`: as the last command in this group, a
    # false test would be the group's exit status, and with `pipefail` that
    # fails the whole pipeline before kubectl has applied anything.
    if [ -n "$extra" ]; then printf '%b\n' "$extra"; fi
  } | kubectl apply -f - >/dev/null
  echo "  $name"
}

up() {
  local model="${1:-ollama}"

  bold "kagent controller $KAGENT_VERSION"
  # The chart ships a dozen sample agents — k8s, istio, helm, cilium, argo.
  # Every one of them wants a model, so on a cluster with no provider
  # configured they sit in CreateContainerConfigError and `--wait` blocks
  # until it times out. We are bringing our own agent and our own model, so
  # they are off. This is the same "an Agent needs a model" cost the lab
  # avoids by making the whole path opt-in.
  helm upgrade --install kagent oci://ghcr.io/kagent-dev/kagent/helm/kagent \
    --namespace kagent --create-namespace \
    --version "$KAGENT_VERSION" \
    --set k8s-agent.enabled=false \
    --set kgateway-agent.enabled=false \
    --set istio-agent.enabled=false \
    --set promql-agent.enabled=false \
    --set observability-agent.enabled=false \
    --set argo-rollouts-agent.enabled=false \
    --set helm-agent.enabled=false \
    --set cilium-policy-agent.enabled=false \
    --set cilium-manager-agent.enabled=false \
    --set cilium-debug-agent.enabled=false \
    --set querydoc.enabled=false \
    --wait --timeout 10m >/dev/null
  # Every namespace in this lab is enrolled in ambient, so that what calls
  # what is attested rather than merely reachable. Helm created this one, so
  # it misses the label the others get from k8s/base/namespaces — and without
  # it the controller's calls arrive with no identity, which a `principals`
  # rule cannot match. That is the trap KUBERNETES.md lists, met again.
  kubectl label namespace kagent istio.io/dataplane-mode=ambient --overwrite >/dev/null
  kubectl -n kagent rollout restart deploy/kagent-controller >/dev/null
  kubectl -n kagent rollout status deploy/kagent-controller --timeout=300s >/dev/null
  echo "  ready"

  bold "The U4A adapter, in Bob's namespace"
  # The same shim Bob runs beside Claude Code, as a service. It holds his key
  # and runs the four beats; the agent above it sees ordinary MCP.
  "$K8S/scripts/job-configmaps.sh"
  kubectl apply -f "$K8S/base/sterling-vance/agent-shim.yaml" >/dev/null
  # After the apply, because the manifest's own replicas: 0 is what keeps a
  # cold cluster on the portal demo.
  kubectl -n sterling-vance scale deploy/agent-shim --replicas=1 >/dev/null
  kubectl -n sterling-vance rollout status deploy/agent-shim --timeout=300s >/dev/null
  echo "  ready"

  model_config "$model"

  bold "Bob's agent, as a kagent Agent"
  kubectl apply -f "$K8S/components/kagent/agent.yaml" >/dev/null

  # Order matters here, and getting it wrong fails in a way that looks like a
  # bad model. An Agent reads its tool list once at start-up, so if its pod
  # comes up before the RemoteMCPServer has been reconciled it has no tools at
  # all — and the model, asked about a portfolio with nothing to call,
  # cheerfully invents a function name. The symptom is "tool not found";
  # the cause is a race.
  printf '  waiting for the adapter to be discovered'
  for _ in $(seq 1 60); do
    if [ "$(kubectl -n sterling-vance get remotemcpserver alice-vault-via-uma \
              -o jsonpath='{.status.conditions[0].status}' 2>/dev/null)" = True ]; then
      break
    fi
    printf '.'; sleep 5
  done; echo
  tools=$(kubectl -n sterling-vance get remotemcpserver alice-vault-via-uma \
            -o jsonpath='{.status.discoveredTools[*].name}' 2>/dev/null)
  if [ -z "$tools" ]; then
    echo "  the adapter's tools were never discovered — check:" >&2
    echo "    kubectl -n sterling-vance describe remotemcpserver alice-vault-via-uma" >&2
    exit 1
  fi
  echo "  tools discovered: $tools"

  # Only now is it safe to have the Agent start, or restart into, a pod that
  # will see them.
  kubectl -n sterling-vance rollout restart deploy/advisory-agent >/dev/null 2>&1 || true
  kubectl -n sterling-vance rollout status deploy/advisory-agent --timeout=300s >/dev/null 2>&1 || true
  echo "  ready"

  printf '\n  Ask it something:  make kagent-check\n'
  printf '  Alice decides in her portal, as always.\n'
}

# One question, put to Bob's agent.
#
# `sim=1` answers her pending queue headlessly, which is what the check needs.
# `sim=0` leaves every decision to whoever is at her portal, and the Job simply
# waits — an ask-me tier is a slow tool call from the agent's side, so waiting
# is the demonstration rather than a hang.
ask() {
  local question="$1" sim="${2:-1}"

  bold "Asking Bob's agent"
  echo "  \"$question\""
  if [ "$sim" = "0" ]; then
    echo "  Nobody is answering for Alice. Approve or deny it in her portal."
  else
    echo "  A simulated Alice will answer her pending queue."
  fi

  # --from-literal rather than a template substitution: kubectl quotes the
  # value, so a question containing an apostrophe or a slash stays intact.
  kubectl -n sterling-vance create configmap kagent-ask-input \
    --from-literal=question="$question" --from-literal=sim="$sim" \
    --dry-run=client -o yaml | kubectl apply -f - >/dev/null

  kubectl -n sterling-vance delete job kagent-ask --ignore-not-found >/dev/null 2>&1
  kubectl apply -f "$K8S/base/jobs/kagent-ask.yaml" >/dev/null
  # Follow the logs rather than waiting in silence: with sim=0 the interesting
  # part is the pause, and a demo needs it visible while it happens.
  kubectl -n sterling-vance wait --for=condition=ready pod \
    -l app=kagent-ask --timeout=120s >/dev/null 2>&1 || true
  kubectl -n sterling-vance logs -f job/kagent-ask 2>/dev/null \
    || kubectl -n sterling-vance logs job/kagent-ask --tail=60
}

check() {
  ask "What is in Alice's portfolio?" 1
}

down() {
  kubectl delete -f "$K8S/components/kagent/agent.yaml" --ignore-not-found >/dev/null 2>&1 || true
  kubectl -n sterling-vance scale deploy/agent-shim --replicas=0 >/dev/null 2>&1 || true
  echo "==> kagent stopped; the adapter is scaled back to zero"
}

case "${1:-up}" in
  up)    up "${2:-ollama}" ;;
  check) check ;;
  ask)   ask "${2:?a question is required}" "${3:-1}" ;;
  down)  down ;;
  *)     echo "usage: kagent.sh up|check|down [model] | ask <question> [sim]" >&2; exit 1 ;;
esac
