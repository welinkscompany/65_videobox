from __future__ import annotations

import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "verify-long-form-capcut-draft-qa.py"


def _load_qa_module():
    spec = importlib.util.spec_from_file_location("long_form_capcut_draft_qa", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_long_form_qa_declares_three_deterministic_profiles_without_desktop_capcut_claims() -> None:
    qa = _load_qa_module()

    assert tuple(qa.PROFILE_NAMES) == ("loop", "crop_pad_overlay", "audio_ducking")
    assert qa.PROFILE_DIRECTORIES == {
        "loop": "loop",
        "crop_pad_overlay": "crop",
        "audio_ducking": "audio",
    }
    assert qa.PROFILE_PROJECT_NAMES == {
        "loop": "QA loop",
        "crop_pad_overlay": "QA crop",
        "audio_ducking": "QA audio",
    }
    assert qa.DESKTOP_CAPCUT_AUTOMATION is False


def test_long_form_qa_normalizes_profile_evidence_to_release_manifest_shape() -> None:
    qa = _load_qa_module()

    manifest = qa.build_release_manifest(
        {
            "loop": {
                "checks": {"short_broll_loops": True},
                "final_mp4": {"path": "loop/output.mp4", "sha256": "a" * 64},
                "srt": {"path": "loop/subtitle.srt"},
                "capcut_draft": {"path": "loop/draft_content.json", "warnings": []},
            }
        }
    )

    assert manifest["desktop_capcut_opened"] is False
    assert manifest["profiles"]["loop"]["final_mp4"]["sha256"] == "a" * 64
    assert manifest["profiles"]["loop"]["capcut_draft"]["warnings"] == []


def test_long_form_qa_runs_every_profile_in_an_isolated_artifact_root(
    tmp_path: Path, monkeypatch
) -> None:
    qa = _load_qa_module()
    calls: list[tuple[str, Path]] = []

    def fake_profile(*, profile_name: str, work_root: Path, **_kwargs):
        calls.append((profile_name, work_root))
        return {"fixture_name": profile_name, "checks": {"ok": True}}

    monkeypatch.setattr(qa, "_run_profile", fake_profile)
    manifest = qa.run_all_profiles(
        narration=tmp_path / "narration.wav",
        work_root=tmp_path / "artifacts",
        ffmpeg_binary="ffmpeg",
        ffprobe_binary="ffprobe",
    )

    assert [name for name, _path in calls] == list(qa.PROFILE_NAMES)
    assert [path.name for _name, path in calls] == ["loop", "crop", "audio"]
    assert set(manifest["profiles"]) == set(qa.PROFILE_NAMES)
