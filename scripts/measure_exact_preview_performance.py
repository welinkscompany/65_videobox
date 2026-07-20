"""Manual, local-only exact-preview performance measurement.

This is intentionally not a pytest or CI gate: FFmpeg time depends on the
developer machine.  Run with ``--enforce`` only when recording a local
acceptance result for the declared cold/warm limits.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from time import perf_counter

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
for source_root in (
    REPOSITORY_ROOT / "services" / "api" / "src",
    REPOSITORY_ROOT / "packages" / "domain-models" / "src",
    REPOSITORY_ROOT / "packages" / "storage-abstractions" / "src",
    REPOSITORY_ROOT / "packages" / "provider-interfaces" / "src",
    REPOSITORY_ROOT / "packages" / "timeline-schema" / "src",
    REPOSITORY_ROOT / "packages" / "core-engine" / "src",
    REPOSITORY_ROOT / "packages" / "capcut-export" / "src",
):
    sys.path.insert(0, str(source_root))

from videobox_core_engine.local_pipeline import LocalPipelineRunner
from videobox_domain_models.assets import AssetType
from videobox_storage.local_project_store import LocalProjectStore


COLD_RENDER_LIMIT_SECONDS = 20.0
WARM_CACHE_LIMIT_SECONDS = 0.5


def assess_performance(*, cold_seconds: float, warm_seconds: float) -> dict[str, bool]:
    return {
        "cold_pass": cold_seconds <= COLD_RENDER_LIMIT_SECONDS,
        "warm_pass": warm_seconds <= WARM_CACHE_LIMIT_SECONDS,
    }


def measure_exact_preview() -> dict[str, object]:
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg is required for the local exact-preview performance harness")
    with tempfile.TemporaryDirectory(prefix="videobox_exact_preview_performance_") as temporary_root:
        root = Path(temporary_root)
        source = root / "source-10s-1280x720.mp4"
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=navy:s=1280x720:r=30:d=10", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(source)],
            check=True,
            capture_output=True,
        )
        store = LocalProjectStore(root / "projects")
        project = store.bootstrap_project(name="Exact preview performance fixture")
        asset = store.register_asset(project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=source)
        timeline = store.save_timeline_run(
            project_id=project.project_id,
            output_mode="review",
            source_session_revision=1,
            timeline_payload={
                "output": {"width": 1280, "height": 720, "duration_sec": 10.0, "fps_num": 30, "fps_den": 1, "sample_aspect_ratio": "1:1", "rotation": 0},
                "tracks": [{"track_type": "broll", "clips": [{"clip_id": "fixture-broll", "asset_id": asset.asset_id, "asset_uri": asset.storage_uri, "start_sec": 0, "end_sec": 10, "media_controls": {}}]}],
            },
        )
        session = store.save_editing_session(project_id=project.project_id, timeline_id=timeline["timeline_id"], session_payload={"segments": []})
        pipeline = LocalPipelineRunner(store)
        cold_started = perf_counter()
        record = pipeline.start_exact_preview(project_id=project.project_id, session_id=session["session_id"], expected_revision=1)
        pipeline.run_exact_preview(project_id=project.project_id, generation_id=record["generation_id"])
        cold_seconds = perf_counter() - cold_started
        completed = store.get_exact_preview(project_id=project.project_id, generation_id=record["generation_id"])
        if completed["state"] != "succeeded":
            raise RuntimeError(f"exact preview did not complete: {completed['state']}")
        warm_started = perf_counter()
        cached = pipeline.start_exact_preview(project_id=project.project_id, session_id=session["session_id"], expected_revision=1)
        warm_seconds = perf_counter() - warm_started
        if cached["generation_id"] != record["generation_id"] or cached["state"] != "succeeded":
            raise RuntimeError("warm measurement did not use the completed exact-preview cache record")
    result: dict[str, object] = {
        "fixture": "10s 1280x720 local b-roll only",
        "cold_seconds": round(cold_seconds, 4),
        "warm_seconds": round(warm_seconds, 4),
        "cold_limit_seconds": COLD_RENDER_LIMIT_SECONDS,
        "warm_limit_seconds": WARM_CACHE_LIMIT_SECONDS,
    }
    result.update(assess_performance(cold_seconds=cold_seconds, warm_seconds=warm_seconds))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Measure the local exact-preview cold render and warm cache lookup.")
    parser.add_argument("--enforce", action="store_true", help="return non-zero when the local performance limits are missed")
    arguments = parser.parse_args()
    result = measure_exact_preview()
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    if arguments.enforce and not (result["cold_pass"] and result["warm_pass"]):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
