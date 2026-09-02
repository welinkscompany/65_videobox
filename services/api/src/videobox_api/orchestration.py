from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
from urllib.request import urlopen
from uuid import uuid4

from videobox_core_engine.caption_translation_service import CaptionTranslationService
from videobox_core_engine.local_only_runtime import (
    LocalOnlyStructuredGenerationError,
    LocalOnlyStructuredRuntime,
)
from videobox_core_engine.settings import LocalOpenAICompatibleRuntimeConfig
from videobox_provider_interfaces.local_qwen import LocalQwenHTTPTransport, LocalQwenStructuredProvider
from videobox_provider_interfaces.llm import (
    LLMProviderError,
    LLMTaskType,
    StructuredLLMProvider,
    StructuredLLMResponse,
)
from videobox_core_engine.audio_export import extract_audio_only
from videobox_core_engine.local_pipeline import LocalPipelineRunner
from videobox_core_engine.narration_retake_detection import detect_retake_candidates
from videobox_core_engine.reference_style_analysis import analyze_color, analyze_pacing
from videobox_core_engine.youtube_import import YoutubeImportError, download_youtube_video, is_youtube_url
from videobox_core_engine.creation_interview import CreationInterviewRuntime, DeterministicCreationInterviewRuntime
from videobox_domain_models.assets import AssetType
from videobox_domain_models.jobs import JobStatus, JobType
from videobox_storage.local_project_store import LocalProjectStore

BROLL_VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm"}


@dataclass(slots=True, frozen=True)
class RegisteredAsset:
    asset_id: str
    asset_type: str
    storage_uri: str


@dataclass(slots=True)
class LocalOnlyRuntimeService:
    local_provider: StructuredLLMProvider
    local_runtime_config: LocalOpenAICompatibleRuntimeConfig = field(
        default_factory=LocalOpenAICompatibleRuntimeConfig
    )

    def generate_structured(
        self,
        *,
        project_id: str,
        task_type: LLMTaskType,
        prompt: str,
        response_schema: dict[str, Any],
        now: datetime | None = None,
    ) -> StructuredLLMResponse:
        del now
        try:
            return LocalOnlyStructuredRuntime(
                local_provider=self.local_provider,
                local_runtime_config=self.local_runtime_config,
            ).generate(
                project_id=project_id,
                task_type=task_type,
                prompt=prompt,
                response_schema=response_schema,
            )
        except LocalOnlyStructuredGenerationError as exc:
            raise LocalOnlyRuntimeProviderError(
                provider_name=exc.provider_name,
                message=exc.message,
                retryable=False,
                error_code=exc.error_code,
                provider_trace=exc.provider_trace,
            ) from exc


@dataclass(slots=True, frozen=True)
class LocalOnlyRuntimeProviderError(LLMProviderError):
    provider_trace: dict[str, Any] = field(default_factory=dict)


def build_local_qwen_structured_provider(
    *,
    local_runtime_config: LocalOpenAICompatibleRuntimeConfig,
    local_http_client: Callable[..., Any],
) -> LocalQwenStructuredProvider:
    transport = LocalQwenHTTPTransport(
        base_url=local_runtime_config.base_url,
        timeout_seconds=local_runtime_config.timeout_seconds,
        http_client=local_http_client,
    )
    return LocalQwenStructuredProvider(transport=transport)


def build_local_only_runtime_service(
    *,
    store: LocalProjectStore,
    local_runtime_config: LocalOpenAICompatibleRuntimeConfig,
    local_http_client: Callable[..., Any] = urlopen,
) -> LocalOnlyRuntimeService:
    del store
    return LocalOnlyRuntimeService(
        local_provider=build_local_qwen_structured_provider(
            local_runtime_config=local_runtime_config,
            local_http_client=local_http_client,
        ),
        local_runtime_config=local_runtime_config,
    )


