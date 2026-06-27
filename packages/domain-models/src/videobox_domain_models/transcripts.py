from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True, frozen=True)
class TranscriptRecord:
    transcript_id: str
    project_id: str
    source_asset_id: str
    transcript_uri: str
    transcript_text: str
    provider_name: str
    created_at: datetime

    @classmethod
    def create(
        cls,
        *,
        project_id: str,
        source_asset_id: str,
        transcript_uri: str,
        transcript_text: str,
        provider_name: str,
        transcript_id: str | None = None,
    ) -> "TranscriptRecord":
        return cls(
            transcript_id=transcript_id or f"transcript_{uuid4().hex[:12]}",
            project_id=project_id,
            source_asset_id=source_asset_id,
            transcript_uri=transcript_uri,
            transcript_text=transcript_text,
            provider_name=provider_name,
            created_at=_utc_now(),
        )
