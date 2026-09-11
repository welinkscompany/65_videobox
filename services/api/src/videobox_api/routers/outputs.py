from __future__ import annotations

import re
import threading
from urllib.parse import quote

from fastapi import APIRouter, Request, status
from fastapi.responses import FileResponse

from videobox_core_engine.audio_export import extract_audio_only
from videobox_api.content_delivery import deliver_file
from videobox_api.errors import _http_error
from videobox_api.models import (
    CapCutHandoffDiagnosticsResponse,
    CapCutDraftExportArtifactResponse,
    CapCutDraftHandoffResponse,
    CapCutDraftExportJobResponse,
    ExportArtifactResponse,
    ExportJobResponse,
    FinalRenderArtifactResponse,
    FinalRenderJobResponse,
    FinalRenderVerdictRequest,
    OutputJobRequest,
    VariantRenderBatchResponse,
    VariantRenderItemResponse,
    VariantRenderRequest,
    ExactPreviewRequestBody,
    ExactPreviewResponse,
    PreviewArtifactResponse,
    PreviewJobResponse,
    ProviderTraceAuditEntryResponse,
    ProviderTraceAuditResponse,
    ProviderTraceAuditSummaryResponse,
    StartJobResponse,
    SubtitleArtifactResponse,
    SubtitleJobResponse,
)
from videobox_api.orchestration import ApiOrchestrator

# 경로 구분자(`/`, `\`)·따옴표·제어문자(줄바꿈 포함)를 거른다. 프로젝트 이름은
# 사용자가 짓는 값이라 그대로 헤더에 실으면 HTTP 응답 분할(줄바꿈으로 다른
# 헤더를 끼워 넣는 공격)이나 Windows 금지 문자 문제로 이어질 수 있다.
_UNSAFE_DOWNLOAD_NAME_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f\x7f]')

# 밑동 길이 상한(final-fix-report.md 발견 3, 감사 실측). 한글 한 글자는
# percent-encoding을 거치면 `%EA%B0%80`처럼 9글자로 불어난다 -- 300자 이름이
# 2,753자 헤더를 만들고, 약 430자부터 nginx 기본 `proxy_buffer_size`(4k)를
# 넘겨 재생·내려받기가 함께 502로 죽는다(같은 주소를 <video>가 재생에도
# 쓴다). `CreateProjectRequest.name`에 `max_length=200`을 뒀지만(같은 커밋),
# 그건 새로 만드는 프로젝트만 막는다 -- `bootstrap_project`를 직접 부르는
# 경로(마이그레이션 등)는 Pydantic 검증을 안 거치므로, 실제로 헤더에 싣는
# 이 자리에서도 다듬는다. 100자면 전부 3바이트 한글이어도 인코딩 후
# 900자 안팎이라 4096바이트에 넉넉한 여유가 남는다.
_DOWNLOAD_STEM_MAX_CHARS = 100


def _sanitize_download_stem(raw_name: str) -> str:
    """내려받기 파일 이름 밑동을 안전하게 다듬는다. 위험한 글자를 지운 뒤
    앞뒤 공백·마침표를 정리하고(Windows는 마침표로 끝나는 이름을 못 만든다)
    길이를 자른다.

    **길이는 반드시 percent-encoding *전에* 자른다.** 이미 인코딩한
    문자열(`%EA%B0%80` 같은 조각)을 문자 수로 자르면 한 글자를 나타내는
    `%XX` 조각 중간이 끊길 수 있다. 여기서는 아직 원문 문자열이고, 파이썬
    str 슬라이싱은 유니코드 코드 포인트 경계에서만 자르므로(서로게이트 쌍도
    파이썬 3 str은 코드 포인트 하나로 다룬다) 이 순서면 안전하다."""
    cleaned = _UNSAFE_DOWNLOAD_NAME_CHARS.sub("", raw_name).strip(" .")
    return cleaned[:_DOWNLOAD_STEM_MAX_CHARS]


def _final_render_content_disposition(*, project_name: str, fallback: str, suffix: str) -> str:
    """완성본 내려받기 이름을 만든다.

    `job_id`(UUID)만으로는 여러 번 받았을 때 어느 영상인지 구분이 안 돼서
    프로젝트 이름을 쓴다. 헤더 값은 latin-1로만 실을 수 있어 한글 이름을 그대로
    넣으면 서버가 죽는다 -- 그래서 옛 브라우저용 ASCII `filename=` 대체 이름과
    RFC 5987 `filename*=UTF-8''...`(퍼센트 인코딩) 둘 다 싣는다. 최신 브라우저는
    후자를 읽어 한글 이름 그대로 받고, 옛 브라우저는 ASCII 대체 이름을 받는다.
    """
    stem = _sanitize_download_stem(project_name)
    utf8_name = f"{stem}{suffix}" if stem else f"{fallback}{suffix}"
    ascii_stem = stem.encode("ascii", "ignore").decode("ascii").strip(" .")
    ascii_name = f"{ascii_stem}{suffix}" if ascii_stem else f"{fallback}{suffix}"
    return f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{quote(utf8_name, safe="")}'


