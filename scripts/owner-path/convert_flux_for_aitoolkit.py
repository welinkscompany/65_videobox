"""로컬 FLUX를 ai-toolkit이 읽는 모양(diffusers 폴더)으로 바꾼다.

**왜 이게 필요한가.** ai-toolkit은 `FluxTransformer2DModel.from_pretrained(...)`로
모델을 연다(`toolkit/stable_diffusion_model.py:667`). 그건 `transformer/`,
`text_encoder/` 같은 **폴더 구조**를 요구한다. 우리가 가진 것은 ComfyUI가 쓰는
**단일 파일** `flux1-dev.safetensors` 하나다. 그래서 그대로는 못 읽는다.

**왜 그냥 받지 않는가.** `black-forest-labs/FLUX.1-dev`는 HuggingFace에서
**라이선스 동의가 필요한 모델**이다. 게다가 이미 로컬에 24GB가 있는데 또 받는 것은
낭비다. 아래에 로그인 없이 가는 길을 적었다.

**그래서 있는 파일로 만든다.** 변환은 한 번만 하면 된다.

    .venv/Scripts/python.exe scripts/owner-path/convert_flux_for_aitoolkit.py

## 로그인이 필요 없다 — 2026-08-22에 길을 뚫었다

처음에는 막혔다. `from_single_file`이 **설정 파일**을 `black-forest-labs/FLUX.1-dev`에서
받아 오는데 그 저장소가 잠겨 있고, **`FLUX.1-schnell`도 지금은 잠겨 있다**(직접 확인:
`GatedRepoError: 401 ... FLUX.1-schnell is restricted`). schnell이 Apache-2.0으로
열려 있다는 옛 상식은 지금은 틀리다.

**그래서 설정을 받지 않고 만든다.** 그 JSON에 들어 있는 값은 전부 둘 중 하나다 --
diffusers 코드 안에 이미 있거나, 우리 파일에서 잴 수 있다. 짐작한 값은 아래 하나뿐이고
그것도 어디서 왔는지 적어 두었다(`write_scheduler`의 `shift`).

토크나이저와 구조 설명은 **잠기지 않은** 저장소에서 온다 --
`openai/clip-vit-large-patch14`, `google/t5-v1_1-xxl`. 둘 다 로그인 없이 열린다(확인함).

**시간과 자리:** transformer 하나가 23.8GB다. 읽고 다시 쓰므로 디스크에 그만큼
더 필요하고, 램도 넉넉해야 한다(2026-08-22 기준 이 기계는 125.6GB라 여유 있다).
"""
from __future__ import annotations

import json
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


def transformer_config() -> dict:
    """구조 설정을 **우리 파일에서 읽어서** 만든다. 저장소에서 안 받는다.

    `from_single_file`은 기본적으로 `black-forest-labs/FLUX.1-dev`에서
    `transformer/config.json`을 받아 오는데, 그 저장소가 잠겨 있다. 그런데 그 JSON에
    들어 있는 값은 **전부 diffusers 코드 안에 이미 있거나 우리 파일에서 잴 수 있다.**

    2026-08-22 실측(`flux1-dev.safetensors`, 텐서 780개):

        double_blocks 19개, single_blocks 38개  -> diffusers 기본값과 같다
        guidance_in 키가 있다                    -> dev다 (schnell에는 없다)

    나머지(head 128, heads 24, joint 4096, pooled 768, rope (16,56,56))는
    `FluxTransformer2DModel.__init__`의 기본값이고 실제로 FLUX 값이다.

    **그래서 여기서 손으로 정하는 값은 `guidance_embeds` 하나뿐이고, 그것도 짐작이
    아니라 파일에서 읽는다.** 틀렸으면 무게를 싣는 순간 모양이 안 맞아 터진다 --
    조용히 틀릴 수 있는 자리가 아니다.
    """
    import re

    from safetensors import safe_open

    with safe_open(str(UNET), "pt") as handle:
        keys = list(handle.keys())

    double = max(int(m.group(1)) for k in keys if (m := re.match(r"double_blocks\.(\d+)\.", k))) + 1
    single = max(int(m.group(1)) for k in keys if (m := re.match(r"single_blocks\.(\d+)\.", k))) + 1
    return {
        "_class_name": "FluxTransformer2DModel",
        "_diffusers_version": "0.30.0",
        "patch_size": 1,
        "in_channels": 64,
        "num_layers": double,
        "num_single_layers": single,
        "attention_head_dim": 128,
        "num_attention_heads": 24,
        "joint_attention_dim": 4096,
        "pooled_projection_dim": 768,
        "guidance_embeds": any(k.startswith("guidance_in") for k in keys),
        "axes_dims_rope": [16, 56, 56],
    }


