from __future__ import annotations

import dataclasses
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "owner_sample_edit_package.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("owner_sample_edit_package", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _run_ffmpeg(arguments: list[str]) -> None:
    completed = subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-y", *arguments],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr[-2000:]


def _make_video(path: Path, *, codec: str, duration: float = 1.0) -> None:
    video_codec = "libx264" if codec == "h264" else "libx265"
    arguments = [
        "-f",
        "lavfi",
        "-i",
        f"testsrc2=size=160x90:rate=10:duration={duration}",
        "-f",
        "lavfi",
        "-i",
        f"sine=frequency=440:sample_rate=48000:duration={duration}",
        "-shortest",
        "-c:v",
        video_codec,
        "-preset",
        "ultrafast",
        "-pix_fmt",
        "yuv420p",
    ]
    if codec == "hevc":
        arguments.extend(["-x265-params", "log-level=error:pools=1", "-tag:v", "hvc1"])
    arguments.extend(["-c:a", "aac", "-movflags", "+faststart", str(path)])
    _run_ffmpeg(arguments)


@pytest.fixture()
def real_samples(tmp_path: Path) -> Path:
    sample_dir = tmp_path / "samples"
    sample_dir.mkdir()
    _make_video(sample_dir / "h264-short.mp4", codec="h264")
    _make_video(sample_dir / "hevc-short.mp4", codec="hevc")
    return sample_dir


def _fingerprint(path: Path) -> tuple[int, int, str]:
    import hashlib

    stat = path.stat()
    return stat.st_size, stat.st_mtime_ns, hashlib.sha256(path.read_bytes()).hexdigest()


def test_inventory_reads_bounded_metadata_and_preserves_real_sources(real_samples: Path) -> None:
    package = _load_module()
    before = {path.name: _fingerprint(path) for path in real_samples.iterdir()}

    records = package.inventory_samples(real_samples, ffprobe_binary="ffprobe")

    assert [record.name for record in records] == ["h264-short.mp4", "hevc-short.mp4"]
    expected_fields = {
        "name",
        "size_bytes",
        "duration_sec",
        "container",
        "video_codec",
        "audio_codec",
        "pixel_format",
        "sha256",
    }
    assert {field.name for field in dataclasses.fields(package.SampleRecord)} == expected_fields
    assert all(set(dataclasses.asdict(record)) == expected_fields for record in records)
    assert {record.video_codec for record in records} == {"h264", "hevc"}
    assert all(record.audio_codec == "aac" for record in records)
    assert all(record.pixel_format == "yuv420p" for record in records)
    assert all(0.9 <= record.duration_sec <= 1.1 for record in records)
    assert before == {path.name: _fingerprint(path) for path in real_samples.iterdir()}
    assert str(real_samples.resolve()) not in json.dumps(
        [dataclasses.asdict(record) for record in records], ensure_ascii=False
    )


def test_inventory_rejects_nested_supported_media_before_probe(tmp_path: Path) -> None:
    package = _load_module()
    sample_dir = tmp_path / "samples"
    nested = sample_dir / "nested"
    nested.mkdir(parents=True)
    (nested / "escape.mp4").write_bytes(b"not-probed")

    with pytest.raises(package.OwnerSamplePackageError, match="^sample_not_direct_child$"):
        package.inventory_samples(sample_dir, ffprobe_binary="ffprobe")


def test_inventory_rejects_direct_directories_without_nested_traversal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = _load_module()
    sample_dir = tmp_path / "samples"
    deep = sample_dir / "nested" / "deeper"
    deep.mkdir(parents=True)
    (deep / "video.mp4").write_bytes(b"must-not-be-read")
    monkeypatch.setattr(
        Path,
        "rglob",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("nested traversal")),
    )

    with pytest.raises(package.OwnerSamplePackageError, match="^sample_not_direct_child$"):
        package.inventory_samples(sample_dir, ffprobe_binary="ffprobe")

    junction_root = tmp_path / "junction-samples"
    junction = junction_root / "junction"
    junction.mkdir(parents=True)
    original_reparse_check = package._is_reparse_point
    monkeypatch.setattr(
        package,
        "_is_reparse_point",
        lambda path: path == junction or original_reparse_check(path),
    )
    with pytest.raises(package.OwnerSamplePackageError, match="^sample_path_escape$"):
        package.inventory_samples(junction_root, ffprobe_binary="ffprobe")


def test_inventory_rejects_symlink_or_reparse_escape_before_probe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = _load_module()
    sample_dir = tmp_path / "samples"
    outside = tmp_path / "outside.mp4"
    sample_dir.mkdir()
    outside.write_bytes(b"outside")
    linked = sample_dir / "linked.mp4"
    try:
        linked.symlink_to(outside)
    except OSError:
        linked.write_bytes(b"reparse-fixture")
        original = package._is_reparse_point
        monkeypatch.setattr(
            package,
            "_is_reparse_point",
            lambda path: path == linked or original(path),
        )

    with pytest.raises(package.OwnerSamplePackageError, match="^sample_path_escape$"):
        package.inventory_samples(sample_dir, ffprobe_binary="ffprobe")


