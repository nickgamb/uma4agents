FROM python:3.12-slim
RUN pip install --no-cache-dir fastapi uvicorn 'pyjwt[crypto]' python-multipart sse-starlette httpx
WORKDIR /app
COPY app.py policy.py ./
EXPOSE 9000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "9000"]
