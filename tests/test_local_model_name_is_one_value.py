"""로컬 모델 이름이 **여러 곳에 박혀 있고 갈라질 수 있다** — 2026-09-11.

대표님이 새 qwen을 받고 "옛 모델은 지울 거다"라고 했다. 그런데 모델 이름이
한 곳이 아니라 여러 곳에 박혀 있어서, 한 곳만 바꾸면 **옛 모델과 새 모델을
둘 다 LM Studio에 올려 둬야** 한다 — 그게 바로 대표님이 불평한 상태다
(기계가 느려진다).

이 저장소가 커밋에 들고 있는 자리는 셋이다.

- `compose.hermes-yujin.yaml`의 `VIDEOBOX_MEM0_LLM_MODEL` 기본값 (기억 추출)
- `config/hermes/yujin/config.yaml`의 `model.name` (유진 Hermes 프로필의 두뇌)
- `hermes_memory_adapter.py`의 `_LOCAL_MEM0_LLM_MODEL` (**제품 코드에 박힌
  마지막 기본값** -- 환경변수가 없을 때 여기로 떨어진다)

셋째 자리는 처음에 못 세고 "다섯 곳"이라고 말했다가 뒤늦게 찾았다. 코드에
박힌 기본값은 grep 한 번으로는 안 보인다 -- 설정 파일만 훑으면 놓친다.

셋째 자리 `.env.container`의 `VIDEOBOX_LOCAL_MODEL_NAME`은 gitignore 대상이라
여기서 못 본다 -- 그쪽은 `scripts/owner-ready.ps1`의 `Get-LocalModelCheck`가
실제 로드된 목록과 대조한다.

**이 시험은 값을 고정하지 않는다.** 둘이 **서로 같은지**만 본다. 값을 박아 두면
모델을 바꿀 때마다 시험도 같이 고쳐야 하고, 그러면 "시험이 지키는 것"이 아니라
"시험도 같이 옮겨 적는 것"이 된다. 갈라지는 것을 막는 게 목적이다.
"""

from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).parents[1]
OVERLAY_PATH = ROOT / "compose.hermes-yujin.yaml"
YUJIN_PROFILE_PATH = ROOT / "config" / "hermes" / "yujin" / "config.yaml"


def _mem0_llm_model_default() -> str:
    """`${VIDEOBOX_MEM0_LLM_MODEL:-여기}`에서 기본값만 꺼낸다.

    **서비스 이름을 박아 두지 않는다.** 처음에 `videobox-agent-gateway`라고
    적었다가 `KeyError`로 헛다리를 짚었다 -- 이 값은 기억 어댑터
    (`videobox-hermes-memory-adapter`)가 들고 있다. 서비스가 옮겨 다녀도
    이 시험이 지키려는 것(둘이 같은가)은 그대로여야 한다.
    """
    overlay = yaml.safe_load(OVERLAY_PATH.read_text(encoding="utf-8"))
    holders = [
        (name, (service.get("environment") or {})["VIDEOBOX_MEM0_LLM_MODEL"])
        for name, service in overlay.get("services", {}).items()
        if "VIDEOBOX_MEM0_LLM_MODEL" in (service.get("environment") or {})
    ]
    assert len(holders) == 1, f"기억 모델을 정하는 자리가 하나여야 한다: {[n for n, _ in holders]}"
    raw = str(holders[0][1])
    prefix, marker, remainder = raw.partition(":-")
    assert marker, f"기본값이 없는 모양이다: {raw!r}"
    assert prefix.startswith("${"), f"예상한 모양이 아니다: {raw!r}"
    return remainder.rstrip("}")


def _yujin_profile_model() -> str:
    profile = yaml.safe_load(YUJIN_PROFILE_PATH.read_text(encoding="utf-8"))
    return str(profile["model"]["name"])


def _adapter_fallback_model() -> str:
    """제품 코드에 박힌 마지막 기본값. 환경변수가 없으면 여기로 떨어진다."""
    from videobox_agent_gateway.hermes_memory_adapter import _LOCAL_MEM0_LLM_MODEL

    return str(_LOCAL_MEM0_LLM_MODEL)


def test_the_code_fallback_matches_the_compose_default() -> None:
    """환경변수가 없을 때 떨어지는 자리와 compose 기본값이 달라지면, **어느 쪽이
    쓰이느냐가 실행 방식에 따라 달라진다** -- 컨테이너로 띄우면 compose 값,
    어댑터를 직접 부르면 코드 값. 그러면 같은 기계에서 모델 둘이 올라간다."""
    assert _adapter_fallback_model() == _mem0_llm_model_default(), (
        f"코드 기본값({_adapter_fallback_model()})과 compose 기본값"
        f"({_mem0_llm_model_default()})이 서로 다르다"
    )


def test_the_memory_brain_and_the_yujin_brain_are_the_same_model() -> None:
    """둘이 달라지면 **LM Studio에 모델 둘을 동시에 올려 둬야 한다.**

    한 대의 컴퓨터에서 도는 제품이라 그건 곧 느려진다는 뜻이다. 언젠가 일부러
    다른 모델을 쓰기로 한다면 그때 이 시험을 지우면서 그 결정을 적으면 된다 --
    지금은 **말 없이 갈라지는 것**을 막는 게 목적이다.
    """
    assert _mem0_llm_model_default() == _yujin_profile_model(), (
        f"기억 추출({_mem0_llm_model_default()})과 유진의 두뇌"
        f"({_yujin_profile_model()})가 서로 다른 모델을 가리킨다"
    )
