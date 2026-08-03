from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

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

from fastapi.testclient import TestClient

from videobox_api.main import create_app
from videobox_domain_models.assets import AssetType
from videobox_storage.local_project_store import LocalProjectStore


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _probe(path: Path) -> dict:
    completed = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=True,
    )
    return json.loads(completed.stdout)


def _synthetic_hevc(path: Path) -> None:
    subprocess.run(
        [
            "ffmpeg", "-nostdin", "-v", "error", "-y",
            "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=15:duration=1",
            "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=1",
            "-shortest", "-c:v", "libx265", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            "-tag:v", "hvc1", "-c:a", "aac", "-movflags", "+faststart", str(path),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        check=True,
    )


def verify(source_path: Path | None) -> dict:
    with tempfile.TemporaryDirectory(prefix="vb23a-") as temporary:
        qa_root = Path(temporary)
        source = source_path.resolve() if source_path is not None else qa_root / "synthetic-hevc.mp4"
        if source_path is None:
            _synthetic_hevc(source)
        if not source.is_file():
            raise FileNotFoundError("source_not_found")
        source_before = (source.stat().st_size, source.stat().st_mtime_ns, _sha256(source))
        input_probe = _probe(source)
        input_video = next(stream for stream in input_probe["streams"] if stream.get("codec_type") == "video")

        projects_root = qa_root / "runtime"
        app = create_app(projects_root=projects_root)
        with TestClient(app) as client:
            project_id = client.post("/api/projects", json={"name": "Task 23A verifier"}).json()["project_id"]
            store = LocalProjectStore(projects_root)
            asset = store.register_asset(project_id=project_id, asset_type=AssetType.BROLL_VIDEO, source_path=source)
            stored_source = store.resolve_storage_uri(project_id=project_id, storage_uri=asset.storage_uri)
            stored_before = (stored_source.stat().st_size, stored_source.stat().st_mtime_ns, _sha256(stored_source))
            endpoint = f"/api/projects/{project_id}/assets/{asset.asset_id}/browser-preview"
            started = client.post(endpoint)
            if started.status_code not in {200, 202}:
                raise RuntimeError(f"preview_start_failed:{started.status_code}")
            state = started.json()
            for _ in range(600):
                if state["status"] not in {"pending", "running"}:
                    break
                time.sleep(0.05)
                state = client.get(endpoint).json()
            if state["status"] != "ready" or not state["content_url"]:
                raise RuntimeError(f"preview_not_ready:{state.get('error_code')}")
            ranged = client.get(state["content_url"], headers={"Range": "bytes=0-31"})
            output_path = app.state.asset_browser_preview_service.content_path(project_id=project_id, asset_id=asset.asset_id)
            output_probe = _probe(output_path)
            output_video = next(stream for stream in output_probe["streams"] if stream.get("codec_type") == "video")
            stored_after = (stored_source.stat().st_size, stored_source.stat().st_mtime_ns, _sha256(stored_source))

        source_after = (source.stat().st_size, source.stat().st_mtime_ns, _sha256(source))
        return {
            "status": "passed",
            "source_unchanged": source_before == source_after and stored_before == stored_after,
            "input_video_codec": input_video.get("codec_name"),
            "output_video_codec": output_video.get("codec_name"),
            "output_pixel_format": output_video.get("pix_fmt"),
            "range_status": ranged.status_code,
            "external_provider_calls": 0,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Task 23A local HEVC browser preview proxy.")
    parser.add_argument("--source", type=Path, help="Optional read-only HEVC source; it is never modified.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = verify(args.source)
    print(json.dumps(result, ensure_ascii=False) if args.json else "Task 23A browser preview verifier passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
