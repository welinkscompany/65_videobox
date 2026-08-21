from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4
import re


def _utc_now() -> datetime:
    return datetime.now(UTC)


# 이름에서 뽑아 쓰는 부분의 최대 길이. 프로젝트 폴더 밑으로
# `analysis/partial_regenerations` 같은 깊은 경로가 더 붙기 때문에,
# 긴 제목 하나가 경로 길이를 다 먹지 않도록 여기서 자른다.
_MAX_NAME_STEM_LENGTH = 40


def _name_stem(value: str) -> str:
    """이름에서 경로에 그대로 쓸 수 있는 부분만 남긴다.

    한글은 여기서 사라진다. 식별자는 저장 경로이자 DB 키라서 글자 범위를 넓히면
    nginx·ffmpeg 인자·CapCut draft·Windows 경로까지 한꺼번에 영향을 받는다.
    owner에게 보이는 한국어 제목은 `name` 칸에 그대로 남으므로, 사람이 읽을
    이름과 기계가 쓸 주소를 분리해 둔다.
    """
    stem = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    return stem[:_MAX_NAME_STEM_LENGTH].strip("-")


def _new_project_id(name: str) -> str:
    """이름에서 뽑은 부분 뒤에 짧은 무작위를 **항상** 붙인다.

    붙이지 않던 시절에는 이름이 다른 프로젝트가 같은 식별자를 받았다. 한글이
    전부 걸러지는 탓에 `테스트 A`·`샘플 A`·`관리화면 점검 A`가 모두 `a`가 됐고,
    영문 이름도 같은 제목을 두 번 쓰면 그대로 겹쳤다. 겹치면 거절되는 게 아니라
    **조용히 섞였다** — 폴더는 재사용되고 `projects` 행은 덮어써져서, 먼저 있던
    프로젝트가 목록에서 사라지고 그 안의 촬영본이 새 프로젝트 것이 됐다.

    디스크를 먼저 뒤져 빈 이름을 고르는 방법도 있지만 그러지 않았다. 확인과
    생성 사이가 벌어져 같은 순간에 들어온 두 요청은 여전히 겹치고, 식별자를
    만드는 일이 저장소 상태를 알아야 하는 일로 커진다. 무작위를 항상 붙이면
    옛 프로젝트가 쓰던 짧은 식별자(`a`)와도 저절로 어긋난다.
    """
    stem = _name_stem(name) or "project"
    return f"{stem}-{uuid4().hex[:8]}"


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
        # 명시된 `project_id`는 그대로 쓴다. 이미 만들어진 프로젝트를 다시 읽어
        # 올리는 경로가 여기를 지나므로, 옛 식별자를 새로 만들어 버리면 안 된다.
        resolved_project_id = project_id or _new_project_id(name)
        timestamp = _utc_now()
        return cls(
            project_id=resolved_project_id,
            name=name,
            status=ProjectStatus.DRAFT,
            root_storage_uri=f"local://projects/{resolved_project_id}",
            created_at=timestamp,
            updated_at=timestamp,
        )
