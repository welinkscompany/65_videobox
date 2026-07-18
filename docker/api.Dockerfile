FROM python:3.12-slim

RUN apt-get update \
    && apt-get install --no-install-recommends -y ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements-container.txt ./
RUN pip install --no-cache-dir -r requirements-container.txt
COPY . .

RUN useradd --create-home --uid 10001 videobox \
    && chown -R videobox:videobox /app

ENV PYTHONPATH=/app/services/api/src:/app/packages/domain-models/src:/app/packages/storage-abstractions/src:/app/packages/provider-interfaces/src:/app/packages/timeline-schema/src:/app/packages/core-engine/src:/app/packages/capcut-export/src
USER videobox
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "videobox_api.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
