"""지금 설치된 FLUX.1-dev로 한 장 만들어 본다. 짐작하지 않고 잰다.

**LM Studio를 켜 둔 채로 잰다.** 내리고 재면 유진의 두뇌와 같이 못 쓰는 조합을
된다고 판단하게 된다 (§10.14 조항 2-C).

작게 시작한다 -- 되는지 먼저 보고, 되면 그때 키운다. 안 되면 무엇이 막았는지가
결과다.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
import uuid

BASE = "http://127.0.0.1:8188"
WIDTH, HEIGHT, STEPS = 1920, 1080, 20
PROMPT = (
    "cinematic wide shot of a calm sea at dawn, soft pastel sky, "
    "gentle waves, film grain, 16:9"
)


def call(path: str, body: dict | None = None, timeout: float = 60.0):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(BASE + path, data=data, method="POST" if data else "GET")
    if data is not None:
        request.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read().decode("utf-8")
        return json.loads(raw) if raw else {}


def graph(client_id: str) -> dict:
    return {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": "flux1-dev.safetensors", "weight_dtype": "fp8_e4m3fn"}},
        "2": {"class_type": "DualCLIPLoader", "inputs": {"clip_name1": "t5xxl_fp16.safetensors", "clip_name2": "clip_l.safetensors", "type": "flux"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": "ae.safetensors"}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": PROMPT}},
        "5": {"class_type": "FluxGuidance", "inputs": {"conditioning": ["4", 0], "guidance": 3.5}},
        "6": {"class_type": "EmptySD3LatentImage", "inputs": {"width": WIDTH, "height": HEIGHT, "batch_size": 1}},
        "7": {"class_type": "KSampler", "inputs": {
            "model": ["1", 0], "positive": ["5", 0], "negative": ["4", 0], "latent_image": ["6", 0],
            "seed": 42, "steps": STEPS, "cfg": 1.0, "sampler_name": "euler", "scheduler": "simple", "denoise": 1.0,
        }},
        "8": {"class_type": "VAEDecode", "inputs": {"samples": ["7", 0], "vae": ["3", 0]}},
        "9": {"class_type": "SaveImage", "inputs": {"images": ["8", 0], "filename_prefix": "videobox-measure"}},
    }


def main() -> int:
    client_id = uuid.uuid4().hex
    print(f"보내는 것: {WIDTH}x{HEIGHT}, {STEPS}단계, fp8로 실어 보기", flush=True)
    started = time.monotonic()
    try:
        queued = call("/prompt", {"prompt": graph(client_id), "client_id": client_id})
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", "replace")
        print(f"!! 받아들여지지 않음 {error.code}: {body[:700]}")
        return 1
    prompt_id = queued.get("prompt_id")
    print("작업 번호:", prompt_id, flush=True)

    while time.monotonic() - started < 900:
        time.sleep(3)
        history = call(f"/history/{prompt_id}")
        entry = history.get(prompt_id)
        if not entry:
            continue
        status = (entry.get("status") or {}).get("status_str")
        if status == "error" or (entry.get("status") or {}).get("completed") is False:
            messages = (entry.get("status") or {}).get("messages") or []
            print("!! 실패:", json.dumps(messages, ensure_ascii=False)[:900])
            return 1
        outputs = entry.get("outputs") or {}
        images = [item for node in outputs.values() for item in (node.get("images") or [])]
        if images:
            elapsed = time.monotonic() - started
            print(f"됨 — {elapsed:.1f}초, 파일: {images[0].get('filename')}")
            return 0
    print("!! 900초 안에 안 끝남")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
