SHELL=/bin/bash -o pipefail

.PHONY: init dns-setup up down logs smoke-test reset fetch-upstream

# Pinned upstream ref for the AAuth person server (built, not vendored)
PERSON_SERVER_REF = 4e05247

## fetch-upstream: clone the pinned AAuth person server into aauth/upstream/
fetch-upstream:
	@mkdir -p aauth/upstream
	@if [ ! -d aauth/upstream/aauth-person-server/.git ]; then \
		git clone https://github.com/christian-posta/aauth-person-server aauth/upstream/aauth-person-server; \
	fi
	@cd aauth/upstream/aauth-person-server && git fetch -q && git checkout -q $(PERSON_SERVER_REF)
	@echo "Upstream pinned: person-server@$(PERSON_SERVER_REF)"

## init: generate local CA, TLS certs, and signing keys; configure local DNS
init:
	mkdir -p ./certs

	# Edge server cert (envoy - external traffic on *.uma.lab)
	CAROOT=./certs mkcert \
		-cert-file=./certs/edge-server.pem \
		-key-file=./certs/edge-server-key.pem \
		localhost "*.uma.lab"

	# Internal server cert (services behind the edge)
	CAROOT=./certs mkcert \
		-cert-file=./certs/internal-server.pem \
		-key-file=./certs/internal-server-key.pem \
		"*.uma.lab" 127.0.0.1

	# Keycloak server cert (Alice's identity provider)
	CAROOT=./certs mkcert \
		-cert-file=./certs/keycloak-server.pem \
		-key-file=./certs/keycloak-server-key.pem \
		keycloak.uma.lab

	# Internal client cert for mTLS (edge -> internal services)
	CAROOT=./certs mkcert -client \
		-cert-file=./certs/internal-client.pem \
		-key-file=./certs/internal-client-key.pem \
		edge

	# uma-as signing key pair (RPT and intent-contract receipts)
	openssl genrsa -out ./certs/uma-as-signing-key.pem 2048
	openssl rsa -in ./certs/uma-as-signing-key.pem -pubout -out ./certs/uma-as-signing-pub.pem

	$(MAKE) dns-setup

	@echo ""
	@echo "==> Init complete. Run: make up"
	@echo "==> Optional (browser trust for https://*.uma.lab): make trust-ca"

## trust-ca: add the local CA to the system trust store (browser use; may prompt)
.PHONY: trust-ca
trust-ca:
	CAROOT=./certs mkcert -install

## dns-setup: point the OS resolver for uma.lab at the local DNS container
dns-setup:
	@case "$$(uname)" in \
		Darwin) \
			if [ -f /etc/resolver/uma.lab ]; then \
				echo "DNS already configured: /etc/resolver/uma.lab"; \
			else \
				echo "Configuring DNS resolver for uma.lab (requires sudo)..."; \
				sudo mkdir -p /etc/resolver && \
				echo "nameserver 127.0.0.1" | sudo tee /etc/resolver/uma.lab > /dev/null && \
				echo "Created /etc/resolver/uma.lab"; \
			fi ;; \
		Linux) \
			if [ -f /etc/systemd/resolved.conf.d/uma.lab.conf ]; then \
				echo "DNS already configured: /etc/systemd/resolved.conf.d/uma.lab.conf"; \
			else \
				echo "Configuring DNS resolver for uma.lab (requires sudo)..."; \
				sudo mkdir -p /etc/systemd/resolved.conf.d && \
				printf "[Resolve]\nDNS=127.0.0.1\nDomains=~uma.lab\n" | \
					sudo tee /etc/systemd/resolved.conf.d/uma.lab.conf > /dev/null && \
				sudo systemctl restart systemd-resolved && \
				echo "Created /etc/systemd/resolved.conf.d/uma.lab.conf"; \
			fi ;; \
		*) \
			echo "Unsupported OS. Manually configure DNS for uma.lab to resolve via 127.0.0.1:53" ;; \
	esac

up: fetch-upstream
	docker compose up -d --build

down:
	docker compose down --timeout 2 --volumes --remove-orphans

logs:
	docker compose logs -f

## demo acts: walk the day headlessly (same code path as the agent-shim)
.PHONY: demo-tier1 demo-tier2 demo-tier3 demo-all
demo-tier1:
	docker compose --profile demo run --rm demo-driver --act tier1
demo-tier2:
	docker compose --profile demo run --rm demo-driver --act tier2
