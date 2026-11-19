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

section() { printf '\n'; bold "$1"; printf '\n'; }

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

printf '\n'; bold "UMA for Agents lab"; printf '\n'

section "On-ramp"
ns_line uma-edge

section "Resource owners"
ns_line alice
ns_line carol
ns_line northwind

section "Shared by owners"
ns_line tally

section "Resource server"
ns_line meridian
ns_line idp

section "Requesting party"
ns_line sterling-vance
ns_line aauth
ns_line kagent

section "Operator plane"
ns_line observability
printf '\n'
