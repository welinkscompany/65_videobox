"""설명 모션 한 편을 만들어 자료실에 넣는다.

차례: 템플릿 고르기 -> 변수 검사 -> 길이·모양 검사 -> 다리에 맡기기 -> 자료실 등록.
검사는 다리에 가기 **전에** 끝낸다(다리도 한 번 더 검사하지만 여기서 한국어 문제 문장을 준다).

자료실 등록이 실패해도 만든 영상은 돌려준다(`InfographicService._ingest`와 같은 이유).
"""

from __future__ import annotations

import logging
import math
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
from typing import Any

from videobox_domain_models.library_assets import LibraryMediaType

from videobox_core_engine.infographic_service import _file_stem
from videobox_core_engine.motion_host_bridge import (
    MotionHostBridge,
    MotionHostBridgeRefused,
    MotionHostBridgeTimedOut,
    MotionHostBridgeUnavailable,
)
from videobox_core_engine.motion_templates import (
    MAX_MOTION_DURATION_SEC,
    MIN_MOTION_DURATION_SEC,
    MOTION_LAYOUTS,
    MotionTemplateUnknown,
    MotionVariablesInvalid,
    motion_default_title,
    parse_motion_variables,
    resolve_motion_template,
)

_LOG = logging.getLogger(__name__)


class MotionUnavailable(RuntimeError):
    """만들지 못했다. `reason`으로 화면이 "고쳐 주세요"와 "다리를 켜 주세요"를 구분한다."""

    def __init__(self, reason: str, detail: str = "", problems: tuple[str, ...] = ()) -> None:
        super().__init__(detail or reason)
        self.reason = reason
        self.detail = detail
        self.problems = problems


@dataclass
class MadeMotion:
    video_bytes: bytes
    template_key: str
    title: str
    duration_sec: float
    layout: str
    format: str
    elapsed_sec: float
    library_asset_id: str | None = None
    library_error: str | None = None


@dataclass(slots=True)
class MotionService:
    bridge: MotionHostBridge | None = None
    library_ingest: Any = None
    _scratch_factory: Any = field(default=tempfile.TemporaryDirectory, repr=False)

    def make(
        self,
        *,
        template_key: str,
        variables: Mapping[str, Any],
        duration_sec: float,
        layout: str = "full",
        title: str | None = None,
    ) -> MadeMotion:
        try:
            resolve_motion_template(template_key)
        except MotionTemplateUnknown as exc:
            raise MotionUnavailable("motion_template_unknown", str(template_key)) from exc
        try:
            parsed = parse_motion_variables(template_key, variables)
        except MotionVariablesInvalid as exc:
            raise MotionUnavailable("motion_variables_invalid", problems=exc.problems) from exc
        if not (
            isinstance(duration_sec, (int, float))
            and math.isfinite(duration_sec)
            and MIN_MOTION_DURATION_SEC <= duration_sec <= MAX_MOTION_DURATION_SEC
        ):
            raise MotionUnavailable(
                "motion_variables_invalid", problems=("길이: 3초에서 30초 사이로 골라 주세요",)
            )
        if layout not in MOTION_LAYOUTS:
            raise MotionUnavailable("motion_variables_invalid", problems=("모양: 다시 골라 주세요",))
        if self.bridge is None:
            # 꺼진 기능과 고장을 나눈다 -- 다시 눌러도 안 되는 것을 "잠시 뒤"라고 하지 않는다.
            raise MotionUnavailable("motion_bridge_not_configured")

        duration = float(duration_sec)
        try:
            clip = self.bridge.render(
                template=template_key,
                variables=parsed.model_dump(mode="json"),
                duration_sec=duration,
                layout=layout,
            )
        except MotionHostBridgeUnavailable as exc:
            raise MotionUnavailable("motion_bridge_not_running", str(exc)) from exc
        except MotionHostBridgeTimedOut as exc:
            raise MotionUnavailable("motion_took_too_long", str(exc)) from exc
        except MotionHostBridgeRefused as exc:
            if exc.status == 409:
                raise MotionUnavailable("motion_busy", str(exc)) from exc
            if exc.status == 503 and exc.error == "motion_engine_not_prepared":
                raise MotionUnavailable("motion_engine_not_prepared", str(exc)) from exc
            if exc.status == 504:
                raise MotionUnavailable("motion_took_too_long", str(exc)) from exc
            raise MotionUnavailable("motion_render_failed", str(exc)) from exc

        final_title = (title or motion_default_title(template_key, parsed)).strip()[:60]
        made = MadeMotion(
            video_bytes=clip.video_bytes,
            template_key=template_key,
            title=final_title,
            duration_sec=duration,
            layout=layout,
            format=clip.format,
            elapsed_sec=clip.elapsed_sec,
        )
        made.library_asset_id, made.library_error = self._ingest(made)
        return made

    def _ingest(self, made: MadeMotion) -> tuple[str | None, str | None]:
        if self.library_ingest is None:
            return None, None
        try:
            with self._scratch_factory(prefix="videobox-motion-") as scratch:
                path = Path(scratch) / f"{_file_stem(made.title)}.{made.format}"
                path.write_bytes(made.video_bytes)
                ingested = self.library_ingest.ingest(
                    media_type=LibraryMediaType.BROLL,
                    source=path,
                    filename=path.name,
                    # 내용으로 열쇠를 만든다 -- 같은 영상을 두 번 넣지 않는다.
                    idempotency_key=f"motion:{sha256(made.video_bytes).hexdigest()}",
                    provenance={
                        "generated_by": "videobox-motion",
                        "source_kind": "generated_motion",
                        "template": made.template_key,
                        "layout": made.layout,
                        "duration_sec": made.duration_sec,
                        "title": made.title,
                        "engine": "hyperframes 0.8.140",
                    },
                )
            return str(ingested["library_asset_id"]), None
        except Exception as exc:  # noqa: BLE001 - 자료실 등록 실패가 만든 영상을 지우면 안 된다
            # 화면에는 클래스 이름만 올리고, 짧은 이유는 로그에만 남긴다.
            _LOG.warning("motion library ingest failed: %s: %s", type(exc).__name__, str(exc)[:200])
            return None, type(exc).__name__


__all__ = ["MadeMotion", "MotionService", "MotionUnavailable"]
