"""이 컴퓨터에서 도는 캡컷 다리 자체 — 받은 요청으로 실제로 폴더가 옮겨지는가.

`test_capcut_host_bridge.py`는 다리를 **부르는 쪽**을 잰다(가짜 다리를 세워서).
이 파일은 **받는 쪽**을 잰다. 둘을 따로 재면 가운데 이음매가 시험 없이 남는데,
이 저장소는 그 자리에서 여러 번 "부품은 있는데 부르는 자리가 없다"를 겪었다.

**소켓은 안 연다.** 이 저장소의 시험은 연결을 못 열게 막혀 있고
(`tests/conftest.py`), 그 울타리는 옳다. 그래서 다리의 판단을 HTTP 껍데기와
떼어 놓고(`*_payload`) 그 함수를 그대로 부른다. 껍데기가 하는 일은 이 셋을
실어 나르는 것뿐이다. 실제 HTTP로 도는 모습은 2026-09-07에 컨테이너에서
실물로 확인했다(`decisions/2026-09-07-capcut-handoff-bridge.ko.md`).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_SERVICE_PATH = Path(__file__).parents[1] / "scripts" / "host_capcut_service.py"
_spec = importlib.util.spec_from_file_location("videobox_host_capcut_service", _SERVICE_PATH)
assert _spec is not None and _spec.loader is not None
bridge_service = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bridge_service)


@pytest.fixture()
def capcut_computer(tmp_path: Path, monkeypatch) -> Path:
    """캡컷이 깔려 있고 프로젝트 폴더가 있는 컴퓨터를 흉내 낸다."""
    local_app_data = tmp_path / "LocalAppData"
    (local_app_data / "CapCut" / "Apps" / "9.3.0.3970").mkdir(parents=True)
    (local_app_data / "CapCut" / "Apps" / "9.3.0.3970" / "CapCut.exe").write_bytes(b"capcut")
    project_root = local_app_data / "CapCut" / "User Data" / "Projects" / "com.lveditor.draft"
    project_root.mkdir(parents=True)
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))
    monkeypatch.delenv("VIDEOBOX_CAPCUT_SUPPORTED_VERSIONS", raising=False)
    # 다리 자신은 다리를 부르지 않는다. 이 줄이 있어도 `_service()`가
    # `local_app_data`를 손으로 주기 때문에 로컬로 돈다 -- 그걸 같이 잰다.
    monkeypatch.setenv("VIDEOBOX_CAPCUT_BRIDGE_URL", "http://127.0.0.1:8200")
    return project_root


@pytest.fixture()
def allowed_root(tmp_path: Path) -> Path:
    root = tmp_path / "runtime"
    root.mkdir()
    return root


def _draft(root: Path, name: str) -> Path:
    draft = root / name
    draft.mkdir(parents=True)
    (draft / "draft_content.json").write_text('{"draft": true}', encoding="utf-8")
    (draft / "draft_meta_info.json").write_text("{}", encoding="utf-8")
    return draft


def _register(draft: Path, allowed_root: Path, *, export_id="export_002", token="t1"):
    return bridge_service.register_payload(
        {"draft_host_path": str(draft), "export_id": export_id, "ownership_token": token},
        allowed_roots=(allowed_root,),
    )


def test_the_bridge_never_calls_itself(capcut_computer) -> None:
    """다리가 켜져 있다는 설정을 봐도, 다리 자신은 로컬 폴더를 쓴다.
    안 그러면 자기 자신을 부르며 맴돈다."""
    assert bridge_service._service().bridge is None


def test_diagnostics_report_this_computers_capcut(capcut_computer: Path) -> None:
    status, payload = bridge_service.diagnostics_payload()

    assert status == 200
    assert payload["status"] == "ready"
    assert payload["detected_version"] == "9.3.0.3970"
    assert payload["write_access"] is True
    assert Path(payload["project_root_path"]) == capcut_computer


def test_register_copies_the_draft_into_the_capcut_folder(
    capcut_computer: Path, allowed_root: Path
) -> None:
    draft = _draft(allowed_root, "timeline_002")

    status, payload = _register(draft, allowed_root)

    registered = Path(payload["registered_path"])
    assert status == 200
    assert registered == capcut_computer / "videobox-export_002"
    assert (registered / "draft_content.json").read_text(encoding="utf-8") == '{"draft": true}'
    assert payload["reused"] is False
    # 원본은 손대지 않는다.
    assert (draft / "draft_content.json").is_file()


def test_registering_twice_reuses_instead_of_making_a_second_folder(
    capcut_computer: Path, allowed_root: Path
) -> None:
    draft = _draft(allowed_root, "timeline_002")

    _, first = _register(draft, allowed_root)
    _, second = _register(draft, allowed_root)

    assert second["registered_path"] == first["registered_path"]
    assert second["reused"] is True


def test_a_folder_outside_the_allowed_root_is_refused(
    capcut_computer: Path, allowed_root: Path, tmp_path: Path
) -> None:
    """컨테이너가 **자기 자료 밖**의 아무 폴더나 캡컷에 복사시킬 수 없어야 한다."""
    outsider = _draft(tmp_path / "somewhere-else", "timeline_002")

    status, payload = _register(outsider, allowed_root, export_id="export_009")

    assert status == 403
    assert payload["error"] == "draft_outside_allowed_root"
    assert not (capcut_computer / "videobox-export_009").exists()


def test_a_draft_that_is_not_there_is_refused_before_anything_is_copied(
    capcut_computer: Path, allowed_root: Path
) -> None:
    status, payload = _register(allowed_root / "nothing-here", allowed_root)

    assert status == 400
    assert payload["error"] == "draft_not_found"


def test_someone_elses_capcut_project_is_never_overwritten(
    capcut_computer: Path, allowed_root: Path
) -> None:
    """캡컷 폴더에 있는 것은 **owner의 진짜 자료**다. 덮어쓰지 않는다."""
    theirs = capcut_computer / "videobox-export_002"
    theirs.mkdir()
    (theirs / "draft_content.json").write_text('{"mine": true}', encoding="utf-8")
    draft = _draft(allowed_root, "timeline_002")

    status, payload = _register(draft, allowed_root)

    assert status == 409
    assert payload["error"] == "capcut_registration_failed"
    assert (theirs / "draft_content.json").read_text(encoding="utf-8") == '{"mine": true}'


def test_cleanup_removes_only_what_this_request_registered(
    capcut_computer: Path, allowed_root: Path
) -> None:
    draft = _draft(allowed_root, "timeline_002")
    _, registered = _register(draft, allowed_root)

    status, payload = bridge_service.cleanup_payload(
        {
            "export_id": "export_002",
            "registered_host_path": registered["registered_path"],
            "ownership_token": "t1",
        }
    )

    assert status == 200
    assert payload["removed"] is True
    assert not (capcut_computer / "videobox-export_002").exists()


def test_cleanup_with_the_wrong_token_removes_nothing(
    capcut_computer: Path, allowed_root: Path
) -> None:
    draft = _draft(allowed_root, "timeline_002")
    _, registered = _register(draft, allowed_root)

    status, payload = bridge_service.cleanup_payload(
        {
            "export_id": "export_002",
            "registered_host_path": registered["registered_path"],
            "ownership_token": "someone-else",
        }
    )

    assert status == 200
    assert payload["removed"] is False
    assert (capcut_computer / "videobox-export_002").is_dir()
