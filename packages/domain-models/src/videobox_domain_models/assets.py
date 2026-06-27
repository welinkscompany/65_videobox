from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4


def _utc_now() -> datetime:
    return datetime.now(UTC)


class AssetType(StrEnum):
    NARRATION_AUDIO = "narration_audio"
    RAW_VIDEO = "raw_video"
    BROLL_VIDEO = "broll_video"
    IMAGE = "image"
    BGM = "bgm"
    SFX = "sfx"
    VOICE_SAMPLE_AUDIO = "voice_sample_audio"
    GENERATED_TTS_AUDIO = "generated_tts_audio"


@dataclass(slots=True, frozen=True)
class AssetRecord:
    asset_id: str
    project_id: str
    asset_type: AssetType
    storage_uri: str
    created_at: datetime

    @classmethod
    def create(
        cls,
        *,
        project_id: str,
        asset_type: AssetType,
        storage_uri: str,
        asset_id: str | None = None,
    ) -> "AssetRecord":
        return cls(
            asset_id=asset_id or f"asset_{uuid4().hex[:12]}",
            project_id=project_id,
            asset_type=asset_type,
            storage_uri=storage_uri,
            created_at=_utc_now(),
        )
