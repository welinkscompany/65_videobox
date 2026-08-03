from __future__ import annotations

import dataclasses
import importlib.util
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
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
        assert proof["asset_ref"].startswith("assets/")
    assert proofs["previews"]["h264"]["preview_kind"] == "original"
    assert proofs["previews"]["h264"]["proxy_artifact_ref"] is None
    assert proofs["previews"]["h264"]["content_url"].endswith("/content")
    assert "/browser-preview/content" not in proofs["previews"]["h264"]["content_url"]
    assert proofs["previews"]["hevc"]["preview_kind"] == "proxy"
    proxy_ref = proofs["previews"]["hevc"]["proxy_artifact_ref"]
    assert isinstance(proxy_ref, str) and not Path(proxy_ref).is_absolute()
    proxy_path = tmp_path / "runtime" / proxy_ref
    assert proxy_path.is_file()
    assert _sha256(proxy_path) == proofs["previews"]["hevc"]["content_sha256"]
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


def test_preview_proxy_temp_unlink_failure_preserves_main_error_and_clears_standard_temp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = _load_module()
    destination = tmp_path / "review" / "hevc-browser-preview.mp4"
    temporary = destination.with_suffix(".mp4.tmp")
    original_unlink = Path.unlink

    class Response:
        status_code = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def iter_bytes(self, *, chunk_size: int):
            del chunk_size
            yield b"proxy bytes"

    class Client:
        def stream(self, method: str, url: str):
            assert method == "GET"
            assert url == "/preview"
            return Response()

    monkeypatch.setattr(
        Path,
        "unlink",
        lambda self, *args, **kwargs: (
            (_ for _ in ()).throw(OSError("simulated standard temp unlink failure"))
            if self == temporary
            else original_unlink(self, *args, **kwargs)
        ),
    )
    with pytest.raises(package.OwnerSamplePackageError, match="^preview_content_hash_mismatch$"):
        package._preserve_preview_content(
            Client(),
            content_url="/preview",
            destination=destination,
            expected_sha256="0" * 64,
        )

    assert not temporary.exists()


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
    def preview_builder(**kwargs):
        projects_root = Path(kwargs["projects_root"])
        project_root = projects_root / "projects" / "qa-preview"
        source_paths = {"h264": h264_path, "hevc": hevc_path}
        for codec, source in source_paths.items():
            copy = project_root / "assets" / source.name
            copy.parent.mkdir(parents=True, exist_ok=True)
            copy.write_bytes(source.read_bytes())
        proxy = projects_root / "review" / "hevc-browser-preview.mp4"
        proxy.parent.mkdir(parents=True, exist_ok=True)
        proxy.write_bytes(b"bounded h264 proxy evidence")
        return {
            "project_ref": "projects/qa-preview",
            "api_import_log": [
                {"method": "POST", "path": "/api/projects"},
                {
                    "method": "POST",
                    "path": "/api/projects/{project_id}/assets/broll-video",
                },
                {
                    "method": "POST",
                    "path": "/api/projects/{project_id}/assets/broll-video",
                },
            ],
            "previews": {
                codec: {
                    "asset_ref": f"assets/{codec}-asset",
                    "source_name": record.name,
                    "source_sha256": record.sha256,
                    "project_copy_ref": (
                        f"local://projects/qa-preview/assets/{source_paths[codec].name}"
                    ),
                    "project_copy_sha256": record.sha256,
                    "preview_source_sha256": record.sha256,
                    "profile": "h264-yuv420p-aac-1280-v1",
                    "preview_kind": "original" if codec == "h264" else "proxy",
                    "content_url": (
                        f"/api/projects/qa-preview/assets/{codec}-asset/content"
                        if codec == "h264"
                        else f"/api/projects/qa-preview/assets/{codec}-asset/browser-preview/content"
                    ),
                    "range_status": 206,
                    "output_video_codec": "h264",
                    "output_pixel_format": "yuv420p",
                    "content_sha256": record.sha256 if codec == "h264" else _sha256(proxy),
                    "proxy_artifact_ref": (
                        None if codec == "h264" else "review/hevc-browser-preview.mp4"
                    ),
                }
                for codec, record in zip(("h264", "hevc"), records, strict=True)
            },
            "external_provider_calls": 0,
        }

    monkeypatch.setattr(package, "build_preview_proofs", preview_builder)
    narration = tmp_path / "narration.wav"
    narration.write_bytes(b"bounded narration")
    calls: dict[str, object] = {}

    def edit_runner(**kwargs):
        calls.update(kwargs)
        work_root = Path(kwargs["work_root"])
        broll_source = Path(kwargs["broll_source"])
        broll_sha = _sha256(broll_source)
        broll_asset_id = "owner-broll-asset"
        broll_storage_ref = "local://projects/edit-owner/assets/owner-h264.mp4"
        edit_assets = work_root / "projects" / "projects" / "edit-owner" / "assets"
        edit_assets.mkdir(parents=True, exist_ok=True)
        (edit_assets / "owner-h264.mp4").write_bytes(broll_source.read_bytes())
        (edit_assets / "qa-narration.wav").write_bytes(
            Path(kwargs["narration"]).read_bytes()
        )
        controls = {"fit": "fit", "loop": True, "pad": False, "trim_start_sec": 0.0}
        audio_controls = {
            "gain_db": -6.0,
            "fade_in_sec": 0.5,
            "fade_out_sec": 0.5,
            "ducking": True,
        }
        timeline = {
            "timeline_id": "timeline-owner",
            "tracks": [
                {
                    "track_type": "broll",
                    "clips": [
                        {
                            "asset_id": broll_asset_id,
                            "asset_uri": broll_storage_ref,
                            "media_controls": controls,
                        }
                    ],
                },
                {"track_type": "bgm", "clips": [{"media_controls": audio_controls}]},
                {"track_type": "sfx", "clips": [{"media_controls": audio_controls}]},
            ],
            "applied_recommendations": [
                {"recommendation_type": "broll", "selected_asset_id": broll_asset_id},
                {
                    "recommendation_type": "tts_replacement",
                    "payload": {"selected_asset_uri": "local://projects/edit-owner/tts_candidate.wav"},
                },
                {"recommendation_type": "sfx", "selected_asset_id": "sfx-asset"},
                {"recommendation_type": "image_overlay", "selected_asset_id": "overlay-asset"},
            ],
        }
        session = {
            "session_id": "session-owner",
            "session_revision": 7,
            "timeline_id": "timeline-owner",
            "segments": [
                {
                    "segment_id": "seg_001",
                    "broll_override": {"asset_id": broll_asset_id, "media_controls": controls},
                    "music_override": {"asset_id": "bgm-asset", "media_controls": audio_controls},
                    "sfx_override": {"asset_id": "sfx-asset", "media_controls": audio_controls},
                    "tts_replacement": {"asset_id": "tts-asset"},
                    "caption_override": package.REVISED_CAPTION,
                    "image_overlay": {"asset_id": "overlay-asset"},
                    "explanation_card": {"text": "SMOKE OVERLAY"},
                }
            ],
        }
        artifacts = {
            "srt": work_root / "review" / "captions.srt",
            "exact_preview": work_root / "review" / "exact-preview.mp4",
            "timeline_snapshot": work_root / "review" / "timeline.json",
            "editing_session_snapshot": work_root / "review" / "editing-session.json",
            "ffprobe_summary": work_root / "review" / "ffprobe-summary.json",
            "final_mp4": work_root / "review" / "final.mp4",
            "capcut_draft": work_root / "review" / "draft_content.json",
        }
        for path in artifacts.values():
            path.parent.mkdir(parents=True, exist_ok=True)
        artifacts["srt"].write_text(
            f"1\n00:00:00,000 --> 00:00:05,000\n{package.REVISED_CAPTION}\n",
            encoding="utf-8",
        )
        artifacts["exact_preview"].write_bytes(b"injected-valid-exact-media")
        artifacts["timeline_snapshot"].write_text(json.dumps(timeline, ensure_ascii=False), encoding="utf-8")
        artifacts["editing_session_snapshot"].write_text(json.dumps(session, ensure_ascii=False), encoding="utf-8")
        media_summary = {
            "exact_preview": {
                "duration_sec": 5.0,
                "format": "mov,mp4",
                "video_codec": "h264",
                "pixel_format": "yuv420p",
                "audio_codec": "aac",
            },
            "final_mp4": {
                "duration_sec": 600.0,
                "format": "mov,mp4",
                "video_codec": "h264",
                "pixel_format": "yuv420p",
                "audio_codec": "aac",
            },
        }
        artifacts["ffprobe_summary"].write_text(json.dumps(media_summary), encoding="utf-8")
        artifacts["final_mp4"].write_bytes(b"injected-valid-final-media")
        artifacts["capcut_draft"].write_text(
            json.dumps(
                {
                    "assets": [
                        broll_source.name,
                        "tts_candidate.wav",
                        "smoke-impact.wav",
                        "smoke-bgm.wav",
                        "smoke-overlay.png",
                        "SMOKE OVERLAY",
                    ]
                }
            ),
            encoding="utf-8",
        )
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
            "edit_input_evidence": {
                "explicit_broll_enabled": True,
                "edit_project_ref": "projects/edit-owner",
                "broll_asset_ref": f"assets/{broll_asset_id}",
                "broll_storage_ref": broll_storage_ref,
                "broll_source_name": broll_source.name,
                "broll_source_sha256": broll_sha,
                "broll_copy_sha256": broll_sha,
                "narration_asset_ref": "assets/narration-asset",
                "narration_storage_ref": "local://projects/edit-owner/assets/qa-narration.wav",
                "narration_source_sha256": _sha256(Path(kwargs["narration"])),
                "narration_copy_sha256": _sha256(Path(kwargs["narration"])),
                "session_ref": "editing-sessions/session-owner",
                "timeline_ref": "timelines/timeline-owner",
                "session_revision": 7,
            },
            **{
                name: {"path": str(path), "sha256": _sha256(path)}
                for name, path in artifacts.items()
            },
        }

    output_root = tmp_path / "owner-package"
    def media_probe(path: Path) -> dict[str, object]:
        duration = 5.0 if path.name == "exact-preview.mp4" else 600.0
        return {
            "duration_sec": duration,
            "format": "mov,mp4",
            "video_codec": "h264",
            "pixel_format": "yuv420p",
            "audio_codec": "aac",
        }

    result = package.build_owner_sample_package(
        sample_dir=sample_dir,
        output_root=output_root,
        narration=narration,
        ffmpeg_binary="ffmpeg-local",
        ffprobe_binary="ffprobe-local",
        edit_flow_runner=edit_runner,
        media_probe=media_probe,
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
    assert calls["project_name"] == "owner-qa"
    assert calls["require_image_overlay"] is True
    assert Path(calls["narration"]) == package_root / "inputs" / "qa-narration.wav"
    assert Path(calls["broll_source"]).is_file()
    assert Path(calls["broll_source"]).is_relative_to(package_root / "projects")
    assert calls["expected_broll_sha256"] == manifest["selected_sources"]["h264"]["sha256"]
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


def test_owner_edit_project_name_keeps_default_exact_preview_under_windows_legacy_path_budget() -> None:
    package = _load_module()
    expected_destination = (
        package.REPOSITORY_ROOT
        / "artifacts"
        / "owner-sample-edit-20260803T235959Z"
        / "edit"
        / "projects"
        / "projects"
        / package.OWNER_EDIT_PROJECT_NAME
        / "derived"
        / "exact_previews"
        / f"exact_preview_{'f' * 32}.mp4"
    )

    assert package.OWNER_EDIT_PROJECT_NAME == "owner-qa"
    assert len(str(expected_destination)) <= 259


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


def test_reverse_manifest_binds_artifact_hashes_to_editing_state_and_typed_controls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = _load_module()
    package_root, _narration, context = _package_fixture(package, tmp_path, monkeypatch)
    manifest = context["result"]
    nodes = manifest["reverse_trace"]["nodes"]

    assert "typed_controls:applied" in nodes
    assert nodes["typed_controls:applied"]["controls"] == manifest["controls"]
    assert nodes["editing_session:current"]["editing_session_sha256"] == manifest[
        "artifacts"
    ]["editing_session_snapshot"]["sha256"]
    assert nodes["editing_session:current"]["timeline_sha256"] == manifest["artifacts"][
        "timeline_snapshot"
    ]["sha256"]
    for artifact, row in manifest["artifacts"].items():
        assert nodes[f"artifact:{artifact}"]["sha256"] == row["sha256"]
    assert nodes["artifact:review_checklist"]["upstream"] == [
        "human_review_contract:checklist"
    ]
    assert nodes["human_review_contract:checklist"]["upstream"] == []
    for artifact in set(manifest["artifacts"]) - {"review_checklist"}:
        assert nodes[f"artifact:{artifact}"]["upstream"] == ["editing_session:current"]

    final_path = package_root / manifest["artifacts"]["final_mp4"]["path"]
    final_path.write_bytes(b"unrelated replacement artifact")
    manifest["artifacts"]["final_mp4"]["sha256"] = _sha256(final_path)
    with pytest.raises(package.OwnerSamplePackageError, match="^manifest_reverse_trace_invalid$"):
        package.validate_reverse_manifest(package_root, manifest)


def test_reverse_manifest_cross_binds_preview_inventory_graph_and_actual_project_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = _load_module()
    package_root, _narration, context = _package_fixture(package, tmp_path, monkeypatch)
    manifest = context["result"]

    rewritten = json.loads(json.dumps(manifest))
    replacement_sha = "0" * 64
    proof = rewritten["preview_proofs"]["previews"]["h264"]
    proof["source_sha256"] = replacement_sha
    proof["preview_source_sha256"] = replacement_sha
    proof["project_copy_sha256"] = replacement_sha
    proof["content_sha256"] = replacement_sha
    rewritten["reverse_trace"]["nodes"]["copied_asset:h264"]["sha256"] = replacement_sha
    rewritten["reverse_trace"]["nodes"]["source_sha:h264"]["sha256"] = replacement_sha
    with pytest.raises(package.OwnerSamplePackageError, match="^manifest_preview_proof_invalid$"):
        package.validate_reverse_manifest(package_root, rewritten)

    store = package.LocalProjectStore(package_root / "projects")
    project_copy = store.resolve_storage_uri(
        project_id="qa-preview",
        storage_uri=manifest["preview_proofs"]["previews"]["hevc"]["project_copy_ref"],
    )
    project_copy.write_bytes(project_copy.read_bytes() + b"tampered")
    with pytest.raises(package.OwnerSamplePackageError, match="^manifest_project_copy_invalid$"):
        package.validate_reverse_manifest(package_root, manifest)


def test_reverse_manifest_rejects_reparse_project_copy_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = _load_module()
    package_root, _narration, context = _package_fixture(package, tmp_path, monkeypatch)
    manifest = context["result"]
    projects_root = package_root / "projects"
    original = package._is_reparse_point
    monkeypatch.setattr(
        package,
        "_is_reparse_point",
        lambda path: path == projects_root or original(path),
    )

    with pytest.raises(package.OwnerSamplePackageError, match="^manifest_project_copy_invalid$"):
        package.validate_reverse_manifest(package_root, manifest)


def test_reverse_manifest_rejects_other_project_url_and_proxy_file_tamper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = _load_module()
    package_root, _narration, context = _package_fixture(package, tmp_path, monkeypatch)
    manifest = context["result"]

    other_project = json.loads(json.dumps(manifest))
    other_project["preview_proofs"]["previews"]["h264"]["content_url"] = (
        "/api/projects/other/assets/h264-asset/content"
    )
    with pytest.raises(package.OwnerSamplePackageError, match="^manifest_preview_proof_invalid$"):
        package.validate_reverse_manifest(package_root, other_project)

    proxy_ref = manifest["preview_proofs"]["previews"]["hevc"]["proxy_artifact_ref"]
    proxy = package_root / "projects" / proxy_ref
    proxy.write_bytes(proxy.read_bytes() + b"tampered")
    with pytest.raises(package.OwnerSamplePackageError, match="^manifest_preview_proxy_invalid$"):
        package.validate_reverse_manifest(package_root, manifest)


def test_reverse_manifest_rejects_disconnected_typed_control_or_preview_branch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = _load_module()
    package_root, _narration, context = _package_fixture(package, tmp_path, monkeypatch)
    manifest = context["result"]
    nodes = manifest["reverse_trace"]["nodes"]
    assert "typed_controls:applied" in nodes

    disconnected = json.loads(json.dumps(manifest))
    disconnected["reverse_trace"]["nodes"]["typed_controls:applied"]["upstream"].remove(
        "copied_asset:edit_h264"
    )
    with pytest.raises(package.OwnerSamplePackageError, match="^manifest_reverse_trace_invalid$"):
        package.validate_reverse_manifest(package_root, disconnected)

    detached = json.loads(json.dumps(manifest))
    detached["reverse_trace"]["nodes"]["preview:h264"]["upstream"] = [
        "source_sha:h264"
    ]
    with pytest.raises(package.OwnerSamplePackageError, match="^manifest_reverse_trace_invalid$"):
        package.validate_reverse_manifest(package_root, detached)


def test_structured_edit_validation_rejects_timeline_identity_srt_capcut_and_media_mutations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = _load_module()
    package_root, _narration, context = _package_fixture(package, tmp_path, monkeypatch)
    manifest = context["result"]
    inventory = {row["name"]: row for row in manifest["source_inventory"]}
    h264_row = inventory[manifest["selected_sources"]["h264"]["name"]]
    selected = package.SampleRecord(**h264_row)
    edit_result = {"edit_input_evidence": manifest["edit_input_evidence"]}
    artifacts = manifest["artifacts"]

    def probe(path: Path) -> dict[str, object]:
        return {
            "duration_sec": 5.0 if "exact" in path.name else 600.0,
            "format": "mov,mp4",
            "video_codec": "h264",
            "pixel_format": "yuv420p",
            "audio_codec": "aac",
        }

    def validate() -> None:
        package._validate_structured_edit_evidence(
            package_root=package_root,
            edit_result=edit_result,
            artifacts=artifacts,
            narration=manifest["narration"],
            selected_h264=selected,
            media_probe=probe,
        )

    timeline_path = package_root / artifacts["timeline_snapshot"]["path"]
    original_timeline = timeline_path.read_text(encoding="utf-8")
    timeline = json.loads(original_timeline)
    timeline["tracks"][0]["clips"][0]["asset_id"] = "wrong-owner-asset"
    timeline_path.write_text(json.dumps(timeline), encoding="utf-8")
    with pytest.raises(package.OwnerSamplePackageError, match="^edit_structure_invalid$"):
        validate()
    timeline_path.write_text(original_timeline, encoding="utf-8")

    srt_path = package_root / artifacts["srt"]["path"]
    original_srt = srt_path.read_text(encoding="utf-8")
    srt_path.write_text("wrong caption", encoding="utf-8")
    with pytest.raises(package.OwnerSamplePackageError, match="^edit_srt_invalid$"):
        validate()
    srt_path.write_text(original_srt, encoding="utf-8")

    capcut_path = package_root / artifacts["capcut_draft"]["path"]
    original_capcut = capcut_path.read_text(encoding="utf-8")
    capcut_path.write_text("{}", encoding="utf-8")
    with pytest.raises(package.OwnerSamplePackageError, match="^edit_capcut_invalid$"):
        validate()
    capcut_path.write_text(original_capcut, encoding="utf-8")

    summary_path = package_root / artifacts["ffprobe_summary"]["path"]
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["exact_preview"]["duration_sec"] = 1.0
    summary_path.write_text(json.dumps(summary), encoding="utf-8")
    with pytest.raises(package.OwnerSamplePackageError, match="^edit_media_invalid$"):
        validate()


@pytest.mark.parametrize("mutation", ["tracks_none", "clips_none", "segments_none"])
def test_edit_structure_shapes_are_bounded_in_build_and_stored_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: str
) -> None:
    package = _load_module()
    package_root, _narration, context = _package_fixture(package, tmp_path, monkeypatch)
    manifest = context["result"]
    inventory = {row["name"]: row for row in manifest["source_inventory"]}
    selected = package.SampleRecord(
        **inventory[manifest["selected_sources"]["h264"]["name"]]
    )
    artifact_key = "editing_session_snapshot" if mutation == "segments_none" else "timeline_snapshot"
    target = package_root / manifest["artifacts"][artifact_key]["path"]
    payload = json.loads(target.read_text(encoding="utf-8"))
    if mutation == "tracks_none":
        payload["tracks"] = None
    elif mutation == "clips_none":
        payload["tracks"][0]["clips"] = None
    else:
        payload["segments"] = None
    target.write_text(json.dumps(payload), encoding="utf-8")

    def probe(path: Path) -> dict[str, object]:
        return {
            "duration_sec": 5.0 if "exact" in path.name else 600.0,
            "format": "mov,mp4",
            "video_codec": "h264",
            "pixel_format": "yuv420p",
            "audio_codec": "aac",
        }

    with pytest.raises(package.OwnerSamplePackageError, match="^edit_structure_invalid$"):
        package._validate_structured_edit_evidence(
            package_root=package_root,
            edit_result={"edit_input_evidence": manifest["edit_input_evidence"]},
            artifacts=manifest["artifacts"],
            narration=manifest["narration"],
            selected_h264=selected,
            media_probe=probe,
        )

    changed_sha = _sha256(target)
    manifest["artifacts"][artifact_key]["sha256"] = changed_sha
    manifest["reverse_trace"]["nodes"][f"artifact:{artifact_key}"]["sha256"] = changed_sha
    graph_key = (
        "editing_session_sha256"
        if artifact_key == "editing_session_snapshot"
        else "timeline_sha256"
    )
    manifest["reverse_trace"]["nodes"]["editing_session:current"][graph_key] = changed_sha
    with pytest.raises(package.OwnerSamplePackageError, match="^manifest_edit_input_invalid$"):
        package.validate_reverse_manifest(package_root, manifest)