## demo-tier3: pends until Alice approves in her portal (https://portal.uma.lab);
## add SIM=1 to simulate her tap for fully headless runs
demo-tier3:
	docker compose --profile demo run --rm demo-driver --act tier3 $(if $(SIM),--simulate-alice)
demo-all:
	docker compose --profile demo run --rm demo-driver --act all $(if $(SIM),--simulate-alice)

## audit: print Alice's dinner ledger (promised / touched / personally approved)
.PHONY: audit
audit:
	@docker compose exec -T uma-as python3 -c "\
	import urllib.request, json; \
	req = urllib.request.Request('http://localhost:9000/owner/ledger', \
		headers={'Authorization': 'Bearer ' + __import__('os').environ.get('UMA_AS_OWNER_TOKEN', 'owner-dev-portal')}); \
	entries = json.load(urllib.request.urlopen(req)); \
	print(json.dumps(entries, indent=2))"

## smoke-test: verify each service is healthy (grows with the stack)
# Uses curl --resolve + --cacert so it works before make dns-setup / trust-ca.
CURL = curl -sk --cacert ./certs/rootCA.pem \
	--resolve alice-as.uma.lab:443:127.0.0.1 \
	--resolve keycloak.uma.lab:443:127.0.0.1 \
	--resolve gateway.uma.lab:443:127.0.0.1 \
	--resolve portal.uma.lab:443:127.0.0.1 \
	--resolve grafana.uma.lab:443:127.0.0.1 \
	--resolve ps.uma.lab:443:127.0.0.1

smoke-test:
	@echo "==> DNS resolution (host resolver; optional until make dns-setup)..."
	@python3 -c "import socket; socket.gethostbyname('gateway.uma.lab')" 2>/dev/null \
		&& echo "  DNS: OK" || echo "  DNS: not configured (browser use needs 'make dns-setup'; smoke tests don't)"
	@echo "==> uma-as discovery..."
	@$(CURL) https://alice-as.uma.lab/.well-known/uma4agents-configuration | grep -q token_endpoint \
		&& echo "  uma-as: OK" || echo "  uma-as: FAIL"
	@echo "==> uma-as JWKS..."
	@$(CURL) https://alice-as.uma.lab/jwks | grep -q Ed25519 && echo "  jwks: OK" || echo "  jwks: FAIL"
	@echo "==> Keycloak alice realm..."
	@$(CURL) https://keycloak.uma.lab/realms/alice/.well-known/openid-configuration | grep -q issuer \
		&& echo "  keycloak: OK" || echo "  keycloak: FAIL"
	@echo "==> Gateway challenges an unauthorized tool call (expect 401 + UMA ticket)..."
	@RESP=$$($(CURL) -i https://gateway.uma.lab/mcp -X POST \
		-H 'content-type: application/json' -H 'accept: application/json, text/event-stream' \
		-d '{"jsonrpc":"2.0","method":"tools/call","id":1,"params":{"name":"get_positions","arguments":{}}}'); \
		echo "$$RESP" | grep -qi 'www-authenticate: UMA' && echo "$$RESP" | grep -q 'ticket=' \
		&& echo "  gateway challenge: OK" || { echo "  gateway challenge: FAIL"; }
	@echo "==> Alice's portal..."
	@$(CURL) https://portal.uma.lab/health | grep -q ok && echo "  portal: OK" || echo "  portal: FAIL"
	@echo "==> Person server discovery..."
	@$(CURL) https://ps.uma.lab/.well-known/aauth-person.json | grep -q token_endpoint \
		&& echo "  person-server: OK" || echo "  person-server: FAIL"
	@echo "==> Grafana..."
	@$(CURL) https://grafana.uma.lab/api/health | grep -q ok && echo "  grafana: OK" || echo "  grafana: FAIL"
	@echo "==> Loki has protocol events..."
	@docker compose exec -T loki wget -qO- 'http://localhost:3100/loki/api/v1/query_range?query=%7Bevent%3D%22challenge.issued%22%7D&limit=1' 2>/dev/null \
		| grep -q challenge.issued && echo "  loki events: OK" || echo "  loki events: FAIL (may need a challenge first + a few seconds)"

## reset: rewind demo state without tearing the stack down
# Grant-layer state (tickets, contracts, ledger) is in-memory by design;
# restarting the two services rewinds the story.
reset:
	docker compose restart uma-as uma-pep
	@echo "Demo state rewound."
