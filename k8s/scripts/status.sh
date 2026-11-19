#!/usr/bin/env bash
# make k8s-status — the lab's shape, by party.
#
# One namespace per party, grouped by which side of the grant it stands on.
# Each line under a namespace is a running workload; finished Jobs are left
# out, because they are the checks that ran, not the lab. Descriptions come
# from the namespaces themselves (u4a.ai/description), so this never drifts
# from what is deployed.
set -euo pipefail

bold() { printf '\033[1m%s\033[0m' "$1"; }
dim()  { printf '\033[2m%s\033[0m' "$1"; }

section() { printf '\n'; bold "$1"; printf '  '; dim "$2"; printf '\n'; }

ns_line() {
  local ns="$1" desc pods
  kubectl get ns "$ns" >/dev/null 2>&1 || return 0
  desc="$(kubectl get ns "$ns" -o jsonpath='{.metadata.annotations.u4a\.ai/description}' 2>/dev/null)"
  printf '\n  '; bold "$ns"; printf '\n'
  [ -n "$desc" ] && printf '  %s\n' "$desc" | fold -s -w 100 | sed '2,$s/^/  /'
  pods="$(kubectl -n "$ns" get pods --no-headers 2>/dev/null \
    | awk '$3 != "Completed" && $3 != "Succeeded" {printf "    %-46s %-6s %s\n", $1, $2, $3}')"
  if [ -n "$pods" ]; then printf '%s\n' "$pods"; else printf '    '; dim "(nothing running)"; printf '\n'; fi
}

printf '\n'; bold "UMA for Agents — the lab, by party"; printf '\n'
dim "Every party in its own namespace; between parties, only the edge."; printf '\n'

section "On-ramp"           "how anything from outside gets in"
ns_line uma-edge

section "Resource owners"   "each decides about her own things, from her own authority"
ns_line alice
ns_line carol
ns_line northwind

section "Shared by owners"  "run by neither owner"
ns_line idp
ns_line tally

section "Resource server"   "holds the assets, enforces the policy, never reads it"
ns_line meridian

section "Requesting party"  "Bob, his firm, its agent, and who vouches for it"
ns_line sterling-vance
ns_line aauth
ns_line kagent

section "Operator plane"    "sees protocol events, never grant state"
ns_line observability
printf '\n'