def test_invalid_utf8_srt_is_bounded_in_build_and_stored_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = _load_module()
    package_root, _narration, context = _package_fixture(package, tmp_path, monkeypatch)
    manifest = context["result"]
    inventory = {row["name"]: row for row in manifest["source_inventory"]}
    selected = package.SampleRecord(
        **inventory[manifest["selected_sources"]["h264"]["name"]]
    )
    srt = package_root / manifest["artifacts"]["srt"]["path"]
    srt.write_bytes(b"\xff\xfe\xfa")

    with pytest.raises(package.OwnerSamplePackageError, match="^edit_srt_invalid$"):
        package._validate_structured_edit_evidence(
            package_root=package_root,
            edit_result={"edit_input_evidence": manifest["edit_input_evidence"]},
            artifacts=manifest["artifacts"],
            narration=manifest["narration"],
            selected_h264=selected,
            media_probe=lambda path: {},
        )

    changed_sha = _sha256(srt)
    manifest["artifacts"]["srt"]["sha256"] = changed_sha
    manifest["reverse_trace"]["nodes"]["artifact:srt"]["sha256"] = changed_sha
    with pytest.raises(package.OwnerSamplePackageError, match="^edit_srt_invalid$"):
        package.validate_reverse_manifest(package_root, manifest)


