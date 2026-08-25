# Build context is the repo root (shared lib/).
FROM python:3.12-slim
RUN pip install --no-cache-dir fastapi uvicorn 'pyjwt[crypto]' python-multipart httpx
WORKDIR /app
COPY lib/uma4a_http_sig.py .
COPY lib/uma4a_org.py .
COPY services/org-authority/app.py services/org-authority/charter.py ./
COPY services/org-authority/org.rego ./
EXPOSE 9040
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "9040"]
