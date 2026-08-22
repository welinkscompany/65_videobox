"""대표님 얼굴을 한 번 학습시킨다. 학습 도구를 따로 깔 필요가 없다.

**확인한 것 (2026-08-21):** 지금 깔린 ComfyUI 0.24.0에 학습 노드가 **이미 들어 있다** --
`LoadImageDataSetFromFolder` → `MakeTrainingDataset` → `TrainLoraNode` → `SaveLoRA`.
인계 문서에는 "학습 도구는 무료고 5090이면 한 번에 끝난다"고만 적혀 있었는데, 사실은
**받을 것도 없다.** 노드 777개 중에 이미 있다.

왜 LoRA인가 (2026-08-21 인계에서 이미 정한 것, 여기서 다시 정하지 않는다):

- img2img로는 안 된다. denoise를 0.35→0.55→0.75로 올려도 끝까지 정면이었고,
  강도를 올리면 포즈가 바뀌는 게 아니라 얼굴이 남의 것이 됐다.
- Kontext는 **한 장을 고치는** 도구다. 열 장을 뽑으려면 열 번 고쳐야 하고
  고칠수록 원본에서 멀어진다.
- LoRA는 한 번 학습해 두면 **어느 프롬프트에도** 얹힌다. owner가 원한 것이 그것이다.

    .venv/Scripts/python.exe scripts/owner-path/train_face_lora.py

사진이 없으면 아무것도 하지 않고 어디에 넣으면 되는지만 알려 준다.
"""
from __future__ import annotations

import json
import mimetypes
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from PIL import Image

