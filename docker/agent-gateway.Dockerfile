FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

WORKDIR /app

COPY requirements-agent-gateway.txt /app/requirements-agent-gateway.txt
RUN pip install --no-cache-dir -r /app/requirements-agent-gateway.txt

COPY services/agent-gateway/src /app/src

RUN groupadd --gid 10001 videobox-agent-gateway \
    && useradd --uid 10001 --gid 10001 --no-create-home \
        --shell /usr/sbin/nologin videobox-agent-gateway

USER 10001:10001

EXPOSE 8081
CMD ["uvicorn", "videobox_agent_gateway.main:app", "--host", "0.0.0.0", "--port", "8081"]
