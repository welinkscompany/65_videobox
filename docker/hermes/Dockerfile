FROM nousresearch/hermes-agent@sha256:ad79951c26b7707c8c651f30780338d4f9bb17ddca19f6ea78eb27cbf83a3787

USER root

# The bundled Hermes Mem0 plugin declares mem0ai>=2.0.10,<3.  Pin the
# compatible local-only OSS stack at build time; the immutable runtime never
# lazy-installs packages or accepts a Mem0 Cloud credential.
RUN uv pip install --python /opt/hermes/.venv/bin/python \
    "mem0ai==2.0.12" \
    "qdrant-client==1.18.0" \
    "ollama==0.6.2"

COPY docker/hermes/yujin /opt/videobox-yujin
RUN python /opt/videobox-yujin/verify_assets.py

# The official s6 PID 1 must stay root to initialize the writable state volume.
# Its main wrapper drops the long-running Hermes process to the hermes user.
USER root
