"""학습에 넣을 얼굴 사진을 **얼굴 기준으로** 잘라 준비한다.

**왜 따로 만들었나 (2026-08-22, 첫 학습이 실패한 이유).**

첫 시도는 사진 **가운데**를 정사각형으로 잘랐다. 26분 학습이 끝나고 owner가 보고
`전혀 안 닮았는데`라고 했다. 그제서야 잘린 사진들을 **한 장씩 눈으로 보고** 원인이
나왔다 -- 나는 만든 것을 한 번도 안 열어 봤다.

    - 얼굴이 아예 없는 사진 2장 (강의실 슬라이드, 빈 강의실)
    - 선글라스로 얼굴을 가린 사진 2장
    - 나머지도 **얼굴이 화면의 20%가 안 됐다** -- 사무실·컴퓨터·하늘이 더 컸다

사진이 16:9(1024x576)인데 가운데를 자르면 인물이 옆에 있을 때 얼굴이 잘려 나간다.
**모델은 얼굴보다 배경을 더 많이 배웠다.**

**그래서 여기서는 얼굴을 찾아서 그 둘레만 자른다.** 얼굴을 못 찾은 사진은 버린다 --
`!! 버림`으로 이름을 찍어 주므로, 버려진 것이 정말 얼굴 없는 사진인지 확인할 수 있다.

돌리고 나면 **반드시 대조표(contact sheet)를 열어 보라.** 26분을 쓰기 전에 3초면 된다.

    .venv/Scripts/python.exe scripts/owner-path/prepare_face_photos.py
"""
from __future__ import annotations

import shutil
from pathlib import Path

SRC = Path(r"D:\AI_Workspace_louis_office_50\20_project\65_videobox-project\drive-sync\내 얼굴 사진")
OUT = Path(__file__).resolve().parent / ".prepared-face-photos"
SHEET = Path(__file__).resolve().parents[2] / "artifacts" / "face-check" / "prepared-contact-sheet.jpg"

EDGE = 768
#: 얼굴 상자를 얼마나 넓혀 잡을지. 1.0이면 얼굴만 딱 -- 머리와 턱이 잘린다.
#: 1.8이면 머리 위와 어깨가 조금 들어와 사람으로 보인다. 얼굴 LoRA의 보통 값이다.
MARGIN = 1.8
SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
CAPTION = "photo of [trigger] man"


def main() -> int:
    import cv2
    from PIL import Image

    if not SRC.is_dir():
        print(f"!! 사진 폴더가 없습니다: {SRC}")
        return 1

    detector = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    eye_detector = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_eye.xml")

    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    photos = sorted(p for p in SRC.iterdir() if p.suffix.lower() in SUFFIXES)
    kept, dropped = [], []

    for photo in photos:
        image = cv2.imdecode(
            __import__("numpy").fromfile(str(photo), dtype="uint8"), cv2.IMREAD_COLOR)
        if image is None:
            dropped.append((photo.name, "읽지 못함"))
            continue
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        faces = detector.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(80, 80))
        if len(faces) == 0:
            dropped.append((photo.name, "얼굴을 못 찾음"))
            continue

        # 여러 개가 잡히면 **가장 큰 것**이 주인공이다. 뒤에 지나가는 사람이 아니라.
        x, y, w, h = max(faces, key=lambda f: f[2] * f[3])

        # **눈이 보여야 남긴다.** 이 한 줄이 두 가지를 한꺼번에 거른다:
        #   - 선글라스로 눈을 가린 사진 (얼굴은 맞지만 배울 게 없다)
        #   - 얼굴이 아닌 것을 얼굴로 잘못 잡은 사진 (책상과 모니터를 얼굴로 잡았다)
        # 눈은 사람을 알아보는 데 가장 중요한 부분이라, 가려진 사진으로 배우면
        # 닮지 않는다. 2026-08-22 첫 실패에서 실제로 두 장이 그랬다.
        eyes = eye_detector.detectMultiScale(
            gray[y:y + h, x:x + w], scaleFactor=1.1, minNeighbors=6,
            minSize=(max(12, w // 12), max(12, w // 12)))
        if len(eyes) == 0:
            dropped.append((photo.name, "눈이 안 보임 (선글라스이거나 얼굴이 아님)"))
            continue

        cx, cy = x + w / 2, y + h / 2
        side = max(w, h) * MARGIN
        # 사진 밖으로 나가면 안쪽으로 민다. 잘라내지 않고 위치만 옮긴다 --
        # 잘라내면 얼굴이 한쪽으로 치우친 그림이 된다.
        side = min(side, image.shape[0], image.shape[1])
        left = int(min(max(cx - side / 2, 0), image.shape[1] - side))
        top = int(min(max(cy - side / 2, 0), image.shape[0] - side))
        side = int(side)

        with Image.open(photo) as source:
            face = source.convert("RGB").crop(
                (left, top, left + side, top + side)).resize((EDGE, EDGE), Image.LANCZOS)
        index = len(kept)
        face.save(OUT / f"face-{index:02d}.png")
        (OUT / f"face-{index:02d}.txt").write_text(CAPTION, encoding="utf-8")
        kept.append((photo.name, f"{w}x{h} 얼굴"))

    for name, why in dropped:
        print(f"!! 버림  {name[:40]:40} -- {why}")
    print(f"\n남긴 사진 {len(kept)}장 / 전체 {len(photos)}장 -> {OUT}")

    if len(kept) < 10:
        print("!! 10장보다 적습니다. 닮은 정도가 낮게 나옵니다 -- 사진을 더 넣어 주세요.")

    contact_sheet(kept)
    print(f"\n**{SHEET} 를 먼저 열어 보세요.**")
    print("얼굴이 꽉 차 있지 않으면 학습에 26분을 쓰기 전에 여기서 멈추는 게 낫습니다.")
    return 0


def contact_sheet(kept: list) -> None:
    """만든 것을 눈으로 볼 수 있게 한 장으로 붙인다.

    **이 저장소가 비싸게 배운 것이다** -- 만든 것을 안 열어 보면 조용히 틀린다.
    """
    from PIL import Image

    files = sorted(OUT.glob("*.png"))
    columns, cell = 6, 220
    rows = (len(files) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * cell, rows * cell), "white")
    for index, path in enumerate(files):
        with Image.open(path) as image:
            sheet.paste(image.resize((cell, cell)), ((index % columns) * cell, (index // columns) * cell))
    SHEET.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(SHEET, quality=88)


if __name__ == "__main__":
    raise SystemExit(main())
