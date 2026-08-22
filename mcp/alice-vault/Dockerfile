# Build context is the repo root, so the shared enforcement core in lib/ is
# reachable for ENFORCEMENT_MODE=embedded.
FROM python:3.12-slim
# httpx / pyjwt are only needed by the embedded enforcement path; they are
# installed unconditionally so one image serves both modes.
RUN pip install --no-cache-dir "mcp>=2,<3" httpx 'pyjwt[crypto]' cryptography
WORKDIR /app
COPY lib/uma4a_http_sig.py lib/uma4a_pep.py lib/uma4a_publish.py ./
COPY mcp/alice-vault/server.py mcp/alice-vault/uma_extension.py ./
COPY mcp/alice-vault/uma_publish.py ./
# One image, one fixture file per owner. UMA_VAULT_FIXTURES picks.
COPY mcp/alice-vault/fixtures.json mcp/alice-vault/fixtures-carol.json ./
EXPOSE 9020
CMD ["python", "server.py"]
