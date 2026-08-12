"""드롭 폴더에 쌓인 촬영본을 찾을 수 있는 자산으로 만든다.

b-roll 분석은 프로젝트에 묶여 있었다. 그래서 라이브러리에 있는 영상은 가져오기
전까지 유진에게 보이지 않았고, 같은 영상을 두 프로젝트에서 쓰면 두 번 분석했다.
여기서는 파일 내용 해시를 열쇠로 라이브러리 자체를 색인한다 -- 새로 넣은 영상은
저절로 대기 목록에 들어가고, 같은 영상은 다시 분석하지 않는다.

화면 분석과 임베딩은 실패하는 방식이 다르다. 화면 분석이 없으면 저장할 내용
자체가 없으므로 실패로 남기고, 임베딩만 못 만든 경우에는 분석 결과를 지키고
벡터만 다음 차례에 받는다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from videobox_core_engine.media_analysis import FIXED_VISION_RESPONSE_SCHEMA, VISION_ANALYSIS_PROMPT
from videobox_provider_interfaces.embeddings import EmbeddingRequest
from videobox_provider_interfaces.vision import VisionAnalysisRequest

_logger = logging.getLogger(__name__)

# 문장 형식을 바꾸면 올린다. 저장된 벡터는 그때의 문장을 가리키므로, 형식이
# 바뀌면 전부 다시 색인해야 검색이 실제 문장과 맞는다.
FOOTAGE_DESCRIPTION_VERSION = 2

# 실제로 색인해 보니 요약과 태그가 전부 영어로 나왔다. owner는 우리말로 찾고,
# 이 문장은 화면에 그대로 보일 수 있다. 같은 언어끼리 맞출 때 점수도 높다 --
# 영어 요약으로 검색했을 때 0.52~0.59, 우리말 오디오 쪽은 0.68~0.70이었다.
# 프로젝트 쪽 분석도 같은 문구를 쓴다 -- 두 경로가 다르게 물으면 같은 영상이
# 서로 다른 언어로 설명된다.
_VISION_PROMPT = VISION_ANALYSIS_PROMPT

# 화면 분석은 오디오 측정보다 훨씬 무겁다. 한 번에 처리하는 수를 작게 둬서
# 영상을 한꺼번에 넣어도 렌더링이 느려지지 않게 한다.
_DEFAULT_MAX_CLIPS = 2

# owner에게 보여도 되는 갈래만 문장에 넣는다. 나머지는 태그로 저장돼 있어
# 필요할 때 꺼내 쓸 수 있다.
_DESCRIBED_LAYERS = (
    ("place", ""),
    ("scene", ""),
    ("action", ""),
    ("people_objects", ""),
    ("weather", ""),
    ("time_of_day", ""),
    ("season", ""),
    ("mood", ""),
    ("emotion", ""),
)


@dataclass(slots=True)
class LibraryFootageIndexReport:
    analyzed: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    remaining: int = 0


def build_footage_description(
    *, summary: str, layers: dict[str, Any], width: int, height: int,
    user_metadata: dict[str, Any] | None = None,
) -> str:
    """검색되는 문장을 만든다.

    화면에 그대로 보여도 되는 우리말이어야 한다. 방향은 모델이 짐작한 태그가
    아니라 실제 화면 크기에서 나온다 -- 숏폼을 만들 때는 예/아니오 문제다.
    """
    orientation = "가로" if int(width) >= int(height) else "세로"
    words: list[str] = []
    for layer, _ in _DESCRIBED_LAYERS:
        values = layers.get(layer)
        if isinstance(values, list):
            words.extend(str(value) for value in values if str(value).strip())
    unique: list[str] = []
    for word in words:
        if word not in unique:
            unique.append(word)
    tail = f" {', '.join(unique)}." if unique else ""
    text = f"{orientation} 영상. {summary.strip()}{tail}"
    metadata = user_metadata or {}
    tags = metadata.get("tags") if isinstance(metadata, dict) else None
    if isinstance(tags, list):
        normalized = [str(tag).strip() for tag in tags if str(tag).strip()]
        if normalized:
            text += f" 사용자가 붙인 태그: {', '.join(dict.fromkeys(normalized))}."
    return text


def index_pending_library_footage(
    *,
    store: Any,
    paths: Iterable[Path],
    media_probe: Any,
    vision_provider: Any,
    vision_model_name: str | None,
    embedding_provider: Any | None,
    embedding_model_name: str | None,
    max_clips: int | None = _DEFAULT_MAX_CLIPS,
) -> LibraryFootageIndexReport:
    report = LibraryFootageIndexReport()
    pending = store.list_footage_needing_analysis(
        paths=list(paths), description_version=FOOTAGE_DESCRIPTION_VERSION
    )
    batch = pending if max_clips is None else pending[:max_clips]
    report.remaining = len(pending) - len(batch)

    for clip in batch:
        filename = str(clip["filename"])
        path = Path(str(clip["path"]))
        if not path.is_file():
            report.failed.append(filename)
            continue
        existing = None
        getter = getattr(store, "get_footage_descriptor", None)
        if callable(getter):
            existing = getter(content_sha256=str(clip["content_sha256"]))
        # Approved ranges already have a durable, owner-visible description
        # from the proposal.  They must not go through the expensive vision
        # path (or require a fabricated frame); only ask the configured local
        # embedding provider for the missing vector.
        if clip.get("is_segment") or clip.get("source_segment_id"):
            if not existing:
                report.failed.append(filename)
                continue
            description = str(existing.get("description", ""))
            embedding = _embed(
                description,
                embedding_provider=embedding_provider,
                embedding_model_name=embedding_model_name,
                label=filename,
            )
            store.save_footage_descriptor(
                content_sha256=str(clip["content_sha256"]),
                library_asset_id=clip.get("library_asset_id") or existing.get("library_asset_id"),
                filename=str(existing.get("filename") or filename),
                duration_seconds=float(existing["duration_seconds"]),
                width=int(existing["width"]),
                height=int(existing["height"]),
                tags=dict(existing.get("tags") or {}),
                description=description,
                embedding=embedding,
                description_version=FOOTAGE_DESCRIPTION_VERSION,
            )
            if embedding is not None:
                marker = getattr(store, "mark_footage_segment_indexed", None)
                if callable(marker):
                    marker(source_segment_id=str(clip["source_segment_id"]))
            report.analyzed.append(filename)
            continue
        if (
            existing
            and int(existing.get("description_version", 0)) >= FOOTAGE_DESCRIPTION_VERSION
            and existing.get("embedding") is None
        ):
            description = str(existing.get("description", ""))
            embedding = _embed(
                description,
                embedding_provider=embedding_provider,
                embedding_model_name=embedding_model_name,
                label=filename,
            )
            store.save_footage_descriptor(
                content_sha256=str(clip["content_sha256"]),
                library_asset_id=clip.get("library_asset_id") or existing.get("library_asset_id"),
                filename=str(existing.get("filename") or filename),
                duration_seconds=float(existing["duration_seconds"]),
                width=int(existing["width"]),
                height=int(existing["height"]),
                tags=dict(existing.get("tags") or {}),
                description=description,
                embedding=embedding,
                description_version=FOOTAGE_DESCRIPTION_VERSION,
            )
            report.analyzed.append(filename)
            continue
        if vision_provider is None or not vision_model_name:
            # 화면 분석 없이는 새 설명을 만들 수 없다. 조용히 성공한 척하지 않는다.
            report.failed.append(filename)
            continue
        try:
            probe = media_probe.probe(path)
            response = vision_provider.analyze_images(
                VisionAnalysisRequest(
                    model_name=str(vision_model_name),
                    prompt=_VISION_PROMPT,
                    images=tuple(frame.data for frame in probe.frames),
                    response_schema=FIXED_VISION_RESPONSE_SCHEMA,
                )
            )
        except Exception:
            report.failed.append(filename)
            continue

        output = dict(response.output_data)
        layers = output.get("layers") or {}
        description = build_footage_description(
            summary=str(output.get("summary", "")),
            layers=layers if isinstance(layers, dict) else {},
            width=int(probe.width),
            height=int(probe.height),
            user_metadata=dict(clip.get("user_metadata") or {}),
        )
        store.save_footage_descriptor(
            content_sha256=str(clip["content_sha256"]),
            library_asset_id=clip.get("library_asset_id"),
            filename=filename,
            duration_seconds=float(probe.duration_sec),
            width=int(probe.width),
            height=int(probe.height),
            tags=output,
            description=description,
            embedding=_embed(
                description,
                embedding_provider=embedding_provider,
                embedding_model_name=embedding_model_name,
                label=filename,
            ),
            description_version=FOOTAGE_DESCRIPTION_VERSION,
        )
        report.analyzed.append(filename)

    return report


def _embed(
    text: str, *, embedding_provider: Any | None, embedding_model_name: str | None,
    label: str = "",
) -> list[float] | None:
    if embedding_provider is None or not embedding_model_name:
        return None
    try:
        response = embedding_provider.embed(
            EmbeddingRequest(model_name=embedding_model_name, inputs=(text,))
        )
        return [float(value) for value in response.vectors[0]]
    except Exception:
        # 화면 분석 결과는 지킨다. 벡터가 없으면 저장소가 다시 대기로 돌린다.
        #
        # 동작은 그대로 두되 이유는 남긴다. 벡터가 없으면 그 촬영본은 뜻으로 찾을 수
        # 없고 검색이 조용히 낱말 맞추기로 떨어진다 -- owner에게는 "찾아 주는 게 늘
        # 비슷하다"로만 보이고, 왜 그런지는 어디에도 없었다.
        _logger.warning(
            "촬영본을 뜻으로 찾을 수 있게 만들지 못했습니다 (파일=%s, 모델=%s). "
            "그 영상은 이름과 낱말로만 찾힙니다. 다음 색인에서 다시 시도합니다.",
            label or "(이름 없음)",
            embedding_model_name,
            exc_info=True,
        )
        return None
