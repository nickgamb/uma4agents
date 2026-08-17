#!/usr/bin/env bash
# The verification Jobs run the repo's own driver and libraries.
#
# Mounted from ConfigMaps built here rather than baked into an image, for the
# same reason the compose stack bind-mounts them: the thing being tested is
# the code in this working tree, not a copy of it from some earlier build.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
NS=sterling-vance

kubectl -n "$NS" create configmap demo-driver \
  --from-file=driver.py="$ROOT/clients/demo-driver/driver.py" \
  --from-file=assurance_check.py="$ROOT/clients/demo-driver/assurance_check.py" \
  --dry-run=client -o yaml | kubectl apply -f - >/dev/null

kubectl -n "$NS" create configmap demo-lib \
  --from-file=uma4a_grant.py="$ROOT/lib/uma4a_grant.py" \
  --from-file=uma4a_http_sig.py="$ROOT/lib/uma4a_http_sig.py" \
  --from-file=uma4a_enroll.py="$ROOT/lib/uma4a_enroll.py" \
  --from-file=uma4a_pep.py="$ROOT/lib/uma4a_pep.py" \
  --dry-run=client -o yaml | kubectl apply -f - >/dev/null
