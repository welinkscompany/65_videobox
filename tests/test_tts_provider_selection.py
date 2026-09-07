from __future__ import annotations

import pytest

from videobox_api.provider_factories import _build_tts_provider
from videobox_core_engine.settings import TTSEngineConfig


def test_nothing_synthesizes_until_someone_turns_it_on() -> None:
    # 목소리 합성은 무거운 모델을 내려받는다. 켜지 않은 사람에게 그것이
    # 저절로 일어나면 안 된다.
    assert _build_tts_provider(TTSEngineConfig(enabled=False, engine="chatterbox")) is None


def test_choosing_chatterbox_gives_the_commercially_usable_cloner() -> None:
    # XTTS도 복제를 하지만 Coqui CPML은 비상업용이다. 매출을 내려면 이쪽이어야 한다.
    provider = _build_tts_provider(TTSEngineConfig(enabled=True, engine="chatterbox", language="ko"))

    assert provider.provider_name == "chatterbox"
    assert provider.language == "ko"


def test_the_older_cloner_is_still_reachable_for_anyone_already_on_it() -> None:
    # 쓰던 사람의 설정을 조용히 갈아치우지 않는다.
    provider = _build_tts_provider(TTSEngineConfig(enabled=True, engine="local_xtts", language="ko"))

    assert provider.provider_name == "local_xtts"


def test_an_engine_name_nobody_implements_is_refused_at_configuration_time() -> None:
    # 렌더 도중이 아니라 설정할 때 걸려야 고칠 수 있다.
    with pytest.raises(ValueError, match="chatterbox"):
        TTSEngineConfig(enabled=True, engine="voicebox")
