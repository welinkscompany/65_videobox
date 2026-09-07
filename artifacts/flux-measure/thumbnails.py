"""유튜브 썸네일처럼 사람이 들어간 그림을 만들고, 그 위에 우리 글꼴로 글자를 얹는다.

**그림은 ComfyUI(FLUX.1-dev)가, 글자는 우리 렌더 경로가 쓰는 것과 같은 ffmpeg
drawtext가 그린다.** 그래서 이 시험은 두 가지를 한 번에 잰다 -- 사람이 들어간 그림이
쓸 만하게 나오는지, 그리고 저장소에 함께 들어 있는 한국어 글꼴이 그 위에서 읽히는지.

썸네일은 작게 보인다. 그래서 글자를 크게, 테두리를 두껍게 준다 -- 자막 규칙과 다르다.
"""
from __future__ import annotations

import json
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

BASE = "http://127.0.0.1:8188"
ROOT = Path(__file__).resolve().parents[2]
FONTS = ROOT / "assets" / "fonts" / "korean"
OUT = Path(__file__).parent / "thumbnails"
WIDTH, HEIGHT, STEPS = 1280, 720, 20

# (파일 이름, 그림 프롬프트, 얹을 글자, 글꼴, 글자색, 테두리색)
PLAN = [
    (
        "01-놀란-편집자",
        "close-up portrait of a young Korean man at a desk with a laptop, "
        "wide surprised eyes, mouth open, bright studio lighting, vivid colors, "
        "shallow depth of field, high contrast, youtube thumbnail style",
        "편집 3시간이\n3분으로",
        "BlackHanSans-Regular.ttf", "#FFE500", "#101014",
    ),
    (
        "02-카메라-든-여성",
        "portrait of a Korean woman holding a compact camera, confident smile, "
        "pointing at the viewer, colorful gradient background, studio softbox "
        "lighting, crisp detail, youtube thumbnail style",
        "이거 하나면\n끝났어요",
        "DoHyeon-Regular.ttf", "#FFFFFF", "#C2410C",
    ),
    (
        "03-가리키는-남성",
        "medium shot of a Korean man in a hoodie pointing to the side with an "
        "excited expression, dark teal background with rim lighting, dramatic "
        "contrast, youtube thumbnail style",
        "왜 아무도\n몰랐지?",
        "Jua-Regular.ttf", "#FFFFFF", "#1C1C1E",
    ),
    (
        "04-책상-작업",
        "over the shoulder shot of a Korean creator editing video on a large "
        "monitor, warm desk lamp, cinematic evening light, cozy home studio, "
        "youtube thumbnail style",
        "대본만\n붙여넣으면",
        "Gugi-Regular.ttf", "#7CF6C8", "#0B1B14",
    ),
]


def call(path: str, body: dict | None = None, timeout: float = 90.0):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(BASE + path, data=data, method="POST" if data else "GET")
    if data is not None:
        request.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read().decode("utf-8")
        return json.loads(raw) if raw else {}


def graph(prompt: str, seed: int) -> dict:
    return {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": "flux1-dev.safetensors", "weight_dtype": "fp8_e4m3fn"}},
        "2": {"class_type": "DualCLIPLoader", "inputs": {"clip_name1": "t5xxl_fp16.safetensors", "clip_name2": "clip_l.safetensors", "type": "flux"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": "ae.safetensors"}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": prompt}},
        "5": {"class_type": "FluxGuidance", "inputs": {"conditioning": ["4", 0], "guidance": 3.5}},
        "6": {"class_type": "EmptySD3LatentImage", "inputs": {"width": WIDTH, "height": HEIGHT, "batch_size": 1}},
        "7": {"class_type": "KSampler", "inputs": {
            "model": ["1", 0], "positive": ["5", 0], "negative": ["4", 0], "latent_image": ["6", 0],
            "seed": seed, "steps": STEPS, "cfg": 1.0, "sampler_name": "euler", "scheduler": "simple", "denoise": 1.0,
        }},
        "8": {"class_type": "VAEDecode", "inputs": {"samples": ["7", 0], "vae": ["3", 0]}},
        "9": {"class_type": "SaveImage", "inputs": {"images": ["8", 0], "filename_prefix": "videobox-thumb"}},
    }


def generate(prompt: str, seed: int, target: Path) -> float:
    started = time.monotonic()
    queued = call("/prompt", {"prompt": graph(prompt, seed), "client_id": uuid.uuid4().hex})
    prompt_id = queued["prompt_id"]
    while time.monotonic() - started < 600:
        time.sleep(2)
        entry = call(f"/history/{prompt_id}").get(prompt_id)
        if not entry:
            continue
        images = [item for node in (entry.get("outputs") or {}).values() for item in (node.get("images") or [])]
        if images:
            name = images[0]["filename"]
            with urllib.request.urlopen(f"{BASE}/view?filename={name}&type=output", timeout=120) as response:
                target.write_bytes(response.read())
            return time.monotonic() - started
        if (entry.get("status") or {}).get("status_str") == "error":
            raise RuntimeError(json.dumps((entry.get("status") or {}).get("messages"), ensure_ascii=False)[:400])
    raise TimeoutError("600초 안에 안 끝남")


def overlay(source: Path, target: Path, text: str, font: str, colour: str, outline: str) -> None:
    """썸네일 글자. 자막과 규칙이 다르다 -- 작게 보이므로 크고 두껍게 간다."""
    font_path = str(FONTS / font).replace("\\", "/").replace(":", r"\:")
    lines = text.split("\n")
    size = 116 if len(lines) > 1 else 132
    filters = []
    for index, line in enumerate(lines):
        escaped = line.replace("\\", r"\\").replace("'", r"\'").replace(":", r"\:")
        rise = (len(lines) - 1 - index) * int(size * 1.15)
        y = f"h-{int(size * 0.9)}-{rise}" if rise else f"h-{int(size * 0.9)}"
        filters.append(
            f"drawtext=fontfile='{font_path}':text='{escaped}':x=(w-text_w)/2:y={y}"
            f":fontsize={size}:fontcolor={colour}:borderw=10:bordercolor={outline}"
            f":shadowx=0:shadowy=6:shadowcolor=black@0.45"
        )
    result = subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(source), "-vf", ",".join(filters), "-frames:v", "1", str(target)],
        capture_output=True, text=True, timeout=180,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr[:400])


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for index, (name, prompt, text, font, colour, outline) in enumerate(PLAN):
        raw = OUT / f"{name}-원본.png"
        done = OUT / f"{name}.png"
        elapsed = generate(prompt, 1000 + index, raw)
        overlay(raw, done, text, font, colour, outline)
        print(f"  {name}: 그림 {elapsed:.1f}초 · 글꼴 {font} · {done.name}", flush=True)


if __name__ == "__main__":
    main()
