FROM python:3.12-slim
RUN pip install --no-cache-dir fastapi uvicorn httpx authlib itsdangerous
WORKDIR /app
COPY app.py .
COPY static ./static
EXPOSE 9050
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "9050"]
