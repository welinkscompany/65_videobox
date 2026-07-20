import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs/prototypes/2026-07-20-editor-workbench/manifest.json"
APPROVAL = ROOT / "docs/decisions/2026-07-20-editor-workbench-visual-approval.ko.md"
SNAPSHOTS = ROOT / "apps/web/e2e/snapshots"

def test_editor_workbench_artifacts_are_deterministic_and_pending_approval():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert manifest["approval"]["status"] == "pending"
    assert "approval_required" in APPROVAL.read_text(encoding="utf-8")
    expected = {(1920, 1080), (1440, 900), (1280, 800), (768, 1024), (390, 844)}
    actual = {(item["width"], item["height"]) for item in manifest["viewports"]}
    assert actual == expected
    for item in manifest["viewports"]:
        path = SNAPSHOTS / item["file"]
        assert path.is_file()
        assert len(path.read_bytes()) > 100
        assert item["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
