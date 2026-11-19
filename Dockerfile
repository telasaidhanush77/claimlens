# 1) Build the static web UI.
FROM node:22-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

# 2) Python API that also serves the UI from web/out.
FROM python:3.12-slim
WORKDIR /srv
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8000
COPY pyproject.toml ./
COPY app ./app
COPY migrations ./migrations
RUN pip install --no-cache-dir -e .
COPY --from=web /web/out ./web/out
RUN useradd --create-home app && chown -R app /srv
USER app
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
