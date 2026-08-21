"""학습한 얼굴을 썸네일 프롬프트에 얹어 보고, **시간과 닮은 정도를 표로** 만든다.

인계 문서가 시킨 그대로다 -- "LoRA를 학습해서 아까 만든 썸네일 프롬프트에 얹어 보고,
시간·닮은 정도를 표로 만든 뒤 owner가 고르게 하라."

프롬프트는 `artifacts/flux-measure/thumbnails.py`의 넷을 그대로 쓴다. 새로 지어내면
전후 비교가 아니라 다른 시험이 된다.

**닮은 정도를 무엇으로 재는가 -- 읽는 사람이 속지 않게 먼저 적는다.**

이 기계에 얼굴 인식 모델이 없다. ComfyUI의 `clip_vision` 폴더가 비어 있고
(2026-08-21 확인), 얼굴 임베딩 도구는 따로 받아야 한다. 그래서 여기서 내는 숫자는
**LM Studio에 올라와 있는 눈 달린 모델의 판단**이다. 얼굴 인식 점수가 아니다.

- 0~100으로 답하게 하고, 같은 그림을 세 번 물어 평균을 낸다(한 번은 흔들린다).
- 표에 `모델 판단`이라고 적는다. `일치율`이라고 적지 않는다.
- **마지막 판단은 owner가 그림을 보고 한다.** 이 표는 어디부터 볼지 정해 줄 뿐이다.

    .venv/Scripts/python.exe scripts/owner-path/measure_face_likeness.py
"""
from __future__ import annotations

import base64
import json
import statistics
import sys
import time
import urllib.request
import uuid
from pathlib import Path

COMFY = "http://127.0.0.1:8188"
LM_STUDIO = "http://127.0.0.1:1234/v1"
ROOT = Path(__file__).resolve().parents[2]
PHOTOS = Path(r"D:\AI_Workspace_louis_office_50\20_project\65_videobox-project\drive-sync\내 얼굴 사진")
OUT = ROOT / "artifacts" / "face-lora"
LORA_NAME = "videobox-owner-face"
TRIGGER = "ohwnrface person"
WIDTH, HEIGHT, STEPS = 1280, 720, 20
#: 학습한 얼굴을 얼마나 세게 얹을지. 낮으면 안 닮고 높으면 다른 것까지 굳는다 --
#: **어느 값이 좋은지가 이 시험의 답이다.** 짐작으로 하나만 고르지 않는다.
STRENGTHS = (0.7, 0.9, 1.1)

#: `artifacts/flux-measure/thumbnails.py`의 넷. 사람이 나오는 셋만 쓴다 --
#: 책상 사진(04)에는 얼굴이 크게 안 나와서 닮은 정도를 잴 수가 없다.
PROMPTS = [
    ("01-놀란-편집자",
     "close-up portrait of {trigger} at a desk with a laptop, wide surprised eyes, "
     "mouth open, bright studio lighting, vivid colors, shallow depth of field, "
     "high contrast, youtube thumbnail style"),
    ("02-카메라-든-사람",
     "portrait of {trigger} holding a compact camera, confident smile, pointing at "
     "the viewer, colorful gradient background, studio softbox lighting, crisp "
     "detail, youtube thumbnail style"),
    ("03-가리키는-사람",
     "medium shot of {trigger} in a hoodie pointing to the side with an excited "
     "expression, dark teal background with rim lighting, dramatic contrast, "
     "youtube thumbnail style"),
]

_RUBRIC = (
    "You are comparing faces. The first image is a reference photo of a person. "
    "The second image was generated. Rate how much the generated face looks like "
    "the SAME PERSON as the reference, from 0 to 100.\n"
    "100 = unmistakably the same person. 70 = clearly a strong resemblance. "
    "40 = same general type but a different person. 0 = no resemblance.\n"
    "Judge the face only: bone structure, eyes, nose, mouth, face shape. "
    "Ignore clothing, background, lighting, pose and expression.\n"
    'Answer with JSON only: {"score": <integer 0-100>, "why": "<one short sentence>"}'
)


