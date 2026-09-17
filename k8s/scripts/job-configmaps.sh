#!/usr/bin/env bash
# The verification Jobs run the repo's own driver and libraries.
#
# Mounted from ConfigMaps built here rather than baked into an image, for the
# same reason the compose stack bind-mounts them: the thing being tested is
# the code in this working tree, not a copy of it from some earlier build.
#
# `replace --force` rather than `apply`, and the reason is a ceiling rather
# than a preference. `apply` records the entire previous object in a
# kubectl.kubernetes.io/last-applied-configuration annotation, and annotations
# are capped at 256 KiB. demo-driver reached 251 KiB carrying eleven check
# scripts; the twelfth was refused outright, leaving a stale ConfigMap in the
# cluster and jobs that mounted an empty directory over their own script. These
# maps are rebuilt in full from the working tree on every run, so there is
# nothing for a three-way merge to merge, and nothing worth spending the
# ceiling on.
#
# It is well past that ceiling now — the scripts below total over 290 KiB — so
# this is not a margin that can be won back by trimming. Anything that puts
# `apply` back here fails on the next script added, and fails by leaving the
# old ConfigMap in place rather than by saying so.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
NS=sterling-vance

kubectl -n "$NS" create configmap demo-driver \
  --from-file=driver.py="$ROOT/clients/demo-driver/driver.py" \
  --from-file=assurance_check.py="$ROOT/clients/demo-driver/assurance_check.py" \
  --from-file=first_party_check.py="$ROOT/clients/demo-driver/first_party_check.py" \
  --from-file=subagent_check.py="$ROOT/clients/demo-driver/subagent_check.py" \
  --from-file=intent_check.py="$ROOT/clients/demo-driver/intent_check.py" \
  --from-file=adapter_check.py="$ROOT/clients/demo-driver/adapter_check.py" \
  --from-file=kagent_ask.py="$ROOT/clients/demo-driver/kagent_ask.py" \
  --from-file=multi_owner_check.py="$ROOT/clients/demo-driver/multi_owner_check.py" \
  --from-file=establishment_check.py="$ROOT/clients/demo-driver/establishment_check.py" \
  --from-file=org_check.py="$ROOT/clients/demo-driver/org_check.py" \
  --from-file=joint_check.py="$ROOT/clients/demo-driver/joint_check.py" \
  --from-file=consequence_check.py="$ROOT/clients/demo-driver/consequence_check.py" \
  --from-file=clearance_check.py="$ROOT/clients/demo-driver/clearance_check.py" \
  --from-file=embedded_check.py="$ROOT/clients/demo-driver/embedded_check.py" \
  --from-file=flow_check.py="$ROOT/clients/demo-driver/flow_check.py" \
  --from-file=rotation_check.py="$ROOT/clients/demo-driver/rotation_check.py" \
  --from-file=xaa_check.py="$ROOT/clients/demo-driver/xaa_check.py" \
  --dry-run=client -o yaml | kubectl replace --force -f - >/dev/null

kubectl -n "$NS" create configmap agent-shim \
  --from-file=shim.py="$ROOT/clients/agent-shim/shim.py" \
  --from-file=test_shim.py="$ROOT/clients/agent-shim/test_shim.py" \
  --dry-run=client -o yaml | kubectl replace --force -f - >/dev/null

# The second implementation, built. `dist/` is committed for the same reason
# the drafts' rendered output is: what the check runs has to be the artifact,
# not a build step that could differ. Runtime needs no node_modules — the
# agent imports node builtins and its own module, and TypeScript is a
# development dependency only.
# package.json comes along because it is what makes the two files ESM. The
# agent is built as ES modules and imports its own module by path; without a
# `"type": "module"` beside them Node reads the same bytes as CommonJS and
# refuses the first import. Compose gets this for free by running inside the
# package directory.
kubectl -n "$NS" create configmap ts-agent \
  --from-file=check.js="$ROOT/clients/ts-agent/dist/check.js" \
  --from-file=uma4a.js="$ROOT/clients/ts-agent/dist/uma4a.js" \
  --from-file=package.json="$ROOT/clients/ts-agent/package.json" \
  --dry-run=client -o yaml | kubectl replace --force -f - >/dev/null

kubectl -n "$NS" create configmap demo-lib \
  --from-file=uma4a_grant.py="$ROOT/lib/uma4a_grant.py" \
  --from-file=uma4a_http_sig.py="$ROOT/lib/uma4a_http_sig.py" \
  --from-file=uma4a_enroll.py="$ROOT/lib/uma4a_enroll.py" \
  --from-file=uma4a_pep.py="$ROOT/lib/uma4a_pep.py" \
  --from-file=uma4a_consequence.py="$ROOT/lib/uma4a_consequence.py" \
  --from-file=uma4a_clearance.py="$ROOT/lib/uma4a_clearance.py" \
  --from-file=uma4a_org.py="$ROOT/lib/uma4a_org.py" \
  --dry-run=client -o yaml | kubectl replace --force -f - >/dev/null
