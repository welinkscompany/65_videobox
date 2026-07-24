from __future__ import annotations

"""Aggregate deterministic long-form VideoBox CapCut draft QA evidence.

This runner validates generated draft structure and artifacts. It deliberately
does not open or automate the CapCut desktop application.
"""

import argparse
import importlib.util
import json
from pathlib import Path
from typing import Any


PROFILE_NAMES = ("loop", "crop_pad_overlay", "audio_ducking")
PROFILE_DIRECTORIES = {
    "loop": "loop",
    "crop_pad_overlay": "crop",
    "audio_ducking": "audio",
}
PROFILE_PROJECT_NAMES = {
    "loop": "QA loop",
    "crop_pad_overlay": "QA crop",
    "audio_ducking": "QA audio",
}
DESKTOP_CAPCUT_AUTOMATION = False
_SMOKE_SCRIPT = Path(__file__).with_name("verify-production-readiness-smoke.py")


def _load_smoke_module():
    spec = importlib.util.spec_from_file_location("videobox_production_readiness_smoke", _SMOKE_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_profile(
    *,
    profile_name: str,
    narration: Path,
    work_root: Path,
    ffmpeg_binary: str,
    ffprobe_binary: str,
) -> dict[str, Any]:
    smoke = _load_smoke_module()
    return smoke.run_smoke(
        narration=narration,
        work_root=work_root,
        ffmpeg_binary=ffmpeg_binary,
        ffprobe_binary=ffprobe_binary,
        fixture_name=profile_name,
        project_name=PROFILE_PROJECT_NAMES[profile_name],
    )


def run_all_profiles(
    *,
    narration: Path,
    work_root: Path,
    ffmpeg_binary: str,
    ffprobe_binary: str,
) -> dict[str, Any]:
    profiles: dict[str, dict[str, Any]] = {}
    for profile_name in PROFILE_NAMES:
        profiles[profile_name] = _run_profile(
            profile_name=profile_name,
            narration=narration,
            work_root=work_root / PROFILE_DIRECTORIES[profile_name],
            ffmpeg_binary=ffmpeg_binary,
            ffprobe_binary=ffprobe_binary,
        )
    return build_release_manifest(profiles)


def build_release_manifest(profiles: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {
        "desktop_capcut_opened": DESKTOP_CAPCUT_AUTOMATION,
        "profiles": profiles,
    }


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--narration", required=True, type=Path)
    parser.add_argument("--work-root", required=True, type=Path)
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--ffprobe", default="ffprobe")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    print(
        json.dumps(
            run_all_profiles(
                narration=args.narration,
                work_root=args.work_root,
                ffmpeg_binary=args.ffmpeg,
                ffprobe_binary=args.ffprobe,
            ),
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
