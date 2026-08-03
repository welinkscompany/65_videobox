from __future__ import annotations

import dataclasses
import importlib.util
import json
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

    def record(name: str, codec: str, duration: float, size: int):
        return package.SampleRecord(name, size, duration, "mov,mp4", codec, "aac", "yuv420p", name * 8)

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
    real_samples: Path, tmp_path: Path
) -> None:
    package = _load_module()
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
    assert proofs["project_ref"].startswith("projects/")
    assert set(proofs["previews"]) == {"h264", "hevc"}
    for codec, proof in proofs["previews"].items():
        assert proof["source_name"] == selected[codec].name
        assert proof["source_sha256"] == proof["project_copy_sha256"]
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
    assert before == {path.name: _fingerprint(path) for path in real_samples.iterdir()}
    serialized = json.dumps(proofs, ensure_ascii=False)
    assert str(real_samples.resolve()) not in serialized
    assert str((tmp_path / "runtime").resolve()) not in serialized


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


def test_runner_source_has_no_direct_sample_copy_or_asset_registration() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "shutil.copy" not in source
    assert ".register_asset(" not in source
    assert ".content_path(" not in source
