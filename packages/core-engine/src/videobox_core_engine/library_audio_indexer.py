"""Keep the music and effects library findable as it grows.

The owner will add music and sound effects over time. Each new file has to
become searchable without anyone remembering to run a step, so this walks
whatever the store reports as pending -- never measured, bytes changed, or
still missing its vector -- and brings it up to date.

Two capabilities with different failure modes are deliberately kept apart.
Measuring needs only ffmpeg and always works locally; embedding needs the
local model and can be away. Losing the model must not throw away the ffmpeg
work, so a descriptor is saved either way and the asset simply stays pending
until its vector can be made.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol

from videobox_core_engine.audio_descriptors import (
    AudioDescriptor,
    describe_audio_file,
    describe_in_creator_language,
)
from videobox_provider_interfaces.embeddings import EmbeddingRequest

_MEDIA_TYPE_WORDS = {"music": "음악", "sfx": "효과음"}

# Bump when the wording below changes. Stored vectors describe the text that
# was current when they were made, so a format change has to send every asset
# back through the indexer rather than leaving the library ranked against
# sentences that no longer exist.
DESCRIPTION_VERSION = 2

# A fixed template differing by two words leaves every vector nearly parallel:
# live search put a 보통/보통 track above a 강함/빠름 one for "신나고 빠른
# 음악", separated by 0.002. Each bucket gets its own phrasing so the
# sentences genuinely differ.
_STRENGTH_PHRASES = {
    "조용함": "잔잔하게 깔리는 작은 소리",
    "보통": "적당한 크기로 자연스럽게 들리는",
    "강함": "크고 존재감이 뚜렷한",
}
_BRIGHTNESS_PHRASES = {
    "어두움": "낮고 묵직한 음색",
    "중간": "부드럽고 무난한 음색",
    "밝음": "높고 또렷하며 화사한 음색",
}
_PACE_PHRASES = {
    "느림": "천천히 흐르고 여유로운 느낌",
    "보통": "일정하게 이어지는 느낌",
    "빠름": "빠르게 몰아치고 활기찬 신나는 느낌",
}
_logger = logging.getLogger(__name__)
_LENGTH_PHRASES = (
    (2.0, "아주 짧게 한 번 스치는"),
    (15.0, "짧게 쓰는"),
    (60.0, "한 장면에 얹기 좋은"),
    (float("inf"), "영상 전체에 길게 깔아 두기 좋은"),
)


class _LibraryAudioStore(Protocol):
    def list_assets_needing_audio_analysis(
        self, *, description_version: int = 1
    ) -> list[dict[str, Any]]: ...
    def save_audio_descriptor(self, **kwargs: Any) -> None: ...


@dataclass(slots=True)
class LibraryAudioIndexReport:
    analyzed: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    remaining: int = 0


def build_asset_description(
    *, media_type: str, words: dict[str, str], duration_seconds: float,
    user_metadata: dict[str, Any] | None = None,
) -> str:
    """Write the sentence that gets embedded and searched.

    It is written in the same creator language the screen uses, so a query
    like "차분한 배경 음악" lands near the right assets, and so anything shown
    to the owner needs no translating. Length is part of it: a 3-second sting
    and a 3-minute bed suit completely different scenes.
    """
    kind = _MEDIA_TYPE_WORDS.get(media_type, "소리")
    length_phrase = next(
        phrase for limit, phrase in _LENGTH_PHRASES if duration_seconds <= limit
    )
    text = (
        f"{length_phrase} {kind}. "
        f"{_STRENGTH_PHRASES[words['세기']]}, "
        f"{_BRIGHTNESS_PHRASES[words['밝기']]}, "
        f"{_PACE_PHRASES[words['빠르기']]}."
    )
    metadata = user_metadata or {}
    tags = metadata.get("tags") if isinstance(metadata, dict) else None
    if isinstance(tags, list):
        normalized = [str(tag).strip() for tag in tags if str(tag).strip()]
        if normalized:
            text += f" 사용자가 붙인 태그: {', '.join(dict.fromkeys(normalized))}."
    return text


def index_pending_library_audio(
    *,
    store: _LibraryAudioStore,
    embedding_provider: Any | None,
    embedding_model_name: str | None,
    describe: Callable[[Path], AudioDescriptor] = describe_audio_file,
    max_assets: int | None = None,
) -> LibraryAudioIndexReport:
    """Bring pending assets up to date, one bounded pass.

    `max_assets` keeps a first install of 130 files -- or a big drop of new
    ones -- from turning startup into a long analysis run. Whatever is left
    is reported and picked up next time.
    """
    report = LibraryAudioIndexReport()
    pending = store.list_assets_needing_audio_analysis(description_version=DESCRIPTION_VERSION)
    batch = pending if max_assets is None else pending[:max_assets]
    report.remaining = len(pending) - len(batch)

    for asset in batch:
        library_asset_id = str(asset["library_asset_id"])
        path = Path(str(asset["path"]))
        if not path.is_file():
            # A pack whose files were moved or removed. Recording it as failed
            # keeps it visible instead of silently absent from every search.
            report.failed.append(library_asset_id)
            continue
        try:
            descriptor = describe(path)
        except Exception:
            report.failed.append(library_asset_id)
            continue

        words = describe_in_creator_language(descriptor)
        description = build_asset_description(
            media_type=str(asset["media_type"]),
            words=words,
            duration_seconds=descriptor.duration_seconds,
            user_metadata=dict(asset.get("user_metadata") or {}),
        )
        embedding = _embed(
            description,
            embedding_provider=embedding_provider,
            embedding_model_name=embedding_model_name,
            label=library_asset_id,
        )
        store.save_audio_descriptor(
            library_asset_id=library_asset_id,
            sha256=str(asset["sha256"]),
            measurements={
                "duration_seconds": descriptor.duration_seconds,
                "loudness_rms": descriptor.loudness_rms,
                "brightness_hz": descriptor.brightness_hz,
                "onset_rate_per_second": descriptor.onset_rate_per_second,
            },
            words=words,
            description=description,
            embedding=embedding,
            description_version=DESCRIPTION_VERSION,
        )
        report.analyzed.append(library_asset_id)

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
        # The measurements above are still worth saving; the store treats a
        # null vector as "come back for this one".
        #
        # 동작은 그대로 두되 이유는 남긴다. 벡터가 없으면 그 자산은 뜻으로 찾을 수 없고
        # 검색이 조용히 단어 매칭으로 떨어진다 -- owner에게는 "추천이 늘 비슷하다"로만
        # 보이고, 왜 그런지는 어디에도 없었다.
        _logger.warning(
            "음악·효과음을 뜻으로 찾을 수 있게 만들지 못했습니다 (자산=%s, 모델=%s). "
            "그 자산은 이름과 낱말로만 찾힙니다. 다음 색인에서 다시 시도합니다.",
            label or "(이름 없음)",
            embedding_model_name,
            exc_info=True,
        )
        return None
