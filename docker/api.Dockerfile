FROM python:3.12-slim

# espeak-ng는 더빙을 **설치 없이 오늘 써 볼 수 있게** 하는 내레이션 엔진이다
# (수 MB, 밖으로 나가지 않음). 목소리를 복제하지는 못한다 -- 창작자 목소리로
# 더빙하려면 chatterbox를 따로 설치하고 TTSEngineConfig.engine만 바꾸면 된다.
RUN apt-get update \
    && apt-get install --no-install-recommends -y ffmpeg espeak-ng \
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
