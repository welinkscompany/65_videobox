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
MAIN_COMPOSE_PATH = ROOT / "compose.yaml"
YUJIN_PROFILE_PATH = ROOT / "config" / "hermes" / "yujin" / "config.yaml"


def _innermost_default(value: str) -> str:
    """`${A:-${B:-실제값}}`에서 **가장 안쪽 리터럴**만 남긴다.

    두 자리(`compose.hermes-yujin.yaml`의 기억 모델, `compose.yaml`의 두뇌 이름)가
    같은 모양을 쓰므로 **벗기는 규칙은 한 곳에 둔다.** 이 저장소는 2026-09-11에
    "같은 계산이 두 자리에 살면 어긋난다"는 함정에 하루 세 번 걸렸다 -- 시험 코드도
    예외가 아니다.
    """
    original = value
    while value.startswith("${"):
        prefix, marker, remainder = value.partition(":-")
        assert marker, f"기본값이 없는 모양이다: {original!r}"
        assert prefix.startswith("${"), f"예상한 모양이 아니다: {original!r}"
        assert remainder.endswith("}"), f"닫는 괄호가 없다: {original!r}"
        # 바깥 `${...}` 하나에 대응하는 닫는 괄호 딱 하나만 벗긴다. rstrip("}")를
        # 쓰면 겹친 괄호를 통째로 지워 안쪽 표현이 깨진다 -- 실제로 그렇게
        # 깨졌다가 이 시험 자체가 잘못된 이유로 빨개진 적이 있다(2026-09-11).
        value = remainder[:-1]
    return value


def _mem0_llm_model_default() -> str:
    """`${VIDEOBOX_MEM0_LLM_MODEL:-여기}`에서 **가장 안쪽** 기본값만 꺼낸다.

    **서비스 이름을 박아 두지 않는다.** 처음에 `videobox-agent-gateway`라고
    적었다가 `KeyError`로 헛다리를 짚었다 -- 이 값은 기억 어댑터
    (`videobox-hermes-memory-adapter`)가 들고 있다. 서비스가 옮겨 다녀도
    이 시험이 지키려는 것(둘이 같은가)은 그대로여야 한다.

    2026-09-11에 SSOT 작업으로 기본값이 한 겹 더 생겼다
    (`${VIDEOBOX_MEM0_LLM_MODEL:-${VIDEOBOX_LOCAL_MODEL_NAME:-실제값}}`).
    껍질이 몇 겹이든 상관없이 **가장 안쪽 리터럴**까지 벗겨야 코드 기본값·
    유진 두뇌와 같은 자리에서 비교할 수 있다. 겹 수를 세는 것이 목적이 아니라
    "결국 같은 값을 가리키는가"만 보는 게 목적이라 재귀적으로 벗긴다.
    """
    overlay = yaml.safe_load(OVERLAY_PATH.read_text(encoding="utf-8"))
    holders = [
        (name, (service.get("environment") or {})["VIDEOBOX_MEM0_LLM_MODEL"])
        for name, service in overlay.get("services", {}).items()
        if "VIDEOBOX_MEM0_LLM_MODEL" in (service.get("environment") or {})
    ]
    assert len(holders) == 1, f"기억 모델을 정하는 자리가 하나여야 한다: {[n for n, _ in holders]}"
    return _innermost_default(str(holders[0][1]))


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


def _main_compose_local_model_default() -> str:
    """**네 번째 자리.** `compose.yaml`의 `VIDEOBOX_LOCAL_MODEL_NAME` 기본값.

    이 파일 머리말은 커밋에 있는 자리를 "셋"이라고 세었는데 **하나를 빠뜨렸다.**
    `.env.container`가 gitignore라 못 본다고 적었지만, **같은 변수의 기본값이
    `compose.yaml`에도 커밋되어 있다.** 2026-09-12에 대표님이 옛 35b를 삭제한 뒤
    확인해 보니 이 자리만 `qwen3-35b`, 즉 **이제 없는 모델**을 가리키고 있었다.

    지금까지 안 터진 이유는 `.env.container`가 덮어 왔기 때문이다. 그 파일은
    커밋되지 않으므로 **새 환경에서는 없는 모델로 떨어진다.** 그 자리 주석도
    "기본값이 실제 모델명과 어긋나서 override로 메운다"고 스스로 밝히고 있었다 --
    메우지 말고 맞춰야 한다.
    """
    compose = yaml.safe_load(MAIN_COMPOSE_PATH.read_text(encoding="utf-8"))
    holders = [
        (name, (service.get("environment") or {})["VIDEOBOX_LOCAL_MODEL_NAME"])
        for name, service in compose.get("services", {}).items()
        if "VIDEOBOX_LOCAL_MODEL_NAME" in (service.get("environment") or {})
    ]
    assert len(holders) == 1, f"두뇌 이름을 정하는 자리가 하나여야 한다: {[n for n, _ in holders]}"
    return _innermost_default(str(holders[0][1]))


def test_the_main_compose_default_is_the_same_model_as_everything_else() -> None:
    """`.env.container`가 없으면 여기로 떨어진다 -- 그리고 그 파일은 커밋되지 않는다.

    즉 새로 받은 환경에서 실제로 쓰이는 값은 **이 기본값**이다. 다른 셋과 갈라져
    있으면 유진이 없는 모델을 부르고, 화면에는 "유진이 지금 도와줄 수 없어요"만
    뜬다 -- 원인이 설정 한 줄인데 코드를 뒤지게 된다.
    """
    assert _main_compose_local_model_default() == _yujin_profile_model(), (
        f"compose.yaml 기본값({_main_compose_local_model_default()})과 유진의 두뇌"
        f"({_yujin_profile_model()})가 서로 다른 모델을 가리킨다"
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
