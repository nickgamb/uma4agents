# Build context is the repo root (shared lib/).
FROM python:3.12-slim
RUN pip install --no-cache-dir fastapi uvicorn 'pyjwt[crypto]' python-multipart httpx
WORKDIR /app
COPY lib/uma4a_org.py lib/uma4a_joint.py ./
COPY services/joint-tally/app.py ./
EXPOSE 9060
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "9060"]
