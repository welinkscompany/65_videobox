from __future__ import annotations

from math import isfinite
from typing import Any

from videobox_core_engine.filters import normalize_filter


def _finite_control_number(value: object) -> float:
    try:
        parsed = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ValueError("media_controls_invalid_number") from exc
    if not isfinite(parsed):
        raise ValueError("media_controls_invalid_number")
    return parsed


# 화면 입력이 허용하는 범위와 **같은** 경계다(inspector: 속도 0.25~4, 소리 0~2).
# 여기를 넓게 열어 두면 화면에서 만들 수 없는 값이 저장되고, 그 값은 결국
# 렌더러에서 터진다 -- 거절은 사용자 가까운 쪽에서 한 번 더 하는 게 맞다.
SPEED_RANGE = (0.25, 4.0)
VOLUME_RANGE = (0.0, 2.0)
# 변형(캡컷 동영상 탭 `확대·위치·회전`). 위와 같은 이유로 화면 입력과 **같은**
# 경계다. 위치는 화면 크기에 대한 백분율이라 한 화면만큼 밀면 끝이고, 회전은
# 반 바퀴면 양쪽 방향이 다 나온다.
ZOOM_RANGE = (0.5, 4.0)
POSITION_PERCENT_RANGE = (-100.0, 100.0)
ROTATION_DEGREE_RANGE = (-180.0, 180.0)


def _bounded(value: object, bounds: tuple[float, float], label: str) -> float:
    parsed = _finite_control_number(value)
    if not bounds[0] <= parsed <= bounds[1]:
        raise ValueError(f"{label} must be between {bounds[0]} and {bounds[1]}.")
    return parsed


