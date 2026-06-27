from __future__ import annotations

from pathlib import Path
from typing import Any

from videobox_domain_models.assets import AssetType
from videobox_domain_models.jobs import JobStatus, JobType
from videobox_provider_interfaces.stt import MockSTTProvider, STTProvider, STTRequest
from videobox_storage.local_project_store import LocalProjectStore


class LocalPipelineRunner:
    def __init__(
        self,
        store: LocalProjectStore,
        *,
        stt_provider: STTProvider | None = None,
    ) -> None:
        self.store = store
        self.stt_provider = stt_provider or MockSTTProvider()

    def register_narration_asset(self, *, project_id: str, source_path: Path) -> dict[str, Any]:
        asset = self.store.register_asset(
            project_id=project_id,
            asset_type=AssetType.NARRATION_AUDIO,
            source_path=source_path,
        )
        return {
            "asset_id": asset.asset_id,
            "project_id": asset.project_id,
            "asset_type": asset.asset_type.value,
            "storage_uri": asset.storage_uri,
        }

    def register_script_asset(self, *, project_id: str, source_path: Path) -> dict[str, Any]:
        asset = self.store.register_asset(
            project_id=project_id,
            asset_type=AssetType.SCRIPT_DOCUMENT,
            source_path=source_path,
        )
        return {
            "asset_id": asset.asset_id,
            "project_id": asset.project_id,
            "asset_type": asset.asset_type.value,
            "storage_uri": asset.storage_uri,
        }

    def start_transcription(self, *, project_id: str, narration_asset_id: str) -> dict[str, Any]:
        job = self.store.create_job(
            project_id=project_id,
            job_type=JobType.TRANSCRIPTION,
            input_ref=narration_asset_id,
            status=JobStatus.RUNNING,
        )
        asset = self.store.get_asset(project_id=project_id, asset_id=narration_asset_id)
        asset_path = self.store.resolve_storage_uri(project_id=project_id, storage_uri=asset["storage_uri"])
        stt_result = self.stt_provider.transcribe(STTRequest(source_path=asset_path))
        transcript = self.store.save_transcript(
            project_id=project_id,
            source_asset_id=narration_asset_id,
            transcript_text=stt_result.text,
            segments=[
                {
                    "start_sec": segment.start_sec,
                    "end_sec": segment.end_sec,
                    "text": segment.text,
                    "confidence": segment.confidence,
                }
                for segment in stt_result.segments
            ],
            provider_name=stt_result.provider_name,
        )
        self.store.update_job(
            project_id=project_id,
            job_id=job["job_id"],
            status=JobStatus.SUCCEEDED,
            output_ref=transcript["transcript_id"],
        )
        return {"job_id": job["job_id"], "status": JobStatus.SUCCEEDED.value}

    def get_transcription_result(self, *, project_id: str, job_id: str) -> dict[str, Any]:
        job = self.store.get_job(project_id=project_id, job_id=job_id)
        transcript = self.store.get_transcript(project_id=project_id, transcript_id=job["output_ref"])
        return {
            "job_id": job["job_id"],
            "status": job["status"],
            "transcript_id": transcript["transcript_id"],
            "transcript_uri": transcript["transcript_uri"],
            "transcript_text": transcript["transcript_text"],
            "segments": transcript["segments"],
        }

    def start_segment_analysis(
        self,
        *,
        project_id: str,
        transcription_job_id: str,
        script_asset_id: str | None,
    ) -> dict[str, Any]:
        transcription_job = self.store.get_job(project_id=project_id, job_id=transcription_job_id)
        transcript = self.store.get_transcript(
            project_id=project_id,
            transcript_id=transcription_job["output_ref"],
        )
        script_text = self._load_script_text(project_id=project_id, script_asset_id=script_asset_id)
        segments = self._analyze_segments(transcript["segments"], script_text=script_text)
        job = self.store.create_job(
            project_id=project_id,
            job_type=JobType.SEGMENT_ANALYSIS,
            input_ref=transcription_job_id,
            status=JobStatus.RUNNING,
        )
        analysis = self.store.save_segment_analysis(
            project_id=project_id,
            transcript_id=transcript["transcript_id"],
            script_asset_id=script_asset_id,
            segments=segments,
        )
        self.store.update_job(
            project_id=project_id,
            job_id=job["job_id"],
            status=JobStatus.SUCCEEDED,
            output_ref=analysis["segment_analysis_id"],
        )
        return {"job_id": job["job_id"], "status": JobStatus.SUCCEEDED.value}

    def get_segment_analysis_result(self, *, project_id: str, job_id: str) -> dict[str, Any]:
        job = self.store.get_job(project_id=project_id, job_id=job_id)
        analysis = self.store.get_segment_analysis(
            project_id=project_id,
            segment_analysis_id=job["output_ref"],
        )
        return {
            "job_id": job["job_id"],
            "status": job["status"],
            "segment_analysis_id": analysis["segment_analysis_id"],
            "segments": analysis["segments"],
            "file_uri": analysis["file_uri"],
        }

    def _load_script_text(self, *, project_id: str, script_asset_id: str | None) -> str | None:
        if script_asset_id is None:
            return None
        asset = self.store.get_asset(project_id=project_id, asset_id=script_asset_id)
        script_path = self.store.resolve_storage_uri(project_id=project_id, storage_uri=asset["storage_uri"])
        return script_path.read_text(encoding="utf-8")

    def _analyze_segments(
        self,
        transcript_segments: list[dict[str, Any]],
        *,
        script_text: str | None,
    ) -> list[dict[str, Any]]:
        script_lines = []
        if script_text:
            script_lines = [line.strip() for line in script_text.splitlines() if line.strip()]

        analyzed_segments: list[dict[str, Any]] = []
        for index, segment in enumerate(transcript_segments):
            transcript_text = str(segment["text"]).strip()
            script_reference = script_lines[index] if index < len(script_lines) else None
            review_required = (
                "restart" in transcript_text.lower()
                or float(segment.get("confidence", 1.0)) < 0.85
                or (script_reference is not None and transcript_text.rstrip(".") != script_reference.rstrip("."))
            )
            analyzed_segments.append(
                {
                    "segment_id": f"seg_{index + 1:03d}",
                    "text": transcript_text,
                    "start_sec": float(segment["start_sec"]),
                    "end_sec": float(segment["end_sec"]),
                    "confidence": float(segment.get("confidence", 1.0)),
                    "review_required": review_required,
                    "cleanup_decision": "review" if review_required else "keep",
                }
            )
        return analyzed_segments