def test_inventory_applies_count_size_and_video_stream_fences(tmp_path: Path) -> None:
    package = _load_module()

    crowded = tmp_path / "crowded"
    crowded.mkdir()
    for index in range(101):
        (crowded / f"{index:03}.mp4").write_bytes(b"x")
    with pytest.raises(package.OwnerSamplePackageError, match="^sample_count_limit_exceeded$"):
        package.inventory_samples(crowded, ffprobe_binary="ffprobe")

    oversized = tmp_path / "oversized"
    oversized.mkdir()
    with (oversized / "huge.mp4").open("wb") as target:
        target.truncate(2 * 1024 * 1024 * 1024 + 1)
    with pytest.raises(package.OwnerSamplePackageError, match="^sample_size_limit_exceeded$"):
        package.inventory_samples(oversized, ffprobe_binary="ffprobe")

    audio_only = tmp_path / "audio-only"
    audio_only.mkdir()
    _run_ffmpeg(
        [
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=48000:duration=0.2",
            "-vn",
            "-c:a",
            "aac",
            str(audio_only / "audio.mp4"),
        ]
    )
    with pytest.raises(package.OwnerSamplePackageError, match="^sample_video_stream_missing$"):
        package.inventory_samples(audio_only, ffprobe_binary="ffprobe")


def test_inventory_errors_are_bounded_and_do_not_disclose_sample_path(tmp_path: Path) -> None:
    package = _load_module()
    sample_dir = tmp_path / "secret-owner-samples"
    sample_dir.mkdir()
    (sample_dir / "broken.mp4").write_bytes(b"broken")

    with pytest.raises(package.OwnerSamplePackageError) as captured:
        package.inventory_samples(sample_dir, ffprobe_binary="ffprobe")

    assert str(captured.value) == "sample_probe_failed"
    assert str(sample_dir.resolve()) not in str(captured.value)


def test_selection_uses_duration_size_filename_and_requires_both_codecs() -> None:
    package = _load_module()

    def record(
        name: str,
        codec: str,
        duration: float,
        size: int,
        *,
        container: str = "mov,mp4",
        audio: str | None = "aac",
        pixel_format: str | None = "yuv420p",
    ):
        return package.SampleRecord(
            name, size, duration, container, codec, audio, pixel_format, name * 8
        )

    selected = package.select_preview_inputs(
        [
            record("h264-z.mp4", "h264", 1.0, 20),
            record("h264-a.mp4", "h264", 1.0, 20),
            record("h264-smaller.mp4", "h264", 1.0, 10),
            record("hevc-long.mp4", "hevc", 2.0, 1),
            record("hevc-short.mp4", "hevc", 1.0, 99),
        ]
    )
    assert selected["h264"].name == "h264-smaller.mp4"
    assert selected["hevc"].name == "hevc-short.mp4"

    with pytest.raises(package.OwnerSamplePackageError, match="^required_preview_codec_missing$"):
        package.select_preview_inputs([record("only-h264.mp4", "h264", 1.0, 1)])

    compatible = record(
        "compatible.mp4", "h264", 10.0, 100, container=" MOV , mp4 ", audio=None
    )
    selected = package.select_preview_inputs(
        [
            record("wrong-container.mp4", "h264", 1.0, 1, container="matroska,webm"),
            record("wrong-pixel.mp4", "h264", 2.0, 1, pixel_format="yuv444p"),
            record("wrong-audio.mp4", "h264", 3.0, 1, audio="opus"),
            compatible,
            record("hevc.mp4", "hevc", 1.0, 1),
        ]
    )
    assert selected["h264"] == compatible

    with pytest.raises(package.OwnerSamplePackageError, match="^required_preview_codec_missing$"):
        package.select_preview_inputs(
            [
                record("incompatible.mp4", "h264", 1.0, 1, container="webm"),
                record("hevc.mp4", "hevc", 1.0, 1),
            ]
        )


def test_preview_builder_rejects_mislabeled_codec_selection_before_file_or_api_access(
    tmp_path: Path,
) -> None:
    package = _load_module()
    h264 = package.SampleRecord(
        "missing-h264.mp4", 1, 1.0, "mov,mp4", "h264", "aac", "yuv420p", "a" * 64
    )

    with pytest.raises(package.OwnerSamplePackageError, match="^required_preview_codec_missing$"):
        package.build_preview_proofs(
            sample_dir=tmp_path / "does-not-exist",
            selected={"h264": h264, "hevc": h264},
            projects_root=tmp_path / "must-not-be-created",
            ffmpeg_binary="ffmpeg",
            ffprobe_binary="ffprobe",
        )
    assert not (tmp_path / "must-not-be-created").exists()


