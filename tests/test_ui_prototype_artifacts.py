"""Contract for the static Slice 0 creator-workspace approval artifacts."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "prototypes" / "2026-07-17-creator-workspace"
DECISION_RECORD = ROOT / "docs" / "decisions" / "creator-workspace-visual-approval.ko.md"
VIEWPORTS = [(1920, 1080), (1440, 900), (1280, 800), (768, 1024), (390, 844)]
SCREEN_IDS = {"home-empty", "create-interview", "editor-populated"}
REQUIRED_LABELS = {
    "home-empty": {"아직 프로젝트가 없습니다", "새 영상 만들기"},
    "create-interview": {"대본 맥락", "유진 질문", "2 / 4", "모르겠어요", "추천해줘", "건너뛰기", "요약 수정"},
    "editor-populated": {"편집본 미리보기", "선택한 클립 보기", "유진", "적용", "편집 도우미", "자산 상태", "빈 구간", "적용 전에는 편집본이 바뀌지 않습니다", "내레이션", "자막", "B-roll", "BGM/SFX", "오버레이"},
}
APPROVED_DESIGN_TOKENS = {
    "canvas": "#FAFAF9",
    "panel": "#FFFFFF",
    "border": "#E7E5E4",
    "primary": "#292524",
    "secondary": "#57534E",
    "accent": "#4F46E5",
    "preview": "#18181B",
}
APPROVED_FONT_PATH = Path(r"C:\Windows\Fonts\NotoSansKR-VF.ttf")


def canonical_artifact_digest(artifacts: list[dict]) -> str:
    payload = json.dumps(artifacts, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def test_creator_workspace_manifest_links_all_static_pngs_and_approved_direction() -> None:
    manifest_path = OUTPUT / "manifest.json"
    assert manifest_path.is_file(), "expected committed prototype manifest"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    artifacts = manifest["artifacts"]
    assert len(artifacts) == 15
    assert {(item["screen_id"], item["viewport"]["width"], item["viewport"]["height"]) for item in artifacts} == {
        (screen_id, width, height) for screen_id in SCREEN_IDS for width, height in VIEWPORTS
    }

    for item in artifacts:
        assert item["png_path"].startswith("png/")
        expected_path = f"png/{item['screen_id']}-{item['viewport']['width']}x{item['viewport']['height']}.png"
        assert item["png_path"] == expected_path
        png_path = OUTPUT / item["png_path"]
        assert png_path.is_file()
        assert item["sha256"] == hashlib.sha256(png_path.read_bytes()).hexdigest()
        assert item["bytes"] == png_path.stat().st_size
        assert REQUIRED_LABELS[item["screen_id"]].issubset(item["required_korean_labels"])
        assert item["image_mode"] == "RGB"
        assert item["measurements"]
        with Image.open(png_path) as image:
            assert image.size == (item["viewport"]["width"], item["viewport"]["height"])
            assert image.mode == "RGB"
            assert min(image.getpixel((0, 0))) >= 245, "prototype must use the approved white workspace base"

    renderer = manifest["renderer"]
    assert renderer["name"] == "Pillow"
    assert renderer["pillow_major"] == 12
    assert renderer["image_mode"] == "RGB"
    assert Path(renderer["font"]["absolute_path"]) == APPROVED_FONT_PATH
    assert Path(renderer["font"]["absolute_path"]).is_file()
    assert renderer["font"]["sha256"] == hashlib.sha256(Path(renderer["font"]["absolute_path"]).read_bytes()).hexdigest()
    assert manifest["design_tokens"] == APPROVED_DESIGN_TOKENS
    assert not any("루미" in label or "로컬 작업 공간" in label for item in artifacts for label in item["required_korean_labels"])

    approval = manifest["approval"]
    assert approval == {
        "status": "approved",
        "approver": "user",
        "decided_at": "2026-07-17",
        "artifact_manifest_sha": canonical_artifact_digest(artifacts),
    }


def test_verifier_rejects_an_extra_png_outside_the_manifest(tmp_path: Path) -> None:
    copied = tmp_path / "creator-workspace"
    shutil.copytree(OUTPUT, copied)
    (copied / "png" / "stale.png").write_bytes(b"not a declared artifact")
    spec = importlib.util.spec_from_file_location("prototype_builder", ROOT / "scripts" / "build_ui_prototype_artifacts.py")
    assert spec and spec.loader
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    assert any("PNG set" in error for error in builder.verify(copied))


def load_builder():
    spec = importlib.util.spec_from_file_location("prototype_builder", ROOT / "scripts" / "build_ui_prototype_artifacts.py")
    assert spec and spec.loader
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    return builder


def copy_approval_package(tmp_path: Path) -> tuple[Path, Path]:
    copied = tmp_path / "creator-workspace"
    shutil.copytree(OUTPUT, copied)
    decision = tmp_path / "creator-workspace-visual-approval.ko.md"
    shutil.copy2(DECISION_RECORD, decision)
    return copied, decision


def test_verifier_rejects_approved_manifest_without_decision_metadata(tmp_path: Path) -> None:
    copied, decision = copy_approval_package(tmp_path)
    manifest_path = copied / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["approval"]["approver"] = ""
    manifest["approval"]["decided_at"] = ""
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

    errors = load_builder().verify(copied, require_approved=True, decision_path=decision)

    assert "approved approval must include approver and decided_at" in errors


def test_verifier_rejects_decision_record_not_linked_to_manifest_approval(tmp_path: Path) -> None:
    copied, decision = copy_approval_package(tmp_path)
    record = decision.read_text(encoding="utf-8")
    marker = re.search(r"<!-- creator-workspace-approval: (?P<payload>.+) -->", record)
    assert marker, "decision record must contain a machine-verifiable approval marker"
    mismatched = json.loads(marker.group("payload"))
    mismatched["status"] = "rejected"
    mismatched["artifact_manifest_sha"] = "0" * 64
    decision.write_text(
        record[:marker.start("payload")] + json.dumps(mismatched, ensure_ascii=False, sort_keys=True) + record[marker.end("payload"):],
        encoding="utf-8",
    )

    errors = load_builder().verify(copied, require_approved=True, decision_path=decision)

    assert "decision record approval mismatch" in errors
