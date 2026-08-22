"""로컬 FLUX를 ai-toolkit이 읽는 모양(diffusers 폴더)으로 바꾼다.

**왜 이게 필요한가.** ai-toolkit은 `FluxTransformer2DModel.from_pretrained(...)`로
모델을 연다(`toolkit/stable_diffusion_model.py:667`). 그건 `transformer/`,
`text_encoder/` 같은 **폴더 구조**를 요구한다. 우리가 가진 것은 ComfyUI가 쓰는
**단일 파일** `flux1-dev.safetensors` 하나다. 그래서 그대로는 못 읽는다.

**왜 그냥 받지 않는가.** `black-forest-labs/FLUX.1-dev`는 HuggingFace에서
**라이선스 동의가 필요한 모델**이다. 받으려면 owner가 직접 계정으로 약관에 동의하고
토큰을 만들어야 한다 -- 내가 대신 할 일이 아니다. 게다가 이미 로컬에 24GB가 있는데
또 받는 것은 낭비다.

**그래서 있는 파일로 만든다.** 변환은 한 번만 하면 된다.

    .venv/Scripts/python.exe scripts/owner-path/convert_flux_for_aitoolkit.py

## 먼저 owner가 해야 할 일 — HuggingFace 로그인 (2026-08-22에 막혔다)

**파일이 로컬에 다 있어도 이 변환은 로그인 없이는 안 된다.** `from_single_file`이
**설정 파일(`transformer/config.json`)을 저장소에서 받아 오기** 때문이다. 무게는
로컬 것을 쓰지만 "이 무게를 어떤 모양으로 읽을지"는 그 JSON이 정한다.

그리고 2026-08-22 기준 **`FLUX.1-dev`와 `FLUX.1-schnell`이 둘 다 잠겨 있다.**
schnell은 예전에 Apache-2.0으로 그냥 받혔는데 지금은 아니다 -- 옛 안내를 보고
"schnell은 열려 있다"고 판단하면 틀린다. 직접 확인한 값이다:

    GatedRepoError: 401 ... Access to model black-forest-labs/FLUX.1-schnell is restricted.

**이건 owner 계정으로 약관에 동의하는 일이라 AI가 대신 하지 않는다.** 순서:

1. huggingface.co 로그인
2. `huggingface.co/black-forest-labs/FLUX.1-dev`에서 약관 동의 (한 번)
3. `huggingface.co/settings/tokens`에서 읽기 토큰 발급
4. 터미널에서 `hf auth login` -- **토큰은 이 창에만 넣는다. 대화에 붙여넣지 않는다.**

그 뒤에 이 스크립트를 돌리면 된다.

**시간과 자리:** transformer 하나가 23.8GB다. 읽고 다시 쓰므로 디스크에 그만큼
더 필요하고, 램도 넉넉해야 한다(2026-08-22 기준 이 기계는 125.6GB라 여유 있다).
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

COMFY = Path(r"C:\Users\atgro\Documents\comfy\ComfyUI\models")
#: 변환 결과를 두는 곳. ai-toolkit 설정의 `name_or_path`가 여기를 가리킨다.
OUT = Path(r"C:\Users\atgro\Documents\ai-toolkit\models\flux1-dev-diffusers")

UNET = COMFY / "unet" / "flux1-dev.safetensors"
VAE = COMFY / "vae" / "ae.safetensors"
CLIP_L = COMFY / "clip" / "clip_l.safetensors"
T5 = COMFY / "clip" / "t5xxl_fp16.safetensors"


def need(path: Path) -> None:
    if not path.is_file():
        print(f"!! 없습니다: {path}")
        sys.exit(1)


def main() -> int:
    for path in (UNET, VAE, CLIP_L, T5):
        need(path)

    import torch
    from diffusers import AutoencoderKL, FluxTransformer2DModel

    OUT.mkdir(parents=True, exist_ok=True)

    # **transformer가 제일 크다(23.8GB). 여기서 대부분의 시간이 간다.**
    # bf16으로 읽는다 -- ai-toolkit 설정의 `dtype: bf16`과 맞춰야 한다. 다른 dtype으로
    # 두면 나중에 왜 안 닮는지 알 수 없게 된다(ComfyUI 쪽에서 겪은 것과 같은 함정).
    started = time.monotonic()
    print("transformer를 읽습니다 (23.8GB, 몇 분 걸립니다)", flush=True)
    transformer = FluxTransformer2DModel.from_single_file(str(UNET), torch_dtype=torch.bfloat16)
    print(f"  읽음 -- {time.monotonic() - started:.0f}초. 저장합니다", flush=True)
    transformer.save_pretrained(OUT / "transformer")
    del transformer
    print(f"transformer 끝 -- {(time.monotonic() - started) / 60:.1f}분", flush=True)

    print("vae를 읽습니다", flush=True)
    vae = AutoencoderKL.from_single_file(str(VAE), torch_dtype=torch.bfloat16)
    vae.save_pretrained(OUT / "vae")
    del vae

    print(f"됨 -- {OUT}")
    print()
    print("나머지 부품(글자 이해기·토크나이저·스케줄러)은 설정에서 받아 옵니다.")
    print("ai-toolkit 설정에 이 두 줄이 들어 있어야 합니다:")
    print(f"  name_or_path: \"{OUT.as_posix()}\"")
    print("  extras_name_or_path: \"black-forest-labs/FLUX.1-schnell\"")
    print()
    print("**schnell을 쓰는 이유는 라이선스입니다.** dev는 HuggingFace에서 약관 동의가")
    print("필요한데, schnell은 Apache-2.0이라 그냥 받힙니다. 두 모델은 글자 이해기·")
    print("토크나이저·스케줄러가 같으므로, 학습되는 본체(transformer)는 위에서 만든")
    print("**우리 dev 파일**이 그대로 쓰입니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