def test_preview_proofs_use_public_api_and_preserve_source_and_copy_hashes(
    real_samples: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = _load_module()
    renderer_arguments: list[dict] = []
    original_renderer = package.FFmpegBrowserPreviewRenderer
    original_content_probe = package._probe_api_content
    probed_content_urls: list[str] = []

    def capture_renderer(*args, **kwargs):
        renderer_arguments.append(dict(kwargs))
        return original_renderer(*args, **kwargs)

    def capture_content_probe(client, *, content_url, projects_root, ffprobe_binary):
        probed_content_urls.append(content_url)
        return original_content_probe(
            client,
            content_url=content_url,
            projects_root=projects_root,
            ffprobe_binary=ffprobe_binary,
        )

    monkeypatch.setattr(package, "FFmpegBrowserPreviewRenderer", capture_renderer)
    monkeypatch.setattr(package, "_probe_api_content", capture_content_probe)
    before = {path.name: _fingerprint(path) for path in real_samples.iterdir()}
    records = package.inventory_samples(real_samples, ffprobe_binary="ffprobe")
    selected = package.select_preview_inputs(records)

    proofs = package.build_preview_proofs(
        sample_dir=real_samples,
        selected=selected,
        projects_root=tmp_path / "runtime",
        ffmpeg_binary="ffmpeg",
        ffprobe_binary="ffprobe",
    )

    assert proofs["api_import_log"] == [
        {"method": "POST", "path": "/api/projects"},
        {"method": "POST", "path": "/api/projects/{project_id}/assets/broll-video"},
        {"method": "POST", "path": "/api/projects/{project_id}/assets/broll-video"},
    ]
    assert proofs["external_provider_calls"] == 0
    assert renderer_arguments == [
        {"ffmpeg_binary": "ffmpeg", "timeout_seconds": package.PREVIEW_RENDER_TIMEOUT_SECONDS}
    ]
    assert package.PREVIEW_RENDER_TIMEOUT_SECONDS == 45
    assert package.PREVIEW_RENDER_TIMEOUT_SECONDS < package.PREVIEW_TIMEOUT_SECONDS
    assert proofs["project_ref"].startswith("projects/")
    assert set(proofs["previews"]) == {"h264", "hevc"}
    for codec, proof in proofs["previews"].items():
        assert proof["source_name"] == selected[codec].name
        assert proof["source_sha256"] == proof["project_copy_sha256"]
        assert proof["preview_source_sha256"] == proof["project_copy_sha256"]
        assert proof["profile"] == "h264-yuv420p-aac-1280-v1"
        assert proof["project_copy_ref"].startswith("local://projects/")
        assert proof["range_status"] == 206
        assert proof["output_video_codec"] == "h264"
        assert proof["output_pixel_format"] == "yuv420p"
        assert proof["content_url"].startswith("/api/projects/")
        assert "://" not in proof["content_url"]
    assert proofs["previews"]["h264"]["preview_kind"] == "original"
    assert proofs["previews"]["h264"]["content_url"].endswith("/content")
    assert "/browser-preview/content" not in proofs["previews"]["h264"]["content_url"]
    assert proofs["previews"]["hevc"]["preview_kind"] == "proxy"
    assert proofs["previews"]["hevc"]["content_url"].endswith("/browser-preview/content")
    assert probed_content_urls == [
        proofs["previews"]["h264"]["content_url"],
        proofs["previews"]["hevc"]["content_url"],
    ]
    assert proofs["previews"]["h264"]["content_sha256"] == proofs["previews"]["h264"][
        "project_copy_sha256"
    ]
    assert before == {path.name: _fingerprint(path) for path in real_samples.iterdir()}
    serialized = json.dumps(proofs, ensure_ascii=False)
    assert str(real_samples.resolve()) not in serialized
    assert str((tmp_path / "runtime").resolve()) not in serialized


@pytest.mark.parametrize(
    ("field", "wrong_value", "expected_code"),
    [
        ("source_sha256", "0" * 64, "preview_source_identity_mismatch"),
        ("source_sha256", None, "preview_source_identity_mismatch"),
        ("profile", "wrong-profile", "preview_profile_mismatch"),
        ("profile", None, "preview_profile_mismatch"),
    ],
)
def test_preview_proofs_reject_wrong_ready_identity_before_content(
    real_samples: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    wrong_value: str | None,
    expected_code: str,
) -> None:
    package = _load_module()
    selected = package.select_preview_inputs(
        package.inventory_samples(real_samples, ffprobe_binary="ffprobe")
    )
    original_poll = package._poll_preview

    def corrupt_ready_state(*args, **kwargs):
        state = dict(original_poll(*args, **kwargs))
        if wrong_value is None:
            state.pop(field, None)
        else:
            state[field] = wrong_value
        return state

    monkeypatch.setattr(package, "_poll_preview", corrupt_ready_state)
    monkeypatch.setattr(
        package,
        "_probe_api_content",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("content must not be read before identity verification")
        ),
    )
    with pytest.raises(package.OwnerSamplePackageError, match=f"^{expected_code}$"):
        package.build_preview_proofs(
            sample_dir=real_samples,
            selected=selected,
            projects_root=tmp_path / f"runtime-{field}",
            ffmpeg_binary="ffmpeg",
            ffprobe_binary="ffprobe",
        )