def test_edit_artifact_oversize_is_rejected_before_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = _load_module()
    package_root, _narration, context = _package_fixture(package, tmp_path, monkeypatch)
    manifest = context["result"]
    target = package_root / manifest["artifacts"]["final_mp4"]["path"]
    with target.open("r+b") as stream:
        stream.truncate(package.MAX_ARTIFACT_BYTES + 1)
    edit_result = {
        key: {
            "path": str(package_root / manifest["artifacts"][key]["path"]),
            "sha256": manifest["artifacts"][key]["sha256"],
        }
        for key in package.EDIT_RESULT_ARTIFACT_KEYS
    }
    original_hash = package._sha256
    monkeypatch.setattr(
        package,
        "_sha256",
        lambda path: (
            (_ for _ in ()).throw(AssertionError("oversize artifact must not hash"))
            if path == target.resolve()
            else original_hash(path)
        ),
    )

    with pytest.raises(package.OwnerSamplePackageError, match="^edit_artifact_size_exceeded$"):
        package._artifact_evidence_from_edit(
            package_root=package_root,
            edit_result=edit_result,
            checklist_path=package_root / manifest["artifacts"]["review_checklist"]["path"],
        )


def test_stored_manifest_rejects_forged_edit_input_even_when_graph_is_mirrored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = _load_module()
    package_root, _narration, context = _package_fixture(package, tmp_path, monkeypatch)
    manifest = context["result"]

    forged = json.loads(json.dumps(manifest))
    forged["edit_input_evidence"]["broll_source_sha256"] = "0" * 64
    forged["edit_input_evidence"]["broll_copy_sha256"] = "0" * 64
    forged["edit_input_evidence"]["narration_source_sha256"] = "1" * 64
    forged["edit_input_evidence"]["narration_copy_sha256"] = "1" * 64
    forged["reverse_trace"]["nodes"]["copied_asset:edit_h264"]["sha256"] = "0" * 64
    forged["reverse_trace"]["nodes"]["copied_asset:edit_narration"]["sha256"] = "1" * 64

    with pytest.raises(package.OwnerSamplePackageError, match="^manifest_edit_input_invalid$"):
        package.validate_reverse_manifest(package_root, forged)


