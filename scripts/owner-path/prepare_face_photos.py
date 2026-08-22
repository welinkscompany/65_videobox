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

#: **늘리지 않는다. 이것이 2026-08-22 두 번째 실패의 원인이었다.**
#: 원본에서 얼굴이 240~250px인 사진이 많아서 768로 맞추면 16장 중 13장이 **늘어난다.**
#: 늘린 얼굴은 흐릿해서 배울 게 없고, 모델은 원래 알던 "잘생긴 한국 남자"로 돌아간다.
#: 그래서 자른 크기가 이 값보다 작으면 **그 크기 그대로 둔다.** 큰 것만 줄인다.
EDGE = 768
#: 얼굴 상자를 얼마나 넓혀 잡을지. 1.0이면 얼굴만 딱 -- 머리와 턱이 잘린다.
#: 1.8이면 머리 위와 어깨가 조금 들어와 사람으로 보인다. 얼굴 LoRA의 보통 값이다.
MARGIN = 1.8
#: 살결을 부드럽게 하는 세기(0이면 안 함, 1이면 최대). 0.65면 결이 조금 남는다.
SOFTEN = 0.65
#: 1보다 작으면 어두운 쪽이 밝아진다. 0.85면 그늘만 옅어지고 밝은 쪽은 거의 그대로다.
SHADOW_GAMMA = 0.85
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
            face = source.convert("RGB").crop((left, top, left + side, top + side))
            if side > EDGE:  # 줄이기만 한다. 늘리지 않는다.
                face = face.resize((EDGE, EDGE), Image.LANCZOS)
            face = neutralize(face)
            face = soften(face)
        index = len(kept)
        face.save(OUT / f"face-{index:02d}.png")
        (OUT / f"face-{index:02d}.txt").write_text(CAPTION, encoding="utf-8")
        kept.append((photo.name, side))

    for name, why in dropped:
        print(f"!! 버림  {name[:40]:40} -- {why}")
    print(f"\n남긴 사진 {len(kept)}장 / 전체 {len(photos)}장 -> {OUT}")
    if kept:
        sizes = sorted(size for _, size in kept)
        print(f"자른 크기: 가장 작은 것 {sizes[0]}px, 가운데 {sizes[len(sizes) // 2]}px")
        print(f"**학습 설정의 `resolution`을 {min(768, sizes[len(sizes) // 2] // 64 * 64)} 이하로 두세요.**")
        print("그보다 크게 잡으면 늘어난 흐릿한 얼굴로 배우게 됩니다 -- 2026-08-22에 그래서 안 닮았다.")

    if len(kept) < 10:
        print("!! 10장보다 적습니다. 닮은 정도가 낮게 나옵니다 -- 사진을 더 넣어 주세요.")

    contact_sheet(kept)
    print(f"\n**{SHEET} 를 먼저 열어 보세요.**")
    print("얼굴이 꽉 차 있지 않으면 학습에 26분을 쓰기 전에 여기서 멈추는 게 낫습니다.")
    return 0


def neutralize(face):
    """조명이 물들인 색을 걷어낸다.

    **왜 필요한가 (2026-08-22 3차 실패).** owner가 결과를 보고
    `피부톤도 너무 동남아사람 같고`라고 했다. 재보니 13장 중 **8장이 노란색이
    강했다**(얼굴 부분에서 빨강이 파랑보다 45 이상 높음) -- 실내 형광등과 노을빛이다.
    모델은 그 노란빛을 **조명이 아니라 피부색으로** 배웠다.

    **처음에 회색기준(gray-world)으로 맞췄다가 한 번 더 틀렸다.** 얼굴 평균을 완전한
    회색으로 만들면 빨강-파랑 차이가 0이 되는데, **사람 피부는 원래 붉다.** 0으로
    만들면 회색으로 뜬 얼굴을 배우게 된다.

    그래서 기준을 owner 사진 중 **증명사진**(스튜디오 조명이라 색이 맞는 것)에서
    가져왔다. 그 사진의 얼굴 부분이 `R 177 · G 144 · B 135`이고, 평균으로 나누면
    아래 `TARGET`이다. 조명이 다른 사진들을 이 비율로 옮긴다.

    실측 비교 (얼굴 부분 빨강-파랑):
        증명사진·사무실 등 색이 맞는 것   42~44
        실내 형광등·노을이 물든 것        50~59   <- 이것들을 42 근처로 옮긴다
        회색기준으로 맞췄을 때             0      <- 너무 걷어낸 값

    **너무 세게 걷어내면 얼굴이 파랗게 뜬다.** 그래서 보정 배율에 상한을 둔다.
    """
    import numpy as np
    from PIL import Image

    array = np.asarray(face, dtype=np.float32)
    height, width = array.shape[:2]
    # 가장자리는 배경이라 뺀다. 가운데 절반만 보고 조명 색을 잰다.
    middle = array[height // 4:height * 3 // 4, width // 4:width * 3 // 4]
    means = middle.reshape(-1, 3).mean(axis=0)
    if means.min() <= 1:
        return face
    #: owner의 증명사진에서 잰 얼굴 색 비율(R 177 · G 144 · B 135를 평균으로 나눈 값).
    target = np.array([1.157, 0.941, 0.882], dtype=np.float32)
    gains = (means.mean() * target) / means
    gains = np.clip(gains, 0.75, 1.35)
    return Image.fromarray(np.clip(array * gains, 0, 255).astype(np.uint8))


def soften(face):
    """그늘과 잔주름을 부드럽게 편다. **owner 지시 2026-08-22.**

    > `얼굴이 주름이랑 굴곡이 없게해줘. 지금 너무 나이 들어보여`
    > `보정한 사진으로 만들어서 학습해봐`

    학습 사진이 형광등 아래 셀카라 **눈 밑 그림자와 팔자주름이 강하게 찍혔다.**
    모델은 그것을 조명이 아니라 얼굴 생김새로 배운다. 그래서 실제보다 나이 들어
    보이는 얼굴이 나온다. 조명 색을 걷어낸 것과 같은 이유다(`neutralize`).

    두 가지를 한다.

    1. **어두운 쪽만 끌어올린다.** 그늘이 옅어지면 주름이 덜 파인다. 밝은 쪽은
       그대로 둬서 얼굴이 밋밋해지지 않게 한다.
    2. **살결만 부드럽게 한다**(bilateral). 경계는 지키므로 눈·눈썹·머리카락은
       또렷하게 남는다.

    **너무 하면 플라스틱처럼 된다.** 그래서 원본과 65:35로 섞는다 -- 사람 피부의
    결이 조금 남아야 사진으로 보인다. 세기를 바꾸고 싶으면 `SOFTEN`을 만져라.
    """
    import cv2
    import numpy as np
    from PIL import Image

    array = np.asarray(face, dtype=np.uint8)

    # 1) 어두운 쪽만 끌어올린다. 감마 곡선이라 밝은 쪽은 거의 그대로다.
    lifted = (np.power(array / 255.0, SHADOW_GAMMA) * 255.0).astype(np.uint8)

    # 2) 살결만 부드럽게. 색 차이가 큰 경계(눈·눈썹)는 안 뭉갠다.
    smooth = cv2.bilateralFilter(lifted, d=9, sigmaColor=45, sigmaSpace=9)

    blended = cv2.addWeighted(smooth, SOFTEN, lifted, 1.0 - SOFTEN, 0)
    return Image.fromarray(blended)


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