def normalize_media_controls(
    controls: object,
    *,
    media_kind: str,
    duration_sec: float,
) -> dict[str, Any]:
    payload = controls if isinstance(controls, dict) else {}
    if duration_sec <= 0:
        raise ValueError("Media control duration must be positive.")
    if media_kind == "audio":
        gain_db = _finite_control_number(payload.get("gain_db", 0.0))
        fade_in_sec = _finite_control_number(payload.get("fade_in_sec", 0.0))
        fade_out_sec = _finite_control_number(payload.get("fade_out_sec", 0.0))
        if fade_in_sec < 0 or fade_out_sec < 0 or fade_in_sec + fade_out_sec > duration_sec:
            raise ValueError("Audio fade durations must fit within the clip duration.")
        return {
            "gain_db": gain_db,
            "fade_in_sec": fade_in_sec,
            "fade_out_sec": fade_out_sec,
            "ducking": bool(payload.get("ducking", False)),
            # 캡컷 오디오 탭 대조로 들어온 둘(owner 승인 2026-09-01). 캡컷은 이
            # 둘을 클라우드 AI 유료 기능으로 파는데, 우리 쪽은 FFmpeg 필터
            # 하나씩이면 된다 -- `loudnorm`(EBU R128)과 `afftdn`.
            # 기본값 False가 "손대지 않음"이고, 그때 렌더러는 필터를 안 더한다.
            "normalize_loudness": bool(payload.get("normalize_loudness", False)),
            "denoise": bool(payload.get("denoise", False)),
        }
    if media_kind == "broll":
        fit = str(payload.get("fit", "fit")).strip().lower()
        if fit not in {"fit", "crop"}:
            raise ValueError("B-roll fit must be either 'fit' or 'crop'.")
        trim_start_sec = _finite_control_number(payload.get("trim_start_sec", 0.0))
        if trim_start_sec < 0:
            raise ValueError("B-roll trim_start_sec must not be negative.")
        # 장면이 바뀔 때 부드럽게 넘어가기(디졸브). `audio`의 같은 이름은 소리
        # 페이드이고 여기 것은 **화면** 페이드다 -- 종류가 다르므로 이름을 나누지
        # 않는다. 겹쳐 놓은 두 클립에서 위 클립에 걸면 아래가 비쳐 보인다.
        video_fade_in_sec = _finite_control_number(payload.get("fade_in_sec", 0.0))
        video_fade_out_sec = _finite_control_number(payload.get("fade_out_sec", 0.0))
        if video_fade_in_sec < 0 or video_fade_out_sec < 0:
            raise ValueError("B-roll fade durations must not be negative.")
        if video_fade_in_sec + video_fade_out_sec > duration_sec:
            raise ValueError("B-roll fade durations must fit within the clip duration.")
        # 배속과 소리 크기. **예전에는 여기서 조용히 버려졌다** -- inspector에
        # 입력이 있고 저장도 성공하는데 결과가 그대로였다(2026-08-18 확인).
        # 기본값 1.0은 "손대지 않음"이고, 아래 렌더러는 그때 필터를 더하지 않는다.
        speed = _finite_control_number(payload.get("speed", 1.0))
        if not SPEED_RANGE[0] <= speed <= SPEED_RANGE[1]:
            raise ValueError(
                f"B-roll speed must be between {SPEED_RANGE[0]} and {SPEED_RANGE[1]}."
            )
        volume = _finite_control_number(payload.get("volume", 1.0))
        if not VOLUME_RANGE[0] <= volume <= VOLUME_RANGE[1]:
            raise ValueError(
                f"B-roll volume must be between {VOLUME_RANGE[0]} and {VOLUME_RANGE[1]}."
            )
        normalized = {
            "fit": fit,
            "loop": bool(payload.get("loop", True)),
            "pad": bool(payload.get("pad", False)),
            "trim_start_sec": trim_start_sec,
            "preserve_source_audio": bool(payload.get("preserve_source_audio", False)),
            "fade_in_sec": video_fade_in_sec,
            "fade_out_sec": video_fade_out_sec,
            "speed": speed,
            "volume": volume,
            # 배속을 걸 때 목소리 높낮이를 그대로 둘지(캡컷 속도 탭 대조,
            # owner 승인 2026-09-01). **기본값이 True인 이유는 지금까지의
            # 동작이 그것이기 때문이다** -- 렌더러는 처음부터 `atempo`를 써
            # 왔고 그 필터는 높낮이를 안 건드린다. 껐을 때만 새 사슬로 간다.
            # 끄면 빨리 감은 테이프처럼 목소리가 올라가는데, 캡컷에서
            # 스위치를 꺼 본 창작자가 기대하는 소리가 그것이다.
            "preserve_pitch": bool(payload.get("preserve_pitch", True)),
            # 변형(캡컷 동영상 탭 대조, owner 승인 2026-09-01). **키프레임이
            # 아니다** -- 클립 전체에 한 번 걸리는 고정 값이고, 임의 키프레임은
            # 계획서 §2.1이 범위 밖으로 못박은 항목이다(`implementation-plan` §4).
            # 기본값(1.0 / 0 / 0)이 "손대지 않음"이고 그때 렌더러는 사슬을
            # 더하지 않는다 -- 아무것도 안 고른 편집본이 바뀌면 안 된다.
            "zoom": _bounded(payload.get("zoom", 1.0), ZOOM_RANGE, "B-roll zoom"),
            "position_x_percent": _bounded(payload.get("position_x_percent", 0.0), POSITION_PERCENT_RANGE, "B-roll position_x_percent"),
            "position_y_percent": _bounded(payload.get("position_y_percent", 0.0), POSITION_PERCENT_RANGE, "B-roll position_y_percent"),
            "rotation_deg": _bounded(payload.get("rotation_deg", 0.0), ROTATION_DEGREE_RANGE, "B-roll rotation_deg"),
            # 손떨림 보정(캡컷 동영상 탭 대조, owner 승인 2026-09-01).
            # 캡컷은 유료 AI로 파는데 FFmpeg `deshake` 하나면 된다.
            # **`vidstab`이 아니라 `deshake`를 쓴다** -- vidstab이 더 정확하지만
            # 2-pass라 분석 결과 파일을 따로 만들어야 하고, 이 렌더러는 필터
            # 그래프를 한 번에 조립해 ffmpeg 한 번으로 끝내는 구조다. deshake는
            # 단일 패스라 그 구조에 그대로 들어가고 렌더 시간도 안 늘어난다.
            "stabilize": bool(payload.get("stabilize", False)),
        }
        # 색감(`filters.py`). **안 고른 클립에는 칸 자체를 넣지 않는다** --
        # 넣으면 옛 저장분과 모양이 달라지고, 아무것도 안 바뀐 편집본이
        # 바뀐 것처럼 보인다.
        chosen_filter = normalize_filter(payload.get("filter"))
        if chosen_filter is not None:
            normalized["filter"] = chosen_filter
        # Source-window controls come from a selected local asset.  They are
        # distinct from timeline trim and must survive Director apply so both
        # FFmpeg and CapCut read the same original bytes.
        if "in_sec" in payload:
            in_sec = _finite_control_number(payload["in_sec"])
            if in_sec < 0:
                raise ValueError("B-roll in_sec must not be negative.")
            normalized["in_sec"] = in_sec
        if "out_sec" in payload:
            out_sec = _finite_control_number(payload["out_sec"])
            if out_sec <= float(normalized.get("in_sec", 0.0)):
                raise ValueError("B-roll out_sec must be after in_sec.")
            normalized["out_sec"] = out_sec
        return normalized
    raise ValueError(f"Unsupported media control kind: {media_kind}")