def vae_config() -> dict:
    """VAE 설정도 **파일에서 재서** 만든다.

    `AutoencoderKL.from_single_file`은 일반 SD용 설정으로 짐작해서 잠재 채널을 4로
    잡는다. FLUX는 16이라 무게를 싣는 순간 터진다(2026-08-22에 실제로 그랬다:
    `encoder.conv_out.weight expected [8,512,3,3], but got [32,512,3,3]`).

    실측(`ae.safetensors`):
        encoder.conv_out [32,512,3,3] -> 평균+분산이라 잠재 채널은 16
        decoder.conv_in  [512,16,...] -> 16 확인
        down 단계 4개, 출력 채널 128/256/512/512, 단계당 블록 2개
        quant_conv 없음

    **잴 수 없는 값이 둘 있다 -- `scaling_factor`와 `shift_factor`.** 무게에서 나오지
    않는 상수다. 짐작하지 않고 **이 기계에 이미 있는 ComfyUI 소스에서 가져왔다**:
    `comfy/latent_formats.py:163-164`의 FLUX 항목이 `0.3611`과 `0.1159`다.
    이 둘이 틀리면 그림이 조용히 어긋난다 -- 터지지 않으므로 더 위험하다.
    """
    from safetensors import safe_open

    with safe_open(str(VAE), "pt") as handle:
        latent = handle.get_slice("decoder.conv_in.weight").get_shape()[1]
    return {
        "_class_name": "AutoencoderKL",
        "_diffusers_version": "0.30.0",
        "in_channels": 3,
        "out_channels": 3,
        "down_block_types": ["DownEncoderBlock2D"] * 4,
        "up_block_types": ["UpDecoderBlock2D"] * 4,
        "block_out_channels": [128, 256, 512, 512],
        "layers_per_block": 2,
        "latent_channels": latent,
        "norm_num_groups": 32,
        "sample_size": 1024,
        "scaling_factor": 0.3611,
        "shift_factor": 0.1159,
        "use_quant_conv": False,
        "use_post_quant_conv": False,
    }


