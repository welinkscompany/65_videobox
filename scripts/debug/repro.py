"""Reproduce the exact-preview render for this project inside the container."""
import os
import sys
import traceback
from pathlib import Path

sys.path[:0] = [
    "/app/packages/core-engine/src",
    "/app/packages/storage-abstractions/src",
    "/app/packages/timeline-schema/src",
    "/app/packages/domain-models/src",
]

from videobox_core_engine.composition_plan import (  # noqa: E402
    CompositionPlan,
    materialize_editing_session_timeline,
)
from videobox_core_engine.ffmpeg_final_renderer import FfmpegFinalRenderer  # noqa: E402
from videobox_storage.local_project_store import LocalProjectStore  # noqa: E402

PROJECT = "project-318cc020"
SESSION = "editing_session_draft_315088e76623"

store = LocalProjectStore(Path(os.environ.get("VIDEOBOX_DATA_ROOT", "/videobox-data")))
session = store.get_editing_session(project_id=PROJECT, session_id=SESSION)

# Force the transition on so we reproduce the failing case.
for segment in session["segments"]:
    if segment["segment_id"] == "segment_draft_b3759eed7a":
        segment["transition_in"] = {"type": "wipeleft", "duration_sec": 1.0, "chosen_by": "owner"}

timeline = store.get_timeline(project_id=PROJECT, timeline_id=session["timeline_id"])
materialized = materialize_editing_session_timeline(
    timeline=timeline, editing_session=session, project_id=PROJECT
)
plan = CompositionPlan.from_timeline(timeline=materialized)
broll = [i for i in plan.items if i.track_type == "broll"]
print("broll items:")
for item in broll:
    print(f"  {item.clip_id} [{item.start_sec},{item.end_sec}] "
          f"src[{item.source_in_sec},{item.source_out_sec}] transition={item.transition}")

renderer = FfmpegFinalRenderer(store=store)
try:
    out = Path("/videobox-data/repro-preview.mp4")
    renderer.render_exact_preview_to_mp4(
        project_id=PROJECT, composition_plan=plan, timeline_context=materialized,
        output_path=out, subtitle_ass_path=None,
    )
    print("RENDER OK", out.stat().st_size)
except Exception as exc:  # noqa: BLE001
    print("RENDER FAILED:")
    traceback.print_exc()
    print(str(exc)[:4000])
