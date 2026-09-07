"""캡컷으로 넘기는 다리 — 컨테이너가 만든 초안이 이 컴퓨터의 캡컷에 닿는가.

세 가지가 같이 있어야 owner가 화면에서 한 번 눌러 캡컷에서 열 수 있다.

1. **경로**: 초안에 적힌 `/videobox-data/...`를 이 컴퓨터 경로로 옮겨 적는다.
2. **전달**: 컨테이너는 캡컷 폴더에 못 쓰니 호스트 다리가 대신 복사한다.
3. **정직**: 다리가 꺼져 있으면 화면이 그렇게 말한다. 조용히 실패하지 않는다.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from videobox_capcut_export.host_paths import (
    ENVIRONMENT_VARIABLE,
    CapCutHostPathMap,
    rewrite_draft_for_host,
)
from videobox_core_engine.capcut_handoff import (
    BRIDGE_PATH_MAP_MESSAGE,
    BRIDGE_UNAVAILABLE_MESSAGE,
    CapCutHandoffError,
    CapCutHandoffService,
)
from videobox_core_engine.capcut_host_bridge import (
    BRIDGE_PORT,
    CapCutHostBridge,
    CapCutHostBridgeRefused,
    CapCutHostBridgeUnavailable,
)

_CONTAINER_ROOT = "/videobox-data"
_HOST_ROOT = "D:/AI_Workspace_louis_office_50/20_project/65_videobox-project/runtime"
_MAPPING_TEXT = f"{_CONTAINER_ROOT}={_HOST_ROOT}"


# --------------------------------------------------------------------------
# 1. 경로 옮겨 적기
# --------------------------------------------------------------------------


def test_map_reads_the_pairing_from_configuration_not_from_code() -> None:
    mapping = CapCutHostPathMap.parse(_MAPPING_TEXT)

    assert mapping.map_path("/videobox-data/projects/p1/assets/imported/a.jpg") == (
        f"{_HOST_ROOT}/projects/p1/assets/imported/a.jpg"
    )


def test_map_reads_the_environment_variable(monkeypatch) -> None:
    monkeypatch.setenv(ENVIRONMENT_VARIABLE, _MAPPING_TEXT)

    assert CapCutHostPathMap.from_environment().map_path("/videobox-data/x") == f"{_HOST_ROOT}/x"


def test_empty_configuration_changes_nothing(monkeypatch) -> None:
    monkeypatch.delenv(ENVIRONMENT_VARIABLE, raising=False)
    mapping = CapCutHostPathMap.from_environment()

    assert mapping.is_empty is True
    assert mapping.map_path("/videobox-data/x") == "/videobox-data/x"
    assert mapping.maps("/videobox-data/x") is False


def test_longer_prefix_wins_so_a_nested_pairing_is_not_swallowed() -> None:
    mapping = CapCutHostPathMap.parse(
        "/videobox-data=D:/root;/videobox-data/projects=E:/projects"
    )

    assert mapping.map_path("/videobox-data/projects/p1") == "E:/projects/p1"
    assert mapping.map_path("/videobox-data/other") == "D:/root/other"


def test_a_neighbouring_name_that_merely_starts_the_same_is_left_alone() -> None:
    mapping = CapCutHostPathMap.parse(_MAPPING_TEXT)

    assert mapping.map_path("/videobox-database/x") == "/videobox-database/x"


def test_rewrite_moves_every_material_path_in_the_draft(tmp_path: Path) -> None:
    draft = tmp_path / "timeline_002"
    draft.mkdir()
    (draft / "draft_content.json").write_text(
        json.dumps(
            {
                "materials": {
                    "videos": [
                        {"path": "/videobox-data/projects/p1/assets/imported/a.jpg"},
                        {"path": "/videobox-data/projects/p1/assets/imported/b.png"},
                    ],
                    "unrelated": [{"path": "/videobox-database/keep-me"}],
                }
            }
        ),
        encoding="utf-8",
    )
    (draft / "draft_meta_info.json").write_text('{"draft_fold_path": ""}', encoding="utf-8")

    replaced = rewrite_draft_for_host(draft, CapCutHostPathMap.parse(_MAPPING_TEXT))

    content = json.loads((draft / "draft_content.json").read_text(encoding="utf-8"))
    assert replaced == 2
    assert [entry["path"] for entry in content["materials"]["videos"]] == [
        f"{_HOST_ROOT}/projects/p1/assets/imported/a.jpg",
        f"{_HOST_ROOT}/projects/p1/assets/imported/b.png",
    ]
    # 남의 이름은 그대로 둔다.
    assert content["materials"]["unrelated"][0]["path"] == "/videobox-database/keep-me"


def test_rewrite_does_nothing_when_no_pairing_is_configured(tmp_path: Path) -> None:
    draft = tmp_path / "timeline_002"
    draft.mkdir()
    original = '{"path":"/videobox-data/x"}'
    (draft / "draft_content.json").write_text(original, encoding="utf-8")

    assert rewrite_draft_for_host(draft, CapCutHostPathMap()) == 0
    assert (draft / "draft_content.json").read_text(encoding="utf-8") == original


# --------------------------------------------------------------------------
# 2. 다리 클라이언트 — 나가는 곳은 이 컴퓨터뿐
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "base_url",
    [
        "https://127.0.0.1:8200",
        "http://example.com:8200",
        "http://127.0.0.1:9999",
        "http://127.0.0.1:8200/somewhere",
        "http://user:pass@127.0.0.1:8200",
    ],
)
def test_bridge_refuses_to_call_anywhere_but_this_computer(base_url: str) -> None:
    bridge = CapCutHostBridge(base_url=base_url)

    with pytest.raises(CapCutHostBridgeRefused):
        bridge.diagnose()


def test_bridge_allows_the_container_address() -> None:
    calls: list[str] = []

    def client(request, timeout):  # noqa: ANN001, ARG001
        calls.append(request.full_url)
        return b'{"status": "ready"}'

    bridge = CapCutHostBridge(
        base_url=f"http://host.docker.internal:{BRIDGE_PORT}", http_client=client
    )

    assert bridge.diagnose() == {"status": "ready"}
    assert calls == [f"http://host.docker.internal:{BRIDGE_PORT}/diagnostics"]


def test_bridge_reports_unavailable_when_nothing_is_listening() -> None:
    def client(request, timeout):  # noqa: ANN001, ARG001
        raise OSError("connection refused")

    bridge = CapCutHostBridge(http_client=client)

    with pytest.raises(CapCutHostBridgeUnavailable):
        bridge.diagnose()


def test_bridge_is_configured_from_the_environment(monkeypatch) -> None:
    monkeypatch.delenv("VIDEOBOX_CAPCUT_BRIDGE_URL", raising=False)
    assert CapCutHostBridge.from_environment() is None

    monkeypatch.setenv("VIDEOBOX_CAPCUT_BRIDGE_URL", f"http://127.0.0.1:{BRIDGE_PORT}")
    configured = CapCutHostBridge.from_environment()
    assert configured is not None and configured.base_url == f"http://127.0.0.1:{BRIDGE_PORT}"


# --------------------------------------------------------------------------
# 3. 진단과 등록이 다리를 통해 진실을 말하는가
# --------------------------------------------------------------------------


class _StubBridge:
    def __init__(self, *, diagnostics=None, registration=None, error=None) -> None:
        self._diagnostics = diagnostics
        self._registration = registration
        self._error = error
        self.registered: list[dict] = []
        self.cleaned: list[dict] = []

    def diagnose(self):
        if self._error is not None:
            raise self._error
        return self._diagnostics

    def register(self, **kwargs):
        if self._error is not None:
            raise self._error
        self.registered.append(kwargs)
        return self._registration

    def cleanup(self, **kwargs):
        self.cleaned.append(kwargs)
        return {"removed": True}


_READY_DIAGNOSTICS = {
    "status": "ready",
    "installation_path": "C:/Users/atgro/AppData/Local/CapCut/Apps/8.7.0/CapCut.exe",
    "detected_version": "8.7.0",
    "is_supported": True,
    "project_root_path": "C:/Users/atgro/AppData/Local/CapCut/User Data/Projects/com.lveditor.draft",
    "project_root_exists": True,
    "write_access": True,
    "recovery_message": None,
}


def _service(bridge, *, mapping_text: str | None = _MAPPING_TEXT) -> CapCutHandoffService:
    return CapCutHandoffService(
        bridge=bridge,
        host_path_map=CapCutHostPathMap.parse(mapping_text),
    )


def test_diagnostics_report_the_host_capcut_not_the_container(tmp_path: Path) -> None:
    service = _service(_StubBridge(diagnostics=_READY_DIAGNOSTICS))

    diagnostics = service.diagnose()

    assert diagnostics.status == "ready"
    assert diagnostics.is_supported is True
    assert diagnostics.project_root_exists is True
    assert diagnostics.write_access is True
    assert diagnostics.recovery_message is None
    assert diagnostics.detected_version == "8.7.0"


def test_diagnostics_say_how_to_switch_the_bridge_on_when_it_is_off() -> None:
    service = _service(_StubBridge(error=CapCutHostBridgeUnavailable("down")))

    diagnostics = service.diagnose()

    assert diagnostics.status == "failed"
    assert diagnostics.recovery_message == BRIDGE_UNAVAILABLE_MESSAGE


def test_diagnostics_warn_before_the_press_when_the_pairing_is_missing() -> None:
    service = _service(_StubBridge(diagnostics=_READY_DIAGNOSTICS), mapping_text=None)

    diagnostics = service.diagnose()

    assert diagnostics.status == "failed"
    assert diagnostics.recovery_message == BRIDGE_PATH_MAP_MESSAGE


def _draft(tmp_path: Path) -> Path:
    draft = tmp_path / "timeline_002"
    draft.mkdir(parents=True)
    (draft / "draft_content.json").write_text('{"draft": true}', encoding="utf-8")
    return draft


def test_register_sends_the_host_path_so_the_bridge_can_find_the_draft(tmp_path: Path) -> None:
    bridge = _StubBridge(
        registration={
            "registered_path": "C:/CapCut/com.lveditor.draft/videobox-export_002",
            "status": "ready",
            "registered_at": "2026-09-07T00:00:00+00:00",
            "reused": False,
        }
    )
    draft = _draft(tmp_path)
    mapping = CapCutHostPathMap.parse(f"{tmp_path.as_posix()}={_HOST_ROOT}")
    service = CapCutHandoffService(bridge=bridge, host_path_map=mapping)

    record = service.register(source_draft_path=draft, export_id="export_002", ownership_token="t1")

    assert bridge.registered == [
        {
            "draft_host_path": f"{_HOST_ROOT}/timeline_002",
            "export_id": "export_002",
            "ownership_token": "t1",
        }
    ]
    assert record.registered_path == Path("C:/CapCut/com.lveditor.draft/videobox-export_002")
    assert record.reused is False


def test_register_refuses_to_send_a_path_it_could_not_translate(tmp_path: Path) -> None:
    bridge = _StubBridge(registration={"registered_path": "C:/whatever"})
    service = CapCutHandoffService(bridge=bridge, host_path_map=CapCutHostPathMap())

    with pytest.raises(CapCutHandoffError) as failure:
        service.register(source_draft_path=_draft(tmp_path), export_id="export_002")

    assert str(failure.value) == BRIDGE_PATH_MAP_MESSAGE
    assert bridge.registered == []


def test_register_tells_the_owner_to_switch_the_bridge_on(tmp_path: Path) -> None:
    draft = _draft(tmp_path)
    mapping = CapCutHostPathMap.parse(f"{tmp_path.as_posix()}={_HOST_ROOT}")
    service = CapCutHandoffService(
        bridge=_StubBridge(error=CapCutHostBridgeUnavailable("down")), host_path_map=mapping
    )

    with pytest.raises(CapCutHandoffError) as failure:
        service.register(source_draft_path=draft, export_id="export_002")

    assert str(failure.value) == BRIDGE_UNAVAILABLE_MESSAGE


def test_a_service_given_a_local_folder_keeps_working_without_a_bridge(
    tmp_path: Path, monkeypatch
) -> None:
    """호스트에서 직접 도는 다리 자신과 기존 테스트가 여기 걸린다."""
    monkeypatch.setenv("VIDEOBOX_CAPCUT_BRIDGE_URL", f"http://127.0.0.1:{BRIDGE_PORT}")
    local_app_data = tmp_path / "LocalAppData"
    (local_app_data / "CapCut" / "Apps" / "8.7.0").mkdir(parents=True)
    (local_app_data / "CapCut" / "Apps" / "8.7.0" / "CapCut.exe").write_bytes(b"capcut")
    (local_app_data / "CapCut" / "User Data" / "Projects" / "com.lveditor.draft").mkdir(parents=True)

    service = CapCutHandoffService(local_app_data=local_app_data)

    assert service.bridge is None
    assert service.diagnose().status == "ready"


# --------------------------------------------------------------------------
# 4. 실물 초안 — 만든 결과에 이 컴퓨터의 경로가 적혀 있는가
# --------------------------------------------------------------------------


def test_the_real_draft_is_written_with_this_computers_paths(tmp_path: Path) -> None:
    """작은 흉내가 아니라 **진짜 초안**을 만들어 잰다.

    소재 경로가 바뀌지 않으면 캡컷이 파일을 못 찾는다 -- 그게 이 다리의 전부다.
    """
    import shutil
    import subprocess

    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg가 없으면 초안을 만들 수 없다")

    from videobox_capcut_export.pycapcut_adapter import PyCapCutRealExportAdapter
    from videobox_domain_models.assets import AssetType
    from videobox_storage.local_project_store import LocalProjectStore

    store_root = tmp_path / "store"
    store = LocalProjectStore(store_root)
    project = store.bootstrap_project(name="다리 실측")
    photo = tmp_path / "scene.jpg"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=640x360:duration=1",
         "-frames:v", "1", str(photo)],
        check=True,
    )
    asset = store.register_asset(
        project_id=project.project_id, asset_type=AssetType.IMAGE, source_path=photo
    )
    timeline = {
        "project_id": project.project_id,
        "timeline_id": "timeline_bridge",
        "narration_source_uri": None,
        "tracks": [
            {
                "track_type": "narration",
                "clips": [{
                    "clip_id": "narration_1", "segment_id": "seg_1",
                    "asset_uri": f"local://projects/{project.project_id}/segments/seg_1",
                    "start_sec": 0.0, "end_sec": 4.0,
                }],
            },
            {
                "track_type": "broll",
                "clips": [{
                    "clip_id": "broll_1", "segment_id": "seg_1",
                    "asset_uri": asset.storage_uri, "asset_id": asset.asset_id,
                    "start_sec": 0.0, "end_sec": 4.0,
                }],
            },
        ],
    }
    mapping = CapCutHostPathMap.parse(f"{store_root.as_posix()}={_HOST_ROOT}")

    draft = PyCapCutRealExportAdapter(store=store, host_path_map=mapping).export_timeline(
        project_id=project.project_id,
        timeline=timeline,
        drafts_root=tmp_path / "drafts",
        draft_name="bridge-draft",
    )

    content = (Path(draft.draft_path) / "draft_content.json").read_text(encoding="utf-8")
    assert _HOST_ROOT in content
    assert store_root.as_posix() not in content


# --------------------------------------------------------------------------
# 5. 지원 버전 목록 — 실제로 열어 본 것만 통과
# --------------------------------------------------------------------------


def _installed(tmp_path: Path, version: str) -> Path:
    local_app_data = tmp_path / "LocalAppData"
    (local_app_data / "CapCut" / "Apps" / version).mkdir(parents=True)
    (local_app_data / "CapCut" / "Apps" / version / "CapCut.exe").write_bytes(b"capcut")
    (local_app_data / "CapCut" / "User Data" / "Projects" / "com.lveditor.draft").mkdir(parents=True)
    return local_app_data


def test_the_capcut_actually_installed_on_this_computer_is_supported(tmp_path: Path, monkeypatch) -> None:
    """2026-09-07 실측: 설치본이 9.3.0.3970인데 목록이 8.x뿐이라 막혀 있었다."""
    monkeypatch.delenv("VIDEOBOX_CAPCUT_SUPPORTED_VERSIONS", raising=False)
    service = CapCutHandoffService(local_app_data=_installed(tmp_path, "9.3.0.3970"))

    diagnostics = service.diagnose()

    assert diagnostics.detected_version == "9.3.0.3970"
    assert diagnostics.is_supported is True
    assert diagnostics.status == "ready"


def test_a_version_nobody_has_opened_is_still_refused(tmp_path: Path, monkeypatch) -> None:
    """이 문은 "새 버전이면 통과"가 아니라 "본 것만 통과"다."""
    monkeypatch.delenv("VIDEOBOX_CAPCUT_SUPPORTED_VERSIONS", raising=False)
    service = CapCutHandoffService(local_app_data=_installed(tmp_path, "9.0.0.1"))

    assert service.diagnose().is_supported is False


def test_the_supported_list_can_be_widened_by_configuration(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VIDEOBOX_CAPCUT_SUPPORTED_VERSIONS", "9.0.")
    service = CapCutHandoffService(local_app_data=_installed(tmp_path, "9.0.0.1"))

    assert service.diagnose().is_supported is True
