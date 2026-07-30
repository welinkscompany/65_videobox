FROM nousresearch/hermes-agent@sha256:ad79951c26b7707c8c651f30780338d4f9bb17ddca19f6ea78eb27cbf83a3787

RUN uv pip install \
    --python /opt/hermes/.venv/bin/python \
    --no-cache \
    mem0ai==2.0.10

COPY services/agent-gateway/src /opt/videobox-agent-gateway
ENV PYTHONPATH=/opt/videobox-agent-gateway

ENTRYPOINT ["python", "-m", "uvicorn", "videobox_agent_gateway.hermes_memory_adapter:app", "--host", "0.0.0.0", "--port", "8082"]