def test_stored_manifest_rejects_edit_input_path_leak_copy_tamper_and_cross_project_uri(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = _load_module()
    package_root, _narration, context = _package_fixture(package, tmp_path, monkeypatch)
    manifest = context["result"]

    leaked = json.loads(json.dumps(manifest))
    leaked["edit_input_evidence"]["source_path"] = r"C:\secret\owner.mp4"
    with pytest.raises(package.OwnerSamplePackageError, match="^manifest_edit_input_invalid$"):
        package.validate_reverse_manifest(package_root, leaked)

    invalid_type = json.loads(json.dumps(manifest))
    invalid_type["edit_input_evidence"]["broll_storage_ref"] = None
    with pytest.raises(package.OwnerSamplePackageError, match="^manifest_edit_input_invalid$"):
        package.validate_reverse_manifest(package_root, invalid_type)

    broll_copy = (
        package_root
        / "edit"
        / "projects"
        / "projects"
        / "edit-owner"
        / "assets"
        / "owner-h264.mp4"
    )
    original = broll_copy.read_bytes()
    broll_copy.write_bytes(b"tampered edit copy")
    with pytest.raises(package.OwnerSamplePackageError, match="^manifest_edit_input_invalid$"):
        package.validate_reverse_manifest(package_root, manifest)
    broll_copy.write_bytes(original)

    crossed = json.loads(json.dumps(manifest))
    crossed["edit_input_evidence"]["narration_storage_ref"] = (
        "local://projects/other-project/assets/qa-narration.wav"
    )
    crossed["reverse_trace"]["nodes"]["copied_asset:edit_narration"]["ref"] = (
        crossed["edit_input_evidence"]["narration_storage_ref"]
    )
    with pytest.raises(package.OwnerSamplePackageError, match="^manifest_edit_input_invalid$"):
        package.validate_reverse_manifest(package_root, crossed)


def test_stored_manifest_rejects_oversize_edit_copy_before_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = _load_module()
    package_root, _narration, context = _package_fixture(package, tmp_path, monkeypatch)
    manifest = context["result"]
    broll_copy = (
        package_root
        / "edit"
        / "projects"
        / "projects"
        / "edit-owner"
        / "assets"
        / "owner-h264.mp4"
    )
    with broll_copy.open("r+b") as target:
        target.truncate(package.MAX_ARTIFACT_BYTES + 1)
    original_hash = package._sha256
    monkeypatch.setattr(
        package,
        "_sha256",
        lambda path: (
            (_ for _ in ()).throw(AssertionError("oversize edit copy must not be hashed"))
            if path == broll_copy.resolve()
            else original_hash(path)
        ),
    )

    with pytest.raises(package.OwnerSamplePackageError, match="^manifest_edit_input_invalid$"):
        package.validate_reverse_manifest(package_root, manifest)


def test_manifest_rejects_sparse_oversize_bool_nan_and_serialized_size_before_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = _load_module()
    package_root, _narration, context = _package_fixture(package, tmp_path, monkeypatch)
    manifest = context["result"]

    bool_size = json.loads(json.dumps(manifest))
    bool_size["source_inventory"][0]["size_bytes"] = True
    with pytest.raises(package.OwnerSamplePackageError, match="^manifest_source_inventory_invalid$"):
        package.validate_reverse_manifest(package_root, bool_size)

    nan_duration = json.loads(json.dumps(manifest))
    nan_duration["source_inventory"][0]["duration_sec"] = float("nan")
    with pytest.raises(package.OwnerSamplePackageError, match="^manifest_source_inventory_invalid$"):
        package.validate_reverse_manifest(package_root, nan_duration)

    huge_manifest = json.loads(json.dumps(manifest))
    huge_manifest["preview_proofs"]["previews"]["h264"]["content_url"] = (
        "/api/projects/qa-preview/assets/h264-asset/" + "x" * (1024 * 1024)
    )
    with pytest.raises(package.OwnerSamplePackageError, match="^manifest_size_limit_exceeded$"):
        package.validate_reverse_manifest(package_root, huge_manifest)

    sparse = package_root / manifest["artifacts"]["final_mp4"]["path"]
    with sparse.open("wb") as target:
        target.truncate(package.MAX_ARTIFACT_BYTES + 1)
    original_hash = package._sha256
    monkeypatch.setattr(
        package,
        "_sha256",
        lambda path: (_ for _ in ()).throw(AssertionError("oversize artifact must not hash"))
        if path == sparse.resolve()
        else original_hash(path),
    )
    with pytest.raises(package.OwnerSamplePackageError, match="^manifest_artifact_size_exceeded$"):
        package.validate_reverse_manifest(package_root, manifest)


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

    leaked_import_log = json.loads(json.dumps(manifest))
    leaked_import_log["preview_proofs"]["api_import_log"] = [
        {"method": "POST", "path": str((tmp_path / "secret" / "owner.mp4").resolve())}
    ]
    with pytest.raises(package.OwnerSamplePackageError, match="^manifest_preview_proof_invalid$"):
        package.validate_reverse_manifest(package_root, leaked_import_log)

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


def test_package_rejects_existing_empty_root_before_inventory_or_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = _load_module()
    sample_dir = tmp_path / "samples"
    sample_dir.mkdir()
    output_root = tmp_path / "empty-owner-package"
    output_root.mkdir()
    monkeypatch.setattr(
        package,
        "inventory_samples",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not scan")),
    )

    with pytest.raises(package.OwnerSamplePackageError, match="^package_root_exists$"):
        package.build_owner_sample_package(
            sample_dir=sample_dir,
            output_root=output_root,
            narration=tmp_path / "missing.wav",
            ffmpeg_binary="ffmpeg",
            ffprobe_binary="ffprobe",
            edit_flow_runner=lambda **kwargs: {},
        )
    assert list(output_root.iterdir()) == []


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
    monkeypatch.setattr(
        package.os,
        "rename",
        lambda source, destination: (_ for _ in ()).throw(
            OSError("simulated publish failure")
        ),
    )
    with pytest.raises(package.OwnerSamplePackageError, match="^manifest_publish_failed$"):
        _package_fixture(package, tmp_path, monkeypatch)

    package_root = tmp_path / "owner-package"
    assert (package_root / "edit" / "review" / "final.mp4").is_file()
    assert not (package_root / "owner-sample-edit-package.json").exists()
    assert not (package_root / ".owner-sample-edit-package.json.tmp").exists()


def test_manifest_publish_never_overwrites_concurrent_final(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = _load_module()
    concurrent_bytes = b"concurrent owner receipt"

    def inject_concurrent_final(source: Path, destination: Path) -> None:
        Path(destination).write_bytes(concurrent_bytes)
        raise FileExistsError("simulated concurrent publisher")

    monkeypatch.setattr(package.os, "rename", inject_concurrent_final)
    with pytest.raises(package.OwnerSamplePackageError, match="^manifest_publish_failed$"):
        _package_fixture(package, tmp_path, monkeypatch)

    package_root = tmp_path / "owner-package"
    assert (package_root / "owner-sample-edit-package.json").read_bytes() == concurrent_bytes
    assert not (package_root / ".owner-sample-edit-package.json.tmp").exists()
    assert (package_root / "edit" / "review" / "final.mp4").is_file()


def test_failed_publish_temp_uses_quarantine_when_unlink_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = _load_module()
    original_unlink = Path.unlink
    monkeypatch.setattr(
        package,
        "_publish_no_overwrite",
        lambda source, destination: (_ for _ in ()).throw(
            OSError("simulated no-overwrite rename failure")
        ),
    )
    monkeypatch.setattr(
        Path,
        "unlink",
        lambda self, *args, **kwargs: (
            (_ for _ in ()).throw(OSError("simulated standard temp unlink failure"))
            if self.name == ".owner-sample-edit-package.json.tmp"
            else original_unlink(self, *args, **kwargs)
        ),
    )

    with pytest.raises(package.OwnerSamplePackageError, match="^manifest_publish_failed$"):
        _package_fixture(package, tmp_path, monkeypatch)

    package_root = tmp_path / "owner-package"
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


def test_post_publish_source_fence_removes_only_generated_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = _load_module()
    original = package._assert_final_source_fence
    calls = 0

    def fail_second_check(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise package.OwnerSamplePackageError("source_changed_during_package")
        return original(*args, **kwargs)

    monkeypatch.setattr(package, "_assert_final_source_fence", fail_second_check)
    with pytest.raises(package.OwnerSamplePackageError, match="^source_changed_during_package$"):
        _package_fixture(package, tmp_path, monkeypatch)

    package_root = tmp_path / "owner-package"
    assert calls == 2
    assert not (package_root / "owner-sample-edit-package.json").exists()
    assert not (package_root / ".owner-sample-edit-package.json.tmp").exists()
    assert (package_root / "edit" / "review" / "final.mp4").is_file()


def test_post_publish_cleanup_quarantines_owned_manifest_when_unlink_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = _load_module()
    original_fence = package._assert_final_source_fence
    original_unlink = Path.unlink
    calls = 0

    def fail_second_check(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            monkeypatch.setattr(
                Path,
                "unlink",
                lambda self, *a, **kw: (
                    (_ for _ in ()).throw(OSError("simulated quarantine delete failure"))
                    if ".cleanup-" in self.name
                    else original_unlink(self, *a, **kw)
                ),
            )
            raise package.OwnerSamplePackageError("source_changed_during_package")
        return original_fence(*args, **kwargs)

    monkeypatch.setattr(package, "_assert_final_source_fence", fail_second_check)
    with pytest.raises(package.OwnerSamplePackageError, match="^source_changed_during_package$"):
        _package_fixture(package, tmp_path, monkeypatch)

    package_root = tmp_path / "owner-package"
    assert not (package_root / "owner-sample-edit-package.json").exists()
    assert not (package_root / ".owner-sample-edit-package.json.tmp").exists()
    assert list(package_root.glob("owner-sample-edit-package.json.cleanup-*"))


def test_post_publish_cleanup_reports_namespace_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = _load_module()
    original_fence = package._assert_final_source_fence
    original_rename = package.os.rename
    calls = 0

    def fail_second_check(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            monkeypatch.setattr(
                package.os,
                "rename",
                lambda source, destination: (
                    (_ for _ in ()).throw(OSError("simulated cleanup rename failure"))
                    if Path(source).name == "owner-sample-edit-package.json"
                    else original_rename(source, destination)
                ),
            )
            raise package.OwnerSamplePackageError("source_changed_during_package")
        return original_fence(*args, **kwargs)

    monkeypatch.setattr(package, "_assert_final_source_fence", fail_second_check)
    with pytest.raises(package.OwnerSamplePackageError, match="^manifest_cleanup_failed$"):
        _package_fixture(package, tmp_path, monkeypatch)


def _minimal_cli_manifest() -> dict[str, object]:
    return {
        "selected_sources": {
            "h264": {"name": "owner-h264.mp4", "sha256": "a" * 64},
            "hevc": {"name": "owner-hevc.mp4", "sha256": "b" * 64},
        },
        "artifacts": {
            key: {
                "path": f"edit/review/{key}.evidence",
                "sha256": f"{index:x}" * 64,
            }
            for index, key in enumerate(
                (
                    "exact_preview",
                    "final_mp4",
                    "srt",
                    "timeline_snapshot",
                    "editing_session_snapshot",
                    "capcut_draft",
                    "ffprobe_summary",
                    "review_checklist",
                ),
                start=1,
            )
        },
        "authorities": {
            "owner_approval": False,
            "rights_approval": False,
            "desktop_edit": False,
            "desktop_export": False,
            "automatic_apply": False,
            "memory_write": False,
            "external_provider_calls": 0,
        },
        "preview_proofs": {"external_provider_calls": 0},
        "internal_secret": "never-print-me",
    }


def test_cli_default_output_is_repo_local_utc_timestamp_and_summary_is_bounded(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    package = _load_module()
    sample_dir = tmp_path / "owner samples"
    sample_dir.mkdir()
    calls: list[dict[str, object]] = []

    def build(**kwargs):
        calls.append(kwargs)
        return _minimal_cli_manifest()

    exit_code = package.main(
        ["--sample-dir", str(sample_dir), "--json"],
        package_builder=build,
        utc_now=lambda: datetime(2026, 8, 3, 4, 5, 6, tzinfo=timezone.utc),
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == ""
    assert len(captured.out.splitlines()) == 1
    assert json.loads(captured.out) == {
        "status": "ok",
        "package_directory": "owner-sample-edit-20260803T040506Z",
        "selected_filenames": {
            "h264": "owner-h264.mp4",
            "hevc": "owner-hevc.mp4",
        },
        "artifact_count": 8,
        "external_provider_calls": 0,
    }
    assert calls[0]["sample_dir"] == sample_dir
    assert calls[0]["output_root"] == (
        package.REPOSITORY_ROOT
        / "artifacts"
        / "owner-sample-edit-20260803T040506Z"
    )
    assert calls[0]["narration"] == package.DEFAULT_NARRATION_PATH


@pytest.mark.parametrize("existing_kind", ["empty_directory", "file", "reparse"])
def test_cli_rejects_existing_or_reparse_output_before_build_or_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    existing_kind: str,
) -> None:
    package = _load_module()
    sample_dir = tmp_path / "samples"
    sample_dir.mkdir()
    output_root = tmp_path / "existing-output"
    if existing_kind == "file":
        output_root.write_text("preserve", encoding="utf-8")
    else:
        output_root.mkdir()
    if existing_kind == "reparse":
        monkeypatch.setattr(package, "_is_reparse_point", lambda path: path == output_root)

    exit_code = package.main(
        [
            "--sample-dir",
            str(sample_dir),
            "--output-root",
            str(output_root),
            "--json",
        ],
        package_builder=lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("build must not run")
        ),
    )

    assert exit_code != 0
    assert json.loads(capsys.readouterr().out) == {
        "status": "error",
        "error_code": "package_root_exists",
    }
    assert output_root.exists()


@pytest.mark.parametrize(
    "disabled_argument",
    [
        "--project-id",
        "--session-id=existing-session",
        "--confirm-existing-project-mutation",
    ],
)
def test_cli_existing_project_mode_is_disabled_before_parse_scan_build_write_or_network(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    disabled_argument: str,
) -> None:
    package = _load_module()
    output_root = tmp_path / "must-not-exist"
    monkeypatch.setattr(
        package,
        "inventory_samples",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not scan")),
    )
    monkeypatch.setattr(
        package,
        "TestClient",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not network")),
    )

    exit_code = package.main(
        [
            disabled_argument,
            "--ffmpeg",
            "--unknown-malformed-argument",
            "--output-root",
            str(output_root),
            "--json",
        ],
        package_builder=lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("must not build")
        ),
    )

    captured = capsys.readouterr()
    assert exit_code != 0
    assert captured.err == ""
    assert json.loads(captured.out) == {
        "status": "error",
        "error_code": "existing_project_mode_disabled",
    }
    assert not output_root.exists()


def test_cli_does_not_accept_abbreviated_existing_project_arguments(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    package = _load_module()
    sample_dir = tmp_path / "samples"
    sample_dir.mkdir()

    exit_code = package.main(
        [
            "--sample-dir",
            str(sample_dir),
            "--project-i",
            "existing-project",
            "--json",
        ],
        package_builder=lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("abbreviated mutation option must not build")
        ),
    )

    assert exit_code != 0
    assert json.loads(capsys.readouterr().out) == {
        "status": "error",
        "error_code": "cli_arguments_invalid",
    }


def test_cli_help_does_not_advertise_disabled_existing_project_mode(
    capsys: pytest.CaptureFixture[str],
) -> None:
    package = _load_module()

    with pytest.raises(SystemExit) as raised:
        package.main(["--help"])

    assert raised.value.code == 0
    help_text = capsys.readouterr().out
    assert "--project-id" not in help_text
    assert "--session-id" not in help_text
    assert "--confirm-existing-project-mutation" not in help_text


def test_cli_json_and_human_output_never_disclose_paths_commands_or_secrets(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    package = _load_module()
    sample_dir = tmp_path / "private" / "owner-samples"
    sample_dir.mkdir(parents=True)
    output_root = tmp_path / "private" / "owner-output"
    narration = tmp_path / "private" / "owner-narration.wav"
    forbidden = [
        str(sample_dir),
        str(output_root),
        str(narration),
        "never-print-me",
        "SECRET_TOKEN",
        "ffmpeg -i private.mp4",
        "memory_payload",
    ]

    common_args = [
        "--sample-dir",
        str(sample_dir),
        "--output-root",
        str(output_root),
        "--narration",
        str(narration),
        "--ffmpeg",
        "ffmpeg-local",
        "--ffprobe",
        "ffprobe-local",
    ]
    assert package.main(
        [*common_args, "--json"], package_builder=lambda **kwargs: _minimal_cli_manifest()
    ) == 0
    json_output = capsys.readouterr().out
    assert json.loads(json_output)["package_directory"] == output_root.name
    assert all(value not in json_output for value in forbidden)

    assert package.main(
        common_args, package_builder=lambda **kwargs: _minimal_cli_manifest()
    ) == 0
    human_output = capsys.readouterr().out
    assert "owner-output" in human_output
    assert all(value not in human_output for value in forbidden)


def test_cli_errors_are_single_bounded_json_without_traceback_or_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    package = _load_module()
    sample_dir = tmp_path / "private" / "samples"
    sample_dir.mkdir(parents=True)

    exit_code = package.main(
        ["--sample-dir", str(sample_dir), "--json"],
        package_builder=lambda **kwargs: (_ for _ in ()).throw(
            package.OwnerSamplePackageError("unsafe code " + str(sample_dir))
        ),
        utc_now=lambda: datetime(2026, 8, 3, tzinfo=timezone.utc),
    )

    captured = capsys.readouterr()
    assert exit_code != 0
    assert captured.err == ""
    assert len(captured.out.splitlines()) == 1
    assert json.loads(captured.out) == {
        "status": "error",
        "error_code": "owner_sample_package_failed",
    }
    assert str(sample_dir) not in captured.out
    assert "Traceback" not in captured.out


@pytest.mark.parametrize(
    "mutate",
    [
        lambda manifest: manifest.pop("authorities"),
        lambda manifest: manifest["authorities"].__setitem__(
            "external_provider_calls", 9
        ),
        lambda manifest: manifest["authorities"].__setitem__(
            "external_provider_calls", False
        ),
        lambda manifest: manifest["preview_proofs"].__setitem__(
            "external_provider_calls", 9
        ),
        lambda manifest: manifest["preview_proofs"].__setitem__(
            "external_provider_calls", False
        ),
        lambda manifest: manifest["selected_sources"].pop("hevc"),
        lambda manifest: manifest["selected_sources"]["h264"].pop("sha256"),
        lambda manifest: manifest["artifacts"].pop("review_checklist"),
    ],
)
def test_cli_rejects_untrusted_result_schema_instead_of_claiming_zero_external_calls(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    mutate,
) -> None:
    package = _load_module()
    sample_dir = tmp_path / "samples"
    sample_dir.mkdir()
    manifest = _minimal_cli_manifest()
    mutate(manifest)

    exit_code = package.main(
        ["--sample-dir", str(sample_dir), "--json"],
        package_builder=lambda **kwargs: manifest,
        utc_now=lambda: datetime(2026, 8, 3, tzinfo=timezone.utc),
    )

    captured = capsys.readouterr()
    assert exit_code != 0
    assert captured.err == ""
    assert json.loads(captured.out) == {
        "status": "error",
        "error_code": "cli_result_invalid",
    }


@pytest.mark.parametrize("json_mode", [True, False])
def test_cli_unexpected_exception_is_sanitized_without_traceback_or_secret(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    json_mode: bool,
) -> None:
    package = _load_module()
    sample_dir = tmp_path / "private" / "samples"
    sample_dir.mkdir(parents=True)
    arguments = ["--sample-dir", str(sample_dir)]
    if json_mode:
        arguments.append("--json")
    secret = f"SECRET_TOKEN at {sample_dir}"

    exit_code = package.main(
        arguments,
        package_builder=lambda **kwargs: (_ for _ in ()).throw(RuntimeError(secret)),
        utc_now=lambda: datetime(2026, 8, 3, tzinfo=timezone.utc),
    )

    captured = capsys.readouterr()
    assert exit_code != 0
    assert captured.err == ""
    assert "Traceback" not in captured.out
    assert secret not in captured.out
    assert str(sample_dir) not in captured.out
    if json_mode:
        assert len(captured.out.splitlines()) == 1
        assert json.loads(captured.out) == {
            "status": "error",
            "error_code": "internal_error",
        }
    else:
        assert captured.out == "실행 중단: internal_error\n"


@pytest.mark.parametrize(
    "unsafe_name",
    [
        "owner\u0085next.mp4",
        "owner\u200bhidden.mp4",
        "owner\u2028next.mp4",
        "owner\u2029next.mp4",
    ],
)
def test_cli_summary_rejects_unicode_control_and_line_separator_names(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    unsafe_name: str,
) -> None:
    package = _load_module()
    sample_dir = tmp_path / "samples"
    sample_dir.mkdir()
    manifest = _minimal_cli_manifest()
    manifest["selected_sources"]["h264"]["name"] = unsafe_name

    exit_code = package.main(
        ["--sample-dir", str(sample_dir), "--json"],
        package_builder=lambda **kwargs: manifest,
        utc_now=lambda: datetime(2026, 8, 3, tzinfo=timezone.utc),
    )

    captured = capsys.readouterr()
    assert exit_code != 0
    assert captured.err == ""
    assert len(captured.out.splitlines()) == 1
    assert json.loads(captured.out) == {
        "status": "error",
        "error_code": "cli_result_invalid",
    }


@pytest.mark.parametrize(
    "unsafe_path",
    [
        r"\??\C:\private\owner.mp4",
        r"\\?\C:\private\owner.mp4",
        r"\\.\PhysicalDrive0",
        r"\Device\HarddiskVolume1\private\owner.mp4",
        r"GLOBALROOT\Device\HarddiskVolume1\private\owner.mp4",
        r"\??\UNC\server\share\owner.mp4",
        r"\\?\UNC\server\share\owner.mp4",
        r"UNC\server\share\owner.mp4",
        r"\current-drive\owner.mp4",
        r"/current-drive/owner.mp4",
        r"C:drive-relative\owner.mp4",
        r"C:/forward-slash/owner.mp4",
        r"C:\private\owner.mp4:alternate-stream",
        r"C:\private. \owner.mp4",
    ],
)
def test_local_cli_path_rejects_windows_namespace_and_anchored_aliases_before_path_access(
    monkeypatch: pytest.MonkeyPatch, unsafe_path: str
) -> None:
    package = _load_module()
    monkeypatch.setattr(
        package,
        "Path",
        lambda value: (_ for _ in ()).throw(
            AssertionError("invalid lexical path must not construct or inspect Path")
        ),
    )

    with pytest.raises(package.OwnerSamplePackageError, match="^local_path_required$"):
        package._local_cli_path(unsafe_path)


@pytest.mark.parametrize(
    "safe_path",
    [
        r"C:\owner\samples\video.mp4",
        r"artifacts\owner-sample-edit-20260803",
        r"ffmpeg.exe",
    ],
)
def test_local_cli_path_accepts_normal_drive_or_safe_relative_paths(safe_path: str) -> None:
    package = _load_module()

    assert package._local_cli_path(safe_path) == Path(safe_path)


@pytest.mark.parametrize("json_mode", [True, False])
def test_cli_subprocess_writes_strict_utf8_even_when_text_encoding_is_cp949(
    json_mode: bool,
) -> None:
    arguments = [sys.executable, str(SCRIPT), "--project-id", "기존-프로젝트"]
    if json_mode:
        arguments.append("--json")
    environment = dict(os.environ)
    environment["PYTHONIOENCODING"] = "cp949"
    environment["PYTHONUTF8"] = "0"

    completed = subprocess.run(
        arguments,
        capture_output=True,
        timeout=30,
        check=False,
        env=environment,
    )

    assert completed.returncode == 2
    assert completed.stderr == b""
    decoded = completed.stdout.decode("utf-8", errors="strict")
    assert len(decoded.splitlines()) == 1
    if json_mode:
        assert json.loads(decoded) == {
            "status": "error",
            "error_code": "existing_project_mode_disabled",
        }
    else:
        assert decoded == "실행 중단: existing_project_mode_disabled\n"


@pytest.mark.parametrize(
    "flag,value",
    [
        ("--sample-dir", "https://example.invalid/private.mp4"),
        ("--output-root", r"\\server\share\owner-output"),
        ("--narration", "file:///private/voice.wav"),
    ],
)
def test_cli_rejects_nonlocal_path_arguments_before_build(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    flag: str,
    value: str,
) -> None:
    package = _load_module()
    sample_dir = tmp_path / "samples"
    sample_dir.mkdir()
    arguments = ["--sample-dir", str(sample_dir), flag, value, "--json"]

    exit_code = package.main(
        arguments,
        package_builder=lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("build must not run")
        ),
    )

    assert exit_code != 0
    assert json.loads(capsys.readouterr().out) == {
        "status": "error",
        "error_code": "local_path_required",
    }
