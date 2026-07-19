FROM node:20-bookworm-slim AS web-build

WORKDIR /app
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci
COPY apps/web ./
RUN npm run build

FROM node:20-bookworm-slim AS node-runtime

FROM python:3.12-slim

RUN apt-get update \
    && apt-get install --no-install-recommends -y ffmpeg nginx util-linux \
    && rm -rf /var/lib/apt/lists/*

# Keep the Node 20 toolchain available inside the trusted local workspace.
COPY --from=node-runtime /usr/local /usr/local

WORKDIR /app
COPY requirements-container.txt ./
RUN pip install --no-cache-dir -r requirements-container.txt
COPY . .
COPY --from=web-build /app/dist /app/apps/web/dist

RUN groupadd --gid 10001 videobox-api \
    && useradd --uid 10001 --gid 10001 --create-home videobox-api \
    && groupadd --gid 10002 videobox-web \
    && useradd --uid 10002 --gid 10002 --create-home videobox-web \
    && chown -R videobox-api:videobox-api /app \
    && chmod 0755 /app/docker/workspace-entrypoint.sh /app/docker/workspace-supervisor.py

COPY docker/workspace-nginx.conf /etc/nginx/workspace-nginx.conf

ENV PYTHONPATH=/app/services/api/src:/app/packages/domain-models/src:/app/packages/storage-abstractions/src:/app/packages/provider-interfaces/src:/app/packages/timeline-schema/src:/app/packages/core-engine/src:/app/packages/capcut-export/src

EXPOSE 8080
ENTRYPOINT ["/app/docker/workspace-entrypoint.sh"]
