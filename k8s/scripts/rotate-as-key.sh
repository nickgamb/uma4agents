#!/usr/bin/env bash
# Rotate the authorization server's signing key, and put it back.
#
# The deployment half of `make k8s-rotation-check`. The check asserts what a
# rotation has to keep true; this is the rotation it asserts about, and the
# interesting part is that three replicas share one key from a Secret. A
# rotation that reached one replica and not the others would publish two JWKS
# behind one Service and fail roughly two thirds of the verifications — which
# is the failure a single process cannot exhibit and the reason the check is
# worth running here at all.
#
# `keygen.py` cannot do this: it is idempotent per Secret, exits early when one
# exists, and POSTs a new object rather than patching an existing one. That is
# right for provisioning and wrong for rotation, so the second key is generated
# and patched in here.
#
#   stage     add uma-as-2 to the Secret, make it current with uma-as-1 kept as
#             previous, and roll all three replicas
#   restore   drop back to uma-as-1 and remove the interim key
#
# Grants issued under the interim key do not survive the restore. That is the
# point of a check and not of a deployment.
set -euo pipefail

NS=alice
SECRET=uma-as-signing-key
DEPLOY=uma-as
NEW_FILE=uma-as-2.pem
NEW_KID=uma-as-2
OLD_FILE=uma-as-ed25519.pem
OLD_KID=uma-as-1

case "${1:-}" in
  stage)
    # Only if it is not already there: re-staging would mint a second key
    # under a kid the authority has already published, and every token signed
    # with the first would stop verifying.
    if ! kubectl -n "$NS" get secret "$SECRET" -o jsonpath="{.data.$NEW_FILE}" 2>/dev/null | grep -q .; then
      pem=$(openssl genpkey -algorithm ed25519 2>/dev/null | base64 | tr -d '\n')
      kubectl -n "$NS" patch secret "$SECRET" --type=json \
        -p="[{\"op\": \"add\", \"path\": \"/data/$NEW_FILE\", \"value\": \"$pem\"}]" >/dev/null
    fi
    # The new key current, the old one still published. Both have to verify:
    # a grant issued before the rotation is not invalidated by it, which is
    # the whole claim.
    kubectl -n "$NS" set env "deploy/$DEPLOY" \
      "UMA_AS_SIGNING_KEY=/keys/$NEW_FILE" \
      "UMA_AS_KID=$NEW_KID" \
      "UMA_AS_PREVIOUS_KEYS=/keys/$OLD_FILE" \
      "UMA_AS_PREVIOUS_KIDS=$OLD_KID" >/dev/null
    kubectl -n "$NS" rollout status "deploy/$DEPLOY" --timeout=300s >/dev/null
    echo "  rotated: $NEW_KID current, $OLD_KID retained and published"
    ;;
  restore)
    # Unset rather than set back, so the Deployment returns to the manifest's
    # own shape: the defaults in the image are uma-as-1 at the original path,
    # and a deployment carrying explicit env that happens to match them is a
    # deployment that has been edited.
    kubectl -n "$NS" set env "deploy/$DEPLOY" \
      UMA_AS_SIGNING_KEY- UMA_AS_KID- \
      UMA_AS_PREVIOUS_KEYS- UMA_AS_PREVIOUS_KIDS- >/dev/null
    kubectl -n "$NS" rollout status "deploy/$DEPLOY" --timeout=300s >/dev/null
    kubectl -n "$NS" patch secret "$SECRET" --type=json \
      -p="[{\"op\": \"remove\", \"path\": \"/data/$NEW_FILE\"}]" >/dev/null 2>&1 || true
    echo "  restored: $OLD_KID current, interim key removed"
    ;;
  *)
    echo "usage: $(basename "$0") stage|restore" >&2
    exit 2
    ;;
esac
