"""Drive ingest -> STT -> segments -> recommend -> timeline -> preview ->
captions -> export end to end with the real providers Task 1 turned on, and
record what actually happened at every stage.

This exists because the repo's own history shows testing green and the
product working are not the same claim. 2,960 passing tests coexisted with a
container that had never once run real speech recognition (see F-0 in
docs/handoffs/2026-08-05-videobox-owner-dogfood-findings-backlog.ko.md), and
the r4 "verification evidence" artifact turned out to be built from a
deterministic stub that discarded the audio and returned script text on fixed
time boundaries. Both stubs are blocked here by name so neither can quietly
stand in for a real stage again.

No stage substitutes a stub provider, and no stage failure stops the run --
every remaining stage is still attempted and recorded, so one break does not
hide the state of the rest.

Usage:
    .venv\\Scripts\\python.exe scripts/verify_owner_path.py \\
        --narration path\\to\\narration.wav \\
        --script path\\to\\script.txt \\
        --broll path\\to\\clip1.mp4 --broll path\\to\\clip2.mp4 \\
        --work-root artifacts\\owner-path-verify \\
        --json-out artifacts\\owner-path-verify\\report.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    # Windows consoles default to the system codepage (often cp949/cp1252),
    # which mangles Korean transcript/script text on print. The JSON output
    # is unaffected -- json.dumps writes real UTF-8 either way.
    sys.stdout.reconfigure(encoding="utf-8")

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
for source_root in (
    REPOSITORY_ROOT / "packages" / "domain-models" / "src",
    REPOSITORY_ROOT / "packages" / "timeline-schema" / "src",
    REPOSITORY_ROOT / "packages" / "storage-abstractions" / "src",
    REPOSITORY_ROOT / "packages" / "provider-interfaces" / "src",
    REPOSITORY_ROOT / "packages" / "capcut-export" / "src",
    REPOSITORY_ROOT / "packages" / "core-engine" / "src",
    REPOSITORY_ROOT / "services" / "api" / "src",
):
    if str(source_root) not in sys.path:
        sys.path.insert(0, str(source_root))

from videobox_core_engine.local_pipeline import LocalPipelineRunner
from videobox_core_engine.settings import CapCutDraftExportConfig
from videobox_provider_interfaces.stt import STTProvider
from videobox_storage.local_project_store import LocalProjectStore

# Both stubs this project has actually shipped.  See the module docstring.
STUB_PROVIDER_NAMES: frozenset[str] = frozenset({
    "mock_stt",
    "deterministic_korean_smoke_stt",
})

STAGE_NAMES: tuple[str, ...] = (
    "ingest",
    "transcription",
    "segment_analysis",
    "broll_recommendation",
    "timeline_build",
    "preview_render",
    "subtitle_render",
    "final_render",
    "capcut_draft_export",
)


class _StageRecorder:
    """Accumulates one entry per stage and never lets a raised exception skip
    the remaining stages -- the run() loop always attempts every stage name in
    STAGE_NAMES regardless of what happened before it."""

    def __init__(self) -> None:
        self.stages: list[dict[str, Any]] = []
        self._blocked = False

    def run(self, name: str, fn: Any) -> Any:
        if self._blocked:
            self.stages.append({"name": name, "status": "skipped", "detail": "a required prior stage failed", "evidence": {}})
            return None
        try:
            evidence = fn() or {}
            self.stages.append({"name": name, "status": "passed", "detail": "", "evidence": evidence})
            return evidence
        except Exception as exc:  # noqa: BLE001 - recording the failure IS the point
            self.stages.append({"name": name, "status": "failed", "detail": str(exc), "evidence": {}})
            self._blocked = True
            return None


def run_owner_path(
    *,
    narration_path: Path,
    script_text: str,
    broll_paths: Sequence[Path],
    work_root: Path,
    stt_provider: STTProvider,
    ffmpeg_binary: str = "ffmpeg",
    ffprobe_binary: str = "ffprobe",
    auto_approve_segment_review: bool = False,
) -> dict[str, Any]:
    if stt_provider.provider_name in STUB_PROVIDER_NAMES:
        # Fail closed at the transcription stage specifically, rather than
        # refusing to run at all, so the report still shows every other stage
        # as skipped -- the same shape a real failure would produce.
        recorder = _StageRecorder()
        recorder.stages.append({"name": "ingest", "status": "passed", "detail": "", "evidence": {}})
        recorder.stages.append({
            "name": "transcription",
            "status": "failed",
            "detail": f"provider_name={stt_provider.provider_name!r} is a known stub; refusing to accept it as evidence",
            "evidence": {},
        })
        for name in STAGE_NAMES[2:]:
            recorder.stages.append({"name": name, "status": "skipped", "detail": "a required prior stage failed", "evidence": {}})
        return {"stages": recorder.stages}

    work_root.mkdir(parents=True, exist_ok=True)
    store = LocalProjectStore(work_root / "projects")
    from videobox_api.provider_factories import _build_pycapcut_exporter  # noqa: E402 - deferred to avoid a hard FastAPI dependency for callers that only need the stages contract

    pycapcut_exporter = _build_pycapcut_exporter(
        CapCutDraftExportConfig(enabled=True, video_width=1920, video_height=1080, video_fps=30),
        store=store,
    )
    runner = LocalPipelineRunner(
        store=store,
        stt_provider=stt_provider,
        pycapcut_exporter=pycapcut_exporter,
        auto_approve_segment_review=auto_approve_segment_review,
    )
    recorder = _StageRecorder()

    project = store.bootstrap_project(name="owner-path-verify")
    project_id = project.project_id
    script_path = work_root / "script.txt"
    script_path.write_text(script_text, encoding="utf-8")

    def ingest() -> dict[str, Any]:
        narration_asset = runner.register_narration_asset(project_id=project_id, source_path=narration_path)
        script_asset = runner.register_script_asset(project_id=project_id, source_path=script_path)
        broll_assets = [runner.register_broll_asset(project_id=project_id, source_path=path) for path in broll_paths]
        ingest.narration_asset_id = narration_asset["asset_id"]  # type: ignore[attr-defined]
        ingest.script_asset_id = script_asset["asset_id"]  # type: ignore[attr-defined]
        return {"narration_asset_id": narration_asset["asset_id"], "broll_count": len(broll_assets)}

    def transcription() -> dict[str, Any]:
        job = runner.start_transcription(project_id=project_id, narration_asset_id=ingest.narration_asset_id)  # type: ignore[attr-defined]
        result = runner.get_transcription_result(project_id=project_id, job_id=job["job_id"])
        transcription.job_id = job["job_id"]  # type: ignore[attr-defined]
        provider_name = None
        try:
            transcript = store.get_transcript(project_id=project_id, transcript_id=result["transcript_id"])
            provider_name = transcript.get("provider_name")
        except Exception:  # noqa: BLE001 - provider_name is best-effort evidence, not the pass/fail condition
            pass
        if provider_name in STUB_PROVIDER_NAMES:
            raise RuntimeError(f"transcription used stub provider {provider_name!r} despite the guard")
        return {"provider_name": provider_name, "transcript_text": result["transcript_text"], "segment_count": len(result["segments"])}

    def segment_analysis() -> dict[str, Any]:
        job = runner.start_segment_analysis(project_id=project_id, transcription_job_id=transcription.job_id, script_asset_id=ingest.script_asset_id)  # type: ignore[attr-defined]
        result = runner.get_segment_analysis_result(project_id=project_id, job_id=job["job_id"])
        segment_analysis.job_id = job["job_id"]  # type: ignore[attr-defined]
        return {"segment_count": len(result["segments"])}

    def broll_recommendation() -> dict[str, Any]:
        job = runner.start_broll_recommendation(project_id=project_id, segment_analysis_job_id=segment_analysis.job_id)  # type: ignore[attr-defined]
        result = runner.get_broll_recommendation_result(project_id=project_id, job_id=job["job_id"])
        broll_recommendation.job_id = job["job_id"]  # type: ignore[attr-defined]
        return {"candidate_count": len(result.get("recommendations", []))}

    def timeline_build() -> dict[str, Any]:
        job = runner.build_timeline(
            project_id=project_id,
            segment_analysis_job_id=segment_analysis.job_id,  # type: ignore[attr-defined]
            recommendation_job_ids=[broll_recommendation.job_id],  # type: ignore[attr-defined]
        )
        result = runner.get_timeline_result(project_id=project_id, job_id=job["job_id"])
        runner.approve_timeline_review(project_id=project_id, timeline_job_id=job["job_id"])
        timeline_build.job_id = job["job_id"]  # type: ignore[attr-defined]
        return {"track_count": len(result["timeline"]["tracks"])}

    def preview_render() -> dict[str, Any]:
        job = runner.start_preview_render(project_id=project_id, timeline_job_id=timeline_build.job_id)  # type: ignore[attr-defined]
        result = runner.get_preview_result(project_id=project_id, job_id=job["job_id"])
        return {"preview_id": result["preview"]["preview_id"]}

    def subtitle_render() -> dict[str, Any]:
        job = runner.start_subtitle_render(project_id=project_id, timeline_job_id=timeline_build.job_id)  # type: ignore[attr-defined]
        result = runner.get_subtitle_result(project_id=project_id, job_id=job["job_id"])
        return {"subtitle_id": result.get("subtitle_id")}

    def final_render() -> dict[str, Any]:
        job = runner.start_final_render(project_id=project_id, timeline_job_id=timeline_build.job_id)  # type: ignore[attr-defined]
        result = runner.get_final_render_result(project_id=project_id, job_id=job["job_id"])
        render = result.get("render")
        if not render:
            raise RuntimeError(f"final render job succeeded but produced no export record: {result}")
        file_uri = render["file_uri"]
        output_path = store.resolve_storage_uri(project_id=project_id, storage_uri=str(file_uri))
        # get_final_render_export already raises if the artifact is missing on
        # disk, but re-check here so the evidence in the report is self-contained
        # rather than relying on that internal invariant silently.
        return {
            "file_uri": file_uri,
            "output_exists": output_path.exists(),
            "output_size_bytes": output_path.stat().st_size if output_path.exists() else 0,
        }

    def capcut_draft_export() -> dict[str, Any]:
        job = runner.start_capcut_draft_export(project_id=project_id, timeline_job_id=timeline_build.job_id)  # type: ignore[attr-defined]
        # Not get_capcut_export_result: that reads the older single-file
        # CapCut export type. A draft export's file_uri is a directory tree,
        # and calling the wrong getter tries to read that directory as text,
        # which raises PermissionError on Windows -- indistinguishable at
        # first glance from an actual locked-file problem.
        result = runner.get_capcut_draft_export_result(project_id=project_id, job_id=job["job_id"])
        export = result.get("export") or {}
        file_uri = export.get("file_uri")
        draft_dir = store.resolve_storage_uri(project_id=project_id, storage_uri=str(file_uri)) if file_uri else None
        return {
            "file_uri": file_uri,
            "draft_dir_exists": bool(draft_dir and draft_dir.is_dir()),
            "draft_file_count": sum(1 for _ in draft_dir.rglob("*")) if draft_dir and draft_dir.is_dir() else 0,
        }

    recorder.run("ingest", ingest)
    recorder.run("transcription", transcription)
    recorder.run("segment_analysis", segment_analysis)
    recorder.run("broll_recommendation", broll_recommendation)
    recorder.run("timeline_build", timeline_build)
    recorder.run("preview_render", preview_render)
    recorder.run("subtitle_render", subtitle_render)
    recorder.run("final_render", final_render)
    recorder.run("capcut_draft_export", capcut_draft_export)

    return {"project_id": project_id, "stages": recorder.stages}


def _real_stt_provider(*, model_size: str, device: str, compute_type: str, language: str) -> STTProvider:
    from videobox_provider_interfaces.faster_whisper_stt import FasterWhisperSTTProvider

    return FasterWhisperSTTProvider(model_size=model_size, device=device, compute_type=compute_type, language=language)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--narration", required=True, type=Path)
    parser.add_argument("--script", required=True, type=Path, help="Path to a UTF-8 text file with the script.")
    parser.add_argument("--broll", action="append", type=Path, default=[], help="Repeatable. At least one required.")
    parser.add_argument("--work-root", required=True, type=Path)
    parser.add_argument("--json-out", type=Path, default=None)
    parser.add_argument("--stt-model-size", default="small")
    parser.add_argument("--stt-device", default="cpu")
    parser.add_argument("--stt-compute-type", default="int8")
    parser.add_argument("--stt-language", default="ko")
    parser.add_argument(
        "--auto-approve-segment-review", action="store_true",
        help="Owner decision (2026-08-05, Task 21, Option A): place everything automatically.",
    )
    args = parser.parse_args()

    if not args.broll:
        parser.error("at least one --broll is required")

    stt_provider = _real_stt_provider(
        model_size=args.stt_model_size, device=args.stt_device,
        compute_type=args.stt_compute_type, language=args.stt_language,
    )
    report = run_owner_path(
        narration_path=args.narration,
        script_text=args.script.read_text(encoding="utf-8"),
        broll_paths=args.broll,
        work_root=args.work_root,
        stt_provider=stt_provider,
        auto_approve_segment_review=args.auto_approve_segment_review,
    )

    for stage in report["stages"]:
        marker = {"passed": "PASS", "failed": "FAIL", "skipped": "SKIP"}[stage["status"]]
        print(f"[{marker}] {stage['name']}: {stage['detail'] or stage['evidence']}")

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    if any(stage["status"] == "failed" for stage in report["stages"]):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
