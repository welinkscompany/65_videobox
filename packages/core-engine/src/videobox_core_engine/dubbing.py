"""번역한 자막을 그 언어 목소리로 읽혀 내레이션을 바꾼다.

동영상 번역기 2단계다. 1단계(`caption_translation.py`)가 만든 번역을 **그대로
대본으로 쓴다.** 따로 번역하지 않는 이유가 분명하다: 화면의 자막과 들리는 말이
어긋나면 둘 다 틀린 것처럼 보인다. 창작자가 번역을 손보면 다음 더빙이 그것을
읽는다 -- 고칠 자리가 하나여야 한다.

## 길이가 이 기능의 전부다

같은 뜻을 영어로 옮기면 한국어보다 길거나 짧다. 5초짜리 장면에 6.2초를 넣으면
다음 장면을 덮고, 3초를 넣으면 두 장면 사이가 뻥 빈다.

셋 중 하나를 골라야 했다.

1. **장면 길이를 늘린다** -- 뒤 장면이 전부 밀리고 음악·효과음·화면 요소가 다
   어긋난다. 자막 하나 바꿨다고 편집본 전체가 흔들리면 안 된다.
2. **안 맞으면 거절한다** -- 정직하지만 대부분의 장면이 거절된다. 영어가
   한국어보다 0.5초 이상 차이 나는 것은 예외가 아니라 보통이다.
3. **자연스러운 범위 안에서 속도를 조절해 맞춘다** -- 실제 더빙이 하는 일이다.

**3번을 골랐고, 범위를 넘으면 2번으로 떨어진다.** 사람 귀는 ±10% 정도는 거의
못 알아채고 25%까지 빨라지는 것은 참을 만하다. 그 밖은 소리가 우스워져서
없느니만 못하다 -- 그때는 억지로 맞추지 않고 **그 장면을 못 맞췄다고 말한다.**

## 짧은 것과 긴 것은 다루는 법이 다르다

**긴 말은 빠르게 하고, 짧은 말은 뒤를 조용히 둔다.** 처음에는 짧은 말도 느리게
늘려서 맞추려 했는데, 실제로 돌려 보니(2026-09-02) 다섯 장면 중 넷이 거절됐다 --
영어가 한국어 장면보다 짧은 것은 예외가 아니라 보통이고, 3.6초를 5초로 늘리려면
0.72배가 되어 범위를 벗어난다.

늘리는 것은 애초에 틀린 답이었다. 말이 짧으면 **말이 끝나고 조용해지면 된다.**
실제 더빙이 그렇게 한다 -- 대사를 늘어뜨려 장면을 채우지 않는다.

다만 너무 짧으면 번역이 내용을 흘린 것이다. 장면의 절반도 안 되면 그건 맞추기
전에 번역을 봐야 할 문제라 넣지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess
from typing import Any, Mapping, Sequence

from videobox_core_engine.caption_translation import SUPPORTED_CAPTION_LANGUAGES


#: 이 안이면 속도를 건드리지 않는다. 어차피 안 들린다.
DUBBING_EXACT_TOLERANCE_SEC = 0.15

#: 말이 길 때 얼마까지 빠르게 해도 되는지. 이 밖은 소리가 우스워진다.
#: `atempo` 한 번으로 낼 수 있는 범위(0.5~2.0) 안이기도 하다.
DUBBING_MAX_SPEED = 1.25

#: 말이 짧을 때는 늘리지 않고 뒤를 조용히 둔다. 다만 장면의 이만큼도 못 채우면
#: 번역이 내용을 흘린 것이라 넣지 않는다 -- 맞추기 전에 볼 것이 따로 있다.
DUBBING_MIN_FILL_RATIO = 0.5


@dataclass(frozen=True, slots=True)
class DubbingLine:
    """한 장면에 넣을 더빙 한 줄."""

    segment_id: str
    text: str
    target_duration_sec: float


@dataclass(frozen=True, slots=True)
class DubbingFit:
    """만든 소리를 장면 길이에 맞춘 결과.

    `fitted`가 False면 **그 장면은 더빙하지 않는다.** 우스운 소리를 넣느니
    원래 내레이션을 그대로 두고 못 맞췄다고 말하는 편이 낫다.
    """

    fitted: bool
    target_duration_sec: float
    actual_duration_sec: float
    speed: float
    #: 말이 끝난 뒤 조용히 둘 시간. 0이면 그대로 장면을 꽉 채운다.
    pad_sec: float = 0.0
    reason: str | None = None


def dubbing_lines(
    *, editing_session: Mapping[str, Any], language: str
) -> list[DubbingLine]:
    """이 언어로 더빙할 장면들. 번역이 없는 장면은 조용히 건너뛴다.

    건너뛰는 것이 맞는 이유: 번역이 반쯤 된 상태에서도 더빙을 눌러 볼 수 있어야
    하고, 번역 안 된 장면은 **원래 목소리가 그대로 남는 것**이 옳다. 없는 번역을
    한국어 원문으로 메워서 영어 더빙 중간에 한국어가 튀어나오게 하면 안 된다.
    """
    if language not in SUPPORTED_CAPTION_LANGUAGES:
        raise ValueError(f"Unsupported caption language: {language}")
    lines: list[DubbingLine] = []
    for segment in editing_session.get("segments", []):
        if not isinstance(segment, dict):
            continue
        if str(segment.get("cut_action") or "keep") == "remove":
            continue
        translations = segment.get("caption_translations")
        if not isinstance(translations, Mapping):
            continue
        text = str(translations.get(language) or "").strip()
        if not text:
            continue
        start, end = float(segment.get("start_sec") or 0.0), float(segment.get("end_sec") or 0.0)
        if end <= start:
            continue
        lines.append(
            DubbingLine(
                segment_id=str(segment.get("segment_id") or ""),
                text=text,
                target_duration_sec=end - start,
            )
        )
    return lines


def plan_dubbing_fit(*, actual_duration_sec: float, target_duration_sec: float) -> DubbingFit:
    """장면 길이에 맞추려면 속도를 얼마로 해야 하는지, 아예 못 맞추는지.

    파일을 건드리지 않고 숫자만 낸다 -- 판단과 실행을 나눠 두면 "왜 이 장면이
    빠졌는지"를 소리를 만들어 보지 않고도 시험할 수 있다.
    """
    if target_duration_sec <= 0:
        return DubbingFit(False, target_duration_sec, actual_duration_sec, 1.0, reason="target_not_positive")
    if actual_duration_sec <= 0:
        return DubbingFit(False, target_duration_sec, actual_duration_sec, 1.0, reason="silent_audio")
    if abs(actual_duration_sec - target_duration_sec) <= DUBBING_EXACT_TOLERANCE_SEC:
        return DubbingFit(True, target_duration_sec, actual_duration_sec, 1.0)
    if actual_duration_sec < target_duration_sec:
        # 말이 짧다. **늘리지 않는다** -- 말이 끝나고 조용해지면 된다.
        if actual_duration_sec < target_duration_sec * DUBBING_MIN_FILL_RATIO:
            return DubbingFit(
                False, target_duration_sec, actual_duration_sec, 1.0, reason="too_short_to_fill"
            )
        return DubbingFit(
            True, target_duration_sec, actual_duration_sec, 1.0,
            pad_sec=target_duration_sec - actual_duration_sec,
        )
    # 말이 길다. 자연스러운 만큼만 빠르게 해서 맞춘다.
    speed = actual_duration_sec / target_duration_sec
    if speed > DUBBING_MAX_SPEED:
        return DubbingFit(False, target_duration_sec, actual_duration_sec, speed, reason="too_long_to_fit")
    return DubbingFit(True, target_duration_sec, actual_duration_sec, speed)


def apply_dubbing_fit(
    *, source: Path, destination: Path, fit: DubbingFit, ffmpeg_binary: str = "ffmpeg"
) -> None:
    """빠르게 하거나 뒤를 조용히 채워서 장면 길이에 딱 맞춘다.

    속도는 `atempo`로만 바꾼다 -- `asetrate`로 바꾸면 **목소리가 다람쥐가 된다.**
    클립 배속에서 `음조 유지`를 기본값으로 둔 것과 같은 이유고, 더빙에서는 아예
    고를 것도 아니다.

    길이는 마지막에 `-t`로 한 번 더 못박는다. `apad`는 무한히 채우므로 자를 곳을
    말해 주지 않으면 끝나지 않는다.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    filters = []
    if fit.speed != 1.0:
        filters.append(f"atempo={fit.speed:.6f}")
    if fit.pad_sec > 0:
        filters.append("apad")
    command = [ffmpeg_binary, "-y", "-loglevel", "error", "-i", str(source)]
    if filters:
        command += ["-filter:a", ",".join(filters)]
    command += ["-t", f"{fit.target_duration_sec:.6f}", str(destination)]
    result = subprocess.run(command, capture_output=True, text=True, timeout=300)
    if result.returncode != 0 or not destination.exists():
        raise RuntimeError(f"dubbing_fit_failed: {result.stderr.strip()[:400]}")


def unfitted_scene_message(fits: Sequence[tuple[str, DubbingFit]]) -> str | None:
    """못 맞춘 장면을 창작자 말로 알린다. 전부 맞았으면 None.

    개수만 말하지 않고 **왜**를 나눠 말한다. "너무 길어서"와 "너무 짧아서"는
    창작자가 할 일이 다르다 -- 앞은 번역을 줄이는 것이고 뒤는 늘리는 것이다.
    """
    too_long = [segment_id for segment_id, fit in fits if fit.reason == "too_long_to_fit"]
    too_short = [segment_id for segment_id, fit in fits if fit.reason == "too_short_to_fill"]
    parts = []
    if too_long:
        parts.append(f"{len(too_long)}개 장면은 옮긴 말이 길어서 넣지 못했어요")
    if too_short:
        parts.append(f"{len(too_short)}개 장면은 옮긴 말이 짧아서 넣지 못했어요")
    if not parts:
        return None
    return " · ".join(parts) + ". 그 장면은 원래 목소리가 그대로 남아 있어요."
