FROM nousresearch/hermes-agent@sha256:ad79951c26b7707c8c651f30780338d4f9bb17ddca19f6ea78eb27cbf83a3787

RUN uv pip install \
    --python /opt/hermes/.venv/bin/python \
    --no-cache \
    mem0ai==2.0.10

# 자체 호스팅 기억의 벡터 저장소가 놓일 자리. 이름 있는 볼륨은 이 경로의
# 소유권을 물려받는다. 서비스는 uid 10000 으로 돌고 루트 파일시스템이 읽기
# 전용이라, 기동 뒤에는 소유권을 고칠 방법이 없다.
RUN mkdir -p /var/lib/videobox-mem0 \
    && chown 10000:10000 /var/lib/videobox-mem0

COPY services/agent-gateway/src /opt/videobox-agent-gateway
ENV PYTHONPATH=/opt/videobox-agent-gateway

ENTRYPOINT ["python", "-m", "uvicorn", "videobox_agent_gateway.hermes_memory_adapter:app", "--host", "0.0.0.0", "--port", "8082"]
