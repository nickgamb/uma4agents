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
      echo "unknown MODEL=$model (want: anthropic, openai, ollama, bedrock)" >&2
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

# ---------------------------------------------------------------------------
# Pointing an agent at something other than Alice's brokerage account
#
# Every resource in this lab publishes RFC 9728 metadata naming its own
# authority, so the adapter needs nothing but a URL: which owner it ends up
# negotiating with, and how many of them there are, falls out of the resource
# rather than out of configuration here. That is what makes the other demos
# the same demo — a person asks an agent a question, and whoever owns the
# thing decides.
#
#   alice   her brokerage account          she decides, at her portal
#   carol   Carol's, at her own authority  she decides, at hers
#   joint   held by both, threshold 2      both of them decide
#   either  held by both, threshold 1      either of them can
# ---------------------------------------------------------------------------

resource_url() {
  case "$1" in
    alice)  echo "https://gateway.uma.lab/mcp/alice" ;;
    carol)  echo "https://gateway.uma.lab/mcp/carol" ;;
    joint)  echo "https://gateway.uma.lab/mcp/joint/meridian-joint" ;;
    either) echo "https://gateway.uma.lab/mcp/joint/meridian-either" ;;
    # The firm's book, as the member administers it. It does not exist until
    # she has joined the organization — which is the point of it.
    shared) echo "https://gateway.uma.lab/mcp/shared/alice" ;;
    # Her own account again, asked by an agent she operates rather than one of
    # Bob's. The resource is identical; what differs is the asker.
    hers)   echo "https://gateway.uma.lab/mcp/alice" ;;
    *)      return 1 ;;
  esac
}

resource_as() {
  case "$1" in
    alice|shared|hers) echo "https://alice-as.uma.lab" ;;
    carol)        echo "https://carol-as.uma.lab" ;;
    joint|either) echo "https://joint-tally.uma.lab" ;;
  esac
}

resource_who() {
  case "$1" in
    alice)  echo "Alice, at https://portal.uma.lab" ;;
    carol)  echo "Carol, at https://carol-portal.uma.lab" ;;
    joint)  echo "Alice AND Carol, at both portals — it takes both" ;;
    either) echo "Alice OR Carol — either one is enough" ;;
    shared) echo "Alice, at https://portal.uma.lab — it is the firm's book, and hers to administer" ;;
    hers)   echo "Alice, at https://portal.uma.lab — but this agent is one of hers" ;;
  esac
}

# An adapter of its own per resource, because the adapter is where the grant
# happens and a negotiation with one authority has no business sharing a
# process with a negotiation with another.
resource_operator() {
  case "$1" in
    hers) echo "https://alice-agent.uma.lab" ;;
    *)    echo "" ;;
  esac
}