class ApiOrchestrator:
    def __init__(
        self, store: LocalProjectStore, *, pipeline: LocalPipelineRunner | None = None,
        creation_interview_runtime: CreationInterviewRuntime | None = None,
    ) -> None:
        self.store = store
        self.pipeline = pipeline or LocalPipelineRunner(store)
        # This is intentionally a provider-neutral local planning seam. No
        # LLM/provider transport is constructed for an interview.
        self.creation_interview_runtime = creation_interview_runtime or DeterministicCreationInterviewRuntime()
        # 유튜브 학습 작업 상태(owner 결정 2026-08-29: "비동기로 바꾼다").
        # 다운로드·오디오 추출·컷/색감 분석을 합치면 nginx 프록시의 330초
        # 타임아웃보다 오래 걸릴 수 있어 요청 하나 안에서 동기로 끝내지 않는다.
        # **메모리에만 있다** -- 이 작업은 재시도해도 비용이 크지 않은 일회성
        # 가져오기라, 재시작 사이 생존이 필요한 진짜 작업 큐(`MediaAnalysisService`가
        # 쓰는 SQLite claim 방식)를 새로 만들 만큼 값이 크지 않다고 판단했다.
        # 서버가 재시작되면 진행 중이던 작업은 사라지고 owner가 다시 시도해야
        # 한다 -- 그 트레이드오프를 감수한다.
        self._youtube_import_jobs: dict[str, dict[str, Any]] = {}
        self._youtube_import_jobs_lock = threading.Lock()

    def create_creation_brief(self, **kwargs: Any) -> dict[str, Any]:
        return self.pipeline.create_creation_brief(runtime=self.creation_interview_runtime, **kwargs)

    def start_draft_readiness(self, **kwargs: Any) -> dict[str, Any]:
        # Readiness is deterministic local storage planning only; it never
        # constructs a provider transport or editing-session mutation path.
        return self.store.start_draft_readiness(**kwargs)

    def materialize_atomic_draft_bundle(self, **kwargs: Any) -> dict[str, Any]:
        # Approval is represented only by this explicit request; preparation
        # paths never call this method or mutate editing truth.
        return self.store.materialize_atomic_draft_bundle(**kwargs)

    def assert_timeline_output_allowed(self, *, project_id: str, timeline_job_id: str) -> None:
        """Fail closed before queueing output for an in-app-only gap draft."""
        self.pipeline.assert_timeline_output_allowed(project_id=project_id, timeline_job_id=timeline_job_id)

    def register_narration_audio(self, *, project_id: str, source_path: Path) -> RegisteredAsset:
        asset = self.pipeline.register_narration_asset(
            project_id=project_id,
            source_path=source_path,
        )
        return RegisteredAsset(
            asset_id=asset["asset_id"],
            asset_type=asset["asset_type"],
            storage_uri=asset["storage_uri"],
        )

    def register_script_document(self, *, project_id: str, source_path: Path) -> RegisteredAsset:
        asset = self.pipeline.register_script_asset(
            project_id=project_id,
            source_path=source_path,
        )
        return RegisteredAsset(
            asset_id=asset["asset_id"],
            asset_type=asset["asset_type"],
            storage_uri=asset["storage_uri"],
        )

    def register_broll_asset(
        self,
        *,
        project_id: str,
        source_path: Path,
        title: str | None,
        tags: list[str],
    ) -> RegisteredAsset:
        asset = self.pipeline.register_broll_asset(
            project_id=project_id,
            source_path=source_path,
            title=title,
            tags=tags,
        )
        return RegisteredAsset(
            asset_id=asset["asset_id"],
            asset_type=asset["asset_type"],
            storage_uri=asset["storage_uri"],
        )

    def list_broll_assets(self, *, project_id: str) -> list[dict[str, Any]]:
        return self.store.list_assets(project_id=project_id, asset_type=AssetType.BROLL_VIDEO)

    def list_voice_sample_assets(self, *, project_id: str) -> list[dict[str, Any]]:
        return self.store.list_assets(project_id=project_id, asset_type=AssetType.VOICE_SAMPLE_AUDIO)

    def list_narration_audio_assets(self, *, project_id: str) -> list[dict[str, Any]]:
        return self.store.list_assets(project_id=project_id, asset_type=AssetType.NARRATION_AUDIO)

    def register_sfx_asset(self, *, project_id: str, source_path: Path) -> RegisteredAsset:
        asset = self.pipeline.register_sfx_asset(project_id=project_id, source_path=source_path)
        return RegisteredAsset(asset_id=asset["asset_id"], asset_type=asset["asset_type"], storage_uri=asset["storage_uri"])

    def register_broll_assets_batch(
        self,
        *,
        project_id: str,
        source_paths: list[Path],
        source_directory: Path | None,
        tags: list[str],
        title_by_source_path: dict[str, str],
        recursive: bool = False,
    ) -> dict[str, list[dict[str, Any]]]:
        paths, failures = self._resolve_broll_batch_paths(
            source_paths=source_paths,
            source_directory=source_directory, recursive=recursive,
        )
        registered_asset_ids: list[str] = []
        source_by_asset_id: dict[str, str] = {}
        for source_path in paths:
            try:
                asset = self.pipeline.register_broll_asset(
                    project_id=project_id,
                    source_path=source_path,
                    title=title_by_source_path.get(str(source_path)) or source_path.stem,
                    tags=tags,
                )
            except Exception as exc:
                # A bad file must not roll back assets already accepted in this batch.
                failures.append({"source_path": str(source_path.resolve()), "reason": str(exc)})
                continue
            registered_asset_ids.append(asset["asset_id"])
            source_by_asset_id[asset["asset_id"]] = str(source_path.resolve())
        assets_by_id = {
            asset["asset_id"]: asset
            for asset in self.store.list_assets(project_id=project_id, asset_type=AssetType.BROLL_VIDEO)
        }
        return {"assets": [{**assets_by_id[asset_id], "source_path": source_by_asset_id.get(asset_id)} for asset_id in registered_asset_ids if asset_id in assets_by_id], "failures": failures}

    def _resolve_broll_batch_paths(
        self,
        *,
        source_paths: list[Path],
        source_directory: Path | None, recursive: bool = False,
    ) -> tuple[list[Path], list[dict[str, str]]]:
        paths: list[Path] = []
        if source_directory is not None:
            if not source_directory.exists():
                raise ValueError(f"B-roll source directory does not exist: {source_directory}")
            if not source_directory.is_dir():
                raise ValueError(f"B-roll source directory is not a directory: {source_directory}")
            iterator = source_directory.rglob("*") if recursive else source_directory.iterdir()
            paths.extend(sorted((candidate for candidate in iterator if candidate.is_file() and candidate.suffix.lower() in BROLL_VIDEO_EXTENSIONS), key=lambda path: str(path.resolve()).lower()))
        paths.extend(source_paths)
        if not paths:
            raise ValueError("No B-roll video files found for batch import.")
        unique_paths: list[Path] = []
        failures: list[dict[str, str]] = []
        seen: set[Path] = set()
        seen_content: set[str] = set()
        for path in paths:
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            from videobox_storage.local_project_store import sha256_file
            if not resolved.exists() or not resolved.is_file():
                failures.append({"source_path": str(resolved), "reason": "source file does not exist"})
                continue
            if resolved.suffix.lower() not in BROLL_VIDEO_EXTENSIONS:
                failures.append({"source_path": str(resolved), "reason": "unsupported video extension"})
                continue
            if resolved.exists() and resolved.is_file():
                digest = sha256_file(resolved)
                if digest in seen_content:
                    continue
                seen_content.add(digest)
            unique_paths.append(resolved)
        if not unique_paths and not failures:
            raise ValueError("No B-roll video files found for batch import.")
        return unique_paths, failures

    def register_raw_video_asset(self, *, project_id: str, source_path: Path) -> RegisteredAsset:
        asset = self.pipeline.register_raw_video_asset(
            project_id=project_id,
            source_path=source_path,
        )
        return RegisteredAsset(
            asset_id=asset["asset_id"],
            asset_type=asset["asset_type"],
            storage_uri=asset["storage_uri"],
        )

    def register_voice_sample_asset(self, *, project_id: str, source_path: Path) -> RegisteredAsset:
        asset = self.pipeline.register_voice_sample_asset(
            project_id=project_id,
            source_path=source_path,
        )
        return RegisteredAsset(
            asset_id=asset["asset_id"],
            asset_type=asset["asset_type"],
            storage_uri=asset["storage_uri"],
        )

    def start_youtube_reference_style_import(self, *, project_id: str, url: str) -> dict[str, Any]:
        """유튜브 학습을 **바로 시작만** 하고 돌아온다(owner 결정 2026-08-29).

        실제 다운로드·분석은 `run_youtube_reference_style_import_job`이 백그라운드에서
        한다 -- 그래야 nginx 프록시 330초 타임아웃보다 오래 걸리는 긴 영상도
        요청 자체는 즉시 끝난다. 주소 형식만 여기서 먼저 확인해 owner가 바로
        고칠 수 있는 실수(유튜브 링크가 아님)는 기다리게 하지 않는다.
        """
        if not is_youtube_url(url):
            raise YoutubeImportError("youtube_url_invalid")
        job_id = uuid4().hex
        with self._youtube_import_jobs_lock:
            self._youtube_import_jobs[job_id] = {"project_id": project_id, "status": "processing", "result": None, "error_detail": None}
        return {"job_id": job_id, "status": "processing"}

    def run_youtube_reference_style_import_job(self, *, project_id: str, job_id: str, url: str) -> None:
        """백그라운드에서 실제로 돈다. `BackgroundTasks`가 응답을 보낸 뒤 부른다."""
        try:
            result = self.import_reference_style_from_youtube(project_id=project_id, url=url)
            with self._youtube_import_jobs_lock:
                self._youtube_import_jobs[job_id] = {"project_id": project_id, "status": "succeeded", "result": result, "error_detail": None}
        except Exception as exc:
            with self._youtube_import_jobs_lock:
                self._youtube_import_jobs[job_id] = {"project_id": project_id, "status": "failed", "result": None, "error_detail": str(exc)}

    def get_youtube_reference_style_import_job(self, *, project_id: str, job_id: str) -> dict[str, Any]:
        with self._youtube_import_jobs_lock:
            job = self._youtube_import_jobs.get(job_id)
        if job is None or job["project_id"] != project_id:
            raise KeyError("youtube_import_job_not_found")
        return {"job_id": job_id, "status": job["status"], "result": job["result"], "error_detail": job["error_detail"]}

    def import_reference_style_from_youtube(self, *, project_id: str, url: str) -> dict[str, Any]:
        """본인 유튜브 영상 하나에서 목소리 샘플과 편집 스타일 리포트를 함께 뽑는다.

        owner 요청(2026-08-29): "내 유튜브 영상 있는걸로 학습은 안돼?" 영상을
        두 번 받지 않는다 -- 한 번 내려받고, 그 파일에서 소리(목소리 샘플로
        등록)와 그림(컷 빠르기·색감 분석)을 같이 뽑는다. 내려받은 영상 자체는
        프로젝트 자산으로 남기지 않는다 -- 이번 요청은 "이 영상을 소재로 쓰겠다"가
        아니라 "이 영상에서 스타일만 배우겠다"였다.

        **동기 버전은 그대로 남긴다** -- `run_youtube_reference_style_import_job`이
        이 메서드를 그대로 부른다. 실제 무거운 일은 전부 여기 있다.
        """
        staging_dir = self.store.project_root(project_id) / "staging"
        video_path: Path | None = None
        try:
            video_path = download_youtube_video(url, staging_dir)
            audio_path = video_path.with_suffix(".reference-audio.m4a")
            ffmpeg_binary = getattr(self.pipeline.final_renderer, "ffmpeg_binary", "ffmpeg")
            ffprobe_binary = getattr(self.pipeline.final_renderer, "ffprobe_binary", "ffprobe")
            extract_audio_only(
                source_video_path=video_path, destination_audio_path=audio_path,
                ffmpeg_binary=ffmpeg_binary,
            )
            voice_asset = self.register_voice_sample_asset(project_id=project_id, source_path=audio_path)
            pacing = analyze_pacing(video_path, ffmpeg_binary=ffmpeg_binary, ffprobe_binary=ffprobe_binary)
            color = analyze_color(video_path, ffmpeg_binary=ffmpeg_binary)
            return {
                "voice_sample_asset_id": voice_asset.asset_id,
                "pacing": {
                    "average_clip_duration_sec": pacing.average_clip_duration_sec,
                    "clip_count": pacing.clip_count,
                    "shortest_clip_sec": pacing.shortest_clip_sec,
                    "longest_clip_sec": pacing.longest_clip_sec,
                },
                "color": {
                    "average_brightness": color.average_brightness,
                    "average_colorfulness": color.average_colorfulness,
                    "warm_cool_bias": color.warm_cool_bias,
                    "sample_count": color.sample_count,
                },
            }
        finally:
            if video_path is not None:
                video_path.unlink(missing_ok=True)
                audio_candidate = video_path.with_suffix(".reference-audio.m4a")
                # 오디오는 목소리 샘플로 이미 프로젝트 저장소에 복사됐다 -- 스테이징
                # 사본은 남겨 둘 이유가 없다.
                if audio_candidate.is_file() and audio_candidate != video_path:
                    audio_candidate.unlink(missing_ok=True)

    def generate_tts_replacement_candidate(
        self,
        *,
        project_id: str,
        segment_text: str,
        voice_sample_asset_id: str,
        segment_id: str | None = None,
        target_duration_sec: float | None = None,
    ) -> dict[str, Any]:
        return self.pipeline.generate_tts_replacement_candidate(
            project_id=project_id,
            segment_text=segment_text,
            voice_sample_asset_id=voice_sample_asset_id,
            segment_id=segment_id,
            target_duration_sec=target_duration_sec,
        )

    def list_tts_replacement_candidates(self, *, project_id: str, segment_id: str) -> list[dict[str, Any]]:
        return self.pipeline.list_tts_replacement_candidates(project_id=project_id, segment_id=segment_id)

    def review_tts_replacement_candidate(
        self,
        *,
        project_id: str,
        candidate_id: str,
        decision: str,
    ) -> dict[str, Any]:
        return self.pipeline.review_tts_replacement_candidate(
            project_id=project_id,
            candidate_id=candidate_id,
            decision=decision,
        )

    def plan_auto_cut_segments(
        self,
        *,
        project_id: str,
        raw_video_asset_id: str,
        total_duration: float,
        scene_timestamps: list[float],
        black_regions: list[dict[str, float]],
        segment_samples: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return self.pipeline.plan_auto_cut_segments(
            project_id=project_id,
            raw_video_asset_id=raw_video_asset_id,
            total_duration=total_duration,
            scene_timestamps=scene_timestamps,
            black_regions=black_regions,
            segment_samples=segment_samples,
        )

    def run_auto_cut_detection(self, *, project_id: str, raw_video_asset_id: str) -> dict[str, Any]:
        return self.pipeline.run_auto_cut_detection(
            project_id=project_id,
            raw_video_asset_id=raw_video_asset_id,
        )

    def transcribe_source_video(self, *, project_id: str, asset_id: str) -> dict[str, Any]:
        """올린 영상에서 말을 받아써 **대본으로 쓸 글**까지 돌려준다.

        `start_transcription`은 주소만 돌려주고 글을 버린다. 화면은 그 글을 보여
        주고 대본으로 삼아야 하므로 여기서 함께 꺼낸다. 받아쓰기는 자산 종류를
        가리지 않아 영상 파일에도 그대로 돈다.
        """
        started = self.pipeline.start_transcription(project_id=project_id, narration_asset_id=asset_id)
        return self.pipeline.get_transcription_result(project_id=project_id, job_id=started["job_id"])

    def transcribe_source_voice(self, *, project_id: str, asset_id: str) -> dict[str, Any]:
        """녹음한 목소리만으로 시작하는 길(owner 요청 2026-08-29).

        `transcribe_source_video`와 받아쓰는 방식은 완전히 같다 -- 받아쓰기는
        영상이든 순수 음성이든 가리지 않는다. 다른 것은 여기서 그 결과 위에
        "다시 들어볼 구간"까지 같이 골라 준다는 점이다
        (`narration_retake_detection.detect_retake_candidates`). **조용히
        지우지 않는다** -- 후보만 얹어 돌려주고, 뺄지는 화면에서 owner가 고른다.
        """
        transcription = self.transcribe_source_video(project_id=project_id, asset_id=asset_id)
        candidates = detect_retake_candidates(transcription.get("segments") or [])
        transcription["retake_candidates"] = [
            {
                "segment_index": candidate.segment_index,
                "start_sec": candidate.start_sec,
                "end_sec": candidate.end_sec,
                "text": candidate.text,
                "reason": candidate.reason,
            }
            for candidate in candidates
        ]
        return transcription

    def start_transcription(self, *, project_id: str, narration_asset_id: str) -> dict[str, Any]:
        result = self.pipeline.start_transcription(
            project_id=project_id,
            narration_asset_id=narration_asset_id,
        )
        transcription = self.pipeline.get_transcription_result(
            project_id=project_id,
            job_id=result["job_id"],
        )
        return {
            "job_id": result["job_id"],
            "status": result["status"],
            "transcript_uri": transcription["transcript_uri"],
        }

    def get_transcription_job(self, *, project_id: str, job_id: str) -> dict[str, Any]:
        result = self.pipeline.get_transcription_result(project_id=project_id, job_id=job_id)
        return {
            "job_id": result["job_id"],
            "status": result["status"],
            "transcript_uri": result["transcript_uri"],
        }

    def start_segment_analysis(
        self,
        *,
        project_id: str,
        transcription_job_id: str,
        script_asset_id: str | None,
    ) -> dict[str, Any]:
        result = self.pipeline.start_segment_analysis(
            project_id=project_id,
            transcription_job_id=transcription_job_id,
            script_asset_id=script_asset_id,
        )
        analysis = self.pipeline.get_segment_analysis_result(
            project_id=project_id,
            job_id=result["job_id"],
        )
        return {
            "job_id": result["job_id"],
            "status": result["status"],
            "segments_uri": analysis["file_uri"],
        }

    def get_segment_analysis_job(self, *, project_id: str, job_id: str) -> dict[str, Any]:
        result = self.pipeline.get_segment_analysis_result(project_id=project_id, job_id=job_id)
        return {
            "job_id": result["job_id"],
            "status": result["status"],
            "segments": result["segments"],
        }

    def start_broll_recommendation(self, *, project_id: str, segment_analysis_job_id: str) -> dict[str, Any]:
        return self.pipeline.start_broll_recommendation(
            project_id=project_id,
            segment_analysis_job_id=segment_analysis_job_id,
        )

    def get_broll_recommendation_job(self, *, project_id: str, job_id: str) -> dict[str, Any]:
        result = self.pipeline.get_broll_recommendation_result(project_id=project_id, job_id=job_id)
        return {
            "job_id": result["job_id"],
            "status": result["status"],
            "recommendation_type": "broll",
            "recommendations": result["recommendations"],
        }

    def start_music_recommendation(self, *, project_id: str, segment_analysis_job_id: str) -> dict[str, Any]:
        return self.pipeline.start_music_recommendation(
            project_id=project_id,
            segment_analysis_job_id=segment_analysis_job_id,
        )

    def get_music_recommendation_job(self, *, project_id: str, job_id: str) -> dict[str, Any]:
        result = self.pipeline.get_music_recommendation_result(project_id=project_id, job_id=job_id)
        return {
            "job_id": result["job_id"],
            "status": result["status"],
            "recommendation_type": "bgm",
            "recommendations": result["recommendations"],
        }

    def build_timeline(
        self,
        *,
        project_id: str,
        segment_analysis_job_id: str,
        recommendation_job_ids: list[str],
        orientation: str | None = None,
    ) -> dict[str, Any]:
        return self.pipeline.build_timeline(
            project_id=project_id,
            segment_analysis_job_id=segment_analysis_job_id,
            recommendation_job_ids=recommendation_job_ids,
            orientation=orientation,
        )

    def get_timeline_job(self, *, project_id: str, job_id: str) -> dict[str, Any]:
        return self.pipeline.get_timeline_result(project_id=project_id, job_id=job_id)

    def create_editing_session(self, *, project_id: str, timeline_job_id: str) -> dict[str, Any]:
        return self.pipeline.create_editing_session(project_id=project_id, timeline_job_id=timeline_job_id)

    def create_blank_editing_session(self, *, project_id: str) -> dict[str, Any]:
        return self.pipeline.create_blank_editing_session(project_id=project_id)

    def create_script_draft_editing_session(self, *, project_id: str, script_asset_id: str) -> dict[str, Any]:
        return self.pipeline.create_script_draft_editing_session(project_id=project_id, script_asset_id=script_asset_id)

    def apply_script_draft_narration_alignment(self, *, project_id: str, session_id: str, aligned_segments: list[dict[str, Any]], expected_revision: int) -> dict[str, Any]:
        return self.pipeline.apply_script_draft_narration_alignment(project_id=project_id, session_id=session_id, aligned_segments=aligned_segments, expected_revision=expected_revision)

    def sync_script_draft_to_narration_recording(
        self, *, project_id: str, session_id: str, narration_asset_id: str, expected_revision: int
    ) -> dict[str, Any]:
        """Move a script draft onto the timings of an actual recording.

        Everything this needs already existed -- speech recognition, the
        transcript aligner, and the apply step -- but the only way in was to
        hand over start/end numbers by hand, so no screen could offer it and a
        recording never tightened a caption. This is the missing joint.
        """
        session = self.pipeline.get_editing_session(project_id=project_id, session_id=session_id)
        source_ids = [
            str(segment.get("source_script_segment_id") or "")
            for segment in session.get("segments", [])
            if str(segment.get("source_script_segment_id") or "")
        ]
        if not source_ids:
            raise ValueError("editing_session_has_no_script_segments")
        transcription = self.start_transcription(
            project_id=project_id, narration_asset_id=narration_asset_id
        )
        transcript = self.pipeline.store.get_transcript(
            project_id=project_id,
            transcript_id=self.pipeline.store.get_job(
                project_id=project_id, job_id=transcription["job_id"]
            )["output_ref"],
        )
        spoken = [
            segment
            for segment in (transcript.get("segments") or [])
            if isinstance(segment, dict)
        ]
        if not spoken:
            raise ValueError("narration_recording_had_no_speech")
        # Pair each script line with the stretch of speech that says it. The
        # recording can run short or long of the script; a line with nothing
        # spoken for it keeps its provisional bounds rather than collapsing to
        # zero length.
        aligned: list[dict[str, Any]] = []
        for index, source_id in enumerate(source_ids):
            if index >= len(spoken):
                break
            aligned.append({
                "source_script_segment_id": source_id,
                "start_sec": float(spoken[index].get("start_sec") or 0.0),
                "end_sec": float(spoken[index].get("end_sec") or 0.0),
            })
        if not aligned:
            raise ValueError("narration_recording_had_no_speech")
        return self.apply_script_draft_narration_alignment(
            project_id=project_id,
            session_id=session_id,
            aligned_segments=aligned,
            expected_revision=expected_revision,
        )

    def get_editing_session(self, *, project_id: str, session_id: str) -> dict[str, Any]:
        return self.pipeline.get_editing_session(project_id=project_id, session_id=session_id)

    def suggest_scene_transitions(self, *, project_id: str, session_id: str) -> list[dict[str, Any]]:
        from videobox_core_engine.transitions import suggest_scene_transitions

        session = self.store.get_editing_session(project_id=project_id, session_id=session_id)
        return suggest_scene_transitions(session.get("segments", []))

    def get_latest_editing_session(self, *, project_id: str) -> dict[str, Any]:
        return self.pipeline.get_latest_editing_session(project_id=project_id)

    def get_editing_session_fixed_timeline(self, *, project_id: str, session_id: str) -> dict[str, Any]:
        return self.pipeline.get_editing_session_fixed_timeline(project_id=project_id, session_id=session_id)

    def get_editor_playback_manifest(self, *, project_id: str, session_id: str) -> dict[str, Any]:
        from videobox_core_engine.editor_playback_manifest import build_editor_playback_manifest

        session = self.store.get_editing_session(project_id=project_id, session_id=session_id)
        timeline = self.store.get_timeline_run(project_id=project_id, timeline_id=str(session["timeline_id"]))
        exact_preview = self.get_latest_exact_preview_for_session(project_id=project_id, session_id=session_id)
        return build_editor_playback_manifest(
            project_id=project_id,
            session=session,
            timeline=timeline,
            asset_content_url_prefix=f"/api/projects/{project_id}/assets",
            exact_preview=exact_preview,
        )

    def _exact_preview_response(self, *, project_id: str, record: dict[str, Any]) -> dict[str, Any]:
        state = str(record.get("state") or "unavailable")
        status = "stale" if state == "obsolete" else state
        if status not in {"pending", "running", "succeeded", "failed", "stale"}:
            status = "unavailable"
        start = float(record.get("start_sec") if record.get("start_sec") is not None else 0.0)
        end = float(record.get("end_sec") if record.get("end_sec") is not None else record.get("duration_sec") or 0.0)
        payload = {
            "status": status,
            "generation_id": str(record["generation_id"]),
            "timeline_start_sec": start,
            "timeline_end_sec": end,
            "artifact_revision": int(record["expected_revision"]),
            "fingerprint": str(record["fingerprint"]),
            "content_url": None,
            "error_message": record.get("error_message"),
        }
        if status == "succeeded" and record.get("artifact_uri"):
            payload["content_url"] = f"/api/projects/{project_id}/exact-previews/{record['generation_id']}/content"
        return payload

    def start_exact_preview(
        self, *, project_id: str, session_id: str, expected_revision: int, start_sec: float | None = None, end_sec: float | None = None
    ) -> dict[str, Any]:
        return self._exact_preview_response(
            project_id=project_id,
            record=self.pipeline.start_exact_preview(
                project_id=project_id, session_id=session_id, expected_revision=expected_revision,
                start_sec=start_sec, end_sec=end_sec,
            ),
        )

    def run_exact_preview(self, *, project_id: str, generation_id: str) -> None:
        self.pipeline.run_exact_preview(project_id=project_id, generation_id=generation_id)

    def get_exact_preview_status(self, *, project_id: str, generation_id: str) -> dict[str, Any]:
        return self._exact_preview_response(
            project_id=project_id,
            record=self.pipeline.get_exact_preview_status(project_id=project_id, generation_id=generation_id),
        )

    def get_exact_preview_content_path(self, *, project_id: str, generation_id: str) -> Path:
        status = self.get_exact_preview_status(project_id=project_id, generation_id=generation_id)
        if status["status"] != "succeeded":
            raise KeyError("exact_preview_not_current")
        record = self.store.get_exact_preview(project_id=project_id, generation_id=generation_id)
        path = self.store.resolve_storage_uri(project_id=project_id, storage_uri=str(record["artifact_uri"]))
        if not path.is_file():
            raise KeyError("exact_preview_content_missing")
        return path

    def get_latest_exact_preview_for_session(self, *, project_id: str, session_id: str) -> dict[str, Any]:
        record = self.store.get_latest_exact_preview(project_id=project_id, session_id=session_id)
        if record is None:
            return {"status": "unavailable"}
        payload = self.get_exact_preview_status(project_id=project_id, generation_id=str(record["generation_id"]))
        return {
            "status": payload["status"], "url": payload["content_url"],
            "source_session_id": session_id, "source_session_revision": payload["artifact_revision"],
            "generation_id": payload["generation_id"], "timeline_start_sec": payload["timeline_start_sec"],
            "timeline_end_sec": payload["timeline_end_sec"], "artifact_revision": payload["artifact_revision"],
            "fingerprint": payload["fingerprint"],
        }

    def preview_editing_session_selected_range(self, *, project_id: str, session_id: str, start_sec: float, end_sec: float) -> dict[str, Any]:
        return self.pipeline.preview_editing_session_selected_range(project_id=project_id, session_id=session_id, start_sec=start_sec, end_sec=end_sec)

    def split_editing_session_segment(self, *, project_id: str, session_id: str, segment_id: str, split_sec: float, expected_revision: int) -> dict[str, Any]:
        return self.pipeline.split_editing_session_segment(project_id=project_id, session_id=session_id, segment_id=segment_id, split_sec=split_sec, expected_revision=expected_revision)

    def merge_editing_session_segments(self, *, project_id: str, session_id: str, left_segment_id: str, right_segment_id: str, expected_revision: int) -> dict[str, Any]:
        return self.pipeline.merge_editing_session_segments(project_id=project_id, session_id=session_id, left_segment_id=left_segment_id, right_segment_id=right_segment_id, expected_revision=expected_revision)

    def set_editing_session_segment_bounds(self, *, project_id: str, session_id: str, segment_id: str, start_sec: float, end_sec: float, expected_revision: int) -> dict[str, Any]:
        return self.pipeline.set_editing_session_segment_bounds(project_id=project_id, session_id=session_id, segment_id=segment_id, start_sec=start_sec, end_sec=end_sec, expected_revision=expected_revision)

    def set_editing_session_segment_ripple_playback_rate(self, *, project_id: str, session_id: str, segment_id: str, rate: float, expected_revision: int) -> dict[str, Any]:
        return self.pipeline.set_editing_session_segment_ripple_playback_rate(
            project_id=project_id,
            session_id=session_id,
            segment_id=segment_id,
            rate=rate,
            expected_revision=expected_revision,
        )

    def reorder_editing_session_segments(self, *, project_id: str, session_id: str, segment_ids: list[str], bounds_by_id: dict[str, dict[str, float]] | None, expected_revision: int) -> dict[str, Any]:
        return self.pipeline.reorder_editing_session_segments(project_id=project_id, session_id=session_id, segment_ids=segment_ids, bounds_by_id=bounds_by_id, expected_revision=expected_revision)

    def update_editing_session_timeline_placements(self, *, project_id: str, session_id: str, changes: list[dict[str, object]], expected_revision: int) -> dict[str, Any]:
        return self.pipeline.update_editing_session_timeline_placements(project_id=project_id, session_id=session_id, changes=changes, expected_revision=expected_revision)

    def update_editing_session_track_states(self, *, project_id: str, session_id: str, states: dict[str, Any], expected_revision: int) -> dict[str, Any]:
        return self.pipeline.update_editing_session_track_states(project_id=project_id, session_id=session_id, states=states, expected_revision=expected_revision)

    def undo_editing_session(self, *, project_id: str, session_id: str, expected_revision: int) -> dict[str, Any]:
        return self.pipeline.undo_editing_session(project_id=project_id, session_id=session_id, expected_revision=expected_revision)

    def redo_editing_session(self, *, project_id: str, session_id: str, expected_revision: int) -> dict[str, Any]:
        return self.pipeline.redo_editing_session(project_id=project_id, session_id=session_id, expected_revision=expected_revision)

    def preview_caption_style_scope(self, *, project_id: str, session_id: str, scope: str, segment_ids: list[str]) -> dict[str, Any]:
        return self.pipeline.preview_editing_session_caption_style_scope(project_id=project_id, session_id=session_id, scope=scope, segment_ids=segment_ids)

    def update_caption_style(self, *, project_id: str, session_id: str, style: dict[str, Any], scope: str, segment_ids: list[str], expected_revision: int, proposal_id: str | None = None, candidate_id: str | None = None) -> dict[str, Any]:
        return self.pipeline.update_editing_session_caption_style(project_id=project_id, session_id=session_id, style=style, scope=scope, segment_ids=segment_ids, expected_revision=expected_revision, proposal_id=proposal_id, candidate_id=candidate_id)

    def update_segment_caption(
        self,
        *,
        project_id: str,
        session_id: str,
        segment_id: str,
        caption_text: str,
        expected_revision: int,
        proposal_id: str | None = None,
        candidate_id: str | None = None,
    ) -> dict[str, Any]:
        return self.pipeline.update_editing_session_segment_caption(
            project_id=project_id,
            session_id=session_id,
            segment_id=segment_id,
            caption_text=caption_text,
            expected_revision=expected_revision,
            proposal_id=proposal_id,
            candidate_id=candidate_id,
        )

    def translate_editing_session_captions(
        self, *, project_id: str, session_id: str, language: str, expected_revision: int, runtime: Any
    ) -> dict[str, Any]:
        """장면 자막을 로컬 모델로 옮겨 원본 옆에 쌓고, 그 언어로 고른다.

        **이미 번역해 둔 장면은 다시 부르지 않는다.** 자막 하나를 고친 뒤 다시
        누르면 고친 장면만 새로 번역된다 -- 마흔 장면을 통째로 다시 돌리면
        기다리는 시간도 길고, 이미 손본 번역까지 모델이 갈아치운다.
        """
        session = self.pipeline.get_editing_session(project_id=project_id, session_id=session_id)
        pending: list[tuple[str, str]] = []
        for segment in session.get("segments", []):
            if not isinstance(segment, dict):
                continue
            if str(segment.get("cut_action") or "keep") == "remove":
                continue
            text = str(segment.get("caption_text") or "").strip()
            if not text:
                continue
            existing = segment.get("caption_translations")
            if isinstance(existing, dict) and str(existing.get(language) or "").strip():
                continue
            pending.append((str(segment.get("segment_id") or ""), text))
        texts_by_segment = (
            CaptionTranslationService(runtime=runtime).translate(
                project_id=project_id, language=language, captions=pending
            )
            if pending
            else {}
        )
        return self.pipeline.set_editing_session_caption_translations(
            project_id=project_id, session_id=session_id, language=language,
            texts_by_segment=texts_by_segment, expected_revision=expected_revision,
        )

    def set_caption_language(
        self, *, project_id: str, session_id: str, language: str | None, expected_revision: int
    ) -> dict[str, Any]:
        return self.pipeline.set_editing_session_caption_language(
            project_id=project_id, session_id=session_id, language=language,
            expected_revision=expected_revision,
        )

    def update_segment_cut_action(
        self,
        *,
        project_id: str,
        session_id: str,
        segment_id: str,
        cut_action: str,
        expected_revision: int,
    ) -> dict[str, Any]:
        return self.pipeline.update_editing_session_segment_cut_action(
            project_id=project_id,
            session_id=session_id,
            segment_id=segment_id,
            cut_action=cut_action,
            expected_revision=expected_revision,
        )

    def update_segment_transition(
        self,
        *,
        project_id: str,
        session_id: str,
        segment_id: str,
        transition: dict[str, Any] | None,
        expected_revision: int,
    ) -> dict[str, Any]:
        return self.pipeline.update_editing_session_segment_transition(
            project_id=project_id,
            session_id=session_id,
            segment_id=segment_id,
            transition=transition,
            expected_revision=expected_revision,
        )

    def update_segment_broll_override(
        self,
        *,
        project_id: str,
        session_id: str,
        segment_id: str,
        asset_id: str,
        media_controls: dict[str, Any] | None = None,
        expected_revision: int,
    ) -> dict[str, Any]:
        return self.pipeline.update_editing_session_segment_broll_override(
            project_id=project_id,
            session_id=session_id,
            segment_id=segment_id,
            asset_id=asset_id,
            media_controls=media_controls,
            expected_revision=expected_revision,
        )

    def update_segment_sfx_override(self, *, project_id: str, session_id: str, segment_id: str, asset_id: str, media_controls: dict[str, Any] | None = None, expected_revision: int) -> dict[str, Any]:
        return self.pipeline.update_editing_session_segment_sfx_override(project_id=project_id, session_id=session_id, segment_id=segment_id, asset_id=asset_id, media_controls=media_controls, expected_revision=expected_revision)

    def clear_segment_sfx_override(
        self,
        *,
        project_id: str,
        session_id: str,
        segment_id: str,
        expected_revision: int,
    ) -> dict[str, Any]:
        return self.pipeline.clear_editing_session_segment_sfx_override(
            project_id=project_id,
            session_id=session_id,
            segment_id=segment_id,
            expected_revision=expected_revision,
        )

    def clear_segment_broll_override(
        self,
        *,
        project_id: str,
        session_id: str,
        segment_id: str,
        expected_revision: int,
    ) -> dict[str, Any]:
        return self.pipeline.clear_editing_session_segment_broll_override(
            project_id=project_id,
            session_id=session_id,
            segment_id=segment_id,
            expected_revision=expected_revision,
        )

    def build_editing_session_partial_regeneration_request(
        self,
        *,
        project_id: str,
        session_id: str,
        segment_ids: list[str],
        fields: list[str],
    ) -> dict[str, Any]:
        return self.pipeline.build_editing_session_partial_regeneration_request(
            project_id=project_id,
            session_id=session_id,
            segment_ids=segment_ids,
            fields=fields,
        )

    def start_editing_session_partial_regeneration(
        self,
        *,
        project_id: str,
        session_id: str,
        segment_ids: list[str],
        fields: list[str],
        expected_revision: int,
    ) -> dict[str, Any]:
        return self.pipeline.start_editing_session_partial_regeneration(
            project_id=project_id,
            session_id=session_id,
            segment_ids=segment_ids,
            fields=fields,
            expected_revision=expected_revision,
        )

    def get_partial_regeneration_result(self, *, project_id: str, job_id: str) -> dict[str, Any]:
        return self.pipeline.get_partial_regeneration_result(project_id=project_id, job_id=job_id)

    def update_segment_visual_overlay(
        self,
        *,
        project_id: str,
        session_id: str,
        segment_id: str,
        overlay_type: str,
        asset_id: str,
        expected_revision: int,
    ) -> dict[str, Any]:
        return self.pipeline.update_editing_session_segment_visual_overlay(
            project_id=project_id,
            session_id=session_id,
            segment_id=segment_id,
            overlay_type=overlay_type,
            asset_id=asset_id,
            expected_revision=expected_revision,
        )

    def clear_segment_visual_overlays(
        self,
        *,
        project_id: str,
        session_id: str,
        segment_id: str,
        expected_revision: int,
    ) -> dict[str, Any]:
        return self.pipeline.clear_editing_session_segment_visual_overlays(
            project_id=project_id,
            session_id=session_id,
            segment_id=segment_id,
            expected_revision=expected_revision,
        )

    def update_segment_explanation_card(
        self,
        *,
        project_id: str,
        session_id: str,
        segment_id: str,
        title: str,
        body: str,
        text: str,
        expected_revision: int,
        proposal_id: str | None = None,
        candidate_id: str | None = None,
    ) -> dict[str, Any]:
        return self.pipeline.update_editing_session_segment_explanation_card(
            project_id=project_id,
            session_id=session_id,
            segment_id=segment_id,
            title=title,
            body=body,
            text=text,
            expected_revision=expected_revision,
            proposal_id=proposal_id,
            candidate_id=candidate_id,
        )

    def remove_segment_explanation_card(
        self,
        *,
        project_id: str,
        session_id: str,
        segment_id: str,
        expected_revision: int,
    ) -> dict[str, Any]:
        return self.pipeline.remove_editing_session_segment_explanation_card(
            project_id=project_id,
            session_id=session_id,
            segment_id=segment_id,
            expected_revision=expected_revision,
        )

    def update_segment_image_overlay(
        self,
        *,
        project_id: str,
        session_id: str,
        segment_id: str,
        asset_id: str,
        text: str,
        expected_revision: int,
        proposal_id: str | None = None,
        candidate_id: str | None = None,
    ) -> dict[str, Any]:
        return self.pipeline.update_editing_session_segment_image_overlay(
            project_id=project_id,
            session_id=session_id,
            segment_id=segment_id,
            asset_id=asset_id,
            text=text,
            expected_revision=expected_revision,
            proposal_id=proposal_id,
            candidate_id=candidate_id,
        )

    def update_segment_table_overlay(
        self,
        *,
        project_id: str,
        session_id: str,
        segment_id: str,
        columns: list[str],
        rows: list[list[str]],
        text: str,
        expected_revision: int,
        proposal_id: str | None = None,
        candidate_id: str | None = None,
    ) -> dict[str, Any]:
        return self.pipeline.update_editing_session_segment_table_overlay(
            project_id=project_id,
            session_id=session_id,
            segment_id=segment_id,
            columns=columns,
            rows=rows,
            text=text,
            expected_revision=expected_revision,
            proposal_id=proposal_id,
            candidate_id=candidate_id,
        )

    def remove_segment_image_overlay(
        self,
        *,
        project_id: str,
        session_id: str,
        segment_id: str,
        expected_revision: int,
    ) -> dict[str, Any]:
        return self.pipeline.remove_editing_session_segment_image_overlay(
            project_id=project_id,
            session_id=session_id,
            segment_id=segment_id,
            expected_revision=expected_revision,
        )

    def remove_segment_table_overlay(
        self,
        *,
        project_id: str,
        session_id: str,
        segment_id: str,
        expected_revision: int,
    ) -> dict[str, Any]:
        return self.pipeline.remove_editing_session_segment_table_overlay(
            project_id=project_id,
            session_id=session_id,
            segment_id=segment_id,
            expected_revision=expected_revision,
        )

    def update_segment_shape_overlay(
        self,
        *,
        project_id: str,
        session_id: str,
        segment_id: str,
        shape: str,
        vertical: str,
        horizontal: str,
        size: str,
        motion: str = "none",
        expected_revision: int,
    ) -> dict[str, Any]:
        return self.pipeline.update_editing_session_segment_shape_overlay(
            project_id=project_id,
            session_id=session_id,
            segment_id=segment_id,
            shape=shape,
            vertical=vertical,
            horizontal=horizontal,
            size=size,
            motion=motion,
            expected_revision=expected_revision,
        )

    def remove_segment_shape_overlay(
        self,
        *,
        project_id: str,
        session_id: str,
        segment_id: str,
        expected_revision: int,
    ) -> dict[str, Any]:
        return self.pipeline.remove_editing_session_segment_shape_overlay(
            project_id=project_id,
            session_id=session_id,
            segment_id=segment_id,
            expected_revision=expected_revision,
        )

    def update_segment_music_override(
        self,
        *,
        project_id: str,
        session_id: str,
        segment_id: str,
        asset_id: str,
        media_controls: dict[str, Any] | None = None,
        expected_revision: int,
    ) -> dict[str, Any]:
        return self.pipeline.update_editing_session_segment_music_override(
            project_id=project_id,
            session_id=session_id,
            segment_id=segment_id,
            asset_id=asset_id,
            media_controls=media_controls,
            expected_revision=expected_revision,
        )

    def clear_segment_music_override(
        self,
        *,
        project_id: str,
        session_id: str,
        segment_id: str,
        expected_revision: int,
    ) -> dict[str, Any]:
        return self.pipeline.clear_editing_session_segment_music_override(
            project_id=project_id,
            session_id=session_id,
            segment_id=segment_id,
            expected_revision=expected_revision,
        )

    def select_segment_tts_replacement(
        self,
        *,
        project_id: str,
        session_id: str,
        segment_id: str,
        recommendation_id: str,
        asset_id: str,
        expected_revision: int,
        proposal_id: str | None = None,
        candidate_id: str | None = None,
    ) -> dict[str, Any]:
        return self.pipeline.select_editing_session_segment_tts_replacement(
            project_id=project_id,
            session_id=session_id,
            segment_id=segment_id,
            recommendation_id=recommendation_id,
            asset_id=asset_id,
            expected_revision=expected_revision,
            proposal_id=proposal_id,
            candidate_id=candidate_id,
        )

    def clear_segment_tts_replacement(
        self,
        *,
        project_id: str,
        session_id: str,
        segment_id: str,
        expected_revision: int,
    ) -> dict[str, Any]:
        return self.pipeline.clear_editing_session_segment_tts_replacement(
            project_id=project_id,
            session_id=session_id,
            segment_id=segment_id,
            expected_revision=expected_revision,
        )

    def get_review_snapshot(self, *, project_id: str, job_id: str) -> dict[str, Any]:
        return self.pipeline.get_review_snapshot(project_id=project_id, job_id=job_id)

    def approve_pending_recommendation(
        self,
        *,
        project_id: str,
        job_id: str,
        recommendation_id: str,
    ) -> dict[str, Any]:
        return self.pipeline.approve_pending_recommendation(
            project_id=project_id,
            timeline_job_id=job_id,
            recommendation_id=recommendation_id,
        )

    def reject_pending_recommendation(
        self,
        *,
        project_id: str,
        job_id: str,
        recommendation_id: str,
    ) -> dict[str, Any]:
        return self.pipeline.reject_pending_recommendation(
            project_id=project_id,
            timeline_job_id=job_id,
            recommendation_id=recommendation_id,
        )

    def approve_timeline_review(self, *, project_id: str, job_id: str) -> dict[str, Any]:
        return self.pipeline.approve_timeline_review(project_id=project_id, timeline_job_id=job_id)

    def reopen_timeline_review(self, *, project_id: str, job_id: str) -> dict[str, Any]:
        return self.pipeline.reopen_timeline_review(project_id=project_id, timeline_job_id=job_id)

    def start_subtitle_render(self, *, project_id: str, timeline_job_id: str) -> dict[str, Any]:
        return self.pipeline.start_subtitle_render(project_id=project_id, timeline_job_id=timeline_job_id)

    def get_subtitle_result(self, *, project_id: str, job_id: str) -> dict[str, Any]:
        return self.pipeline.get_subtitle_result(project_id=project_id, job_id=job_id)

    def start_preview_render(self, *, project_id: str, timeline_job_id: str) -> dict[str, Any]:
        return self.pipeline.start_preview_render(project_id=project_id, timeline_job_id=timeline_job_id)

    def get_preview_result(self, *, project_id: str, job_id: str) -> dict[str, Any]:
        return self.pipeline.get_preview_result(project_id=project_id, job_id=job_id)

    def start_capcut_export(self, *, project_id: str, timeline_job_id: str) -> dict[str, Any]:
        return self.pipeline.start_capcut_export(project_id=project_id, timeline_job_id=timeline_job_id)

    def get_capcut_export_result(self, *, project_id: str, job_id: str) -> dict[str, Any]:
        return self.pipeline.get_capcut_export_result(project_id=project_id, job_id=job_id)

    def start_final_render(self, *, project_id: str, timeline_job_id: str) -> dict[str, Any]:
        return self.pipeline.start_final_render(project_id=project_id, timeline_job_id=timeline_job_id)

    def start_final_render_job(self, *, project_id: str, timeline_job_id: str) -> dict[str, Any]:
        return self.pipeline.start_final_render_job(project_id=project_id, timeline_job_id=timeline_job_id)

    def start_variant_renders(self, *, project_id: str, session_id: str, variant_ids: list[str]) -> dict[str, Any]:
        return self.pipeline.start_variant_renders(
            project_id=project_id, session_id=session_id, variant_ids=variant_ids
        )

    def run_final_render_job(self, *, project_id: str, timeline_job_id: str, job: dict[str, Any]) -> None:
        self.pipeline.run_final_render_job(project_id=project_id, timeline_job_id=timeline_job_id, job=job)

    def release_final_render_worker(self, *, project_id: str, job_id: str) -> None:
        self.pipeline.release_final_render_worker(
            project_id=project_id,
            job_id=job_id,
        )

    def get_final_render_result(self, *, project_id: str, job_id: str) -> dict[str, Any]:
        return self.pipeline.get_final_render_result(project_id=project_id, job_id=job_id)

    # owner 요청(2026-08-28): 프리뷰 공유 링크 -- 토큰 링크 방식 승인. 이 앱은
    # 지금까지 인증이 전혀 없었다는 점을 밝혀 둔다. 아래 넷은 store에 그대로 위임한다.
    def create_preview_share(self, *, project_id: str, export_id: str) -> dict[str, Any]:
        return self.store.create_preview_share(project_id=project_id, export_id=export_id)

    def get_preview_share(self, *, token: str) -> dict[str, Any] | None:
        return self.store.get_preview_share_by_token(token=token)

    def revoke_preview_share(self, *, project_id: str, share_id: str) -> None:
        self.store.revoke_preview_share(project_id=project_id, share_id=share_id)

    def list_preview_shares_for_render(
        self, *, project_id: str, export_id: str | None = None
    ) -> list[dict[str, Any]]:
        return self.store.list_preview_shares(project_id=project_id, export_id=export_id)

    def start_capcut_draft_export(self, *, project_id: str, timeline_job_id: str) -> dict[str, Any]:
        return self.pipeline.start_capcut_draft_export(project_id=project_id, timeline_job_id=timeline_job_id)

    def start_capcut_draft_export_job(self, *, project_id: str, timeline_job_id: str) -> dict[str, Any]:
        return self.pipeline.start_capcut_draft_export_job(project_id=project_id, timeline_job_id=timeline_job_id)

    def run_capcut_draft_export_job(
        self, *, project_id: str, timeline_job_id: str, job: dict[str, Any]
    ) -> None:
        self.pipeline.run_capcut_draft_export_job(
            project_id=project_id, timeline_job_id=timeline_job_id, job=job
        )

    def release_capcut_draft_export_worker(self, *, project_id: str, job_id: str) -> None:
        self.pipeline.release_capcut_draft_export_worker(
            project_id=project_id,
            job_id=job_id,
        )

    def get_capcut_draft_export_result(self, *, project_id: str, job_id: str) -> dict[str, Any]:
        return self.pipeline.get_capcut_draft_export_result(project_id=project_id, job_id=job_id)

    def register_capcut_draft_handoff(self, *, project_id: str, job_id: str) -> dict[str, Any]:
        return self.pipeline.register_capcut_draft_handoff(project_id=project_id, job_id=job_id)

    def get_capcut_handoff_diagnostics(self) -> dict[str, Any]:
        return self.pipeline.get_capcut_handoff_diagnostics()

    def get_provider_trace_audit(
        self,
        *,
        project_id: str,
        timeline_id: str | None = None,
        include_upstream: bool = False,
        job_type: str | None = None,
        artifact_type: str | None = None,
        final_provider: str | None = None,
        fallback_reason: str | None = None,
    ) -> dict[str, Any]:
        return self.pipeline.store.get_provider_trace_audit(
            project_id=project_id,
            timeline_id=timeline_id,
            include_upstream=include_upstream,
            job_type=job_type,
            artifact_type=artifact_type,
            final_provider=final_provider,
            fallback_reason=fallback_reason,
        )

    # Job types whose start_* call takes exactly one input_ref-shaped kwarg,
    # so a failed run can be retried generically from the stored job record
    # alone. TIMELINE_BUILD (needs recommendation_job_ids too), SEGMENT_ANALYSIS
    # (needs an optional script_asset_id), and PARTIAL_REGENERATION (needs
    # session_id/segment_ids/fields) carry extra parameters that aren't
    # recoverable from input_ref alone, so they're intentionally excluded —
    # those must be re-triggered manually with their full original request.
    _RETRYABLE_JOB_DISPATCH: dict[str, tuple[str, str]] = {
        "transcription": ("start_transcription", "narration_asset_id"),
        "broll_recommendation": ("start_broll_recommendation", "segment_analysis_job_id"),
        "music_recommendation": ("start_music_recommendation", "segment_analysis_job_id"),
        "subtitle_render": ("start_subtitle_render", "timeline_job_id"),
        "preview_render": ("start_preview_render", "timeline_job_id"),
        "capcut_export": ("start_capcut_export", "timeline_job_id"),
        "final_render": ("start_final_render_job", "timeline_job_id"),
        "capcut_draft_export": ("start_capcut_draft_export_job", "timeline_job_id"),
    }

    def retry_job(self, *, project_id: str, job_id: str) -> dict[str, Any]:
        job = self.store.get_job(project_id=project_id, job_id=job_id)
        if job["status"] != "failed":
            raise ValueError(f"Job '{job_id}' is not in a failed state and cannot be retried.")
        job_type = str(job["job_type"])
        dispatch = self._RETRYABLE_JOB_DISPATCH.get(job_type)
        if dispatch is None:
            raise ValueError(
                f"Job type '{job_type}' cannot be retried automatically; "
                "restart it with its original request instead."
            )
        method_name, input_kwarg = dispatch
        if not job["input_ref"]:
            raise ValueError(f"Job '{job_id}' has no input_ref recorded and cannot be retried.")
        method = getattr(self, method_name)
        result = method(project_id=project_id, **{input_kwarg: job["input_ref"]})
        return {"job_type": job_type, "input_ref": job["input_ref"], **result}
