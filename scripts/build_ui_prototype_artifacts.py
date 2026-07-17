"""Build and verify the static creator-workspace visual approval package.

This is deliberately a Pillow-only documentation renderer.  It does not start
the web app, call providers, or copy code from referenced OSS projects.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, __version__ as PILLOW_VERSION


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "docs" / "prototypes" / "2026-07-17-creator-workspace"
DEFAULT_DECISION_RECORD = ROOT / "docs" / "decisions" / "creator-workspace-visual-approval.ko.md"
FONT_PATH = Path(r"C:\Windows\Fonts\NotoSansKR-VF.ttf").resolve()
VIEWPORTS = [(1920, 1080), (1440, 900), (1280, 800), (768, 1024), (390, 844)]
SCREENS = ("home-empty", "create-interview", "editor-populated")

DESIGN_TOKENS = {
    "canvas": "#FAFAF9",
    "panel": "#FFFFFF",
    "border": "#E7E5E4",
    "primary": "#292524",
    "secondary": "#57534E",
    "accent": "#4F46E5",
    "preview": "#18181B",
}
BG, PANEL, PANEL_2, LINE = DESIGN_TOKENS["canvas"].lower(), DESIGN_TOKENS["panel"].lower(), "#f5f5f4", DESIGN_TOKENS["border"].lower()
TEXT, MUTED, BLUE, GREEN, AMBER, PURPLE = DESIGN_TOKENS["primary"].lower(), DESIGN_TOKENS["secondary"].lower(), DESIGN_TOKENS["accent"].lower(), "#15803d", "#a16207", "#6d28d9"
ACCENT_SOFT, PREVIEW_TEXT = "#eef2ff", "#fafaf9"


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    loaded = ImageFont.truetype(str(FONT_PATH), size)
    if bold:
        loaded.set_variation_by_axes([700])
    return loaded


def rect(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], fill: str, outline: str | None = None, radius: int = 10) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline or fill, width=1)


def text(draw: ImageDraw.ImageDraw, xy: tuple[int, int], value: str, size: int = 16, color: str = TEXT, bold: bool = False) -> None:
    draw.text(xy, value, font=font(size, bold), fill=color)


def shell(draw: ImageDraw.ImageDraw, width: int, height: int, title: str, collapsed: bool = False) -> tuple[int, int]:
    sidebar = 72 if collapsed else (220 if width >= 768 else 0)
    draw.rectangle((0, 0, width, height), fill=BG)
    if sidebar:
        draw.rectangle((0, 0, sidebar, height), fill="#ffffff")
        text(draw, (18, 22), "V" if collapsed else "VideoBox", 22, BLUE, True)
        if not collapsed:
            text(draw, (18, 62), "윤서의 인터뷰", 14, TEXT, True)
            text(draw, (18, 84), "내 영상 작업", 12, MUTED)
        for index, label in enumerate(["홈", "새 영상", "편집", "미디어", "출력", "설정"]):
            y = 142 + index * 48
            if label == title:
                rect(draw, (10, y - 8, sidebar - 10, y + 28), ACCENT_SOFT, radius=8)
            text(draw, (24 if not collapsed else 26, y), "●" if collapsed else label, 14, BLUE if label == title else MUTED, label == title)
    top_x = sidebar
    draw.rectangle((top_x, 0, width, 64), fill="#ffffff")
    text(draw, (top_x + 24, 21), title, 18, TEXT, True)
    text(draw, (width - 240, 22), "저장됨  ·  작업 2건", 13, GREEN)
    return sidebar, 64


def home(draw: ImageDraw.ImageDraw, width: int, height: int) -> dict:
    sidebar, top = shell(draw, width, height, "홈")
    x = sidebar + 32
    text(draw, (x, top + 42), "오늘 어떤 영상을 만들까요?" if width >= 500 else "어떤 영상을 만들까요?", 30 if width >= 768 else 19, TEXT, True)
    text(draw, (x, top + 86), "대본부터 시작하면 유진이 인터뷰 형식으로 정리해 드립니다." if width >= 500 else "대본부터 시작해 보세요.", 15 if width >= 500 else 12, MUTED)
    card_w = min(700, width - x - 30)
    rect(draw, (x, top + 136, x + card_w, top + 340), PANEL, LINE, 16)
    text(draw, (x + 28, top + 166), "아직 프로젝트가 없습니다", 22, TEXT, True)
    text(draw, (x + 28, top + 207), "첫 영상의 목적과 시청자를 적어 주세요.", 15, MUTED)
    rect(draw, (x + 28, top + 254, x + min(235, card_w - 56), top + 302), BLUE, radius=10)
    text(draw, (x + 48, top + 269), "새 영상 만들기", 15, "#ffffff", True)
    if width >= 768:
        rect(draw, (x, top + 374, x + card_w, top + 530), PANEL, LINE, 16)
        text(draw, (x + 28, top + 404), "만드는 순서", 16, TEXT, True)
        text(draw, (x + 28, top + 441), "1  대본과 목표 정리   2  유진 인터뷰   3  자산 점검", 14, MUTED)
        text(draw, (x + 28, top + 474), "4  한 번 승인   5  편집과 출력으로 이어가기", 14, MUTED)
    return {"shell": "sidebar" if sidebar else "mobile-header", "primary_action": "새 영상 만들기"}


def interview(draw: ImageDraw.ImageDraw, width: int, height: int) -> dict:
    sidebar, top = shell(draw, width, height, "새 영상")
    x = sidebar + 28
    narrow = width < 768
    left_w = width - x - 28 if narrow else int((width - x - 52) * 0.60)
    rect(draw, (x, top + 24, x + left_w, height - 28), PANEL, LINE, 16)
    text(draw, (x + 20, top + 43), "유진과 영상 기획하기", 21 if not narrow else 17, TEXT, True)
    if narrow:
        rect(draw, (x + 20, top + 74, x + left_w - 20, top + 110), ACCENT_SOFT, radius=8)
        text(draw, (x + 34, top + 85), "대본 맥락 · 대본 보기", 11, BLUE, True)
        y = top + 132
    else:
        rect(draw, (x + 20, top + 76, x + left_w - 20, top + 142), PANEL_2, radius=10)
        text(draw, (x + 34, top + 89), "대본 맥락  ·  팀의 첫 인터뷰", 12, BLUE, True)
        text(draw, (x + 34, top + 112), "처음 시작하는 팀의 10분 제작 흐름을 소개합니다.", 12, MUTED)
        y = top + 166
    text(draw, (x + 20, y), "유진 질문   2 / 4", 13, PURPLE, True)
    rect(draw, (x + 20, y + 26, x + left_w - 20, y + 90), PANEL_2, radius=10)
    question = "시청자가 바로 따라 할 수 있도록, 첫 장면에서 무엇을 보여 줄까요?" if width >= 500 else "첫 장면에서 무엇을 보여 줄까요?"
    text(draw, (x + 34, y + 44), question, 13 if width >= 500 else 11, TEXT)
    action_y = y + 108
    for i, label in enumerate(["모르겠어요", "추천해줘", "건너뛰기"]):
        bx = x + 20 + i * int((left_w - 48) / 3)
        rect(draw, (bx, action_y, bx + int((left_w - 64) / 3), action_y + 34), ACCENT_SOFT, radius=8)
        text(draw, (bx + 10, action_y + 9), label, 10 if narrow else 12, BLUE, True)
    summary_y = action_y + 58
    rect(draw, (x + 20, summary_y, x + left_w - 20, min(summary_y + 72, height - 116)), "#ffffff", LINE, 10)
    text(draw, (x + 34, summary_y + 13), "영상 요약  ·  요약 수정", 12, TEXT, True)
    text(draw, (x + 34, summary_y + 36), "대본과 답변을 나중에 직접 고칠 수 있습니다.", 11, MUTED)
    rect(draw, (x + 20, height - 86, x + left_w - 20, height - 42), "#ffffff", LINE, 10)
    text(draw, (x + 34, height - 72), "답변을 입력하세요", 12, MUTED)
    text(draw, (x + left_w - 72, height - 72), "보내기", 12, BLUE, True)
    if not narrow:
        right_x = x + left_w + 24
        rect(draw, (right_x, top + 24, width - 28, top + 263), PANEL, LINE, 16)
        text(draw, (right_x + 20, top + 49), "대본 맥락", 16, TEXT, True)
        text(draw, (right_x + 20, top + 87), "제목  팀의 첫 인터뷰", 13, MUTED)
        text(draw, (right_x + 20, top + 119), "요약  10분 제작 흐름 소개", 13, MUTED)
        text(draw, (right_x + 20, top + 151), "요약 수정  ·  아직 승인 전", 13, AMBER)
    return {"layout": "작업 도구" if narrow else "질문과 대본", "required_state": "아직 승인 전", "question_progress": "2 / 4"}


def editor(draw: ImageDraw.ImageDraw, width: int, height: int) -> dict:
    sidebar, top = shell(draw, width, height, "편집", collapsed=width >= 768)
    content_x, content_w = sidebar + 16, width - sidebar - 32
    if width >= 1600:
        mode, left_w, right_w = "both-docks", 250, 360
    elif width >= 1280:
        mode, left_w, right_w = "one-dock", 285, 0
    else:
        mode, left_w, right_w = "drawers", 0, 0
    preview_w = content_w - left_w - right_w - (24 if left_w else 0) - (24 if right_w else 0)
    workspace_bottom = int(height * .69)
    if left_w:
        rect(draw, (content_x, top + 16, content_x + left_w, workspace_bottom), PANEL, LINE, 12)
        text(draw, (content_x + 18, top + 38), "자산 · 대본 · 자막", 14, TEXT, True)
        for i, label in enumerate(["인터뷰 시작 장면", "팀 소개 사진", "핵심 문장 자막"]):
            rect(draw, (content_x + 16, top + 72 + i * 76, content_x + left_w - 16, top + 132 + i * 76), PANEL_2, radius=8)
            text(draw, (content_x + 28, top + 92 + i * 76), label, 12, MUTED)
    stage_x = content_x + left_w + (24 if left_w else 0)
    rect(draw, (stage_x, top + 16, stage_x + preview_w, workspace_bottom), "#f5f5f4", LINE, 12)
    if mode != "drawers":
        text(draw, (stage_x + 18, top + 37), "편집본 미리보기", 14, TEXT, True)
        text(draw, (stage_x + preview_w - 138, top + 37), "선택한 클립 보기", 11, BLUE, True)
    video_x, video_y = stage_x + int(preview_w * .12), top + (220 if mode == "drawers" else 70)
    video_w, video_h = int(preview_w * .76), min(int(preview_w * .43), workspace_bottom - video_y - 80)
    rect(draw, (video_x, video_y, video_x + video_w, video_y + video_h), DESIGN_TOKENS["preview"].lower(), radius=8)
    text(draw, (video_x + 28, video_y + 28), "팀의 첫 인터뷰", 22 if width >= 768 else 16, PREVIEW_TEXT, True)
    text(draw, (video_x + 28, video_y + video_h - 40), "10분 안에 시작하는 인터뷰 제작", 14, PREVIEW_TEXT, True)
    text(draw, (stage_x + 18, workspace_bottom - 45), "▶  00:18 / 02:14     현재 편집본", 13, MUTED)
    if right_w:
        right_x = stage_x + preview_w + 24
        rect(draw, (right_x, top + 16, right_x + right_w, workspace_bottom), PANEL, LINE, 12)
        text(draw, (right_x + 18, top + 38), "유진", 15, PURPLE, True)
        text(draw, (right_x + 18, top + 72), "추천: 첫 질문 뒤에 팀 소개", 12, MUTED)
        text(draw, (right_x + 18, top + 95), "적용 전에는 편집본이 바뀌지 않습니다.", 11, MUTED)
        rect(draw, (right_x + 18, top + 134, right_x + right_w - 18, top + 176), ACCENT_SOFT, radius=8)
        text(draw, (right_x + 31, top + 147), "추천 적용", 12, BLUE, True)
        text(draw, (right_x + 18, top + 214), "편집 도우미", 13, TEXT, True)
        text(draw, (right_x + 18, top + 241), "자산 상태  ·  3개 준비됨", 11, GREEN)
        text(draw, (right_x + 18, top + 266), "빈 구간  ·  00:42–00:46", 11, AMBER)
    timeline_y = workspace_bottom + 16
    rect(draw, (content_x, timeline_y, width - 16, height - 16), PANEL, LINE, 12)
    text(draw, (content_x + 18, timeline_y + 17), "타임라인  ·  00:18", 13, TEXT, True)
    for index, label in enumerate(["내레이션", "자막", "B-roll", "BGM/SFX", "오버레이"]):
        y = timeline_y + 43 + index * 28
        text(draw, (content_x + 18, y), label, 11, MUTED)
        rect(draw, (content_x + 94, y - 5, width - 40 - index * 40, y + 12), ["#3867a9", "#2d926f", "#845fc4", "#c4863f", "#bd5e93"][index], radius=5)
    if mode == "one-dock":
        rect(draw, (stage_x + 12, top + 51, stage_x + 184, top + 82), ACCENT_SOFT, radius=8)
        text(draw, (stage_x + 24, top + 60), "유진 / 작업 도구", 10, BLUE, True)
    if mode == "drawers":
        drawer_w = min(preview_w - 24, 270)
        rect(draw, (stage_x + 12, top + 28, stage_x + drawer_w, top + 162), "#f5f3ff", BLUE, 10)
        text(draw, (stage_x + 24, top + 42), "유진 작업 도구  ·  포커스", 12, PURPLE, True)
        text(draw, (stage_x + 24, top + 65), "추천: 팀 소개 장면 추가", 10, TEXT)
        text(draw, (stage_x + 24, top + 86), "적용", 10, BLUE, True)
        text(draw, (stage_x + 72, top + 86), "빈 구간  ·  00:42–00:46", 10, AMBER)
        text(draw, (stage_x + 24, top + 107), "적용 전에는 편집본이 바뀌지 않습니다", 9, TEXT)
        for i, label in enumerate(["자산", "대본", "자막", "편집 도우미"]):
            text(draw, (stage_x + 74 + i * 43, top + 135), label, 9, MUTED)
        rect(draw, (stage_x + 18, top + 174, stage_x + min(preview_w - 18, 250), top + 202), "#ffffff", radius=6)
        text(draw, (stage_x + 26, top + 182), "편집본 미리보기  ·  선택한 클립 보기", 9, TEXT, True)
    return {"dock_mode": mode, "content_width": content_w, "preview_width": preview_w, "sidebar": "접힘" if sidebar else "작업 도구", "fixed_tracks": ["내레이션", "자막", "B-roll", "BGM/SFX", "오버레이"], "context": "유진/편집 도우미/자산 상태/빈 구간"}


def render(screen: str, width: int, height: int) -> tuple[Image.Image, dict]:
    image = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(image)
    if screen == "home-empty":
        measurements = home(draw, width, height)
    elif screen == "create-interview":
        measurements = interview(draw, width, height)
    else:
        measurements = editor(draw, width, height)
    return image, measurements


def canonical_artifact_digest(artifacts: list[dict]) -> str:
    return sha256_bytes(json.dumps(artifacts, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def decision_record_approval(path: Path) -> dict | None:
    if not path.is_file():
        return None
    marker = re.search(r"<!-- creator-workspace-approval: (?P<payload>.+) -->", path.read_text(encoding="utf-8"))
    if not marker:
        return None
    try:
        value = json.loads(marker.group("payload"))
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def build(output: Path) -> dict:
    png_dir = output / "png"
    png_dir.mkdir(parents=True, exist_ok=True)
    artifacts: list[dict] = []
    labels = {
        "home-empty": ["아직 프로젝트가 없습니다", "새 영상 만들기"],
        "create-interview": ["대본 맥락", "유진 질문", "2 / 4", "모르겠어요", "추천해줘", "건너뛰기", "요약 수정", "대본 보기"],
        "editor-populated": ["편집본 미리보기", "선택한 클립 보기", "유진", "적용", "편집 도우미", "자산 상태", "빈 구간", "적용 전에는 편집본이 바뀌지 않습니다", "내레이션", "자막", "B-roll", "BGM/SFX", "오버레이"],
    }
    for screen in SCREENS:
        for width, height in VIEWPORTS:
            image, measurements = render(screen, width, height)
            relative = Path("png") / f"{screen}-{width}x{height}.png"
            path = output / relative
            image.save(path, format="PNG", optimize=False)
            data = path.read_bytes()
            artifacts.append({
                "screen_id": screen,
                "viewport": {"width": width, "height": height},
                "png_path": relative.as_posix(),
                "sha256": sha256_bytes(data),
                "bytes": len(data),
                "required_korean_labels": labels[screen],
                "image_mode": "RGB",
                "measurements": measurements,
            })
    artifacts.sort(key=lambda item: (item["screen_id"], item["viewport"]["width"]))
    manifest = {
        "artifact_set": "creator-workspace-visual-prototype",
        "artifact_version": 1,
        "renderer": {"name": "Pillow", "pillow_major": int(PILLOW_VERSION.split(".", 1)[0]), "image_mode": "RGB", "font": {"absolute_path": str(FONT_PATH), "sha256": sha256_bytes(FONT_PATH.read_bytes())}},
        "design_tokens": DESIGN_TOKENS,
        "artifacts": artifacts,
        "approval": {"status": "pending", "approver": "", "decided_at": "", "artifact_manifest_sha": canonical_artifact_digest(artifacts)},
    }
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return manifest


def verify(output: Path, require_approved: bool = False, decision_path: Path | None = None) -> list[str]:
    errors: list[str] = []
    manifest_path = output / "manifest.json"
    if not manifest_path.is_file():
        return ["manifest.json is missing"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    artifacts = manifest.get("artifacts", [])
    expected = {(screen, width, height) for screen in SCREENS for width, height in VIEWPORTS}
    actual = {(item.get("screen_id"), item.get("viewport", {}).get("width"), item.get("viewport", {}).get("height")) for item in artifacts}
    if actual != expected or len(artifacts) != 15:
        errors.append("artifact matrix must contain exactly three screens at five viewports")
    png_dir = (output / "png").resolve()
    expected_png_paths: set[Path] = set()
    for item in artifacts:
        screen_id = item.get("screen_id")
        viewport = item.get("viewport", {})
        declared = item.get("png_path")
        canonical = f"png/{screen_id}-{viewport.get('width')}x{viewport.get('height')}.png"
        if declared != canonical:
            errors.append(f"noncanonical PNG path: {declared}")
            continue
        path = (output / declared).resolve()
        try:
            path.relative_to(png_dir)
        except ValueError:
            errors.append(f"PNG path escapes png directory: {declared}")
            continue
        expected_png_paths.add(path)
        if not path.is_file():
            errors.append(f"missing PNG: {declared}")
            continue
        data = path.read_bytes()
        if item.get("sha256") != sha256_bytes(data) or item.get("bytes") != len(data):
            errors.append(f"hash or byte mismatch: {item.get('png_path')}")
        with Image.open(path) as image:
            viewport = item.get("viewport", {})
            if image.mode != "RGB" or image.size != (viewport.get("width"), viewport.get("height")):
                errors.append(f"image geometry mismatch: {item.get('png_path')}")
        m = item.get("measurements", {})
        width = item.get("viewport", {}).get("width", 0)
        if item.get("screen_id") == "editor-populated":
            if width >= 1600 and not (m.get("dock_mode") == "both-docks" and m.get("preview_width", 0) >= 720):
                errors.append("wide editor density rule failed")
            if 1280 <= width < 1600 and not (m.get("dock_mode") == "one-dock" and m.get("preview_width", 0) >= max(640, m.get("content_width", 0) * .5)):
                errors.append("mid editor density rule failed")
            if width < 1280 and m.get("dock_mode") != "drawers":
                errors.append("narrow editor 작업 도구 rule failed")
    actual_png_paths = {path.resolve() for path in (output / "png").glob("*.png")} if (output / "png").is_dir() else set()
    if actual_png_paths != expected_png_paths:
        errors.append("PNG set mismatch: stale, extra, or missing direct png/*.png artifact")
    renderer = manifest.get("renderer", {})
    if renderer.get("name") != "Pillow" or renderer.get("pillow_major") != int(PILLOW_VERSION.split(".", 1)[0]) or renderer.get("image_mode") != "RGB":
        errors.append("renderer provenance policy mismatch")
    if manifest.get("design_tokens") != DESIGN_TOKENS:
        errors.append("design token policy mismatch")
    font_info = renderer.get("font", {})
    font_path = Path(font_info.get("absolute_path", ""))
    if font_path != FONT_PATH or not font_path.is_absolute() or not font_path.is_file() or font_info.get("sha256") != sha256_bytes(font_path.read_bytes()):
        errors.append("font provenance path or SHA mismatch")
    approval = manifest.get("approval", {})
    if approval.get("artifact_manifest_sha") != canonical_artifact_digest(artifacts):
        errors.append("approval aggregate artifact digest mismatch")
    if approval.get("status") not in {"pending", "approved", "rejected"}:
        errors.append("invalid approval status")
    status = approval.get("status")
    if status == "pending" and (approval.get("approver") or approval.get("decided_at")):
        errors.append("pending approval must have blank decision fields")
    if status in {"approved", "rejected"} and (not isinstance(approval.get("approver"), str) or not approval.get("approver").strip() or not isinstance(approval.get("decided_at"), str) or not approval.get("decided_at").strip()):
        errors.append(f"{status} approval must include approver and decided_at")
    if require_approved:
        if status != "approved":
            errors.append("explicit human approval is required")
        else:
            record = decision_record_approval((decision_path or DEFAULT_DECISION_RECORD).resolve())
            expected_record = {
                "status": approval.get("status"),
                "approver": approval.get("approver"),
                "decided_at": approval.get("decided_at"),
                "artifact_manifest_sha": approval.get("artifact_manifest_sha"),
            }
            if record != expected_record:
                errors.append("decision record approval mismatch")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--require-approved", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    if not args.verify:
        build(output)
    errors = verify(output, args.require_approved)
    if errors:
        print("FAIL: " + "; ".join(errors), file=sys.stderr)
        return 1
    print("GREEN: creator workspace prototype artifacts verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
