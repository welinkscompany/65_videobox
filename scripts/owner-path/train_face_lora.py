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
BASE = "http://127.0.0.1:8188"
PHOTOS = Path(r"D:\AI_Workspace_louis_office_50\20_project\65_videobox-project\drive-sync\내 얼굴 사진")
#: ComfyUI input 아래의 폴더 이름. `LoadImageDataSetFromFolder`가 이 이름으로 읽는다.
DATASET = "videobox-owner-face"
#: **사진은 1024px 이하로 줄여서 넣는다.** 원본 크기로는 메모리가 터진다(위 참고).
#: 학습 문장. 이 낱말이 나중에 프롬프트에서 얼굴을 부르는 열쇠가 된다.
TRIGGER = "photo of ohwnrface person"
LORA_NAME = "videobox-owner-face"
PHOTO_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}

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
    name = f"{image.stem.encode('ascii', 'ignore').decode() or 'photo'}-{uuid.uuid4().hex[:8]}{image.suffix.lower()}"
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
            "loss_function": "MSE", "seed": 20260821, "training_dtype": "bf16",
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
            "gradient_checkpointing": True, "checkpoint_depth": 1, "offloading": False,
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

    print(f"사진 {len(found)}장을 올립니다 -> ComfyUI input/{DATASET}", flush=True)
    for photo in found:
        upload(photo, DATASET)

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