agent_for() {
  local r="$1" url; url="$(resource_url "$r")" || {
    echo "unknown RESOURCE=$r (want: alice, carol, joint, either, shared, hers)" >&2; exit 1; }

  bold "An adapter and an agent pointed at: $r"
  echo "  resource:  $url"
  echo "  decided by: $(resource_who "$r")"

  kubectl apply -f - >/dev/null <<YAML
apiVersion: apps/v1
kind: Deployment
metadata:
  name: agent-shim-$r
  namespace: sterling-vance
  labels: { app: agent-shim-$r }
spec:
  replicas: 1
  selector:
    matchLabels: { app: agent-shim-$r }
  template:
    metadata:
      labels:
        app: agent-shim-$r
        istio.io/use-waypoint: waypoint
    spec:
      serviceAccountName: agent-shim
      containers:
        - name: agent-shim
          image: localhost:5001/u4a/uma-as:dev
          imagePullPolicy: Always
          command: ["/bin/sh", "-ec"]
          args:
            - |
              pip install -q 'mcp>=2,<3' httpx 'pyjwt[crypto]' 2>/dev/null
              exec python3 /shim/shim.py
          env:
            - { name: UMA4A_SHIM_TRANSPORT, value: streamable-http }
            - { name: UMA4A_SHIM_HOST, value: 0.0.0.0 }
            - { name: UMA4A_SHIM_PORT, value: "9030" }
            - { name: UMA4A_GATEWAY, value: $url }
            - { name: UMA4A_CACERT, value: /certs/rootCA.pem }
            - { name: UMA4A_KEYSTORE, value: /keys/agent-key.pem }
            - { name: UMA4A_STANDING_MAX_EXPIRES, value: "604800" }
            - { name: UMA4A_PEND_HANDBACK, value: "5" }
            - { name: UMA4A_PUBLISH_TO, value: "$(resource_operator "$r")" }
            - { name: PYTHONPATH, value: /shim/lib }
            - { name: PYTHONUNBUFFERED, value: "1" }
          ports:
            - { name: mcp, containerPort: 9030 }
          volumeMounts:
            - { name: shim, mountPath: /shim/shim.py, subPath: shim.py, readOnly: true }
            - { name: lib, mountPath: /shim/lib, readOnly: true }
            - { name: ca, mountPath: /certs, readOnly: true }
            - { name: keys, mountPath: /keys }
          resources:
            requests: { cpu: 50m, memory: 128Mi }
            limits: { memory: 384Mi }
      volumes:
        - name: shim
          configMap: { name: agent-shim }
        - name: lib
          configMap: { name: demo-lib }
        - name: ca
          configMap: { name: uma-lab-ca-bundle }
        - name: keys
          emptyDir: {}
---
apiVersion: v1
kind: Service
metadata:
  name: agent-shim-$r
  namespace: sterling-vance
  labels: { app: agent-shim-$r }
spec:
  selector: { app: agent-shim-$r }
  ports:
    - { name: mcp, port: 9030, targetPort: 9030 }
---
apiVersion: kagent.dev/v1alpha2
kind: RemoteMCPServer
metadata:
  name: vault-via-uma-$r
  namespace: sterling-vance
spec:
  description: Tools reached through the U4A adapter for the $r resource.
  protocol: STREAMABLE_HTTP
  url: http://agent-shim-$r.sterling-vance.svc.cluster.local:9030/mcp
  # Long, on purpose. A jointly held account needs two people to answer before
  # the tool call returns, and they are not sitting at the same desk. 120s is
  # the right budget for a resource with one owner and far too short here.
  timeout: 900s
  sseReadTimeout: 900s
  terminateOnClose: false
YAML

  kubectl -n sterling-vance rollout status deploy/agent-shim-$r --timeout=300s >/dev/null
  printf '  waiting for the adapter to be discovered'
  for _ in $(seq 1 60); do
    if [ -n "$(kubectl -n sterling-vance get remotemcpserver vault-via-uma-$r \
                 -o jsonpath='{.status.discoveredTools[*].name}' 2>/dev/null)" ]; then
      break
    fi
    printf '.'; sleep 5
  done; echo
  local tools
  tools=$(kubectl -n sterling-vance get remotemcpserver vault-via-uma-$r \
            -o jsonpath='{.status.discoveredTools[*].name}' 2>/dev/null)
  if [ -z "$tools" ]; then
    echo "  the adapter's tools were never discovered — check:" >&2
    echo "    kubectl -n sterling-vance describe remotemcpserver vault-via-uma-$r" >&2
    exit 1
  fi
  echo "  tools discovered: $tools"

  kubectl apply -f - >/dev/null <<YAML
apiVersion: kagent.dev/v1alpha2
kind: Agent
metadata:
  name: advisory-agent-$r
  namespace: sterling-vance
spec:
  type: Declarative
  description: Sterling & Vance's advisory agent, acting for Bob.
  declarative:
    modelConfig: u4a-model
    systemMessage: |
      You are an advisory agent working for Bob at Sterling & Vance. You may
      look at the account's holdings and transactions, and you may propose
      trades against it.

      The account's authorization server decides what you actually get, and
      the people who own it are not sitting at a keyboard waiting for you.

      If a tool returns PENDING, the owner has been asked and has not answered
      yet. That is a normal state, not an error and not a refusal. Report that
      the request is waiting on her decision, and stop for now. Do NOT call the
      tool again in the same reply and do not wait in a loop — whoever asked
      you will ask again, and your next turn will pick the same request back
      up. She may take hours.

      If a tool tells you the request was declined, say so plainly and stop.
      Do not retry a refusal, and never change the request to get a different
      answer.

      Use one tool per question and report what it returned.

    tools:
      - type: McpServer
        mcpServer:
          apiGroup: kagent.dev
          kind: RemoteMCPServer
          name: vault-via-uma-$r
          toolNames: [get_positions, get_transactions, execute_trade]
YAML
  kubectl -n sterling-vance rollout restart deploy/advisory-agent-$r >/dev/null 2>&1 || true
  kubectl -n sterling-vance rollout status deploy/advisory-agent-$r --timeout=300s >/dev/null 2>&1 || true
  echo "  ready"
  printf '\n  Ask it something:  make kagent-ask RESOURCE=%s Q="..." SIM=0\n' "$r"
  printf '  Answer it as: %s\n' "$(resource_who "$r")"
}

up() {
  local model="${1:-anthropic}"

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

  if [ "${2:-alice}" != "alice" ]; then
    agent_for "${2}"
    return
  fi

  printf '\n  Ask it something:  make kagent-ask Q="..." SIM=0\n'
  printf '  Alice decides in her portal, as always.\n'
}

# One question, put to Bob's agent.
#
# `sim=1` answers her pending queue headlessly, which is what the check needs.
# `sim=0` leaves every decision to whoever is at her portal, and the Job simply
# waits — an ask-me tier is a slow tool call from the agent's side, so waiting
# is the demonstration rather than a hang.
ask() {
  local question="$1" sim="${2:-1}" r="${3:-alice}"
  local agent="advisory-agent" as_url
  as_url="$(resource_as "$r")"
  [ "$r" = "alice" ] || agent="advisory-agent-$r"

  bold "Asking Bob's agent"
  echo "  \"$question\""
  echo "  asked of: sterling-vance/$agent"
  if [ "$sim" = "0" ]; then
    echo "  Nobody is answering. Decide it as: $(resource_who "$r")"
  else
    echo "  A simulated Alice will answer her pending queue."
  fi

  # --from-literal rather than a template substitution: kubectl quotes the
  # value, so a question containing an apostrophe or a slash stays intact.
  kubectl -n sterling-vance create configmap kagent-ask-input \
    --from-literal=question="$question" --from-literal=sim="$sim" \
    --dry-run=client -o yaml | kubectl apply -f - >/dev/null

  kubectl -n sterling-vance delete job kagent-ask --ignore-not-found >/dev/null 2>&1
  sed -e "s|/sterling-vance/advisory-agent|/sterling-vance/$agent|" \
      -e "s|https://alice-as.uma.lab|$as_url|" \
      "$K8S/base/jobs/kagent-ask.yaml" | kubectl apply -f - >/dev/null
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
  up)    up "${2:-anthropic}" "${3:-alice}" ;;
  check) check ;;
  ask)   ask "${2:?a question is required}" "${3:-1}" "${4:-alice}" ;;
  down)  down ;;
  *)     echo "usage: kagent.sh up|check|down [model] | ask <question> [sim]" >&2; exit 1 ;;
esac
