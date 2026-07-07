# Builds the upstream AAuth Person Server / Agent Server unified portal from
# the pinned checkout in aauth/upstream/ (see make fetch-upstream).

FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY upstream/aauth-person-server/ .
RUN pip install --no-cache-dir -e .
EXPOSE 8765
CMD ["uvicorn", "portal.http.app:app", "--host", "0.0.0.0", "--port", "8765"]