# **먼저 자리를 확인하라. 설정을 만지기 전에 이것부터다.**
#
# 2026-08-22에 두 번 실패했고 둘 다 원인이 같았다 -- 자리가 없었다.
#   1차: GPU 메모리 부족(74분)  2차: 4시간 초과(offloading으로 억지로 밀어 넣음)
#
# 그때 실측: GPU 사용률 6%인데 **VRAM 29.2/32.6GB**, 시스템 **RAM 56.9/61.6GB**.
# LM Studio 하나가 VRAM 29GB와 RAM 25GB를 동시에 물고 있었다. 모델이 올라만
# 있고 놀아도 자리는 그대로 차지한다 -- **사용률과 점유는 다른 값이다.**
#
# 나는 사진 크기와 학습 설정만 두 번 만졌다. 원인은 거기가 아니었다.
#
#     nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total --format=csv
#
# 여유가 20GB 아래면 **LM Studio에서 모델을 내리고** 시작하라. 그동안 유진 대화·
# 대본 쓰기·B-roll 분석이 멈춘다(끝나면 다시 올리면 된다).
#
# **그런데 `lms unload`만으로는 안 내려간다 -- 몇 초 만에 저절로 다시 올라온다.**
# 2026-08-22에 내리자마자 `lms ps`에 다시 떠 있었다. VideoBox 컨테이너의 B-roll
# 분석 루프가 1분마다 모델을 부르고, LM Studio는 요청이 오면 알아서 다시 올린다.
# **부르는 쪽을 먼저 멈춰야 한다.** 순서는 이렇다:
#
#     docker compose -p 65_videobox stop      # 부르는 쪽부터
#     lms unload --all                        # 그다음 내린다
#     nvidia-smi ...                          # 여유 20GB 넘는지 눈으로 확인
#     .venv/Scripts/python.exe scripts/owner-path/train_face_lora.py
#
# 끝나면 `scripts/owner-ready.ps1 -Mode Start`로 다시 올린다.
#
# 2026-08-22 3차 시작 시점 실측 -- VRAM 여유 24.2GB, RAM 여유 32.6GB.
# 1·2차 때는 각각 3.4GB와 4.7GB였다.
#
# ============================================================================
# **다음 사람은 여기서부터 시작하라. 자리 문제가 아니다.**
#
# 2026-08-22에 자리를 완전히 비우고(VRAM 30GB 여유, 큐 비움, ComfyUI 새로 띄움)
# 사진도 18장 768x768로 통일해서 돌렸는데 **똑같이 터졌다.** 요구량이 이랬다:
#
#     72장 · 크기 제각각   -> 56.8GB
#     18장 · 768 통일      -> 59.6GB
#     18장 · 캐시까지 비움 -> 59.08GB
#
# **사진을 4분의 1로 줄였는데 요구량이 오히려 늘었다.** 데이터셋 크기와 무관하다는
# 뜻이고, 그러면 먹는 쪽은 사진이 아니라 **모델 설정**이다. 유력한 것은
# `training_dtype: "bf16"` -- fp8로 실은 12B 모델을 학습할 때 bf16으로 되올리면
# 그것만으로 24GB쯤이고, 여기에 AdamW 상태와 활성값이 얹힌다.
#
# **다음에 시도할 순서 (한 번에 하나씩, 매번 요구량 숫자를 적어라):**
#   1) `training_dtype`을 `"fp8_e4m3fn"`으로. 숫자가 절반 아래로 떨어지는지 본다.
#      떨어지면 그게 원인이다.
#   2) `checkpoint_depth`를 1에서 4~8로. 1은 사실상 체크포인팅을 거의 안 하는 값이다.
#   3) 그래도면 `offloading: True`. 2차가 이 설정으로 **메모리는 통과했다**
#      (터지지 않고 4시간 넘게 돌았다). 다만 느리고, 그때 GPU 0%로 물려 있었다.
#
# **숫자가 안 변하면 그 변수는 원인이 아니다.** 오늘 나는 사진 크기·장수·LM Studio를
# 차례로 없앴는데 59GB가 꿈쩍하지 않았다. 그게 답을 말해 주고 있었는데 세 번을 더
# 돌리고 나서야 봤다.
# ============================================================================
BASE = "http://127.0.0.1:8188"
PHOTOS = Path(r"D:\AI_Workspace_louis_office_50\20_project\65_videobox-project\drive-sync\내 얼굴 사진")
#: ComfyUI input 아래의 폴더 이름. `LoadImageDataSetFromFolder`가 이 이름으로 읽는다.
DATASET = "videobox-owner-face"
#: **사진은 1024px 이하로 줄여서 넣는다.** 원본 크기로는 메모리가 터진다(위 참고).
#: 학습 문장. 이 낱말이 나중에 프롬프트에서 얼굴을 부르는 열쇠가 된다.
TRIGGER = "photo of ohwnrface person"
LORA_NAME = "videobox-owner-face"
PHOTO_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
#: **전부 같은 크기의 정사각형으로 맞춰서 올린다.** 2026-08-22 3차 실패의 원인이다 --
#: GPU를 통째로 비웠는데도 56.8GB를 요구하며 터졌다. 사진을 "1024px로 줄였다"고
#: 했지만 실제로는 **가로만** 1024였고 세로는 그대로여서 1024x1822짜리가 섞여
#: 있었다. `bucket_mode`가 꺼져 있으면 전부 가장 큰 것에 맞춰지므로 한 장이 크면
#: 열여덟 장이 다 커진다. 얼굴 학습은 정사각형 가운데 잘라내기가 표준이기도 하다.
EDGE = 512

#: 실측이 아니라 출발점이다. **돌려 보고 이 값을 고쳐라.** 15장 기준으로
#: 얼굴 LoRA는 보통 사진 한 장당 100단계 안팎이면 닮기 시작한다.
STEPS = 1600
RANK = 16
LEARNING_RATE = 0.0002
BATCH_SIZE = 1


def call(path: str, body: dict | None = None, timeout: float = 120.0) -> dict:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(BASE + path, data=data, method="POST" if data else "GET")
    if data is not None:
        request.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read().decode("utf-8")
        return json.loads(raw) if raw else {}


