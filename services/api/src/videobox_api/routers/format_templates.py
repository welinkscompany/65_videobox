"""마음에 든 영상의 포맷을 저장하고 다음 영상에서 불러 쓴다.

포맷은 프로젝트가 아니라 사용자에게 붙는다 — 다음 영상은 보통 새 프로젝트이고,
프로젝트 안에 넣으면 정작 쓸 때 지난 프로젝트를 뒤져야 한다.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Response, status
from pydantic import BaseModel, Field

from videobox_api.errors import _http_error
from videobox_core_engine.format_template import (
    apply_format_template,
    format_template_from_session,
)
from videobox_storage.format_template_store import FormatTemplateStore


class SaveFormatTemplateRequest(BaseModel):
    name: str = Field(min_length=1)
    session_id: str = Field(min_length=1)


class ApplyFormatTemplateRequest(BaseModel):
    session_id: str = Field(min_length=1)
    expected_revision: int
    # 가로 포맷을 세로 영상에 쓰고 싶을 때가 있다. 이게 없으면 세로 영상이
    # 조용히 가로가 된다.
    keep_output_size: bool = False


def build_format_templates_router(*, orchestrator: Any, template_store: FormatTemplateStore) -> APIRouter:
    router = APIRouter()

    @router.get("/api/format-templates")
    def list_format_templates() -> dict[str, Any]:
        try:
            return {"templates": template_store.list_templates()}
        except Exception as exc:
            raise _http_error(exc) from exc

    @router.post("/api/projects/{project_id}/format-templates", status_code=status.HTTP_201_CREATED)
    def save_format_template(project_id: str, payload: SaveFormatTemplateRequest) -> dict[str, Any]:
        """이 편집본이 '어떻게 보이는지'만 뽑아 이름을 붙여 둔다."""
        try:
            session = orchestrator.pipeline.store.get_editing_session(
                project_id=project_id, session_id=payload.session_id
            )
            # 화면 크기는 편집본이 아니라 타임라인에 있다. 편집본만 보고 만들면
            # 크기가 빈 포맷이 저장된다.
            timeline = None
            timeline_id = str(session.get("timeline_id") or "").strip()
            if timeline_id:
                timeline = orchestrator.pipeline.store.get_timeline_run(
                    project_id=project_id, timeline_id=timeline_id
                )
            template = format_template_from_session(
                name=payload.name, session=session, timeline=timeline
            )
            return template_store.save_template(template=template)
        except Exception as exc:
            raise _http_error(exc) from exc

    @router.post("/api/projects/{project_id}/format-templates/{template_id}/apply")
    def apply_saved_format_template(
        project_id: str, template_id: str, payload: ApplyFormatTemplateRequest
    ) -> dict[str, Any]:
        try:
            template = template_store.get_template(template_id=template_id)
            session = orchestrator.pipeline.store.get_editing_session(
                project_id=project_id, session_id=payload.session_id
            )
            applied = apply_format_template(
                session=session, template=template, keep_output_size=payload.keep_output_size
            )
            # 자막 스타일 변경은 이미 검증된 경로가 있다. 여기서 저장소를 직접
            # 건드리면 같은 규칙이 두 벌이 되고, 그중 하나가 조용히 낡는다.
            updated = orchestrator.update_caption_style(
                project_id=project_id,
                session_id=payload.session_id,
                style=applied.get("caption_style") or {},
                scope="all",
                segment_ids=None,
                expected_revision=payload.expected_revision,
            )
            return {"template_id": template_id, "session": updated}
        except Exception as exc:
            raise _http_error(exc) from exc

    @router.delete(
        "/api/format-templates/{template_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        response_class=Response,
    )
    def delete_format_template(template_id: str) -> Response:
        try:
            template_store.delete_template(template_id=template_id)
        except Exception as exc:
            raise _http_error(exc) from exc
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return router
