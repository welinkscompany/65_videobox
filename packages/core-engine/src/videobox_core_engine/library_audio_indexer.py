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
DESCRIPTION_VERSION = 4

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
# **재서 쓴 문장만으로는 효과음이 서로 구별되지 않는다**(실측 2026-09-05).
# 세기·밝기·빠르기 세 칸(27가지)에 효과음 100개가 들어가니 폭발음과 버튼음이
# 거의 같은 문장을 갖는다 -- "팝 하고 터지는 소리"를 찾았을 때 상위 넷의 점수가
# 0.646086/0.646015/0.646015/0.646015로 사실상 같았고, 1등이 RPG 폭발음이었다.
#
# 정체는 이미 이름에 있다(`sfx-various-click`). 창작자는 "딸깍"이라고 찾으므로
# 흔한 낱말은 한국어 뜻을 같이 적는다. 임베딩 모델이 다국어라(영어 질의가
# 한국어 설명에 걸리는 것을 실측했다) 영어 낱말 자체도 그냥 두면 도움이 된다.
_NAME_MEANINGS = {
    "ambient": "은은하게 깔리는", "amber": "울리는", "bang": "쾅 하는", "bangs": "쾅 하는",
    "baseballbat": "방망이 치는", "bat": "치는", "bee": "벌 날갯짓", "beep": "삐 소리",
    "bell": "종소리", "bounce": "통통 튀는", "bouncing": "통통 튀는", "break": "부서지는",
    "button": "단추 누르는", "calm": "차분한", "cancel": "취소 소리", "cannon": "대포",
    "chill": "느긋한", "chills": "느긋한", "cider": "청량한", "city": "도시",
    "classic": "클래식", "click": "딸깍", "cloud": "구름처럼 포근한", "coin": "동전",
    "crush": "으스러지는", "death": "쓰러지는", "dialogue": "대화", "distant": "멀리서",
    "door": "문 여닫는", "drift": "흘러가는", "dull": "둔탁한", "explosion": "폭발",
    "fall": "떨어지는", "fire": "발사", "footstep": "발소리", "footsteps": "발소리",
    "fox": "여우", "glug": "꿀꺽 마시는", "grass": "풀 스치는", "gunshot": "총소리",
    "hit": "부딪히는", "hurt": "맞는", "ice": "얼음", "impact": "쿵 부딪히는",
    "item": "아이템 얻는", "lofi": "로파이", "loop": "반복", "lost": "헤매는",
    "menu": "메뉴", "message": "알림", "miss": "빗나가는", "moan": "신음",
    "move": "이동", "movement": "움직임", "mysterious": "신비로운", "napping": "졸린",
    "nom": "우물우물 먹는", "peaceful": "평온한", "piano": "피아노", "player": "인물",
    "pop": "팝 하고 터지는", "power": "힘이 차는", "powered": "작동하는",
    "punch": "주먹질", "relax": "편안한", "rock": "돌", "scooter": "스쿠터",
    "sea": "바다", "select": "선택 소리", "ship": "배", "slip": "미끄러지는",
    "slow": "느린", "small": "작은", "spear": "창", "splash": "물 튀는",
    "splat": "철퍽", "splurt": "쏟아지는", "sproing": "튕기는", "steal": "훔치는",
    "step": "발소리", "steps": "발소리", "stone": "돌", "stride": "성큼 걷는",
    "success": "성공 알림", "swim": "헤엄치는", "swish": "휙 스치는",
    "swoosh": "휙 스치는", "tap": "톡 두드리는", "teleport": "순간이동",
    "throw": "던지는", "tick": "똑딱", "tom": "북 치는", "treasure": "보물",
    "vibrophone": "비브라폰", "wall": "벽", "weeds": "풀숲", "whoosh": "휙 스치는",
    # 2026-09-05에 들어온 브이로그용 소리들. **낱말을 같이 넣지 않으면 새로
    # 넣은 보람이 없다** -- "타자 치는 소리"로 찾았더니 `keypress` 설명이
    # 영어뿐이라 걸리지 않고, 한국어 "타자"가 야구 타자로 읽혀 야구방망이가
    # 1등으로 나왔다.
    "typing": "타자 치는 타이핑 키보드", "keypress": "키 하나 누르는 타자 키보드",
    "paper": "종이", "ripped": "찢는", "medium": "보통", "fast": "빠른",
}

# 이름 노릇을 못 하는 토막들. 접두사·번호·해시는 뜻이 없고, 넣으면 서로 다른
# 자산을 다시 비슷하게 만든다 -- 고치려던 것과 같은 문제다.
_NAME_NOISE = {"sfx", "music", "n", "v", "rpg", "various", "user", "pack", "starter", "x"}


def _identity_phrase(asset_name: str | None) -> str:
    """이름에서 소리의 정체를 뽑는다. 뜻이 없으면 빈 문자열."""
    if not asset_name:
        return ""
    tokens: list[str] = []
    for raw in str(asset_name).replace("_", "-").replace(" ", "-").lower().split("-"):
        token = raw.rstrip("0123456789")
        if len(token) < 2 or token in _NAME_NOISE:
            continue
        # 내용 해시처럼 보이면 이름이 아니다.
        if len(token) > 12 and all(ch in "0123456789abcdef" for ch in token):
            continue
        if token not in tokens:
            tokens.append(token)
    if not tokens:
        return ""
    meanings = [_NAME_MEANINGS[token] for token in tokens if token in _NAME_MEANINGS]
    english = " ".join(tokens)
    if meanings:
        return f" 소리의 정체: {' '.join(dict.fromkeys(meanings))} ({english})."
    return f" 소리의 정체: {english}."


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
    user_metadata: dict[str, Any] | None = None, asset_name: str | None = None,
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
    text += _identity_phrase(asset_name)
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
        existing = None
        getter = getattr(store, "get_audio_descriptor", None)
        if callable(getter):
            existing = getter(library_asset_id=library_asset_id)
        # **재는 일과 쓰는 일을 따로 판단한다.** 둘을 묶어 두면 문구를 한 줄
        # 고칠 때마다 자산 130개를 ffmpeg로 다시 재게 된다 -- 파일이 그대로면
        # 측정값도 그대로다. 판이 올라갔을 때 다시 해야 하는 것은 문장뿐이다.
        same_file = bool(existing and str(existing.get("sha256")) == str(asset.get("sha256")))
        if same_file:
            measurements = {
                "duration_seconds": float(existing["duration_seconds"]),
                "loudness_rms": float(existing["loudness_rms"]),
                "brightness_hz": float(existing["brightness_hz"]),
                "onset_rate_per_second": float(existing["onset_rate_per_second"]),
            }
            words = dict(existing["words"])
        else:
            try:
                descriptor = describe(path)
            except Exception:
                report.failed.append(library_asset_id)
                continue
            measurements = {
                "duration_seconds": descriptor.duration_seconds,
                "loudness_rms": descriptor.loudness_rms,
                "brightness_hz": descriptor.brightness_hz,
                "onset_rate_per_second": descriptor.onset_rate_per_second,
            }
            words = describe_in_creator_language(descriptor)
        if same_file and int(existing.get("description_version", 0)) >= DESCRIPTION_VERSION:
            description = str(existing["description"])
        else:
            description = build_asset_description(
                media_type=str(asset["media_type"]),
                words=words,
                duration_seconds=float(measurements["duration_seconds"]),
                user_metadata=dict(asset.get("user_metadata") or {}),
                asset_name=str(asset.get("asset_id") or ""),
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
            measurements=measurements,
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