def test_h264_public_content_hash_must_match_project_copy(
    real_samples: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = _load_module()
    selected = package.select_preview_inputs(
        package.inventory_samples(real_samples, ffprobe_binary="ffprobe")
    )
    original_probe = package._probe_api_content

    def corrupt_h264_content_hash(client, *, content_url, projects_root, ffprobe_binary):
        result = original_probe(
            client,
            content_url=content_url,
            projects_root=projects_root,
            ffprobe_binary=ffprobe_binary,
        )
        if "/browser-preview/content" not in content_url:
            return result[0], result[1], "0" * 64
        return result

    monkeypatch.setattr(package, "_probe_api_content", corrupt_h264_content_hash)
    with pytest.raises(package.OwnerSamplePackageError, match="^preview_content_hash_mismatch$"):
        package.build_preview_proofs(
            sample_dir=real_samples,
            selected=selected,
            projects_root=tmp_path / "runtime-hash",
            ffmpeg_binary="ffmpeg",
            ffprobe_binary="ffprobe",
        )


def test_preview_poll_waits_for_terminal_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    package = _load_module()

    class Response:
        status_code = 200

        def __init__(self, body):
            self.body = body

        def json(self):
            return self.body

    class Client:
        def __init__(self):
            self.states = [
                {"status": "running"},
                {"status": "failed", "error_code": "PREVIEW_RENDER_FAILED"},
            ]
            self.calls = 0

        def get(self, endpoint):
            self.calls += 1
            return Response(self.states.pop(0))

    client = Client()
    monkeypatch.setattr(package.time, "sleep", lambda _seconds: None)
    with pytest.raises(package.OwnerSamplePackageError, match="^preview_not_ready$"):
        package._poll_preview(client, "/local/status", {"status": "pending"})
    assert client.calls == 2


def test_preview_proofs_fail_closed_when_source_changes(
    real_samples: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = _load_module()
    selected = package.select_preview_inputs(
        package.inventory_samples(real_samples, ffprobe_binary="ffprobe")
    )
    changed = False

    def mutate_then_poll(*args, **kwargs):
        nonlocal changed
        if not changed:
            source = real_samples / selected["h264"].name
            source.write_bytes(source.read_bytes() + b"changed")
            changed = True
        raise package.OwnerSamplePackageError("preview_not_ready")

    monkeypatch.setattr(package, "_poll_preview", mutate_then_poll)
    with pytest.raises(package.OwnerSamplePackageError, match="^source_changed_during_package$"):
        package.build_preview_proofs(
            sample_dir=real_samples,
            selected=selected,
            projects_root=tmp_path / "runtime-mutated",
            ffmpeg_binary="ffmpeg",
            ffprobe_binary="ffprobe",
        )


@pytest.mark.parametrize("replacement_kind", ["deleted", "unreadable", "reparse"])
def test_preview_source_fence_normalizes_inability_and_replacement_over_preview_error(
    real_samples: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    replacement_kind: str,
) -> None:
    package = _load_module()
    selected = package.select_preview_inputs(
        package.inventory_samples(real_samples, ffprobe_binary="ffprobe")
    )
    source = real_samples / selected["h264"].name
    changed = False
    original_reparse_check = package._is_reparse_point

    def mutate_then_fail(*args, **kwargs):
        nonlocal changed
        if not changed:
            stat = source.stat()
            contents = source.read_bytes()
            source.unlink()
            if replacement_kind == "unreadable":
                source.mkdir()
            elif replacement_kind == "reparse":
                outside = tmp_path / "same-content-replacement.mp4"
                outside.write_bytes(contents)
                os.utime(outside, ns=(stat.st_atime_ns, stat.st_mtime_ns))
                try:
                    source.symlink_to(outside)
                except OSError:
                    os.replace(outside, source)
                    monkeypatch.setattr(
                        package,
                        "_is_reparse_point",
                        lambda path: path == source or original_reparse_check(path),
                    )
            changed = True
        raise package.OwnerSamplePackageError("preview_not_ready")

    monkeypatch.setattr(package, "_poll_preview", mutate_then_fail)
    with pytest.raises(package.OwnerSamplePackageError) as captured:
        package.build_preview_proofs(
            sample_dir=real_samples,
            selected=selected,
            projects_root=tmp_path / f"runtime-{replacement_kind}",
            ffmpeg_binary="ffmpeg",
            ffprobe_binary="ffprobe",
        )

    assert str(captured.value) == "source_changed_during_package"
    assert str(real_samples.resolve()) not in str(captured.value)


def test_initial_fingerprint_read_error_keeps_inventory_error_semantics(tmp_path: Path) -> None:
    package = _load_module()

    with pytest.raises(package.OwnerSamplePackageError) as captured:
        package._source_fingerprint(tmp_path / "missing.mp4")

    assert str(captured.value) == "sample_read_failed"


def test_runner_source_has_no_direct_sample_copy_or_asset_registration() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "shutil.copy" not in source
    assert ".register_asset(" not in source
    assert ".content_path(" not in source
    assert ".rglob(" not in source


def _sha256(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _package_fixture(
    package, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path, dict[str, object]]:
    sample_dir = tmp_path / "samples"
    sample_dir.mkdir()
    h264_path = sample_dir / "owner-h264.mp4"
    hevc_path = sample_dir / "owner-hevc.mp4"
    h264_path.write_bytes(b"owner-h264")
    hevc_path.write_bytes(b"owner-hevc")
    records = [
        package.SampleRecord(
            h264_path.name,
            h264_path.stat().st_size,
            1.0,
            "mov,mp4",
            "h264",
            "aac",
            "yuv420p",
            _sha256(h264_path),
        ),
        package.SampleRecord(
            hevc_path.name,
            hevc_path.stat().st_size,
            2.0,
            "mov,mp4",
            "hevc",
            "aac",
            "yuv420p",
            _sha256(hevc_path),
        ),
    ]
    monkeypatch.setattr(package, "inventory_samples", lambda *args, **kwargs: records)
    monkeypatch.setattr(
        package,
        "build_preview_proofs",
        lambda **kwargs: {
            "project_ref": "projects/qa-preview",
            "api_import_log": [],
            "previews": {
                codec: {
                    "source_name": record.name,
                    "source_sha256": record.sha256,
                    "project_copy_ref": f"local://projects/qa-preview/{codec}.mp4",
                    "project_copy_sha256": record.sha256,
                    "preview_source_sha256": record.sha256,
                    "profile": "h264-yuv420p-aac-1280-v1",
                    "preview_kind": "original" if codec == "h264" else "proxy",
                    "content_url": f"/api/projects/qa-preview/{codec}/content",
                    "range_status": 206,
                    "output_video_codec": "h264",
                    "output_pixel_format": "yuv420p",
                    "content_sha256": record.sha256,
                }
                for codec, record in zip(("h264", "hevc"), records, strict=True)
            },
            "external_provider_calls": 0,
        },
    )
    narration = tmp_path / "narration.wav"
    narration.write_bytes(b"bounded narration")
    calls: dict[str, object] = {}

    def edit_runner(**kwargs):
        calls.update(kwargs)
        work_root = Path(kwargs["work_root"])
        artifacts = {
            "srt": work_root / "review" / "captions.srt",
            "exact_preview": work_root / "review" / "exact-preview.mp4",
            "timeline_snapshot": work_root / "review" / "timeline.json",
            "editing_session_snapshot": work_root / "review" / "editing-session.json",
            "ffprobe_summary": work_root / "review" / "ffprobe-summary.json",
            "final_mp4": work_root / "review" / "final.mp4",
            "capcut_draft": work_root / "review" / "draft_content.json",
        }
        for name, path in artifacts.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"{name}\n", encoding="utf-8")
        checks = {
            "broll_controls_in_timeline": True,
            "audio_controls_in_timeline": True,
            "approved_sfx_in_final_and_capcut": True,
            "revised_caption_in_srt": True,
            "approved_tts_in_final_and_capcut": True,
            "image_overlay_in_final_and_capcut": True,
        }
        return {
            "fixture_name": kwargs["fixture_name"],
            "desktop_capcut_opened": False,
            "checks": checks,
            **{
                name: {"path": str(path), "sha256": _sha256(path)}
                for name, path in artifacts.items()
            },
        }

    output_root = tmp_path / "owner-package"
    result = package.build_owner_sample_package(
        sample_dir=sample_dir,
        output_root=output_root,
        narration=narration,
        ffmpeg_binary="ffmpeg-local",
        ffprobe_binary="ffprobe-local",
        edit_flow_runner=edit_runner,
    )
    return output_root, narration, {"result": result, "calls": calls}


def test_review_checklist_is_unchecked_and_never_claims_automatic_approval(
    tmp_path: Path,
) -> None:
    package = _load_module()
    checklist = package.write_review_checklist(tmp_path)
    text = checklist.read_text(encoding="utf-8")

    assert "자동 통과 아님" in text
    assert [line.split(":", 1)[0] for line in text.splitlines() if line.startswith("- [ ] ")] == [
        "- [ ] 영상",
        "- [ ] 자막",
        "- [ ] 목소리",
        "- [ ] 음악",
        "- [ ] 효과음",
        "- [ ] 장면 전환",
        "- [ ] 권리",
        "- [ ] 최종 export",
    ]
    assert "- [x]" not in text.lower()
    assert "승인 완료" not in text


def test_package_uses_audio_ducking_and_records_all_controls_and_false_authorities(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = _load_module()
    package_root, narration, context = _package_fixture(package, tmp_path, monkeypatch)
    manifest = context["result"]
    calls = context["calls"]

    assert calls["fixture_name"] == "audio_ducking"
    assert Path(calls["narration"]) == package_root / "inputs" / "qa-narration.wav"
    assert manifest["controls"] == {
        "broll": True,
        "bgm": True,
        "sfx": True,
        "caption": True,
        "tts": True,
        "explanation_overlay": True,
    }
    assert manifest["authorities"] == {
        "owner_approval": False,
        "rights_approval": False,
        "desktop_edit": False,
        "desktop_export": False,
        "automatic_apply": False,
        "memory_write": False,
        "external_provider_calls": 0,
    }
    assert manifest["narration"]["source_sha256"] == _sha256(narration)
    assert manifest["narration"]["copy_sha256"] == _sha256(Path(calls["narration"]))
    assert manifest["narration"]["source_sha256"] == manifest["narration"]["copy_sha256"]


def test_package_manifest_links_all_review_artifacts_to_source_hashes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = _load_module()
    package_root, _narration, context = _package_fixture(package, tmp_path, monkeypatch)
    manifest = context["result"]

    assert set(manifest["artifacts"]) == {
        "exact_preview",
        "final_mp4",
        "srt",
        "timeline_snapshot",
        "editing_session_snapshot",
        "capcut_draft",
        "ffprobe_summary",
        "review_checklist",
    }
    for evidence in manifest["artifacts"].values():
        assert not Path(evidence["path"]).is_absolute()
        assert ".." not in Path(evidence["path"]).parts
        assert _sha256(package_root / evidence["path"]) == evidence["sha256"]
    assert package.validate_reverse_manifest(package_root, manifest) is None
    serialized = json.dumps(manifest, ensure_ascii=False)
    assert str((tmp_path / "samples").resolve()) not in serialized
    assert str(package_root.resolve()) not in serialized
    assert (package_root / "owner-sample-edit-package.json").is_file()
    assert not (package_root / ".owner-sample-edit-package.json.tmp").exists()


@pytest.mark.parametrize(
    "unsafe_path",
    [
        "../outside.mp4",
        "C:/outside.mp4",
        r"C:\outside.mp4",
        r"\\server\share\outside.mp4",
        "/outside.mp4",
    ],
)
def test_reverse_manifest_rejects_absolute_drive_unc_and_traversal_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, unsafe_path: str
) -> None:
    package = _load_module()
    package_root, _narration, context = _package_fixture(package, tmp_path, monkeypatch)
    manifest = context["result"]
    manifest["artifacts"]["final_mp4"]["path"] = unsafe_path

    with pytest.raises(package.OwnerSamplePackageError, match="^manifest_artifact_path_invalid$"):
        package.validate_reverse_manifest(package_root, manifest)


def test_reverse_manifest_rejects_missing_non_file_symlink_escape_and_sha_tamper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = _load_module()
    package_root, _narration, context = _package_fixture(package, tmp_path, monkeypatch)
    manifest = context["result"]

    missing = json.loads(json.dumps(manifest))
    missing["artifacts"]["final_mp4"]["path"] = "review/missing.mp4"
    with pytest.raises(package.OwnerSamplePackageError, match="^manifest_artifact_missing$"):
        package.validate_reverse_manifest(package_root, missing)

    directory = package_root / "review" / "directory"
    directory.mkdir(parents=True)
    non_file = json.loads(json.dumps(manifest))
    non_file["artifacts"]["final_mp4"]["path"] = "review/directory"
    with pytest.raises(package.OwnerSamplePackageError, match="^manifest_artifact_missing$"):
        package.validate_reverse_manifest(package_root, non_file)

    tampered = json.loads(json.dumps(manifest))
    tampered["artifacts"]["final_mp4"]["sha256"] = "0" * 64
    with pytest.raises(package.OwnerSamplePackageError, match="^manifest_artifact_sha_mismatch$"):
        package.validate_reverse_manifest(package_root, tampered)

    outside = tmp_path / "outside.mp4"
    outside.write_bytes(b"outside")
    link = package_root / "review" / "linked.mp4"
    try:
        link.symlink_to(outside)
    except OSError:
        original = package._is_reparse_point
        link.write_bytes(b"reparse")
        monkeypatch.setattr(
            package,
            "_is_reparse_point",
            lambda path: path == link or original(path),
        )
    escaped = json.loads(json.dumps(manifest))
    escaped["artifacts"]["final_mp4"] = {
        "path": "review/linked.mp4",
        "sha256": _sha256(outside if link.is_symlink() else link),
    }
    with pytest.raises(package.OwnerSamplePackageError, match="^manifest_artifact_path_invalid$"):
        package.validate_reverse_manifest(package_root, escaped)


def test_reverse_manifest_rejects_malformed_unbounded_or_non_resolving_graph(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = _load_module()
    package_root, _narration, context = _package_fixture(package, tmp_path, monkeypatch)
    manifest = context["result"]

    cycle = json.loads(json.dumps(manifest))
    cycle["reverse_trace"]["nodes"]["source_sha:h264"]["upstream"] = [
        "artifact:final_mp4"
    ]
    with pytest.raises(package.OwnerSamplePackageError, match="^manifest_reverse_trace_invalid$"):
        package.validate_reverse_manifest(package_root, cycle)

    disconnected = json.loads(json.dumps(manifest))
    disconnected["reverse_trace"]["nodes"]["artifact:final_mp4"]["upstream"] = []
    with pytest.raises(package.OwnerSamplePackageError, match="^manifest_reverse_trace_invalid$"):
        package.validate_reverse_manifest(package_root, disconnected)

    unbounded = json.loads(json.dumps(manifest))
    for index in range(package.MAX_REVERSE_TRACE_NODES + 1):
        unbounded["reverse_trace"]["nodes"][f"extra:{index}"] = {
            "kind": "source_sha",
            "sha256": "a" * 64,
            "upstream": [],
        }
    with pytest.raises(package.OwnerSamplePackageError, match="^manifest_reverse_trace_invalid$"):
        package.validate_reverse_manifest(package_root, unbounded)

    too_many_artifacts = json.loads(json.dumps(manifest))
    template = too_many_artifacts["artifacts"]["final_mp4"]
    for index in range(package.MAX_MANIFEST_ARTIFACTS + 1):
        too_many_artifacts["artifacts"][f"extra_{index}"] = dict(template)
    with pytest.raises(package.OwnerSamplePackageError, match="^manifest_artifacts_invalid$"):
        package.validate_reverse_manifest(package_root, too_many_artifacts)

    leaked = json.loads(json.dumps(manifest))
    leaked["source_inventory"][0]["source_path"] = str(
        (tmp_path / "secret" / "owner.mp4").resolve()
    )
    with pytest.raises(package.OwnerSamplePackageError, match="^manifest_source_inventory_invalid$"):
        package.validate_reverse_manifest(package_root, leaked)

    leaked_preview = json.loads(json.dumps(manifest))
    leaked_preview["preview_proofs"]["previews"]["h264"]["source_path"] = str(
        (tmp_path / "secret" / "owner-h264.mp4").resolve()
    )
    with pytest.raises(package.OwnerSamplePackageError, match="^manifest_preview_proof_invalid$"):
        package.validate_reverse_manifest(package_root, leaked_preview)

    leaked_top_level = json.loads(json.dumps(manifest))
    leaked_top_level["source_path"] = str((tmp_path / "secret" / "owner.mp4").resolve())
    with pytest.raises(package.OwnerSamplePackageError, match="^manifest_schema_invalid$"):
        package.validate_reverse_manifest(package_root, leaked_top_level)

    invalid_narration = json.loads(json.dumps(manifest))
    invalid_narration["narration"]["copy_sha256"] = "0" * 64
    invalid_narration["reverse_trace"]["nodes"]["copied_asset:narration"]["sha256"] = (
        "0" * 64
    )
    with pytest.raises(package.OwnerSamplePackageError, match="^manifest_narration_invalid$"):
        package.validate_reverse_manifest(package_root, invalid_narration)

    leaked_trace = json.loads(json.dumps(manifest))
    leaked_trace["reverse_trace"]["nodes"]["source_sha:h264"]["source_path"] = str(
        (tmp_path / "secret" / "owner-h264.mp4").resolve()
    )
    with pytest.raises(package.OwnerSamplePackageError, match="^manifest_reverse_trace_invalid$"):
        package.validate_reverse_manifest(package_root, leaked_trace)


def test_package_rejects_existing_nonempty_root_before_running_edit_flow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = _load_module()
    sample_dir = tmp_path / "samples"
    sample_dir.mkdir()
    output_root = tmp_path / "owner-package"
    output_root.mkdir()
    marker = output_root / "owner-evidence.txt"
    marker.write_text("preserve", encoding="utf-8")
    monkeypatch.setattr(
        package,
        "inventory_samples",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must fail before inventory")),
    )

    with pytest.raises(package.OwnerSamplePackageError, match="^package_root_not_empty$"):
        package.build_owner_sample_package(
            sample_dir=sample_dir,
            output_root=output_root,
            narration=tmp_path / "missing.wav",
            ffmpeg_binary="ffmpeg",
            ffprobe_binary="ffprobe",
            edit_flow_runner=lambda **kwargs: {},
        )
    assert marker.read_text(encoding="utf-8") == "preserve"


def test_package_rejects_output_inside_sample_directory_without_creating_it(
    tmp_path: Path,
) -> None:
    package = _load_module()
    sample_dir = tmp_path / "samples"
    sample_dir.mkdir()
    output_root = sample_dir / "must-not-be-created"

    with pytest.raises(package.OwnerSamplePackageError, match="^package_root_overlaps_samples$"):
        package.build_owner_sample_package(
            sample_dir=sample_dir,
            output_root=output_root,
            narration=tmp_path / "missing.wav",
            ffmpeg_binary="ffmpeg",
            ffprobe_binary="ffprobe",
            edit_flow_runner=lambda **kwargs: {},
        )
    assert not output_root.exists()


def test_package_rejects_missing_sample_root_before_creating_output(tmp_path: Path) -> None:
    package = _load_module()
    output_root = tmp_path / "must-not-be-created"

    with pytest.raises(package.OwnerSamplePackageError, match="^sample_directory_invalid$"):
        package.build_owner_sample_package(
            sample_dir=tmp_path / "missing-samples",
            output_root=output_root,
            narration=tmp_path / "missing.wav",
            ffmpeg_binary="ffmpeg",
            ffprobe_binary="ffprobe",
            edit_flow_runner=lambda **kwargs: {},
        )
    assert not output_root.exists()


def test_missing_default_narration_uses_checked_in_local_generator_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = _load_module()
    missing_default = tmp_path / "artifacts" / "task5-korean-600.wav"
    monkeypatch.setattr(package, "DEFAULT_NARRATION_PATH", missing_default)
    generated: list[dict[str, object]] = []

    def generate(target: Path, *, ffmpeg_binary: str, ffprobe_binary: str) -> None:
        generated.append(
            {
                "target": target,
                "ffmpeg_binary": ffmpeg_binary,
                "ffprobe_binary": ffprobe_binary,
            }
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"generated local narration")

    monkeypatch.setattr(package, "_run_narration_generator", generate, raising=False)
    sample_dir = tmp_path / "samples"
    sample_dir.mkdir()
    monkeypatch.setattr(package, "inventory_samples", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        package,
        "select_preview_inputs",
        lambda records: (_ for _ in ()).throw(package.OwnerSamplePackageError("stop_after_narration")),
    )

    with pytest.raises(package.OwnerSamplePackageError, match="^stop_after_narration$"):
        package.build_owner_sample_package(
            sample_dir=sample_dir,
            output_root=tmp_path / "owner-package",
            narration=missing_default,
            ffmpeg_binary="ffmpeg-local",
            ffprobe_binary="ffprobe-local",
            edit_flow_runner=lambda **kwargs: {},
        )
    assert generated == [
        {
            "target": tmp_path / "owner-package" / "inputs" / "qa-narration.wav",
            "ffmpeg_binary": "ffmpeg-local",
            "ffprobe_binary": "ffprobe-local",
        }
    ]


def test_manifest_publish_failure_exposes_no_final_or_partial_manifest_but_keeps_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = _load_module()
    original_replace = Path.replace

    def fail_manifest_replace(path: Path, target: Path):
        if path.name == ".owner-sample-edit-package.json.tmp":
            raise OSError("simulated publish failure")
        return original_replace(path, target)

    monkeypatch.setattr(Path, "replace", fail_manifest_replace)
    with pytest.raises(package.OwnerSamplePackageError, match="^manifest_publish_failed$"):
        _package_fixture(package, tmp_path, monkeypatch)

    package_root = tmp_path / "owner-package"
    assert (package_root / "edit" / "review" / "final.mp4").is_file()
    assert not (package_root / "owner-sample-edit-package.json").exists()
    assert not (package_root / ".owner-sample-edit-package.json.tmp").exists()


def test_final_source_fence_failure_occurs_before_manifest_publish(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = _load_module()
    monkeypatch.setattr(
        package,
        "_assert_final_source_fence",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            package.OwnerSamplePackageError("source_changed_during_package")
        ),
    )

    with pytest.raises(package.OwnerSamplePackageError, match="^source_changed_during_package$"):
        _package_fixture(package, tmp_path, monkeypatch)

    package_root = tmp_path / "owner-package"
    assert (package_root / "edit" / "review" / "final.mp4").is_file()
    assert not (package_root / "owner-sample-edit-package.json").exists()
    assert not (package_root / ".owner-sample-edit-package.json.tmp").exists()
