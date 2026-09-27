"""The voice bridge must default to the commercially usable engine.

AK W1215-1 (owner decision 2026-09-28): voice cloning uses chatterbox
(Resemble AI, MIT, Korean) by default. XTTS is Coqui CPML -- non-commercial --
and before this change it was the bridge's default whenever
`VIDEOBOX_HOST_TTS_ENGINE` was unset, and `start-voice.ps1 -Engine auto`
silently fell back to it when chatterbox was not installed. A misspelt engine
name also fell through to XTTS. VideoBox has no notion of which channel is
monetized, so the bridge itself refuses the non-commercial engine unless the
person starting it says so explicitly.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _bridge():
    spec = importlib.util.spec_from_file_location(
        "videobox_host_tts_service_under_test", ROOT / "scripts" / "host_tts_service.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    # dataclasses look the defining module up in sys.modules.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_the_bridge_defaults_to_chatterbox_which_is_commercially_usable() -> None:
    choice = _bridge().resolve_engine({})
    assert choice.engine == "chatterbox"
    assert choice.commercial_use is True
    assert "MIT" in choice.licence


def test_xtts_is_refused_without_an_explicit_non_commercial_acknowledgement() -> None:
    bridge = _bridge()
    with pytest.raises(ValueError, match="non_commercial_tts_engine_requires_acknowledgement"):
        bridge.resolve_engine({"VIDEOBOX_HOST_TTS_ENGINE": "local_xtts"})


def test_xtts_with_the_acknowledgement_runs_and_says_it_is_non_commercial() -> None:
    bridge = _bridge()
    choice = bridge.resolve_engine(
        {"VIDEOBOX_HOST_TTS_ENGINE": "local_xtts", bridge.NON_COMMERCIAL_ACK_ENV: "1"}
    )
    assert choice.engine == "local_xtts"
    assert choice.commercial_use is False
    assert "비상업" in choice.licence


def test_an_unknown_engine_name_is_an_error_not_a_silent_xtts() -> None:
    with pytest.raises(ValueError, match="unknown_tts_engine"):
        _bridge().resolve_engine({"VIDEOBOX_HOST_TTS_ENGINE": "chaterbox"})


def test_health_tells_the_caller_the_licence_of_what_is_speaking() -> None:
    bridge = _bridge()
    payload = bridge.health_payload(bridge.resolve_engine({}))
    assert payload == {
        "status": "ok",
        "engine": "chatterbox",
        "licence": payload["licence"],
        "commercial_use": True,
    }
    assert "MIT" in payload["licence"]


def _start_voice() -> str:
    return (ROOT / "scripts" / "start-voice.ps1").read_text(encoding="utf-8-sig")


def test_start_voice_auto_never_falls_back_to_xtts() -> None:
    script = _start_voice()
    default_block = re.search(r"default\s*\{(?P<body>.*?)\n    \}", script, re.S)
    assert default_block is not None
    assert "local_xtts" not in default_block.group("body")
    assert "$xtts" not in default_block.group("body")


def test_start_voice_marks_xtts_non_commercial_and_passes_the_acknowledgement() -> None:
    bridge = _bridge()
    script = _start_voice()
    branch = re.search(r"'local_xtts'\s*\{(?P<body>[^}]*)\}", script)
    assert branch is not None
    assert "비상업" in branch.group("body")
    assert f"$env:{bridge.NON_COMMERCIAL_ACK_ENV} = '1'" in branch.group("body")