def comfy(path: str, body: dict | None = None, timeout: float = 120.0):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(COMFY + path, data=data, method="POST" if data else "GET")
    if data is not None:
        request.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read()
        return json.loads(raw.decode("utf-8")) if raw else {}


def graph(prompt: str, seed: int, lora_strength: float | None) -> dict:
    """그림 만들 때 쓰는 것과 **같은 9노드**에 LoRA 한 겹만 얹는다.

    비교가 되려면 나머지가 같아야 한다. 씨앗도 같은 값을 쓴다 -- 그래야 차이가
    LoRA에서 온 것인지 운에서 온 것인지 구분된다.
    """
    nodes: dict = {
        "1": {"class_type": "UNETLoader", "inputs": {
            "unet_name": "flux1-dev.safetensors", "weight_dtype": "fp8_e4m3fn"}},
        "2": {"class_type": "DualCLIPLoader", "inputs": {
            "clip_name1": "t5xxl_fp16.safetensors", "clip_name2": "clip_l.safetensors", "type": "flux"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": "ae.safetensors"}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": prompt}},
        "5": {"class_type": "FluxGuidance", "inputs": {"conditioning": ["4", 0], "guidance": 3.5}},
        "6": {"class_type": "EmptySD3LatentImage", "inputs": {
            "width": WIDTH, "height": HEIGHT, "batch_size": 1}},
        "7": {"class_type": "KSampler", "inputs": {
            "model": ["1", 0], "positive": ["5", 0], "negative": ["4", 0], "latent_image": ["6", 0],
            "seed": seed, "steps": STEPS, "cfg": 1.0, "sampler_name": "euler",
            "scheduler": "simple", "denoise": 1.0}},
        "8": {"class_type": "VAEDecode", "inputs": {"samples": ["7", 0], "vae": ["3", 0]}},
        "9": {"class_type": "SaveImage", "inputs": {"images": ["8", 0], "filename_prefix": "videobox-face"}},
    }
    if lora_strength is not None:
        nodes["10"] = {"class_type": "LoraLoaderModelOnly", "inputs": {
            "model": ["1", 0], "lora_name": _lora_file(), "strength_model": lora_strength}}
        nodes["7"]["inputs"]["model"] = ["10", 0]
    return nodes


def _lora_file() -> str:
    """학습이 붙인 실제 파일 이름을 ComfyUI에게 물어본다. 이름을 짐작하지 않는다."""
    options = comfy("/object_info/LoraLoaderModelOnly")["LoraLoaderModelOnly"]["input"]["required"]["lora_name"][0]
    matching = [name for name in options if LORA_NAME in name]
    if not matching:
        raise SystemExit(
            f"학습된 얼굴을 찾지 못했습니다. 먼저 학습을 돌려 주세요:\n"
            f"  .venv/Scripts/python.exe scripts/owner-path/train_face_lora.py\n"
            f"  (ComfyUI가 아는 목록: {options})"
        )
    return sorted(matching)[-1]


def generate(prompt: str, seed: int, lora_strength: float | None, target: Path) -> float:
    started = time.monotonic()
    prompt_id = comfy("/prompt", {"prompt": graph(prompt, seed, lora_strength),
                                  "client_id": uuid.uuid4().hex})["prompt_id"]
    while time.monotonic() - started < 900:
        time.sleep(2)
        entry = comfy(f"/history/{prompt_id}").get(prompt_id)
        if not entry:
            continue
        images = [item for node in (entry.get("outputs") or {}).values()
                  for item in (node.get("images") or [])]
        if images:
            name = images[0]["filename"]
            with urllib.request.urlopen(f"{COMFY}/view?filename={name}&type=output", timeout=120) as response:
                target.write_bytes(response.read())
            return time.monotonic() - started
        if (entry.get("status") or {}).get("status_str") == "error":
            raise RuntimeError(json.dumps((entry.get("status") or {}).get("messages"), ensure_ascii=False)[:400])
    raise TimeoutError("900초 안에 안 끝남")


