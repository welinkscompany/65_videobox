from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4


def _utc_now() -> datetime:
    return datetime.now(UTC)


class JobType(StrEnum):
    MEDIA_ANALYSIS = "media_analysis"
    INGEST = "ingest"
    TRANSCRIPTION = "transcription"
    SEGMENT_ANALYSIS = "segment_analysis"
    BROLL_RECOMMENDATION = "broll_recommendation"
    MUSIC_RECOMMENDATION = "music_recommendation"
    TIMELINE_BUILD = "timeline_build"
    PARTIAL_REGENERATION = "partial_regeneration"
    SUBTITLE_RENDER = "subtitle_render"
    PREVIEW_RENDER = "preview_render"
    CAPCUT_EXPORT = "capcut_export"
    FINAL_RENDER = "final_render"
    CAPCUT_DRAFT_EXPORT = "capcut_draft_export"


class JobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(slots=True, frozen=True)
class JobRecord:
    job_id: str
    project_id: str
    job_type: JobType
    status: JobStatus
    input_ref: str | None
    output_ref: str | None
    error_message: str | None
    started_at: datetime | None
    finished_at: datetime | None

    @classmethod
    def create(
        cls,
        *,
        project_id: str,
        job_type: JobType,
        input_ref: str | None = None,
        status: JobStatus = JobStatus.PENDING,
        job_id: str | None = None,
    ) -> "JobRecord":
        started_at = _utc_now() if status is not JobStatus.PENDING else None
        finished_at = started_at if status in {JobStatus.SUCCEEDED, JobStatus.FAILED} else None
        return cls(
            job_id=job_id or f"job_{uuid4().hex[:12]}",
            project_id=project_id,
            job_type=job_type,
            status=status,
            input_ref=input_ref,
            output_ref=None,
            error_message=None,
            started_at=started_at,
            finished_at=finished_at,
        )
