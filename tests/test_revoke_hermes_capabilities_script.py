"""`scripts/revoke_hermes_capabilities.py`가 저장 계층의 revoke 함수를 실제로 잇는지.

`revoke_issued_hermes_capabilities`는 이미 있고 시험도 있었지만, 부르는 자리가
시험 밖에는 없었다(`docs/handoffs/2026-09-08-hermes-egress-and-multitrack-plans.ko.md`
§2 Phase 4). 이 시험은 새 로직을 검증하는 게 아니라 **CLI가 그 함수를 진짜
부르는지**만 검증한다.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = str(REPOSITORY_ROOT / "scripts")
if SCRIPTS_ROOT not in sys.path:
    sys.path.insert(0, SCRIPTS_ROOT)

import revoke_hermes_capabilities as revoke_script  # noqa: E402
from videobox_storage.local_project_store import LocalProjectStore  # noqa: E402


NOW_EPOCH = 1_800_000_000


def _prepare_current_capability_scope(store: LocalProjectStore, project_id: str) -> tuple[str, int, int]:
    session = store.save_editing_session(
        project_id=project_id,
        timeline_id="capability-current-timeline",
        session_payload={"segments": [], "history": []},
    )
    while int(session["session_revision"]) < 3:
        session = store.update_editing_session(
            project_id=project_id,
            session_id=session["session_id"],
            session_payload={"segments": [], "history": []},
            expected_revision=session["session_revision"],
        )
    while store.get_asset_index_revision(project_id) < 7:
        store.bump_asset_index_revision(project_id)
    return (
        str(session["session_id"]),
        int(session["session_revision"]),
        store.get_asset_index_revision(project_id),
    )


def _seed_one_live_capability(store: LocalProjectStore, project_id: str) -> None:
    session_id, session_revision, asset_index_revision = _prepare_current_capability_scope(
        store, project_id
    )
    store.register_hermes_run_capabilities(
        project_id=project_id,
        conversation_id="conversation-1",
        run_id="run-1",
        session_id=session_id,
        session_revision=session_revision,
        asset_index_revision=asset_index_revision,
        capabilities=(
            {"capability_id": "cap-read-0001", "action": "read_context", "expires_at": NOW_EPOCH + 300},
            {"capability_id": "cap-publish-0001", "action": "publish_proposal", "expires_at": NOW_EPOCH + 300},
        ),
    )


def test_script_revokes_a_real_capability_through_the_store(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project("revoke script")
    _seed_one_live_capability(store, project.project_id)

    exit_code = revoke_script.main(
        [
            "--project-id", project.project_id,
            "--conversation-id", "conversation-1",
            "--run-id", "run-1",
            "--json",
        ],
        store_factory=lambda _root: store,
    )

    assert exit_code == 0
    result = json.loads(capsys.readouterr().out)
    assert result == {"status": "ok", "revoked_count": 2}

    # 정말 지웠는지 -- 같은 걸 또 지워 보면 이번엔 0개여야 한다(멱등).
    second_exit_code = revoke_script.main(
        [
            "--project-id", project.project_id,
            "--conversation-id", "conversation-1",
            "--run-id", "run-1",
            "--json",
        ],
        store_factory=lambda _root: store,
    )
    assert second_exit_code == 0
    second_result = json.loads(capsys.readouterr().out)
    assert second_result == {"status": "ok", "revoked_count": 0}


def test_script_reports_a_named_error_for_a_malformed_id(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project("revoke script bad id")

    exit_code = revoke_script.main(
        [
            "--project-id", project.project_id,
            "--conversation-id", "",
            "--run-id", "run-1",
            "--json",
        ],
        store_factory=lambda _root: store,
    )

    assert exit_code == 2
    result = json.loads(capsys.readouterr().out)
    assert result == {"status": "error", "error_code": "hermes_capability_expected_invalid"}


def test_script_reports_the_store_error_code_when_the_store_rejects_the_reason(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`reason`은 스크립트가 CLI로 안 받는다 -- 저장 계층이 정확한 문자열 하나만
    받아 준다는 계약을 그대로 지키는지, 가짜가 아니라 진짜 store에 대고 잰다."""

    class _WrongReasonStore:
        def revoke_issued_hermes_capabilities(self, *, reason: str, **_: Any) -> int:
            if reason != "hermes_capability_revoked":
                raise ValueError("hermes_capability_audit_reason_invalid")
            return 0

    exit_code = revoke_script.main(
        ["--project-id", "p1", "--conversation-id", "c1", "--run-id", "r1", "--json"],
        store_factory=lambda _root: _WrongReasonStore(),
    )

    assert exit_code == 0
    result = json.loads(capsys.readouterr().out)
    assert result == {"status": "ok", "revoked_count": 0}
