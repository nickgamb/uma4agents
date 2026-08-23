#!/usr/bin/env bash
#
# Publish Alice's portal to a browser tab in a Codespace.
#
# The lab serves everything under *.uma.lab behind an edge that routes by
# hostname, which a browser outside the VM cannot resolve. Inside the VM it
# can — /etc/hosts is written at create time — so the terminal half of the
# lab needs none of this. Only the browser does.
#
# Two things happen here.
#
# 1. Port-forwards. Alice's portal and her identity provider both serve plain
#    HTTP inside the cluster (9010 and 8080) because the edge terminates TLS
#    for them. That is exactly the shape Codespaces port forwarding wants, so
#    they are forwarded directly rather than through the edge. Her browser
#    session never traverses the enforcement point, so nothing the lab is
#    demonstrating is bypassed — agent traffic still goes through the gateway.
#
# 2. Origin rewriting. OIDC ties the issuer, the browser redirect and the
#    token's `iss` claim together, and all three currently name
#    keycloak.uma.lab. In a Codespace the browser reaches a github.dev
#    address instead, so Keycloak is told its public origin, the portal is
#    told to expect it, and the realm client is taught to accept a redirect
#    back to it.
set -euo pipefail

log()  { printf '\n\033[1;32m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m !\033[0m %s\n' "$*"; }

# Codespaces exports these into interactive shells, but not into a plain
# `gh codespace ssh` exec — so fall back to the file the platform writes,
# taking the first plain assignment (one of the later ones is base64).
if [ -z "${CODESPACE_NAME:-}" ] && [ -d /workspaces/.codespaces/shared ]; then
  CODESPACE_NAME="$(grep -rhoE '^CODESPACE_NAME=[A-Za-z0-9-]+$' \
    /workspaces/.codespaces/shared/.env* 2>/dev/null | head -1 | cut -d= -f2 || true)"
  GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN="${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN:-$(
    grep -rhoE '^GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN=[^ ]+$' \
      /workspaces/.codespaces/shared/.env* 2>/dev/null | head -1 | cut -d= -f2 || true)}"
fi

if [ -z "${CODESPACE_NAME:-}" ]; then
  warn "Not running in a Codespace — nothing to expose."
  warn "Locally the lab is reachable at https://portal.uma.lab after 'make dns-setup'."
  exit 0
fi

DOMAIN="${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN:-app.github.dev}"
PORTAL_URL="https://${CODESPACE_NAME}-9010.${DOMAIN}"
KEYCLOAK_URL="https://${CODESPACE_NAME}-8080.${DOMAIN}"

log "Portal   ${PORTAL_URL}"
log "Keycloak ${KEYCLOAK_URL}"

# --- 1. tell the pieces what the browser will call them ---------------------
# Keycloak already runs with KC_PROXY_HEADERS=xforwarded because the edge
# terminates TLS; this only changes which origin it advertises.
log "Pointing Keycloak and the portal at the forwarded origins"

# Keycloak advertises the forwarded origin as its issuer and as the endpoint
# the *browser* visits. hostname-backchannel-dynamic keeps the endpoints a
# *server* calls resolving from the request instead — without it Keycloak
# would advertise the github.dev address for the token endpoint too, and the
# portal cannot follow it: that address is authenticated at GitHub's edge and
# served with a public certificate, while this pod trusts only the lab CA.
kubectl -n idp set env deploy/keycloak \
  "KC_HOSTNAME=${KEYCLOAK_URL}" \
  "KC_HOSTNAME_BACKCHANNEL_DYNAMIC=true" >/dev/null

# The portal expects the public issuer — that is what the ID token will
# carry — but reads the discovery document over the cluster network.
# PORTAL_PUBLIC_URL is what the browser knows this portal by. Without it the
# portal builds its redirect URI from the incoming request, which through a
# forwarded port says localhost:9010 — a host the browser cannot return to,
# and one the realm has no reason to have registered.
kubectl -n alice set env deploy/portal \
  "OIDC_ISSUER=${KEYCLOAK_URL}/realms/alice" \
  "OIDC_METADATA_URL=http://keycloak.idp.svc.cluster.local:8080/realms/alice/.well-known/openid-configuration" \
  "PORTAL_PUBLIC_URL=${PORTAL_URL}" \
  >/dev/null