def build_outputs_router(orchestrator: ApiOrchestrator) -> APIRouter:
    router = APIRouter()

    @router.post("/api/projects/{project_id}/editing-sessions/{session_id}/exact-preview", status_code=status.HTTP_202_ACCEPTED)
    def start_exact_preview(project_id: str, session_id: str, payload: ExactPreviewRequestBody) -> ExactPreviewResponse:
        try:
            result = orchestrator.start_exact_preview(
                project_id=project_id, session_id=session_id, expected_revision=payload.expected_revision,
                start_sec=payload.start_sec, end_sec=payload.end_sec,
            )
            threading.Thread(
                target=orchestrator.run_exact_preview,
                kwargs={"project_id": project_id, "generation_id": result["generation_id"]}, daemon=True,
            ).start()
        except Exception as exc:
            raise _http_error(exc) from exc
        return ExactPreviewResponse(**result)

    @router.get("/api/projects/{project_id}/exact-previews/{generation_id}")
    def get_exact_preview(project_id: str, generation_id: str) -> ExactPreviewResponse:
        try:
            return ExactPreviewResponse(**orchestrator.get_exact_preview_status(
                project_id=project_id, generation_id=generation_id
            ))
        except Exception as exc:
            raise _http_error(exc) from exc

    @router.get("/api/projects/{project_id}/exact-previews/{generation_id}/content")
    def get_exact_preview_content(project_id: str, generation_id: str, request: Request):
        try:
            return deliver_file(
                request=request,
                path=orchestrator.get_exact_preview_content_path(project_id=project_id, generation_id=generation_id),
                media_type="video/mp4",
            )
        except Exception as exc:
            raise _http_error(exc) from exc

    @router.get("/api/capcut/handoff-diagnostics")
    def get_capcut_handoff_diagnostics() -> CapCutHandoffDiagnosticsResponse:
        try:
            diagnostics = orchestrator.get_capcut_handoff_diagnostics()
        except Exception as exc:
            raise _http_error(exc) from exc
        return CapCutHandoffDiagnosticsResponse(**diagnostics)

    @router.post("/api/projects/{project_id}/jobs/subtitle-render", status_code=status.HTTP_202_ACCEPTED)
    def start_subtitle_render(project_id: str, payload: OutputJobRequest) -> StartJobResponse:
        try:
            result = orchestrator.start_subtitle_render(
                project_id=project_id,
                timeline_job_id=payload.timeline_job_id,
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        return StartJobResponse(**result)

    @router.get("/api/projects/{project_id}/subtitles/{job_id}")
    def get_subtitle_result(project_id: str, job_id: str) -> SubtitleJobResponse:
        try:
            result = orchestrator.get_subtitle_result(project_id=project_id, job_id=job_id)
            result["subtitle"] = orchestrator.pipeline.store.get_subtitle_run(project_id=project_id, subtitle_id=result["subtitle"]["subtitle_id"])
        except Exception as exc:
            raise _http_error(exc) from exc
        return SubtitleJobResponse(
            job_id=result["job_id"],
            status=result["status"],
            subtitle=SubtitleArtifactResponse(**result["subtitle"]),
        )

    @router.get("/api/projects/{project_id}/subtitles/{job_id}/content")
    def get_subtitle_content(project_id: str, job_id: str):
        """진짜 내려받는 `.srt` 파일 -- 위 엔드포인트는 JSON만 준다(owner 요청 2026-08-28).

        `.srt` 파일 자체는 이미 `save_subtitle_run`이 디스크에 써 두고 있었다 --
        내려받는 문(엔드포인트)이 없었을 뿐이다. `deliver_file` 대신 `FileResponse`를
        직접 쓰는 건 파일명을 지정하기 위해서다 -- `deliver_file`은 텍스트류를
        인라인 대상에 안 넣어서 `download`라는 이름 없는 파일로 받게 된다."""
        try:
            result = orchestrator.get_subtitle_result(project_id=project_id, job_id=job_id)
            if str(result.get("status")) != "succeeded":
                raise KeyError("subtitle_not_ready")
            path = orchestrator.store.resolve_storage_uri(
                project_id=project_id, storage_uri=str(result["subtitle"]["file_uri"])
            )
            if not path.is_file():
                raise KeyError("subtitle_content_missing")
        except Exception as exc:
            raise _http_error(exc) from exc
        return FileResponse(path, media_type="application/x-subrip", filename="subtitle.srt")

    @router.post("/api/projects/{project_id}/jobs/preview-render", status_code=status.HTTP_202_ACCEPTED)
    def start_preview_render(project_id: str, payload: OutputJobRequest) -> StartJobResponse:
        try:
            result = orchestrator.start_preview_render(
                project_id=project_id,
                timeline_job_id=payload.timeline_job_id,
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        return StartJobResponse(**result)

    @router.get("/api/projects/{project_id}/previews/{job_id}")
    def get_preview_result(project_id: str, job_id: str) -> PreviewJobResponse:
        try:
            result = orchestrator.get_preview_result(project_id=project_id, job_id=job_id)
            result["preview"] = orchestrator.pipeline.store.get_preview_run(project_id=project_id, preview_id=result["preview"]["preview_id"])
        except Exception as exc:
            raise _http_error(exc) from exc
        return PreviewJobResponse(
            job_id=result["job_id"],
            status=result["status"],
            preview=PreviewArtifactResponse(**result["preview"]),
        )

    @router.post("/api/projects/{project_id}/jobs/capcut-export", status_code=status.HTTP_202_ACCEPTED)
    def start_capcut_export(project_id: str, payload: OutputJobRequest) -> StartJobResponse:
        try:
            result = orchestrator.start_capcut_export(
                project_id=project_id,
                timeline_job_id=payload.timeline_job_id,
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        return StartJobResponse(**result)

    @router.get("/api/projects/{project_id}/exports/{job_id}")
    def get_export_result(project_id: str, job_id: str) -> ExportJobResponse:
        try:
            result = orchestrator.get_capcut_export_result(project_id=project_id, job_id=job_id)
            result["export"] = orchestrator.pipeline.store.get_export_run(project_id=project_id, export_id=result["export"]["export_id"])
        except Exception as exc:
            raise _http_error(exc) from exc
        return ExportJobResponse(
            job_id=result["job_id"],
            status=result["status"],
            export=ExportArtifactResponse(**result["export"]),
        )

    @router.post("/api/projects/{project_id}/jobs/final-render", status_code=status.HTTP_202_ACCEPTED)
    def start_final_render(project_id: str, payload: OutputJobRequest) -> StartJobResponse:
        try:
            orchestrator.assert_timeline_output_allowed(project_id=project_id, timeline_job_id=payload.timeline_job_id)
            result = orchestrator.start_final_render_job(
                project_id=project_id,
                timeline_job_id=payload.timeline_job_id,
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        if result.pop("should_start", True):
            worker = threading.Thread(
                target=orchestrator.run_final_render_job,
                kwargs={
                    "project_id": project_id,
                    "timeline_job_id": payload.timeline_job_id,
                    "job": {"job_id": result["job_id"]},
                },
                daemon=True,
            )
            try:
                worker.start()
            except Exception:
                orchestrator.release_final_render_worker(
                    project_id=project_id,
                    job_id=str(result["job_id"]),
                )
                raise
        return StartJobResponse(**result)

    @router.post("/api/projects/{project_id}/variant-renders", status_code=status.HTTP_202_ACCEPTED)
    def start_variant_renders(project_id: str, payload: VariantRenderRequest) -> VariantRenderBatchResponse:
        try:
            result = orchestrator.start_variant_renders(
                project_id=project_id,
                session_id=payload.session_id,
                variant_ids=payload.variant_ids,
            )
            for item in result.get("items", []):
                if item.get("status") not in {"running", "pending"} or not item.get("should_start"):
                    continue
                worker = threading.Thread(
                    target=orchestrator.run_final_render_job,
                    kwargs={
                        "project_id": project_id,
                        "timeline_job_id": item["timeline_job_id"],
                        "job": {"job_id": item["job_id"]},
                    },
                    daemon=True,
                )
                try:
                    worker.start()
                except Exception:
                    orchestrator.release_final_render_worker(
                        project_id=project_id,
                        job_id=str(item["job_id"]),
                    )
                    item["status"] = "failed"
                    item["error_code"] = "worker_start_failed"
            return VariantRenderBatchResponse(
                project_id=project_id,
                status=("failed" if result.get("items") and all(item.get("status") == "failed" for item in result["items"]) else "accepted"),
                items=[VariantRenderItemResponse(**{key: value for key, value in item.items() if key != "should_start"}) for item in result.get("items", [])],
            )
        except Exception as exc:
            raise _http_error(exc) from exc

    @router.get("/api/projects/{project_id}/final-renders/{job_id}")
    def get_final_render_result(project_id: str, job_id: str) -> FinalRenderJobResponse:
        try:
            result = orchestrator.get_final_render_result(project_id=project_id, job_id=job_id)
            if result.get("render"):
                result["render"] = orchestrator.pipeline.store.get_final_render_export(project_id=project_id, export_id=result["render"]["export_id"])
        except Exception as exc:
            raise _http_error(exc) from exc
        return FinalRenderJobResponse(
            job_id=result["job_id"],
            status=result["status"],
            render=FinalRenderArtifactResponse(**result["render"]) if result["render"] else None,
            error_message=result.get("error_message"),
        )

    @router.post("/api/projects/{project_id}/final-renders/{job_id}/verdict")
    def record_final_render_verdict(
        project_id: str, job_id: str, payload: FinalRenderVerdictRequest
    ) -> FinalRenderJobResponse:
        """완성본을 보고 내린 판단을 그 완성본 옆에 남긴다.

        기계가 잰 지표만으로는 무엇이 좋은 영상인지 배울 수 없다.
        """
        try:
            result = orchestrator.get_final_render_result(project_id=project_id, job_id=job_id)
            if not result.get("render"):
                raise KeyError(f"Final render has no artifact yet: {job_id}")
            orchestrator.pipeline.store.record_final_render_verdict(
                project_id=project_id,
                export_id=result["render"]["export_id"],
                verdict=payload.verdict,
                note=payload.note,
            )
            result["render"] = orchestrator.pipeline.store.get_final_render_export(
                project_id=project_id, export_id=result["render"]["export_id"]
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        return FinalRenderJobResponse(
            job_id=result["job_id"],
            status=result["status"],
            render=FinalRenderArtifactResponse(**result["render"]),
        )

    @router.get("/api/projects/{project_id}/final-renders/{job_id}/content")
    def get_final_render_content(project_id: str, job_id: str, request: Request):
        """Project-scoped browser playback for the composited MP4 artifact.

        같은 주소를 화면의 <video> 태그가 재생에도 쓴다(OutputsPage.tsx:1084)와
        내려받기 단추(`<a download>`, `:1091`)가 함께 쓴다. `video/mp4`는
        `deliver_file`의 인라인 목록에 있어 원래 `Content-Disposition`이 안
        붙었고, 그래서 내려받으면 확장자 없는 `content`라는 이름으로 저장됐다
        (task-3, 2026-09-11).

        `Content-Disposition: attachment`를 얹어도 <video> 재생이 깨지지
        않는다 -- <video>/<img> 같은 하위 자원 요청은 이 헤더를 무시하고 그대로
        재생한다(사양이 아니라 실제 크로미움 브라우저로 실측함: 별도 서버 +
        <video> 태그로 attachment 헤더를 단 mp4가 재생되는 것을 확인). `<a
        download>`만 이 헤더의 파일 이름을 쓴다.
        """
        try:
            result = orchestrator.get_final_render_result(project_id=project_id, job_id=job_id)
            render = result.get("render")
            if not render or str(result.get("status")) != "succeeded":
                raise KeyError("final_render_not_ready")
            path = orchestrator.store.resolve_storage_uri(project_id=project_id, storage_uri=str(render["file_uri"]))
            if not path.is_file(): raise KeyError("final_render_content_missing")
            response = deliver_file(request=request, path=path, media_type="video/mp4")
            project_name = str(orchestrator.store.get_project(project_id=project_id).get("name") or "")
        except Exception as exc:
            raise _http_error(exc) from exc
        response.headers["Content-Disposition"] = _final_render_content_disposition(
            project_name=project_name, fallback=job_id, suffix=".mp4",
        )
        return response

    @router.get("/api/projects/{project_id}/final-renders/{job_id}/audio-content")
    def get_final_render_audio_content(project_id: str, job_id: str, request: Request):
        """완성본에서 오디오 트랙만 뽑아 내려준다 (owner 요청 2026-08-28: "오디오만... 내보내기").

        새 렌더 job을 만들지 않는다 -- 이미 있는 완성본 mp4에서 `ffmpeg -vn`으로
        그때그때 뽑고(`audio_export.py`), 옆에 캐시해 다음 요청은 다시 안 돌린다."""
        try:
            result = orchestrator.get_final_render_result(project_id=project_id, job_id=job_id)
            render = result.get("render")
            if not render or str(result.get("status")) != "succeeded":
                raise KeyError("final_render_not_ready")
            video_path = orchestrator.store.resolve_storage_uri(project_id=project_id, storage_uri=str(render["file_uri"]))
            if not video_path.is_file():
                raise KeyError("final_render_content_missing")
            audio_path = video_path.with_name(f"{video_path.stem}.audio-only.m4a")
            ffmpeg_binary = getattr(orchestrator.pipeline.final_renderer, "ffmpeg_binary", "ffmpeg")
            extract_audio_only(source_video_path=video_path, destination_audio_path=audio_path, ffmpeg_binary=ffmpeg_binary)
        except Exception as exc:
            raise _http_error(exc) from exc
        # 코드리뷰로 발견(2026-08-28): `audio/mp4`는 `deliver_file`의 인라인
        # 목록에 있어서 `Content-Disposition`을 안 붙인다 -- 재생 링크로는
        # 맞는 동작이지만, 이 단추는 "내려받기"라 파일 이름이 있어야 한다.
        # Range 지원(오디오 탐색)은 그대로 두고 이름만 얹는다.
        response = deliver_file(request=request, path=audio_path, media_type="audio/mp4")
        response.headers["Content-Disposition"] = f'attachment; filename="{job_id}.m4a"'
        return response

    @router.post("/api/projects/{project_id}/jobs/capcut-draft-export", status_code=status.HTTP_202_ACCEPTED)
    def start_capcut_draft_export(project_id: str, payload: OutputJobRequest) -> StartJobResponse:
        try:
            orchestrator.assert_timeline_output_allowed(project_id=project_id, timeline_job_id=payload.timeline_job_id)
            result = orchestrator.start_capcut_draft_export_job(
                project_id=project_id,
                timeline_job_id=payload.timeline_job_id,
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        if result.pop("should_start", True):
            worker = threading.Thread(
                target=orchestrator.run_capcut_draft_export_job,
                kwargs={
                    "project_id": project_id,
                    "timeline_job_id": payload.timeline_job_id,
                    "job": {"job_id": result["job_id"]},
                },
                daemon=True,
            )
            try:
                worker.start()
            except Exception:
                orchestrator.release_capcut_draft_export_worker(
                    project_id=project_id,
                    job_id=str(result["job_id"]),
                )
                raise
        return StartJobResponse(**result)

    @router.get("/api/projects/{project_id}/capcut-draft-exports/{job_id}")
    def get_capcut_draft_export_result(project_id: str, job_id: str) -> CapCutDraftExportJobResponse:
        try:
            result = orchestrator.get_capcut_draft_export_result(project_id=project_id, job_id=job_id)
            if result.get("export"):
                result["export"] = orchestrator.pipeline.store.get_capcut_draft_export(project_id=project_id, export_id=result["export"]["export_id"])
        except Exception as exc:
            raise _http_error(exc) from exc
        return CapCutDraftExportJobResponse(
            job_id=result["job_id"],
            status=result["status"],
            export=CapCutDraftExportArtifactResponse(**result["export"]) if result["export"] else None,
            error_message=result.get("error_message"),
        )

    @router.post("/api/projects/{project_id}/capcut-draft-exports/{job_id}/handoff")
    def register_capcut_draft_handoff(project_id: str, job_id: str) -> dict[str, CapCutDraftHandoffResponse]:
        try:
            handoff = orchestrator.register_capcut_draft_handoff(project_id=project_id, job_id=job_id)
        except Exception as exc:
            raise _http_error(exc) from exc
        return {"handoff": CapCutDraftHandoffResponse(**handoff)}

    @router.get("/api/projects/{project_id}/provider-traces")
    def get_provider_trace_audit(
        project_id: str,
        timeline_id: str | None = None,
        include_upstream: bool = False,
        job_type: str | None = None,
        artifact_type: str | None = None,
        final_provider: str | None = None,
        fallback_reason: str | None = None,
    ) -> ProviderTraceAuditResponse:
        try:
            result = orchestrator.get_provider_trace_audit(
                project_id=project_id,
                timeline_id=timeline_id,
                include_upstream=include_upstream,
                job_type=job_type,
                artifact_type=artifact_type,
                final_provider=final_provider,
                fallback_reason=fallback_reason,
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        return ProviderTraceAuditResponse(
            summary=ProviderTraceAuditSummaryResponse(**result["summary"]),
            entries=[ProviderTraceAuditEntryResponse(**item) for item in result["entries"]],
            direct_entries=[
                ProviderTraceAuditEntryResponse(**item) for item in result.get("direct_entries", [])
            ],
            upstream_entries=[
                ProviderTraceAuditEntryResponse(**item) for item in result.get("upstream_entries", [])
            ],
        )

    return router
