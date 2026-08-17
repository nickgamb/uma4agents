# Build context is the repo root (shared lib/).
FROM python:3.12-slim
# asyncpg ships unconditionally though this stack never uses it: the store is
# selected at runtime (UMA_AS_STORE), and one image serving both deployment
# shapes is what lets `make embedded-check` compare like with like. It is a
# small wheel and is never imported unless the Postgres store is chosen.
RUN pip install --no-cache-dir fastapi uvicorn 'pyjwt[crypto]' python-multipart sse-starlette httpx asyncpg
WORKDIR /app
COPY lib/uma4a_http_sig.py .
COPY services/uma-as/app.py services/uma-as/policy.py ./
COPY services/uma-as/assurance.py ./
COPY services/uma-as/store.py services/uma-as/store_memory.py ./
COPY services/uma-as/store_postgres.py services/uma-as/schema.sql ./
EXPOSE 9000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "9000"]
