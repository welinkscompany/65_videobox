FROM node:20-bookworm-slim AS web-build

WORKDIR /app
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci
COPY apps/web ./
RUN npm run build

FROM node:20-bookworm-slim AS node-runtime

FROM python:3.12-slim

# Individual deb.debian.org CDN nodes intermittently answer 400 for a single
# package, which fails the whole install.  Retry the fetch rather than the build.
RUN printf 'Acquire::Retries "5";\nAcquire::http::Timeout "30";\n' > /etc/apt/apt.conf.d/80-retries \
    && apt-get update \
    # fonts-nanum: 자막·글줄 오버레이의 한글. fonts-dejavu-core: "여기를 보세요"
    # 아이콘이 그리는 기호(✔ ✕ ⚠ 등) -- 한글 글꼴에는 없다. 지금까지는 다른
    # 패키지에 딸려 들어와 있었을 뿐이라 여기서 명시한다: 사라지면 그 아이콘들이
    # 렌더에서 막힌다(빈 상자를 그리느니 멈추도록 돼 있다).
    # espeak-ng는 더빙을 **설치 없이 오늘 써 볼 수 있게** 하는 내레이션 엔진이다
    # (수 MB, 밖으로 나가지 않음). 목소리를 복제하지는 못한다 -- 창작자 목소리로
    # 더빙하려면 chatterbox를 따로 설치하고 VIDEOBOX_TTS_ENGINE만 바꾸면 된다.
    && apt-get install --no-install-recommends -y --fix-missing ffmpeg espeak-ng nginx util-linux fonts-nanum fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# Keep the Node 20 toolchain available inside the trusted local workspace.
COPY --from=node-runtime /usr/local /usr/local

WORKDIR /app
COPY requirements-container.txt ./
RUN pip install --no-cache-dir -r requirements-container.txt
# 글꼴만 뺀다. 바로 아래에서 fontconfig가 보는 자리에 같은 파일을 한 번 더 싣기
# 때문에, 빼지 않으면 이미지에 두 벌이 들어간다 -- 실측(2026-08-20) 한국어
# 34.1MB·아이콘 10.65MB가 `COPY . .` 층과 그 뒤 `chown -R /app` 층에 각각 앉아
# 합쳐 약 90MB였다. 컨테이너에서 글꼴을 찾는 쪽은 `/usr/share/fonts/truetype/videobox-*`를
# **먼저** 보므로(`overlay_shapes.ICON_FONT_FILES`) 저장소 자리는 이미지에 없어도
# 된다. 그 자리는 컨테이너 없이 worktree에서 바로 돌릴 때만 쓴다.
# `--exclude`는 BuildKit 프런트엔드가 필요하다(이 기계의 BuildKit v0.30에서 확인).
COPY --exclude=assets/fonts . .
COPY --from=web-build /app/dist /app/apps/web/dist

# 자막용 한국어 글꼴. 전부 OFL-1.1이라 이미지에 함께 배포할 수 있고, 근거는
# `assets/fonts/korean/provenance.json`과 THIRD_PARTY_NOTICES.md에 있다.
# 이 자리에 없으면 libass가 조용히 다른 글꼴로 떨어져 완성본만 달라진다.
COPY assets/fonts/korean /usr/share/fonts/truetype/videobox-korean

# "여기를 보세요" 아이콘용 글꼴(Material Symbols Outlined, Apache-2.0). 전구·
# 돋보기·물음표·느낌표처럼 글줄 글꼴에 없는 그림을 그린다 -- 그 넷은 이 글꼴이
# 오기 전까지 컨테이너에서 전부 두부로 나왔다. 자막 글꼴 목록에는 넣지 않는다.
# 근거는 `assets/fonts/icons/provenance.json`과 THIRD_PARTY_NOTICES.md에 있다.
COPY assets/fonts/icons /usr/share/fonts/truetype/videobox-icons
RUN fc-cache -f

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
