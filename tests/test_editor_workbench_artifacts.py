import hashlib
import json
import re
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs/prototypes/2026-07-20-editor-workbench/manifest.json"
APPROVAL = ROOT / "docs/decisions/2026-07-20-editor-workbench-visual-approval.ko.md"
SNAPSHOTS = ROOT / "apps/web/e2e/snapshots"
SOURCE = ROOT / "apps/web/src/features/editor/workbench/EditorWorkbench.tsx"

def png_dimensions(path: Path) -> tuple[int, int]:
    header = path.read_bytes()[:24]
    assert header[:8] == b"\x89PNG\r\n\x1a\n"
    assert header[12:16] == b"IHDR"
    return struct.unpack(">II", header[16:24])

def canonical_manifest_digest(manifest: dict) -> str:
    payload = {key: manifest[key] for key in ("task", "approval", "required_korean_labels", "viewports")}
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()

def test_editor_workbench_artifacts_are_deterministic_and_pending_approval():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert manifest["approval"]["status"] == "pending"
    approval_record = APPROVAL.read_text(encoding="utf-8")
    assert manifest["approval"]["record"] == "docs/decisions/2026-07-20-editor-workbench-visual-approval.ko.md"
    assert manifest["manifest_sha256"] == canonical_manifest_digest(manifest)
    marker = re.search(r"<!-- editor-workbench-approval: (?P<payload>.+) -->", approval_record)
    assert marker
    assert json.loads(marker.group("payload")) == {"manifest_sha256": manifest["manifest_sha256"], "status": "pending"}
    source = SOURCE.read_text(encoding="utf-8")
    assert set(manifest["required_korean_labels"]) == {"읽기 전용 편집 작업판", "자산과 대본", "유진과 Inspector", "미리보기 자리", "타임라인"}
    for label in manifest["required_korean_labels"]:
        assert label in source
    expected = {(1920, 1080), (1440, 900), (1280, 800), (768, 1024), (390, 844)}
    actual = {(item["width"], item["height"]) for item in manifest["viewports"]}
    assert actual == expected
    manifest_files = {item["file"] for item in manifest["viewports"]}
    snapshot_files = {path.name for path in SNAPSHOTS.glob("editor-workbench-*.png")}
    assert snapshot_files == manifest_files
    for item in manifest["viewports"]:
        path = SNAPSHOTS / item["file"]
        assert path.is_file()
        assert len(path.read_bytes()) > 100
        assert png_dimensions(path) == (item["width"], item["height"])
        assert item["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