def upload(image: Path, subfolder: str) -> str:
    """ComfyUI의 input 폴더로 사진을 올린다.

    한글 파일 이름을 여기서 직접 다루지 않는다 -- 2026-08-20에 Windows curl이
    cp949로 보내서 이름이 깨졌고, 그것을 제품 결함으로 착각했다. 이름은 우리가
    붙인 ASCII로 바꿔 올리고, 원래 이름은 쓰지 않는다.
    """
    boundary = "----videobox" + uuid.uuid4().hex
    mime = mimetypes.guess_type(image.name)[0] or "image/png"
    # **이름에 무작위 꼬리를 붙이지 않는다.** 2026-08-22에 이것 때문에 네 번 실패했다 --
    # 돌릴 때마다 18장이 새 이름으로 올라가서 폴더에 18 -> 36 -> 54 -> **72장**이
    # 쌓였고, `LoadImageDataSetFromFolder`는 그 폴더를 통째로 읽는다. 학습은 매번
    # 앞선 실패의 사진까지 같이 물고 있었다. 메모리가 터진 진짜 이유가 여기다.
    # 같은 이름 + `overwrite=true`라야 다시 돌려도 18장 그대로다.
    name = f"{image.stem.encode('ascii', 'ignore').decode() or 'photo'}{image.suffix.lower()}"
    parts = [
        (f'--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="{name}"\r\n'
         f"Content-Type: {mime}\r\n\r\n").encode("utf-8"),
        image.read_bytes(),
        f"\r\n--{boundary}\r\nContent-Disposition: form-data; name=\"subfolder\"\r\n\r\n{subfolder}\r\n".encode("utf-8"),
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"overwrite\"\r\n\r\ntrue\r\n".encode("utf-8"),
        f"--{boundary}--\r\n".encode("utf-8"),
    ]
    request = urllib.request.Request(f"{BASE}/upload/image", data=b"".join(parts), method="POST")
    request.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    with urllib.request.urlopen(request, timeout=300) as response:
        return json.loads(response.read().decode("utf-8")).get("name", name)


