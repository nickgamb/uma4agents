# Build context is the repo root (shared lib/).
FROM python:3.12-slim
RUN pip install --no-cache-dir fastapi uvicorn 'pyjwt[crypto]' python-multipart httpx
WORKDIR /app
COPY services/xaa-broker/app.py .
EXPOSE 9080
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "9080"]
