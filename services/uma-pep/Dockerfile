# Build context is the repo root (shared lib/).
FROM python:3.12-slim
RUN pip install --no-cache-dir fastapi uvicorn httpx 'pyjwt[crypto]'
WORKDIR /app
COPY lib/uma4a_http_sig.py .
COPY services/uma-pep/app.py .
EXPOSE 9002
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "9002"]
