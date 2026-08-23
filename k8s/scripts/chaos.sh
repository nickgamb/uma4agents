#!/usr/bin/env bash
# Kill things while Alice is being asked.
#
# The demo's premise is that the owner may be asleep for hours. Under compose
# that is a claim about the protocol; here it is a claim about the deployment,
# and it is only true if the pending negotiation outlives the process that
# took it and the database that stored it.
#
# So: put a request in front of Alice, delete the authorization server that
# accepted it, take out the database primary, and then have her answer the
# very same request. If it is still hers to answer at the end, "the protocol
# waits" is a property of the system rather than of a lucky process.
set -uo pipefail

pass=0
fail=0
ok()   { printf '  ok   %s\n' "$1"; pass=$((pass + 1)); }
bad()  { printf '  FAIL %s — %s\n' "$1" "${2:-}"; fail=$((fail + 1)); }
step() { printf '\n\033[1m==> %s\033[0m\n' "$1"; }

# Ask whichever instance is currently primary rather than one by name — this
# script deliberately kills one of them, and a counter that queries the corpse
# reports zero and calls it a lost negotiation.
db_primary() {
  kubectl -n alice get cluster uma-as-db -o jsonpath='{.status.currentPrimary}' 2>/dev/null
}

psql_q() {
  local primary
  primary=$(db_primary)
  [ -n "$primary" ] || return 0
  kubectl -n alice exec "$primary" -c postgres -- \
    psql -U postgres -d u4a -tAc "$1" 2>/dev/null | tr -d '[:space:]'
}

pending_count() {
  psql_q "SELECT count(*) FROM negotiations WHERE state = 'awaiting-owner' AND decision IS NULL;"
}

step "Start from a clean slate"
# Leftovers from an earlier run make the last step ambiguous — there would be
# no way to tell which request Alice had answered. A chaos demo should begin
# from a known state, or the first thing it proves is that it did not.
psql_q "TRUNCATE tickets, negotiations, rpts, connections, ledger, owner_events;" >/dev/null
echo "  grant state cleared"

step "Put a request in front of Alice"
# tier3 is her ask-me tier: it pends rather than granting, and there is no
# --simulate-alice here, so it stays pending. That is the state everything
# below has to leave intact.
kubectl -n sterling-vance delete job demo --ignore-not-found >/dev/null 2>&1
sed 's|--act all --simulate-alice|--act tier3|' k8s/base/jobs/demo.yaml \
  | kubectl apply -f - >/dev/null

printf "  waiting for it to pend"
for _ in $(seq 1 40); do
  n=$(pending_count)
  [ -n "$n" ] && [ "$n" != "0" ] && break
  printf "."; sleep 3
done
echo
before=$(pending_count)
if [ -n "$before" ] && [ "$before" != "0" ]; then
  ok "a negotiation is waiting for Alice ($before pending)"
else
  bad "a negotiation is waiting for Alice" "nothing pending — see 'kubectl -n sterling-vance logs job/demo'"
  printf '\nk8s-chaos: %d passed, %d failed\n' "$pass" "$fail"
  exit 1
fi

step "Delete the authorization server that took it"
victim=$(kubectl -n alice get pods -l app=uma-as -o jsonpath='{.items[0].metadata.name}')
kubectl -n alice delete pod "$victim" --wait=false >/dev/null
echo "  deleted $victim"
kubectl -n alice rollout status deploy/uma-as --timeout=180s >/dev/null 2>&1

if [ "$(pending_count)" != "0" ]; then
  ok "the pend survived — it was never in that process's memory"
else
  bad "the pend survived" "the pending negotiation is gone"
fi

step "Take the database primary out, with the request still waiting"
primary=$(db_primary)
echo "  killing the primary ($primary)"
kubectl -n alice delete pod "$primary" --wait=false >/dev/null

# What is asserted here is that losing the primary does not lose the
# negotiation — not that CloudNativePG rebuilds the lost instance within any
# particular number of seconds. A rebuild from scratch on a laptop takes
# minutes, and asserting on it would fail this demo for a reason that has
# nothing to do with the lab.
printf "  waiting for a standby to take over"
for _ in $(seq 1 60); do
  now=$(db_primary)
  [ -n "$now" ] && [ "$now" != "$primary" ] && break
  printf "."; sleep 3
done
echo
now=$(db_primary)
ready=$(kubectl -n alice get cluster uma-as-db -o jsonpath='{.status.readyInstances}' 2>/dev/null)
if [ -n "$now" ] && [ "$now" != "$primary" ]; then
  ok "a standby took over ($primary -> $now)"
  echo "       ${ready:-?} of 3 instances ready; the lost one rebuilds in the background"
else
  bad "a standby took over" "primary is still ${now:-none}"
fi

sleep 15
if [ "$(pending_count)" != "0" ]; then
  ok "Alice's request is still waiting for her, across both failures"
else
  bad "Alice's request is still waiting" "the pend did not survive the failover"
fi

step "And she can still answer it"
# She decides the request that survived, not a fresh one. Starting a new
# negotiation here would show that the lab still works, which it does and
# which is not the question. The question is whether the thing that was
# waiting for her when the machine came apart is still hers to answer.
#
# Her portal is the only workload the mesh permits to call the owner API, so
# the decision is made from there — which is where her tap would come from.
decided=$(kubectl -n alice exec -i deploy/portal -- python3 - <<'PYEOF' 2>/dev/null | tr -d '[:space:]'
import json, urllib.parse, urllib.request

token = json.load(urllib.request.urlopen(urllib.request.Request(
    "https://keycloak.uma.lab/realms/alice/protocol/openid-connect/token",
    data=urllib.parse.urlencode({
        "grant_type": "password", "client_id": "meridian-portal",
        "username": "alice", "password": "alice-demo"}).encode()),
    cafile="/certs/rootCA.pem"))["access_token"]

auth = {"Authorization": "Bearer " + token}
base = "http://uma-as.alice.svc.cluster.local:9000"

pending = json.load(urllib.request.urlopen(
    urllib.request.Request(base + "/owner/pending", headers=auth)))
if not pending:
    print("NONE")
    raise SystemExit(0)

family = pending[0]["family"]
reply = urllib.request.urlopen(urllib.request.Request(
    base + "/owner/pending/" + family + "/decision",
    data=json.dumps({"decision": "approved"}).encode(),
    headers={**auth, "Content-Type": "application/json"}, method="POST"))
print(json.load(reply)["decision"])
PYEOF
)

if [ "$decided" = "approved" ]; then
  ok "Alice approved the request that survived both failures"
else
  bad "Alice approved the request that survived" "owner API said '${decided:-nothing}'"
fi

printf '\nk8s-chaos: %d passed, %d failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
