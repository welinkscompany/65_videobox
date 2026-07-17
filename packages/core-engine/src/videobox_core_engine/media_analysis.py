from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable
from threading import Lock

from videobox_domain_models.media_analysis import MediaAnalysisStatus
from videobox_provider_interfaces.vision import FIXED_VISION_RESPONSE_SCHEMA, VisionAnalysisRequest
from videobox_provider_interfaces.embeddings import EmbeddingRequest
from videobox_provider_interfaces.lm_studio import LMStudioProviderError

from videobox_core_engine.media_probe import MediaProbeResult
from videobox_storage.local_project_store import sha256_file


TAG_PROMPT_VERSION = "v1"
TAG_SCHEMA_VERSION = "v1"
RETRY_BACKOFF_SECONDS = (5, 30)


@dataclass(frozen=True, slots=True)
class AnalysisProfile:
    model_key: str = "local-vision"
    variant: str = "default"
    quantization: str = "default"
    vision_model_name: str = "local"
    embedding_model_name: str | None = None


class MediaAnalysisService:
    """Single-worker, locally dispatched analysis that relies on store CAS for late workers."""
    def __init__(self, *, store: Any, media_probe: Any, vision_provider: Any, embedding_provider: Any = None, profile: AnalysisProfile | None = None, clock: Callable[[], datetime] | None = None, extractor_version: str = "v1") -> None:
        self.store, self.media_probe, self.vision_provider = store, media_probe, vision_provider
        self.embedding_provider, self.profile = embedding_provider, profile or AnalysisProfile()
        self.clock = clock or (lambda: datetime.now(UTC))
        self.extractor_version = extractor_version
        self._dispatch_lock = Lock()

    def cache_key(self, *, source_sha256: str, profile: AnalysisProfile) -> str:
        payload = {
            "source_sha256": source_sha256, "extractor_version": self.extractor_version,
            "ffmpeg_version": str(getattr(self.media_probe, "ffmpeg_version", "unknown")),
            "model_key": profile.model_key, "model_variant": profile.variant, "quantization": profile.quantization,
            "vision_model_name": profile.vision_model_name, "embedding_model_name": profile.embedding_model_name,
            "prompt_version": TAG_PROMPT_VERSION, "schema_version": TAG_SCHEMA_VERSION,
        }
        canonical = json.dumps(payload, separators=(",", ":"), ensure_ascii=True)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def enqueue_analysis(self, *, project_id: str, asset_id: str, profile: AnalysisProfile | None = None) -> dict[str, Any]:
        profile = profile or self.profile
        asset = self.store.get_asset(project_id=project_id, asset_id=asset_id)
        source = self.store.resolve_storage_uri(project_id=project_id, storage_uri=asset["storage_uri"])
        source_sha = sha256_file(source)
        key = self.cache_key(source_sha256=source_sha, profile=profile)
        self.store.record_media_analysis_cache(project_id=project_id, asset_id=asset_id, source_sha256=source_sha, cache_key=key)
        analysis = self.store.create_media_analysis(project_id=project_id, asset_id=asset_id, idempotency_key=f"{source_sha}:{key}", cache_key=key)
        self.store.record_media_analysis_profile(project_id=project_id, analysis_id=analysis["analysis_id"], profile={"vision_model_name": profile.vision_model_name, "embedding_model_name": profile.embedding_model_name})
        return analysis

    def get_analysis(self, project_id: str, analysis_id: str) -> dict[str, Any]:
        return self.store.get_media_analysis(project_id=project_id, analysis_id=analysis_id)

    def cancel_analysis(self, *, project_id: str, analysis_id: str) -> dict[str, Any] | None:
        current = self.get_analysis(project_id, analysis_id)
        return self.store.request_media_analysis_cancel(project_id=project_id, analysis_id=analysis_id, expected_attempt=int(current["attempt"]))

    def dispatch_once(self, *, project_id: str, analysis_id: str) -> dict[str, Any] | None:
        if not self._dispatch_lock.acquire(blocking=False):
            return None
        try:
            return self._dispatch_once(project_id=project_id, analysis_id=analysis_id)
        finally:
            self._dispatch_lock.release()

    def _dispatch_once(self, *, project_id: str, analysis_id: str) -> dict[str, Any] | None:
        claimed = self.store.claim_media_analysis(project_id=project_id, analysis_id=analysis_id)
        if claimed is None:
            return None
        attempt = int(claimed["attempt"])
        try:
            asset = self.store.get_asset(project_id=project_id, asset_id=str(claimed["asset_id"]))
            source = self.store.resolve_storage_uri(project_id=project_id, storage_uri=asset["storage_uri"])
            if not source.exists():
                raise FileNotFoundError(f"Analysis source is missing: {source}")
            probe: MediaProbeResult = self.media_probe.probe(source)
            if self._cancelled(project_id, analysis_id):
                return None
            images = tuple(frame.data for frame in probe.frames)
            profile = self.store.get_media_analysis_profile(project_id=project_id, analysis_id=analysis_id)
            response = self.vision_provider.analyze_images(VisionAnalysisRequest(model_name=str(profile["vision_model_name"]), prompt="Analyze local media", images=images, response_schema=FIXED_VISION_RESPONSE_SCHEMA))
            if self._cancelled(project_id, analysis_id):
                return None
            output = dict(response.output_data)
            result = {"probe": self._probe_payload(probe), "tags": output, "cache_key": claimed["cache_key"]}
            source_sha = str(claimed["idempotency_key"]).split(":", 1)[0]
            windows = [{"start_sec": start, "end_sec": end} for start, end in zip(probe.scene_boundaries, probe.scene_boundaries[1:])]
            self.store.record_media_scene_windows(project_id=project_id, analysis_id=analysis_id, source_sha256=source_sha, profile_hash=str(claimed["cache_key"]), windows=windows)
            embedding_model = profile.get("embedding_model_name")
            if self.embedding_provider is not None and embedding_model:
                embedded = self.embedding_provider.embed(EmbeddingRequest(model_name=str(embedding_model), inputs=(str(output["summary"]),)))
                self.store.record_media_embedding(project_id=project_id, analysis_id=analysis_id, source_sha256=source_sha, profile_hash=str(claimed["cache_key"]), embedding=list(embedded.vectors[0]))
            status = MediaAnalysisStatus.SUCCEEDED if self._quality_ok(output, probe) else MediaAnalysisStatus.NEEDS_REVIEW
            return self.store.complete_media_analysis(project_id=project_id, analysis_id=analysis_id, expected_attempt=attempt, result=result, status=status)
        except Exception as exc:
            if self._cancelled(project_id, analysis_id):
                return None
            if isinstance(exc, FileNotFoundError):
                return self.store.mark_media_analysis_blocked(project_id=project_id, analysis_id=analysis_id, expected_attempt=attempt, error_code="SOURCE_MISSING", error_message=str(exc))
            if isinstance(exc, ValueError) and "ffprobe" in str(exc).lower():
                return self.store.mark_media_analysis_blocked(project_id=project_id, analysis_id=analysis_id, expected_attempt=attempt, error_code="PROBE_CORRUPT", error_message=str(exc))
            if isinstance(exc, subprocess.CalledProcessError):
                return self.store.mark_media_analysis_blocked(project_id=project_id, analysis_id=analysis_id, expected_attempt=attempt, error_code="PROBE_CORRUPT", error_message=str(exc))
            if isinstance(exc, LMStudioProviderError) and exc.code == "blocked":
                return self.store.mark_media_analysis_blocked(project_id=project_id, analysis_id=analysis_id, expected_attempt=attempt, error_code="LM_STUDIO_BLOCKED", error_message=str(exc))
            retry_index = attempt - 1
            next_retry = None
            if retry_index < len(RETRY_BACKOFF_SECONDS):
                next_retry = (self.clock() + timedelta(seconds=RETRY_BACKOFF_SECONDS[retry_index])).isoformat()
            return self.store.fail_media_analysis(project_id=project_id, analysis_id=analysis_id, expected_attempt=attempt, error_code="MEDIA_ANALYSIS_FAILED", error_message=str(exc), next_retry_at=next_retry)

    def _cancelled(self, project_id: str, analysis_id: str) -> bool:
        return bool(self.get_analysis(project_id, analysis_id).get("cancel_requested"))

    @staticmethod
    def _probe_payload(probe: MediaProbeResult) -> dict[str, Any]:
        return {"duration_sec": probe.duration_sec, "codec": probe.codec, "width": probe.width, "height": probe.height, "aspect_ratio": probe.aspect_ratio, "fps": probe.fps, "audio_codec": probe.audio_codec, "scene_boundaries": list(probe.scene_boundaries), "frames": [{"long_edge_px": frame.long_edge_px, "encoded_size_bytes": frame.encoded_size_bytes} for frame in probe.frames]}

    @staticmethod
    def _quality_ok(output: dict[str, Any], probe: MediaProbeResult) -> bool:
        required = {"layers", "summary", "confidence", "review_reasons"}
        if set(output) != required or not isinstance(output.get("summary"), str) or not isinstance(output.get("review_reasons"), list):
            return False
        layers = output.get("layers")
        confidence = output.get("confidence")
        expected_layers = set(FIXED_VISION_RESPONSE_SCHEMA["properties"]["layers"]["required"])
        if not isinstance(layers, dict) or set(layers) != expected_layers or not all(isinstance(value, list) and all(isinstance(tag, str) for tag in value) for value in layers.values()):
            return False
        return sum(bool(value) for value in layers.values()) >= 3 and isinstance(confidence, (int, float)) and not isinstance(confidence, bool) and 0.5 <= confidence <= 1.0 and all(isinstance(reason, str) for reason in output["review_reasons"]) and all(0.0 <= value <= probe.duration_sec for value in probe.scene_boundaries)
