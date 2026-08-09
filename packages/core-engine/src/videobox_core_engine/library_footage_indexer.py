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

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from videobox_core_engine.media_analysis import FIXED_VISION_RESPONSE_SCHEMA, VISION_ANALYSIS_PROMPT
from videobox_provider_interfaces.embeddings import EmbeddingRequest
from videobox_provider_interfaces.vision import VisionAnalysisRequest

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
    *, summary: str, layers: dict[str, Any], width: int, height: int
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
    return f"{orientation} 영상. {summary.strip()}{tail}"


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
    if vision_provider is None or not vision_model_name:
        # 화면 분석 없이는 저장할 내용이 없다. 조용히 성공한 척하지 않는다.
        return report

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
        )
        store.save_footage_descriptor(
            content_sha256=str(clip["content_sha256"]),
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
            ),
            description_version=FOOTAGE_DESCRIPTION_VERSION,
        )
        report.analyzed.append(filename)

    return report


def _embed(
    text: str, *, embedding_provider: Any | None, embedding_model_name: str | None
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
        return None