# The authorization server validates Alice's own OIDC token, so it has to
# expect the same issuer Keycloak now stamps on it — while still reading her
# realm's keys over the cluster network.
kubectl -n alice set env deploy/uma-as \
  "UMA_AS_OWNER_ISSUER=${KEYCLOAK_URL}/realms/alice" \
  "UMA_AS_OWNER_METADATA_URL=http://keycloak.idp.svc.cluster.local:8080/realms/alice/.well-known/openid-configuration" \
  >/dev/null

kubectl -n idp rollout status deploy/keycloak --timeout=180s
kubectl -n alice rollout status deploy/portal --timeout=180s
kubectl -n alice rollout status deploy/uma-as --timeout=240s

# --- 2. let the realm redirect back to the forwarded portal -----------------
# Patched through the admin API rather than the realm ConfigMap: the import
# only runs on a first start, so editing the ConfigMap would need the realm
# wiped to take effect.
log "Allowing the portal's forwarded origin as a redirect target"
# Read from the deployment rather than assuming: this is a documented demo
# credential set as a plain env value, not a Secret, and guessing a Secret
# name here would fail silently into a fallback that only looked correct.
KC_ADMIN_PASS="$(kubectl -n idp get deploy/keycloak -o jsonpath=\
'{.spec.template.spec.containers[0].env[?(@.name=="KC_BOOTSTRAP_ADMIN_PASSWORD")].value}')"
KC_ADMIN_USER="$(kubectl -n alice get deploy/keycloak -o jsonpath=\
'{.spec.template.spec.containers[0].env[?(@.name=="KC_BOOTSTRAP_ADMIN_USERNAME")].value}')"

kubectl -n idp exec deploy/keycloak -- sh -c "
  /opt/keycloak/bin/kcadm.sh config credentials \
    --server http://localhost:8080 --realm master \
    --user '${KC_ADMIN_USER}' --password '${KC_ADMIN_PASS}' >/dev/null &&
  CID=\$(/opt/keycloak/bin/kcadm.sh get clients -r alice \
    -q clientId=meridian-portal --fields id --format csv --noquotes | tail -n1) &&
  /opt/keycloak/bin/kcadm.sh update clients/\$CID -r alice \
    -s 'redirectUris=[\"${PORTAL_URL}/*\",\"https://portal.uma.lab/*\"]' \
    -s 'webOrigins=[\"${PORTAL_URL}\",\"https://portal.uma.lab\"]'
" || warn "Realm patch failed — sign-in will bounce. See the note in docs/KUBERNETES.md."

# --- 3. forward the ports ---------------------------------------------------
# Under setsid and in a restart loop, deliberately. `kubectl port-forward`
# dies when the pod it is attached to is replaced — which happens on every
# rollout, and the chaos target kills pods on purpose — and a bare `nohup ... &`
# from a make recipe does not outlive the terminal that ran it. Either way the
# PORTS tab would still list the port while nothing answered behind it, which
# is the failure this whole script exists to avoid.
forward() {
  # Namespaced, because the identity provider is not in an owner's namespace
  # — it is neither owner's, and both resolve it.
  local ns="$1" svc="$2" port="$3"
  setsid bash -c "
    while true; do
      kubectl -n $ns port-forward --address 127.0.0.1 svc/$svc $port:$port
      sleep 2
    done" >"/tmp/pf-$svc.log" 2>&1 < /dev/null &
}

log "Forwarding 9010 and 8080"
pkill -f 'kubectl.*port-forward.*(svc/portal|svc/keycloak)' 2>/dev/null || true
pkill -f 'port-forward.*svc/(portal|keycloak)' 2>/dev/null || true
forward alice portal 9010
forward idp keycloak 8080

# Confirm rather than assume — a listed port with nothing behind it is the
# exact thing that made this look broken before.
for _ in $(seq 1 20); do
  sleep 1
  if (ss -ltn 2>/dev/null || netstat -ltn 2>/dev/null) | grep -q ':9010'; then
    break
  fi
done
if ! (ss -ltn 2>/dev/null || netstat -ltn 2>/dev/null) | grep -q ':9010'; then
  warn "Port 9010 never came up — see /tmp/pf-portal.log"
fi

log "Open ${PORTAL_URL} and sign in as alice / alice-demo"
cat <<'EOF'
   The forwarded ports stay private, which is what you want: this lab ships
   fixed development credentials, and a public port puts them on the open
   internet behind nothing but an unguessable URL. Private ports are reachable
   from your own browser because you are signed in to GitHub — making them
   public is only for showing someone else, and is a deliberate choice.

EOF
