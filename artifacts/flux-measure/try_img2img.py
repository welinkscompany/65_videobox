"""올린 사진을 FLUX로 바꿔 보면 어디까지 되는지 잰다.

owner가 물었다 -- "내 사진을 올려서 옆모습으로 바꾼다든지" 할 수 있느냐.
**짐작으로 답하지 않는다.** 지금 깔린 것(flux1-dev + img2img)만으로 강도를 올려 가며
같은 사람으로 남는지 본다.

denoise가 낮으면 원본에 가깝고(같은 사람, 거의 그대로), 높으면 프롬프트를 따르지만
얼굴이 남의 것이 된다. 그 사이 어디가 쓸 만한지가 결과다.
"""
from __future__ import annotations

import json
import shutil
import time
import urllib.request
import uuid
from pathlib import Path

BASE = "http://127.0.0.1:8188"
HERE = Path(__file__).parent
OUT = HERE / "img2img"
SOURCE = HERE / "thumbnails" / "01-놀란-편집자-원본.png"
PROMPT = "side profile portrait of the same young Korean man, looking to the left, studio lighting, sharp detail"
STRENGTHS = [0.35, 0.55, 0.75]


def call(path: str, body: dict | None = None, timeout: float = 120.0):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(BASE + path, data=data, method="POST" if data else "GET")
    if data is not None:
        request.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read().decode("utf-8")
        return json.loads(raw) if raw else {}


def upload(image: Path) -> str:
    boundary = "----videobox" + uuid.uuid4().hex
    body = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="{image.name}"\r\n'
        "Content-Type: image/png\r\n\r\n"
    ).encode("utf-8") + image.read_bytes() + f"\r\n--{boundary}--\r\n".encode("utf-8")
    request = urllib.request.Request(f"{BASE}/upload/image", data=body, method="POST")
    request.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.loads(response.read().decode("utf-8"))["name"]


def graph(uploaded: str, denoise: float, seed: int) -> dict:
    return {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": "flux1-dev.safetensors", "weight_dtype": "fp8_e4m3fn"}},
        "2": {"class_type": "DualCLIPLoader", "inputs": {"clip_name1": "t5xxl_fp16.safetensors", "clip_name2": "clip_l.safetensors", "type": "flux"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": "ae.safetensors"}},
        "4": {"class_type": "LoadImage", "inputs": {"image": uploaded}},
        "5": {"class_type": "VAEEncode", "inputs": {"pixels": ["4", 0], "vae": ["3", 0]}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": PROMPT}},
        "7": {"class_type": "FluxGuidance", "inputs": {"conditioning": ["6", 0], "guidance": 3.5}},
        "8": {"class_type": "KSampler", "inputs": {
            "model": ["1", 0], "positive": ["7", 0], "negative": ["6", 0], "latent_image": ["5", 0],
            "seed": seed, "steps": 20, "cfg": 1.0, "sampler_name": "euler", "scheduler": "simple", "denoise": denoise,
        }},
        "9": {"class_type": "VAEDecode", "inputs": {"samples": ["8", 0], "vae": ["3", 0]}},
        "10": {"class_type": "SaveImage", "inputs": {"images": ["9", 0], "filename_prefix": "videobox-i2i"}},
    }


def run(uploaded: str, denoise: float, target: Path) -> float:
    started = time.monotonic()
    prompt_id = call("/prompt", {"prompt": graph(uploaded, denoise, 7), "client_id": uuid.uuid4().hex})["prompt_id"]
    while time.monotonic() - started < 600:
        time.sleep(2)
        entry = call(f"/history/{prompt_id}").get(prompt_id)
        if not entry:
            continue
        images = [item for node in (entry.get("outputs") or {}).values() for item in (node.get("images") or [])]
        if images:
            with urllib.request.urlopen(f"{BASE}/view?filename={images[0]['filename']}&type=output", timeout=120) as response:
                target.write_bytes(response.read())
            return time.monotonic() - started
        if (entry.get("status") or {}).get("status_str") == "error":
            raise RuntimeError(json.dumps((entry.get("status") or {}).get("messages"), ensure_ascii=False)[:400])
    raise TimeoutError("안 끝남")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SOURCE, OUT / "00-원본.png")
    uploaded = upload(SOURCE)
    print("올린 이름:", uploaded, flush=True)
    for denoise in STRENGTHS:
        target = OUT / f"denoise-{denoise}.png"
        elapsed = run(uploaded, denoise, target)
        print(f"  denoise {denoise}: {elapsed:.1f}초 → {target.name}", flush=True)


if __name__ == "__main__":
    main()