def _vision_model() -> str:
    with urllib.request.urlopen("http://127.0.0.1:1234/api/v1/models", timeout=30) as response:
        payload = json.load(response)
    for model in payload.get("models", []):
        if (model.get("capabilities") or {}).get("vision") and model.get("loaded_instances"):
            return model["loaded_instances"][0]["id"]
    raise SystemExit("눈 달린 모델이 LM Studio에 올라와 있지 않습니다. 하나 올린 뒤 다시 실행해 주세요.")


def _encoded(path: Path) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def judge(model: str, reference: Path, generated: Path, rounds: int = 3) -> tuple[float | None, str]:
    """**얼굴 인식 점수가 아니다.** 눈 달린 모델의 판단이고, 그래서 세 번 물어 평균 낸다."""
    scores: list[int] = []
    why = ""
    for _ in range(rounds):
        body = {
            "model": model,
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": _RUBRIC},
                {"type": "image_url", "image_url": {"url": _encoded(reference)}},
                {"type": "image_url", "image_url": {"url": _encoded(generated)}},
            ]}],
            "temperature": 0,
        }
        request = urllib.request.Request(f"{LM_STUDIO}/chat/completions",
                                         data=json.dumps(body).encode("utf-8"), method="POST")
        request.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(request, timeout=300) as response:
                text = json.load(response)["choices"][0]["message"]["content"]
            parsed = json.loads(text[text.index("{"):text.rindex("}") + 1])
            scores.append(int(parsed["score"]))
            why = str(parsed.get("why") or why)
        except Exception as error:  # noqa: BLE001 -- 한 번 못 재도 나머지는 잰다
            why = why or f"판단 실패: {error!r}"
    return (statistics.mean(scores) if scores else None), why


def main() -> int:
    references = sorted(p for p in PHOTOS.glob("*") if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"})
    if not references:
        print(f"기준 사진이 없습니다: {PHOTOS}")
        return 1
    OUT.mkdir(parents=True, exist_ok=True)
    model = _vision_model()
    reference = references[0]
    print(f"기준 사진: {reference.name} · 판단 모델: {model}\n", flush=True)

    rows: list[tuple[str, str, float, float | None, str]] = []
    for index, (name, template) in enumerate(PROMPTS):
        seed = 2000 + index
        for strength in (None, *STRENGTHS):
            label = "얼굴 없이" if strength is None else f"얼굴 {strength}"
            # 얼굴을 안 얹을 때는 부르는 낱말도 빼야 공정하다.
            prompt = template.format(trigger=TRIGGER if strength is not None else "a young Korean man")
            target = OUT / f"{name}-{'base' if strength is None else strength}.png"
            elapsed = generate(prompt, seed, strength, target)
            score, why = judge(model, reference, target)
            rows.append((name, label, elapsed, score, why))
            print(f"  {name} · {label}: {elapsed:.1f}초 · 모델 판단 "
                  f"{'못 잼' if score is None else f'{score:.0f}/100'}", flush=True)

    print("\n| 썸네일 | 얼굴 얹기 | 걸린 시간 | 모델 판단(닮음) | 모델이 든 이유 |")
    print("|---|---|---|---|---|")
    for name, label, elapsed, score, why in rows:
        shown = "못 잼" if score is None else f"{score:.0f}/100"
        print(f"| {name} | {label} | {elapsed:.1f}초 | {shown} | {why[:60]} |")
    print(f"\n그림은 여기 있습니다: {OUT}")
    print("**이 숫자는 얼굴 인식 점수가 아니라 모델의 판단입니다.** 어디부터 볼지만 정해 줍니다 --")
    print("마지막 판단은 그림을 직접 보고 해 주세요.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
