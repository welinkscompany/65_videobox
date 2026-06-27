from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4
import re


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or f"project-{uuid4().hex[:8]}"


class ProjectStatus(StrEnum):
    DRAFT = "draft"
    READY = "ready"
    ARCHIVED = "archived"


@dataclass(slots=True, frozen=True)
class ProjectRecord:
    project_id: str
    name: str
    status: ProjectStatus
    root_storage_uri: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def create(cls, name: str, *, project_id: str | None = None) -> "ProjectRecord":
        resolved_project_id = project_id or _slugify(name)
        timestamp = _utc_now()
        return cls(
            project_id=resolved_project_id,
            name=name,
            status=ProjectStatus.DRAFT,
            root_storage_uri=f"local://projects/{resolved_project_id}",
            created_at=timestamp,
            updated_at=timestamp,
        )