def graph() -> dict:
    """학습 그래프. 그림 만들 때와 **같은 모델·같은 dtype**을 쓴다.

    다른 dtype으로 학습해 두면 나중에 얹었을 때 왜 안 닮는지 알 수 없게 된다.
    """
    return {
        "1": {"class_type": "UNETLoader", "inputs": {
            "unet_name": "flux1-dev.safetensors", "weight_dtype": "fp8_e4m3fn"}},
        "2": {"class_type": "DualCLIPLoader", "inputs": {
            "clip_name1": "t5xxl_fp16.safetensors", "clip_name2": "clip_l.safetensors", "type": "flux"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": "ae.safetensors"}},
        "4": {"class_type": "LoadImageDataSetFromFolder", "inputs": {"folder": DATASET}},
        "5": {"class_type": "MakeTrainingDataset", "inputs": {
            "images": ["4", 0], "vae": ["3", 0], "clip": ["2", 0], "texts": TRIGGER}},
        "6": {"class_type": "TrainLoraNode", "inputs": {
            "model": ["1", 0], "latents": ["5", 0], "positive": ["5", 1],
            "batch_size": BATCH_SIZE, "grad_accumulation_steps": 1, "steps": STEPS,
            "learning_rate": LEARNING_RATE, "rank": RANK, "optimizer": "AdamW",
            # **`none` = 모델의 원래 계산 dtype을 그대로 둔다.** `bf16`은 fp8로 실은 12B
            # 모델을 통째로 bf16으로 되올려서 그것만으로 24GB쯤 된다. 2026-08-22 4차
            # 실패까지 이 값이 `bf16`이었다. (`fp8_e4m3fn`은 이 노드의 선택지에 없다 --
            # 고를 수 있는 것은 `bf16`/`fp32`/`none` 셋뿐이다.)
            "loss_function": "MSE", "seed": 20260821, "training_dtype": "none",
            "lora_dtype": "bf16", "quantized_backward": False, "algorithm": "LoRA",
            # 5090에 32GB가 있어도 LM Studio가 같이 물고 있다. 체크포인팅을 끄면
            # 학습이 아니라 메모리가 먼저 터진다.
            # 2026-08-22 실측: 원본 크기(최대 2639px) 18장으로 돌렸더니 74분 만에
            # **GPU 메모리 부족**으로 죽었다(60.45GiB 요구 / 31.84GiB 한계).
            # 사진을 1024px로 줄이고 `offloading`을 켠다 -- 안 쓰는 층을 램으로
            # 내려 두는 옵션이라 느려지지만 32GB 안에 들어간다.
            # **2차도 실패했다 — 이번엔 4시간을 넘겨 안 끝났다(14,409초).**
            #
            # 내 방법이 틀렸다. 사진을 1024px로 줄이면서 `offloading`도 **같이**
            # 켰다. offloading은 안 쓰는 층을 램으로 내렸다 올리므로 훨씬 느리다.
            # 1024px만으로 메모리가 충분했을 수도 있는데 확인하지 않았다.
            #
            # **다음 사람: 한 번에 하나만 바꿔라.**
            #   1) `offloading: False`로 되돌리고 1024px 그대로 돌린다.
            #      들어가면 그걸로 끝이다 -- 1차 실패는 사진 크기 탓이었던 것이다.
            #   2) 그래도 메모리가 터지면 `STEPS`를 800으로, 그다음 `RANK`를 8로.
            #   3) 그래도면 사진을 768px로 줄이고, 마지막에 offloading을 켠다.
            #
            # 시간을 재서 남겨라. 지금 4시간 상한(`main`의 while)도 근거 없는 값이다.
            # ================================================================
            # **손잡이 넷을 다 돌려 봤고 넷 다 실패했다. 다시 돌리지 마라.**
            # 2026-08-22 실측, 요구 메모리(한계 31.84GB):
            #
            #   dtype bf16 + depth 1                 -> 59.08GB   터짐
            #   dtype none + depth 1                 -> 54.73GB   터짐
            #   dtype none + depth 5                 -> 57.99GB   터짐 (깊게 = 더 나쁨)
            #   dtype none + depth 1 + offloading    -> 55.79GB   터짐
            #   위와 같고 사진만 512x512                -> 55.16GB   터짐
            #
            # **해상도를 바꿔도 숫자가 안 움직인다. 계산이 맞아떨어진다:**
            #     FLUX.1-dev 12B x 4바이트(fp32) = 48GB + 활성값 ~7GB = 55GB
            # 이 노드는 12B 모델을 fp32로 통째로 올린다. 사진을 몇 장 넣든 몇 픽셀로
            # 줄이든 이 48GB는 그대로다. **32GB 카드로는 이 노드로 FLUX 학습이 안 된다.**
            # 설정 문제가 아니라 도구의 한계다. 손잡이를 더 돌리지 마라.
            #
            # 사진도 72장->18장, 크기도 4분의 1로 줄였는데 숫자가 55~59GB에서 안 나온다.
            # GPU를 통째로 비워도 같다. **어느 손잡이도 이 벽을 못 넘는다.**
            #
            # **다음 사람에게: 이 숫자를 그대로 믿지 마라.** 32GB 카드에서 "할당됨
            # 55GB"는 실제 상주 메모리일 수 없다. 누적 할당량이거나 offload된 것까지
            # 세는 값으로 보인다. 그렇다면 나는 내내 **비교할 수 없는 값을 비교하며**
            # 손잡이를 돌린 셈이다. 다음 판단은 이 숫자가 아니라 실제 상주량
            # (`torch.cuda.max_memory_allocated`나 nvidia-smi 최고치)으로 하라.
            #
            # **2026-08-22 마지막 실측 -- 램을 128GB로 올린 뒤.**
            # 메모리 벽은 넘었다. 터지지 않고 80분을 돌았다. **그런데 속도 벽에 걸렸다:**
            #
            #     Training LoRA: 2%|2 | 32/1600 [1:19:26<65:02:18, 149.32s/it, loss=0.4440]
            #
            # **한 단계에 149초. 1600단계면 65시간이다.** loss는 움직이고 있었으니
            # 학습 자체는 되고 있었다. offloading이 매 단계마다 12B 모델을 램과 카드
            # 사이로 옮기는 값이 이것이다. **되기는 되는데 사흘 걸린다 -- 답이 아니다.**
            #
            # 램 증설이 헛일이었다는 뜻은 아니다. 늘리기 전에는 2~4분 안에 죽었다.
            # 다만 이 노드로는 여기까지가 끝이다. **ai-toolkit으로 가라**(fp8로 학습해
            # offloading 없이 카드 안에 들어간다). `docs/handoffs/`의 최신 인계 참고.
            #
            # 아직 안 해 본 것 (그래도 이 노드를 고집한다면):
            #   - 사진을 512x512로. 768은 FLUX 12B + 32GB에는 여전히 크다
            #   - `bucket_mode: True` -- 크기를 묶어서 처리한다
            #   - `algorithm`을 `LoKr`로. LoRA보다 학습 파라미터가 훨씬 적다
            # ================================================================
            "gradient_checkpointing": True, "checkpoint_depth": 1, "offloading": True,
            "existing_lora": "[None]", "bucket_mode": False, "bypass_mode": False}},
        "7": {"class_type": "SaveLoRA", "inputs": {
            "lora": ["6", 0], "prefix": f"loras/{LORA_NAME}", "steps": STEPS}},
    }


def photos() -> list[Path]:
    if not PHOTOS.is_dir():
        return []
    return sorted(p for p in PHOTOS.iterdir() if p.is_file() and p.suffix.lower() in PHOTO_SUFFIXES)


def main() -> int:
    found = photos()
    if not found:
        print(f"사진이 없습니다. 여기에 10~20장 넣어 주세요:\n  {PHOTOS}")
        print("  (그 폴더의 `여기에-사진을-넣어주세요.txt`에 어떤 사진이 좋은지 적어 두었습니다.)")
        return 1
    if len(found) < 10:
        # 막지는 않는다. 다만 **결과를 근거로 쓰기 전에** 이 사실을 알아야 한다 --
        # 사진이 모자라 낮게 나온 값을 보고 "LoRA가 별로다"라고 판단하면 틀린다.
        print(f"!! 사진이 {len(found)}장뿐입니다. 10장보다 적으면 닮은 정도가 낮게 나옵니다.")
        print("!! 그 결과를 'LoRA가 별로다'의 근거로 쓰지 마세요. 사진이 모자란 것입니다.")

    print(f"사진 {len(found)}장을 {EDGE}x{EDGE}로 맞춰 올립니다 -> ComfyUI input/{DATASET}", flush=True)
    staged = Path(__file__).resolve().parent / ".prepared-face-photos"
    staged.mkdir(exist_ok=True)
    for old in staged.glob("*.png"):
        old.unlink()
    for index, photo in enumerate(found):
        # 원본은 건드리지 않는다. 가운데를 정사각형으로 잘라 옆에 새로 만든다.
        with Image.open(photo) as image:
            image = image.convert("RGB")
            side = min(image.size)
            left = (image.width - side) // 2
            top = (image.height - side) // 2
            square = image.crop((left, top, left + side, top + side)).resize(
                (EDGE, EDGE), Image.LANCZOS)
        prepared = staged / f"face-{index:02d}.png"
        square.save(prepared)
        upload(prepared, DATASET)

    print(f"학습 시작: {STEPS}단계, rank {RANK}, 학습률 {LEARNING_RATE}", flush=True)
    print("  (5090에서 20~40분 예상입니다. 정확한 값은 아래 결과가 말해 줍니다.)", flush=True)
    started = time.monotonic()
    try:
        queued = call("/prompt", {"prompt": graph(), "client_id": uuid.uuid4().hex})
    except urllib.error.HTTPError as error:
        print(f"!! 받아들여지지 않음 {error.code}: {error.read().decode('utf-8', 'replace')[:900]}")
        return 1
    prompt_id = queued.get("prompt_id")
    print("작업 번호:", prompt_id, flush=True)

    while time.monotonic() - started < 4 * 60 * 60:
        time.sleep(15)
        entry = call(f"/history/{prompt_id}").get(prompt_id)
        if not entry:
            print(f"  ... {time.monotonic() - started:.0f}초", flush=True)
            continue
        status = (entry.get("status") or {})
        if str(status.get("status_str")) == "error":
            print("!! 실패:", json.dumps(status.get("messages"), ensure_ascii=False)[:1200])
            return 1
        if status.get("completed"):
            elapsed = time.monotonic() - started
            print(f"됨 -- {elapsed / 60:.1f}분. LoRA 이름: {LORA_NAME}")
            print("다음: .venv/Scripts/python.exe scripts/owner-path/measure_face_likeness.py")
            return 0
    print("!! 4시간 안에 안 끝남")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
