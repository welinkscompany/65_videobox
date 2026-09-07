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


def test_host_bridge_builds_the_bridge_provider_and_nothing_else() -> None:
    """호스트 목소리 다리를 골랐으면 정말 그 provider가 나와야 한다 (코드리뷰
    2026-09-07). 이 팩토리 분기를 재는 시험이 하나도 없었다 -- 안 켜면 조용히
    기계 목소리(espeak/chatterbox)로 대신 읽는 회귀가 나도 아무도 몰랐다.
    """
    from videobox_provider_interfaces.host_tts_bridge_provider import HostTTSBridgeProvider

    provider = _build_tts_provider(
        TTSEngineConfig(enabled=True, engine="host_bridge", language="ko", host_bridge_base_url="http://127.0.0.1:8199")
    )

    assert isinstance(provider, HostTTSBridgeProvider)
    assert provider.provider_name == "host_bridge"
    # base_url을 그대로 전달한다 -- 다른 엔진의 기본값으로 슬쩍 바뀌면 다리가
    # 안 켜져 있을 때 엉뚱한 주소에 물으며 실패 이유가 헷갈린다.
    assert provider.base_url == "http://127.0.0.1:8199"
