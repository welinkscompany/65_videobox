"""로컬 모델 이름이 **여러 곳에 박혀 있고 갈라질 수 있다** — 2026-09-11.

대표님이 새 qwen을 받고 "옛 모델은 지울 거다"라고 했다. 그런데 모델 이름이
한 곳이 아니라 여러 곳에 박혀 있어서, 한 곳만 바꾸면 **옛 모델과 새 모델을
둘 다 LM Studio에 올려 둬야** 한다 — 그게 바로 대표님이 불평한 상태다
(기계가 느려진다).

**2026-09-18에 Mem0(기억 추출 전용 모델 자리)를 걷어냈다.** 이 저장소가
커밋에 들고 있는 자리는 이제 둘뿐이다.

- `compose.yaml`의 `VIDEOBOX_LOCAL_MODEL_NAME` 기본값 (두뇌)
- `config/hermes/yujin/config.yaml`의 `model.name` (유진 Hermes 프로필의 두뇌)

`compose.hermes-yujin.yaml`의 `VIDEOBOX_MEM0_LLM_MODEL`과 `hermes_memory_adapter.py`의
`_LOCAL_MEM0_LLM_MODEL`(제품 코드에 박힌 기억 추출 기본값) 자리는 Mem0와 함께
사라졌다 -- 기억은 이제 로컬 Postgres에만 쓰고 별도 모델 호출이 없다
(`docs/decisions/2026-09-18-mem0-removed-native-memory-librarian.ko.md`).

`.env.container`의 `VIDEOBOX_LOCAL_MODEL_NAME`은 gitignore 대상이라
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
MAIN_COMPOSE_PATH = ROOT / "compose.yaml"
YUJIN_PROFILE_PATH = ROOT / "config" / "hermes" / "yujin" / "config.yaml"


def _innermost_default(value: str) -> str:
    """`${A:-${B:-실제값}}`에서 **가장 안쪽 리터럴**만 남긴다."""
    original = value
    while value.startswith("${"):
        prefix, marker, remainder = value.partition(":-")
        assert marker, f"기본값이 없는 모양이다: {original!r}"
        assert prefix.startswith("${"), f"예상한 모양이 아니다: {original!r}"
        assert remainder.endswith("}"), f"닫는 괄호가 없다: {original!r}"
        value = remainder[:-1]
    return value


def _yujin_profile_model() -> str:
    profile = yaml.safe_load(YUJIN_PROFILE_PATH.read_text(encoding="utf-8"))
    return str(profile["model"]["name"])


def _main_compose_local_model_default() -> str:
    """`compose.yaml`의 `VIDEOBOX_LOCAL_MODEL_NAME` 기본값.

    `.env.container`가 gitignore라 못 본다고 적었지만, **같은 변수의
    기본값이 `compose.yaml`에도 커밋되어 있다.** 2026-09-12에 대표님이 옛
    35b를 삭제한 뒤 확인해 보니 이 자리만 `qwen3-35b`, 즉 **이제 없는
    모델**을 가리키고 있었다.

    지금까지 안 터진 이유는 `.env.container`가 덮어 왔기 때문이다. 그
    파일은 커밋되지 않으므로 **새 환경에서는 없는 모델로 떨어진다.**
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

    즉 새로 받은 환경에서 실제로 쓰이는 값은 **이 기본값**이다. 유진의
    두뇌와 갈라져 있으면 유진이 없는 모델을 부르고, 화면에는 "유진이 지금
    도와줄 수 없어요"만 뜬다 -- 원인이 설정 한 줄인데 코드를 뒤지게 된다.
    """
    assert _main_compose_local_model_default() == _yujin_profile_model(), (
        f"compose.yaml 기본값({_main_compose_local_model_default()})과 유진의 두뇌"
        f"({_yujin_profile_model()})가 서로 다른 모델을 가리킨다"
    )