def main() -> int:
    for path in (UNET, VAE, CLIP_L, T5):
        need(path)

    import torch
    from diffusers import AutoencoderKL, FluxTransformer2DModel

    OUT.mkdir(parents=True, exist_ok=True)

    # **transformer가 제일 크다(23.8GB). 여기서 대부분의 시간이 간다.**
    # bf16으로 읽는다 -- ai-toolkit 설정의 `dtype: bf16`과 맞춰야 한다. 다른 dtype으로
    # 두면 나중에 왜 안 닮는지 알 수 없게 된다(ComfyUI 쪽에서 겪은 것과 같은 함정).
    # 23.8GB를 다시 읽는 데 몇 분이 걸린다. 이미 끝난 것은 건너뛴다 --
    # 뒤 단계에서 막혀 다시 돌릴 때 앞 단계를 또 기다리지 않게.
    done = OUT / "transformer" / "diffusion_pytorch_model.safetensors.index.json"
    if done.is_file():
        print(f"transformer는 이미 변환돼 있습니다 -- 건너뜁니다 ({OUT / 'transformer'})", flush=True)
        return convert_vae()

    # 구조 설정을 먼저 우리 손으로 써 둔다. 이게 있으면 `from_single_file`이
    # 잠긴 저장소를 찾아가지 않는다.
    config_dir = OUT / "transformer"
    config_dir.mkdir(parents=True, exist_ok=True)
    config = transformer_config()
    (config_dir / "config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
    print(f"구조 설정을 만들었습니다 -- 블록 {config['num_layers']}+{config['num_single_layers']}, "
          f"guidance_embeds={config['guidance_embeds']}", flush=True)

    started = time.monotonic()
    print("transformer를 읽습니다 (23.8GB, 몇 분 걸립니다)", flush=True)
    transformer = FluxTransformer2DModel.from_single_file(
        str(UNET), config=str(config_dir), torch_dtype=torch.bfloat16)
    print(f"  읽음 -- {time.monotonic() - started:.0f}초. 저장합니다", flush=True)
    transformer.save_pretrained(OUT / "transformer")
    del transformer
    print(f"transformer 끝 -- {(time.monotonic() - started) / 60:.1f}분", flush=True)

    return convert_vae()


def convert_text_encoders() -> None:
    """글자 이해기 둘과 토크나이저를 만든다.

    **무게는 로컬 것, 구조 설명과 토크나이저는 잠기지 않은 저장소에서 가져온다.**

    - CLIP-L  <- `openai/clip-vit-large-patch14` (2026-08-22 확인: 로그인 없이 열림)
    - T5-XXL  <- `google/t5-v1_1-xxl` (같이 확인)

    우리 `clip_l.safetensors`와 `t5xxl_fp16.safetensors`는 **이미 transformers
    이름 규칙을 쓴다**(`text_model.embeddings...`, `encoder.block.0.layer...`).
    그래서 이름을 바꿔 줄 필요 없이 그대로 실린다 -- 실측으로 확인했다.
    """
    import torch
    from safetensors.torch import load_file
    from transformers import (AutoTokenizer, CLIPTextConfig, CLIPTextModel,
                              T5Config, T5EncoderModel)

    print("CLIP-L을 만듭니다", flush=True)
    clip_config = CLIPTextConfig.from_pretrained("openai/clip-vit-large-patch14")
    clip = CLIPTextModel(clip_config).to(torch.bfloat16)
    missing, unexpected = clip.load_state_dict(load_file(str(CLIP_L)), strict=False)
    # **여기서 조용히 틀리면 안 된다.** 무게가 안 실렸는데 넘어가면 나중에 "왜 안
    # 닮지"로만 나타난다. 안 맞는 것이 있으면 그 자리에서 말한다.
    report("CLIP-L", missing, unexpected)
    clip.save_pretrained(OUT / "text_encoder")
    AutoTokenizer.from_pretrained("openai/clip-vit-large-patch14").save_pretrained(OUT / "tokenizer")
    del clip

    print("T5-XXL을 만듭니다 (9.8GB)", flush=True)
    t5_config = T5Config.from_pretrained("google/t5-v1_1-xxl")
    t5 = T5EncoderModel(t5_config).to(torch.bfloat16)
    missing, unexpected = t5.load_state_dict(load_file(str(T5)), strict=False)
    report("T5-XXL", missing, unexpected)
    t5.save_pretrained(OUT / "text_encoder_2")
    AutoTokenizer.from_pretrained("google/t5-v1_1-xxl").save_pretrained(OUT / "tokenizer_2")
    del t5


def report(name: str, missing: list, unexpected: list) -> None:
    """안 실린 무게가 있으면 숨기지 않는다."""
    # `encoder.embed_tokens.weight`처럼 다른 이름과 값을 나눠 쓰는 것은 빠져도 정상이다.
    real = [k for k in missing if "embed_tokens" not in k]
    if real or unexpected:
        print(f"!! {name}: 안 실린 것 {len(real)}개, 모르는 것 {len(unexpected)}개")
        for key in (real + unexpected)[:5]:
            print(f"   {key}")
        print("!! 이 상태로 학습하면 왜 안 닮는지 알 수 없게 됩니다. 멈추세요.")
    else:
        print(f"   {name} 무게가 전부 실렸습니다", flush=True)


def write_scheduler() -> None:
    """스케줄러 설정. **잴 수 없어서 출처를 밝힌다.**

    `base_shift 0.5 · max_shift 1.15 · base_image_seq_len 256 · max_image_seq_len 4096`은
    diffusers `FlowMatchEulerDiscreteScheduler` 기본값과 ai-toolkit이 쓰는 대체값
    (`toolkit/pipelines.py:1395-1399`)이 **정확히 같다**. 두 곳에서 확인한 값이다.

    `shift 3.0`과 `use_dynamic_shifting true`는 FLUX-dev 쪽 값이다. 여기 둘은 로컬에서
    확인할 데가 없었다 -- **이 둘만 확인 못 한 값이라고 적어 둔다.** 뽑아 본 그림이
    이상하면 여기부터 의심하라.
    """
    scheduler = {
        "_class_name": "FlowMatchEulerDiscreteScheduler",
        "_diffusers_version": "0.30.0",
        "num_train_timesteps": 1000,
        "shift": 3.0,
        "use_dynamic_shifting": True,
        "base_shift": 0.5,
        "max_shift": 1.15,
        "base_image_seq_len": 256,
        "max_image_seq_len": 4096,
    }
    out = OUT / "scheduler"
    out.mkdir(parents=True, exist_ok=True)
    (out / "scheduler_config.json").write_text(json.dumps(scheduler, indent=2), encoding="utf-8")
    print("   스케줄러 설정을 만들었습니다", flush=True)


def convert_vae() -> int:
    import torch
    from diffusers import AutoencoderKL

    print("vae를 읽습니다", flush=True)
    vae_dir = OUT / "vae"
    vae_dir.mkdir(parents=True, exist_ok=True)
    (vae_dir / "config.json").write_text(json.dumps(vae_config(), indent=2), encoding="utf-8")
    vae = AutoencoderKL.from_single_file(str(VAE), config=str(vae_dir), torch_dtype=torch.bfloat16)
    vae.save_pretrained(vae_dir)
    del vae

    convert_text_encoders()
    write_scheduler()
    print(f"됨 -- {OUT}")
    print()
    print("**HuggingFace 로그인 없이 끝났습니다.** 잠긴 저장소는 하나도 안 썼습니다.")
    print("ai-toolkit 설정에는 이 한 줄만 있으면 됩니다:")
    print(f"  name_or_path: \"{OUT.as_posix()}\"")
    print("  (extras_name_or_path는 필요 없습니다 -- 부품이 전부 이 폴더에 있습니다.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
