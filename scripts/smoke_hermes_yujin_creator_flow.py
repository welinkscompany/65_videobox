"""Local creator-flow smoke with real VideoBox and Agent Gateway applications."""

from __future__ import annotations

import argparse
from copy import deepcopy
from hashlib import sha256
import hmac
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import sys
import tempfile
from unittest.mock import patch
from urllib.parse import quote, urlsplit
from uuid import uuid4


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
for source_root in (
    REPOSITORY_ROOT / "services" / "api" / "src",
    REPOSITORY_ROOT / "services" / "agent-gateway" / "src",
    REPOSITORY_ROOT / "packages" / "domain-models" / "src",
    REPOSITORY_ROOT / "packages" / "storage-abstractions" / "src",
    REPOSITORY_ROOT / "packages" / "provider-interfaces" / "src",
    REPOSITORY_ROOT / "packages" / "timeline-schema" / "src",
    REPOSITORY_ROOT / "packages" / "core-engine" / "src",
    REPOSITORY_ROOT / "packages" / "capcut-export" / "src",
):
    sys.path.insert(0, str(source_root))

import httpx
from fastapi.testclient import TestClient

from videobox_agent_gateway.hermes_rpc_client import HermesRpcEvent
from videobox_agent_gateway.main import create_app as create_agent_gateway_app
from videobox_api.main import create_app as create_videobox_app


SERVICE_TOKEN = "creator-smoke-service-token-with-32-bytes"
PASS_MARKER = "HERMES_YUJIN_CREATOR_NON_LIVE_PASS"
_ROOT_ATTESTATION_REQUEST_DOMAIN = (
    "videobox-live-smoke-root-attestation-request-v1"
)
_ROOT_ATTESTATION_RESPONSE_DOMAIN = (
    "videobox-live-smoke-root-attestation-response-v1"
)


class LiveSmokeBlocked(ValueError):
    pass


class _FakeHermes:
    def __init__(self, response: str) -> None:
        self.response = response
        self.local_response_calls = 0
        self.external_provider_calls = 0

    async def stream_prompt(self, *, text: str):
        if not text:
            raise AssertionError("fake Hermes received an empty prompt")
        self.local_response_calls += 1
        yield HermesRpcEvent("message.complete", self.response)


def _assert(condition: bool, marker: str) -> None:
    if not condition:
        raise AssertionError(f"HERMES_YUJIN_CREATOR_SMOKE_FAILED:{marker}")


def _live_assert(condition: bool, marker: str) -> None:
    if not condition:
        raise LiveSmokeBlocked(
            f"HERMES_YUJIN_CREATOR_LIVE_BLOCKED:{marker}"
        )


def _sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validated_live_base_uri(value: str) -> str:
    parsed = urlsplit(value)
    _live_assert(
        parsed.scheme == "http"
        and (parsed.hostname or "").lower()
        in {"127.0.0.1", "localhost", "::1"}
        and parsed.username is None
        and parsed.password is None
        and parsed.path in {"", "/"}
        and not parsed.query
        and not parsed.fragment,
        "base_uri_loopback_required",
    )
    return value.rstrip("/")


def _validate_live_project_root(*, root: Path, project_id: str) -> None:
    _live_assert(
        bool(project_id)
        and root.name == project_id,
        "project_root_identity_mismatch",
    )
    sqlite_marker = root / "db" / "project.sqlite"
    cross_store_layout = all(
        path.is_dir()
        for path in (
            root / "db",
            root / "inputs" / "raw_video",
            root / "editing_sessions",
            root / "timelines",
        )
    )
    _live_assert(
        sqlite_marker.is_file() or cross_store_layout,
        "project_root_layout_missing",
    )


def _live_root_attestation_secret() -> bytes:
    value = os.environ.get(
        "VIDEOBOX_HERMES_YUJIN_LIVE_ROOT_ATTESTATION_SECRET",
        "",
    )
    _live_assert(bool(value), "root_attestation_configuration_required")
    encoded = value.encode("utf-8")
    _live_assert(
        value == value.strip()
        and len(encoded) >= 32
        and "placeholder" not in value.lower()
        and "changeme" not in value.lower(),
        "root_attestation_configuration_invalid",
    )
    return encoded


def _root_attestation_mac(secret: bytes, message: str) -> str:
    return hmac.new(secret, message.encode("utf-8"), sha256).hexdigest()


def _attest_live_project_root(
    *,
    client: httpx.Client,
    project_id: str,
    root: Path,
    secret: bytes,
) -> None:
    nonce = secrets.token_hex(32)
    request_attestation = _root_attestation_mac(
        secret,
        (
            f"{_ROOT_ATTESTATION_REQUEST_DOMAIN}\0"
            f"{project_id}\0{nonce}"
        ),
    )
    response = client.get(
        (
            "/internal/live-smoke/projects/"
            f"{quote(project_id, safe='')}/root-attestation"
        ),
        params={"nonce": nonce},
        headers={
            "X-VideoBox-Live-Smoke-Attestation": request_attestation,
        },
    )
    try:
        payload = response.json()
    except (TypeError, ValueError):
        payload = {}
    canonical_root = os.path.normcase(str(root.resolve(strict=True)))
    expected_response = _root_attestation_mac(
        secret,
        (
            f"{_ROOT_ATTESTATION_RESPONSE_DOMAIN}\0"
            f"{project_id}\0{nonce}\0{canonical_root}"
        ),
    )
    actual_response = str(payload.get("root_attestation") or "")
    _live_assert(
        response.status_code == 200
        and not response.is_redirect
        and payload.get("version") == "v1"
        and payload.get("project_id") == project_id
        and payload.get("nonce") == nonce
        and len(actual_response) == 64
        and hmac.compare_digest(actual_response, expected_response),
        "root_attestation_mismatch",
    )


_LOCAL_SESSION_REQUIRED_FIELDS = frozenset(
    {
        "session_id",
        "project_id",
        "timeline_id",
        "session_revision",
        "caption_style",
        "segments",
        "history",
        "undo_stack",
        "redo_stack",
        "timeline_placement_overrides",
        "created_at",
        "updated_at",
    }
)
_LOCAL_SESSION_OPTIONAL_FIELDS = frozenset(
    {
        "script_asset_id",
        "timing_source",
        "narration_alignment_required",
        "stale_proposal_source_script_segment_ids",
        "output_freshness",
    }
)
_SEGMENT_OPTIONAL_DEFAULTS: dict[str, object] = {
    "broll_override": None,
    "visual_overlays": [],
    "music_override": None,
    "sfx_override": None,
    "tts_replacement": None,
    "caption_style": None,
}
_HISTORY_OPTIONAL_DEFAULTS: dict[str, object] = {
    "action_id": None,
    "label": None,
    "created_at": None,
    "reversible": None,
    "blocked_reason": None,
    "caption_text": None,
    "cut_action": None,
    "asset_id": None,
    "overlay_type": None,
    "recommendation_id": None,
    "inverse_payload": None,
    "forward_payload": None,
}
_API_TOP_OPTIONAL_FIELDS = (
    "script_asset_id",
    "timing_source",
    "narration_alignment_required",
    "stale_proposal_source_script_segment_ids",
)


def _reject_duplicate_json_keys(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_json_key")
        result[key] = value
    return result


def _load_local_session_file(
    *,
    root: Path,
    project_id: str,
    session_id: str,
) -> dict[str, object]:
    try:
        if (
            not session_id
            or any(
                character not in "abcdefghijklmnopqrstuvwxyz"
                "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
                for character in session_id
            )
        ):
            raise ValueError("session_id_invalid")
        editing_sessions = (root / "editing_sessions").resolve(strict=True)
        path = (editing_sessions / f"{session_id}.json").resolve(strict=True)
        if path.parent != editing_sessions or not path.is_file():
            raise ValueError("session_path_invalid")
        raw = path.read_bytes()
        if not raw or len(raw) > 16 * 1024 * 1024:
            raise ValueError("session_file_size_invalid")
        payload = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_reject_duplicate_json_keys,
            parse_constant=lambda _value: (_ for _ in ()).throw(
                ValueError("non_finite_json_value")
            ),
        )
        if not isinstance(payload, dict):
            raise ValueError("session_file_not_object")
        keys = frozenset(payload)
        if (
            not _LOCAL_SESSION_REQUIRED_FIELDS.issubset(keys)
            or not keys.issubset(
                _LOCAL_SESSION_REQUIRED_FIELDS
                | _LOCAL_SESSION_OPTIONAL_FIELDS
            )
            or payload.get("project_id") != project_id
            or payload.get("session_id") != session_id
            or not isinstance(payload.get("timeline_id"), str)
            or not str(payload.get("timeline_id") or "")
            or not isinstance(payload.get("session_revision"), int)
            or isinstance(payload.get("session_revision"), bool)
            or int(payload["session_revision"]) < 1
            or payload.get("caption_style") is not None
            and not isinstance(payload.get("caption_style"), dict)
            or not isinstance(payload.get("segments"), list)
            or not isinstance(payload.get("history"), list)
            or not isinstance(payload.get("undo_stack"), list)
            or not isinstance(payload.get("redo_stack"), list)
            or not isinstance(payload.get("timeline_placement_overrides"), dict)
            or not isinstance(payload.get("created_at"), str)
            or not isinstance(payload.get("updated_at"), str)
            or not payload["created_at"]
            or not payload["updated_at"]
        ):
            raise ValueError("session_file_contract_invalid")
        if payload["timeline_placement_overrides"] or "output_freshness" in payload:
            raise ValueError("session_file_unexposed_state")
        if not all(isinstance(item, dict) for item in payload["segments"]):
            raise ValueError("session_segments_invalid")
        if not all(isinstance(item, dict) for item in payload["history"]):
            raise ValueError("session_history_invalid")
        return payload
    except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError):
        raise LiveSmokeBlocked(
            "HERMES_YUJIN_CREATOR_LIVE_BLOCKED:session_file_api_mismatch"
        ) from None


def _session_api_projection_from_local(
    local: dict[str, object],
) -> dict[str, object]:
    segments = []
    for raw in local["segments"]:
        item = dict(raw)
        for key, default in _SEGMENT_OPTIONAL_DEFAULTS.items():
            item.setdefault(key, deepcopy(default))
        if item.get("source_script_segment_id") is None:
            item.pop("source_script_segment_id", None)
        segments.append(item)
    history = []
    for raw in local["history"]:
        item = dict(raw)
        for key, default in _HISTORY_OPTIONAL_DEFAULTS.items():
            item.setdefault(key, deepcopy(default))
        history.append(item)
    projected: dict[str, object] = {
        "session_id": local["session_id"],
        "project_id": local["project_id"],
        "timeline_id": local["timeline_id"],
        "session_revision": local["session_revision"],
        "caption_style": local["caption_style"],
        "segments": segments,
        "history": history,
        "undo_count": len(local["undo_stack"]),
        "redo_count": len(local["redo_stack"]),
        "created_at": local["created_at"],
        "updated_at": local["updated_at"],
    }
    for key in _API_TOP_OPTIONAL_FIELDS:
        if local.get(key) is not None:
            projected[key] = local[key]
    return projected


def _assert_local_session_matches_api(
    *,
    local: dict[str, object],
    remote: object,
) -> None:
    if not isinstance(remote, dict):
        _live_assert(False, "session_file_api_mismatch")
    canonical_remote = dict(remote)
    for key in _API_TOP_OPTIONAL_FIELDS:
        if canonical_remote.get(key) is None:
            canonical_remote.pop(key, None)
    _live_assert(
        canonical_remote == _session_api_projection_from_local(local),
        "session_file_api_mismatch",
    )


def _output_jobs(jobs: list[dict[str, object]]) -> list[dict[str, object]]:
    output_job_types = {
        "preview_render",
        "subtitle_render",
        "final_render",
        "capcut_export",
        "capcut_draft_export",
    }
    return [
        item
        for item in jobs
        if str(item.get("job_type") or "") in output_job_types
    ]


def _typed_caption_response(
    *,
    session_id: str,
    session_revision: int,
    asset_index_revision: int,
    segment_id: str,
    script_id: str,
    caption_text: str,
) -> str:
    visible_reply = "현재 장면에 맞는 자막 한 건을 추천합니다."
    payload = {
        "schema_version": "videobox.yujin-response.v1",
        "reply_text": visible_reply,
        "proposal": {
            "proposal_id": "untrusted-smoke-proposal",
            "base_revision": (
                f"session:{session_id}:revision:{session_revision}:"
                f"assets:{asset_index_revision}"
            ),
            "title": "자막 추천",
            "rationale": "현재 장면의 의미를 짧게 전달합니다.",
            "operations": [
                {
                    "operation_id": "untrusted-caption-operation",
                    "kind": "caption",
                    "target": {
                        "script_id": script_id,
                        "segment_id": segment_id,
                        "track_id": "caption-primary",
                    },
                    "parameters": {
                        "action": "set_text",
                        "text": caption_text,
                    },
                    "requires_materialization": False,
                    "preview_summary": "현재 장면 자막 교체",
                }
            ],
        },
    }
    return (
        f"{visible_reply}\n"
        "```videobox-yujin-response\n"
        f"{json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}\n"
        "```"
    )


def _gateway_http_client_factory(gateway_app):
    def factory(*, base_url: str, timeout: float):
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=gateway_app),
            base_url=base_url,
            timeout=timeout,
            follow_redirects=False,
            trust_env=False,
        )

    return factory


def run_non_live() -> dict[str, int | bool]:
    network_attempts = 0

    def reject_network(*_args: object, **_kwargs: object) -> None:
        nonlocal network_attempts
        network_attempts += 1
        raise AssertionError("external network is forbidden in non-live smoke")

    with tempfile.TemporaryDirectory(
        prefix="videobox_hermes_yujin_creator_smoke_",
    ) as temporary_root:
        projects_root = Path(temporary_root) / "projects"
        fake_hermes = _FakeHermes("")
        gateway_app = create_agent_gateway_app(
            hermes_client=fake_hermes,
            service_token=SERVICE_TOKEN,
        )
        app = create_videobox_app(
            projects_root=projects_root,
            agent_gateway_url="http://videobox-agent-gateway:8081",
            agent_gateway_service_token=SERVICE_TOKEN,
            agent_gateway_http_client_factory=_gateway_http_client_factory(
                gateway_app
            ),
        )
        store = app.state.store
        project = store.bootstrap_project(name="Hermes Yujin creator smoke")
        segment_id = "segment-smoke"
        script_id = "script-smoke"
        session = store.save_editing_session(
            project_id=project.project_id,
            timeline_id="timeline_001",
            session_payload={
                "segments": [
                    {
                        "segment_id": segment_id,
                        "caption_text": "기존 자막",
                        "start_sec": 0.0,
                        "end_sec": 2.0,
                        "cut_action": "keep",
                        "review_required": False,
                    }
                ],
                "script_asset_id": script_id,
                "history": [],
            },
        )
        timeline = store.save_timeline_run(
            project_id=project.project_id,
            output_mode="review",
            source_session_id=session["session_id"],
            source_session_revision=session["session_revision"],
            timeline_payload={
                "version": "v001",
                "output": {
                    "width": 1920,
                    "height": 1080,
                    "duration_sec": 2.0,
                },
                "tracks": [],
            },
        )
        asset_index_revision = store.get_asset_index_revision(project.project_id)
        recommended_caption = "추천 자막"
        fake_hermes.response = _typed_caption_response(
            session_id=session["session_id"],
            session_revision=session["session_revision"],
            asset_index_revision=asset_index_revision,
            segment_id=segment_id,
            script_id=script_id,
            caption_text=recommended_caption,
        )

        with patch.object(socket, "create_connection", reject_network):
            with TestClient(app) as client:
                base = f"/api/projects/{project.project_id}"
                local_session = _load_local_session_file(
                    root=store.project_root(project.project_id),
                    project_id=project.project_id,
                    session_id=session["session_id"],
                )
                session_read_response = client.get(
                    f"{base}/editing-sessions/{session['session_id']}"
                )
                _assert(
                    session_read_response.status_code == 200,
                    "session_binding_read",
                )
                _assert_local_session_matches_api(
                    local=local_session,
                    remote=session_read_response.json(),
                )
                conversation_response = client.post(
                    f"{base}/director/conversations",
                    json={"session_id": session["session_id"]},
                )
                _assert(
                    conversation_response.status_code == 201,
                    "conversation_create",
                )
                conversation_id = conversation_response.json()["conversation_id"]
                run_response = client.post(
                    f"{base}/director/conversations/{conversation_id}/hermes-runs",
                    json={
                        "session_id": session["session_id"],
                        "client_message_id": "creator-smoke-message",
                        "text": "현재 장면 자막을 한 줄 추천해 주세요.",
                        "expected_session_revision": session["session_revision"],
                        "selected_segment_id": segment_id,
                    },
                )
                _assert(run_response.status_code == 201, "run_create")
                events_response = client.get(run_response.json()["events_url"])
                _assert(events_response.status_code == 200, "events_read")
                _assert(
                    "event: run_completed" in events_response.text
                    and "event: blocked" not in events_response.text,
                    "sse_terminal",
                )

                messages_response = client.get(
                    f"{base}/director/conversations/{conversation_id}/messages",
                    params={"session_id": session["session_id"]},
                )
                _assert(messages_response.status_code == 200, "messages_read")
                messages = messages_response.json()["messages"]
                assistant = next(
                    item for item in reversed(messages) if item["role"] == "assistant"
                )
                proposal_id = assistant.get("proposal_id")
                _assert(bool(proposal_id), "proposal_id_missing")
                proposal_response = client.get(
                    f"{base}/director/proposals/{proposal_id}"
                )
                _assert(proposal_response.status_code == 200, "proposal_read")
                proposal = proposal_response.json()
                _assert(
                    proposal["status"] == "ready"
                    and proposal["diff"]["proposal_mode"]
                    == "yujin_actionable_v1",
                    "proposal_not_ready",
                )
                candidate = proposal["candidates"][0]
                _assert(
                    candidate["canonical_metadata"]["command_kind"]
                    == "set_caption_text",
                    "candidate_not_typed_caption",
                )
                preflight_response = client.post(
                    f"{base}/director/proposals/{proposal_id}/preflight"
                )
                _assert(
                    preflight_response.status_code == 200
                    and preflight_response.json()["status"] == "ready",
                    "proposal_preflight",
                )
                output_readiness_before = client.get(
                    f"{base}/review-approvals/timelines/"
                    f"{timeline['timeline_id']}"
                )
                _assert(
                    output_readiness_before.status_code == 200
                    and output_readiness_before.json().get("source_session_id")
                    == session["session_id"]
                    and output_readiness_before.json().get(
                        "source_session_revision"
                    )
                    == session["session_revision"]
                    and output_readiness_before.json().get("is_current") is True
                    and output_readiness_before.json().get("invalidated_at") is None
                    and output_readiness_before.json().get(
                        "invalidated_reason"
                    )
                    is None,
                    "output_readiness_before",
                )
                jobs_before_response = client.get(f"{base}/jobs")
                _assert(
                    jobs_before_response.status_code == 200,
                    "jobs_before_read",
                )

                before_apply = deepcopy(
                    store.get_editing_session(
                        project_id=project.project_id,
                        session_id=session["session_id"],
                    )
                )
                _assert(
                    before_apply == session,
                    "mutation_detected_before_explicit_apply",
                )

                apply_response = client.patch(
                    f"{base}/editing-sessions/{session['session_id']}/"
                    f"segments/{segment_id}/caption",
                    json={
                        "expected_revision": before_apply["session_revision"],
                        "caption_text": candidate["controls"]["text"],
                    },
                )
                _assert(apply_response.status_code == 200, "caption_apply")
                after_apply = apply_response.json()
                revision_delta = (
                    after_apply["session_revision"]
                    - before_apply["session_revision"]
                )
                before_captions = {
                    item["segment_id"]: item.get("caption_text")
                    for item in before_apply["segments"]
                }
                after_captions = {
                    item["segment_id"]: item.get("caption_text")
                    for item in after_apply["segments"]
                }
                caption_changes = sum(
                    before_captions.get(key) != value
                    for key, value in after_captions.items()
                )
                _assert(revision_delta == 1, "session_revision_delta")
                _assert(
                    caption_changes == 1
                    and after_captions[segment_id] == recommended_caption,
                    "caption_change_count",
                )

                manifest_response = client.get(
                    f"{base}/editing-sessions/{session['session_id']}/"
                    "playback-manifest"
                )
                _assert(
                    manifest_response.status_code == 200
                    and manifest_response.json()["session_revision"]
                    == after_apply["session_revision"],
                    "playback_manifest",
                )
                manifest_captions = {
                    item["segment_id"]: item["text"]
                    for item in manifest_response.json()["captions"]
                }
                _assert(
                    manifest_captions[segment_id] == recommended_caption,
                    "playback_caption",
                )
                output_readiness_after = client.get(
                    f"{base}/review-approvals/timelines/"
                    f"{timeline['timeline_id']}"
                )
                _assert(
                    output_readiness_after.status_code == 200
                    and output_readiness_after.json().get("source_session_id")
                    == session["session_id"]
                    and output_readiness_after.json().get(
                        "source_session_revision"
                    )
                    == session["session_revision"]
                    and output_readiness_after.json().get("is_current") is False
                    and bool(
                        output_readiness_after.json().get("invalidated_at")
                    )
                    and output_readiness_after.json().get(
                        "invalidated_reason"
                    )
                    == "editing_session_mutation",
                    "output_readiness_after",
                )
                jobs_response = client.get(f"{base}/jobs")
                _assert(jobs_response.status_code == 200, "jobs_read")
                output_job_types = {
                    "preview_render",
                    "subtitle_render",
                    "final_render",
                    "capcut_export",
                    "capcut_draft_export",
                }
                output_jobs_before = [
                    item
                    for item in jobs_before_response.json()["jobs"]
                    if item["job_type"] in output_job_types
                ]
                output_jobs = [
                    item
                    for item in jobs_response.json()["jobs"]
                    if item["job_type"] in output_job_types
                ]

        _assert(fake_hermes.local_response_calls == 1, "fake_hermes_call_count")
        _assert(fake_hermes.external_provider_calls == 0, "external_provider_call")
        _assert(network_attempts == 0, "network_attempt")
        _assert(not output_jobs_before and not output_jobs, "output_job_created")
        return {
            "sse_completed": True,
            "proposal_ready": True,
            "session_file_bound": True,
            "mutation_before_apply": 0,
            "session_revision_delta": revision_delta,
            "caption_changes": caption_changes,
            "playback_manifest_checked": True,
            "output_readiness_checked": True,
            "output_jobs": len(output_jobs),
            "external_provider_calls": fake_hermes.external_provider_calls,
        }


def run_live(
    *,
    base_uri: str,
    project_id: str,
    session_id: str,
    disposable_project_root: Path,
    sample_asset_path: Path,
    timeout_seconds: float,
) -> dict[str, int | bool]:
    """Run one explicit caption apply against an already disposable live project."""

    resolved_base_uri = _validated_live_base_uri(base_uri)
    root = disposable_project_root.resolve(strict=True)
    sample = sample_asset_path.resolve(strict=True)
    _live_assert(root.is_dir(), "disposable_root_required")
    _live_assert(sample.is_file(), "sample_asset_required")
    _live_assert(
        root != Path.home().resolve()
        and root.parent != root
        and not root.is_relative_to(REPOSITORY_ROOT.resolve()),
        "disposable_root_unsafe",
    )
    _validate_live_project_root(root=root, project_id=project_id)
    _live_assert(timeout_seconds > 0 and timeout_seconds <= 60, "timeout_invalid")
    local_session_before = _load_local_session_file(
        root=root,
        project_id=project_id,
        session_id=session_id,
    )
    root_attestation_secret = _live_root_attestation_secret()

    original_source_sha = _sha256(sample)
    with tempfile.TemporaryDirectory(
        prefix="videobox_hermes_yujin_live_",
        dir=root,
    ) as disposable_copy_root:
        copied_sample = Path(disposable_copy_root) / sample.name
        shutil.copy2(sample, copied_sample)
        copied_source_sha = _sha256(copied_sample)
        _live_assert(
            copied_source_sha == original_source_sha,
            "sample_copy_hash_mismatch",
        )

        with httpx.Client(
            base_url=resolved_base_uri,
            timeout=timeout_seconds,
            follow_redirects=False,
            trust_env=False,
        ) as client:
            _attest_live_project_root(
                client=client,
                project_id=project_id,
                root=root,
                secret=root_attestation_secret,
            )
            projects_response = client.get("/api/projects")
            _live_assert(
                projects_response.status_code == 200
                and not projects_response.is_redirect,
                "projects_read_failed",
            )
            project = next(
                (
                    item
                    for item in projects_response.json().get("projects", [])
                    if str(item.get("project_id") or "") == project_id
                ),
                None,
            )
            _live_assert(project is not None, "disposable_project_missing")
            project_name = str(project.get("name") or "").lower()
            _live_assert(
                "disposable" in project_name and "smoke" in project_name,
                "project_not_disposable",
            )
            _live_assert(
                str(project.get("root_storage_uri") or "")
                == f"local://projects/{project_id}",
                "project_storage_identity_mismatch",
            )

            encoded_project = quote(project_id, safe="")
            encoded_session = quote(session_id, safe="")
            base = f"/api/projects/{encoded_project}"
            session_path = (
                f"{base}/editing-sessions/{encoded_session}"
            )
            session_response = client.get(session_path)
            _live_assert(
                session_response.status_code == 200
                and not session_response.is_redirect,
                "session_read_failed",
            )
            session_before_run = session_response.json()
            _live_assert(
                str(session_before_run.get("project_id") or "") == project_id
                and str(session_before_run.get("session_id") or "")
                == session_id,
                "session_identity_mismatch",
            )
            _assert_local_session_matches_api(
                local=local_session_before,
                remote=session_before_run,
            )
            register_response = client.post(
                f"{base}/assets/raw-video",
                json={"source_path": str(copied_sample)},
            )
            _live_assert(
                register_response.status_code == 201
                and not register_response.is_redirect,
                "sample_copy_registration_failed",
            )
            copied_asset_id = str(
                register_response.json().get("asset_id") or ""
            )
            _live_assert(bool(copied_asset_id), "sample_copy_asset_missing")
            copied_asset_content_path = (
                f"{base}/assets/{quote(copied_asset_id, safe='')}/content"
            )
            copied_asset_before = client.get(copied_asset_content_path)
            _live_assert(
                copied_asset_before.status_code == 200
                and sha256(copied_asset_before.content).hexdigest()
                == original_source_sha,
                "registered_sample_hash_mismatch",
            )
            segments = [
                item
                for item in session_before_run.get("segments", [])
                if isinstance(item, dict)
                and str(item.get("segment_id") or "").strip()
            ]
            _live_assert(bool(segments), "caption_segment_required")
            selected_segment_id = str(segments[0]["segment_id"])
            before_jobs_response = client.get(f"{base}/jobs")
            _live_assert(
                before_jobs_response.status_code == 200,
                "jobs_before_read_failed",
            )
            _live_assert(
                not _output_jobs(before_jobs_response.json().get("jobs", [])),
                "disposable_project_has_output_jobs",
            )

            conversation_response = client.post(
                f"{base}/director/conversations",
                json={"session_id": session_id},
            )
            _live_assert(
                conversation_response.status_code == 201
                and not conversation_response.is_redirect,
                "conversation_create_failed",
            )
            conversation_id = str(
                conversation_response.json().get("conversation_id") or ""
            )
            encoded_conversation = quote(conversation_id, safe="")
            run_response = client.post(
                f"{base}/director/conversations/{encoded_conversation}/"
                "hermes-runs",
                json={
                    "session_id": session_id,
                    "client_message_id": f"live-smoke-{uuid4().hex}",
                    "text": (
                        "현재 첫 장면의 기존 뜻을 유지하면서 자막 한 줄만 "
                        "짧게 추천해 주세요."
                    ),
                    "expected_session_revision": int(
                        session_before_run["session_revision"]
                    ),
                    "selected_segment_id": selected_segment_id,
                },
            )
            _live_assert(
                run_response.status_code == 201
                and not run_response.is_redirect,
                "hermes_run_create_failed",
            )
            events_url = str(run_response.json().get("events_url") or "")
            _live_assert(
                events_url.startswith(f"{base}/director/conversations/"),
                "events_url_invalid",
            )
            events_response = client.get(
                events_url,
                headers={"Accept": "text/event-stream"},
            )
            _live_assert(
                events_response.status_code == 200
                and not events_response.is_redirect
                and events_response.headers.get("content-type", "")
                .split(";", 1)[0]
                .strip()
                .lower()
                == "text/event-stream",
                "hermes_events_failed",
            )
            _live_assert(
                "event: run_completed" in events_response.text
                and "event: blocked" not in events_response.text,
                "hermes_run_not_completed",
            )

            messages_response = client.get(
                f"{base}/director/conversations/{encoded_conversation}/messages",
                params={"session_id": session_id},
            )
            _live_assert(
                messages_response.status_code == 200,
                "messages_read_failed",
            )
            assistant = next(
                (
                    item
                    for item in reversed(
                        messages_response.json().get("messages", [])
                    )
                    if item.get("role") == "assistant"
                ),
                None,
            )
            _live_assert(
                assistant is not None and bool(assistant.get("proposal_id")),
                "proposal_missing",
            )
            proposal_id = str(assistant["proposal_id"])
            encoded_proposal = quote(proposal_id, safe="")
            proposal_response = client.get(
                f"{base}/director/proposals/{encoded_proposal}"
            )
            _live_assert(
                proposal_response.status_code == 200,
                "proposal_read_failed",
            )
            proposal = proposal_response.json()
            _live_assert(
                proposal.get("status") == "ready"
                and proposal.get("source_session_id") == session_id
                and proposal.get("diff", {}).get("proposal_mode")
                == "yujin_actionable_v1",
                "proposal_not_ready",
            )
            candidate = next(
                (
                    item
                    for item in proposal.get("candidates", [])
                    if item.get("media_type") == "caption"
                    and item.get("availability") == "actionable"
                    and item.get("review_status") == "approved"
                    and item.get("canonical_metadata", {}).get("command_kind")
                    == "set_caption_text"
                    and item.get("canonical_metadata", {}).get(
                        "target_segment_id"
                    )
                    == selected_segment_id
                ),
                None,
            )
            _live_assert(candidate is not None, "caption_candidate_missing")
            recommended_caption = str(
                candidate.get("controls", {}).get("text") or ""
            ).strip()
            _live_assert(
                bool(recommended_caption)
                and len(recommended_caption.encode("utf-8")) <= 2_048,
                "caption_candidate_invalid",
            )
            preflight_response = client.post(
                f"{base}/director/proposals/{encoded_proposal}/preflight"
            )
            _live_assert(
                preflight_response.status_code == 200
                and preflight_response.json().get("status") == "ready",
                "proposal_preflight_failed",
            )

            before_apply_response = client.get(session_path)
            _live_assert(
                before_apply_response.status_code == 200
                and before_apply_response.json() == session_before_run,
                "mutation_detected_before_apply",
            )
            local_session_before_apply = _load_local_session_file(
                root=root,
                project_id=project_id,
                session_id=session_id,
            )
            _assert_local_session_matches_api(
                local=local_session_before_apply,
                remote=before_apply_response.json(),
            )
            apply_response = client.patch(
                f"{session_path}/segments/"
                f"{quote(selected_segment_id, safe='')}/caption",
                json={
                    "expected_revision": int(
                        session_before_run["session_revision"]
                    ),
                    "caption_text": recommended_caption,
                    "proposal_id": proposal_id,
                    "candidate_id": str(candidate["candidate_id"]),
                },
            )
            _live_assert(
                apply_response.status_code == 200
                and not apply_response.is_redirect,
                "caption_apply_failed",
            )
            session_after_apply = apply_response.json()
            local_session_after_apply = _load_local_session_file(
                root=root,
                project_id=project_id,
                session_id=session_id,
            )
            _assert_local_session_matches_api(
                local=local_session_after_apply,
                remote=session_after_apply,
            )
            _live_assert(
                int(session_after_apply["session_revision"])
                == int(session_before_run["session_revision"]) + 1,
                "caption_apply_revision_invalid",
            )
            before_captions = {
                str(item["segment_id"]): item.get("caption_text")
                for item in session_before_run["segments"]
            }
            after_captions = {
                str(item["segment_id"]): item.get("caption_text")
                for item in session_after_apply["segments"]
            }
            changed_segments = [
                segment
                for segment, text in after_captions.items()
                if before_captions.get(segment) != text
            ]
            _live_assert(
                changed_segments == [selected_segment_id]
                and after_captions[selected_segment_id]
                == recommended_caption,
                "caption_apply_scope_invalid",
            )

            manifest_response = client.get(
                f"{session_path}/playback-manifest"
            )
            _live_assert(
                manifest_response.status_code == 200
                and int(manifest_response.json()["session_revision"])
                == int(session_after_apply["session_revision"]),
                "playback_manifest_failed",
            )
            timeline_id = quote(
                str(session_after_apply.get("timeline_id") or ""),
                safe="",
            )
            readiness_response = client.get(
                f"{base}/review-approvals/timelines/{timeline_id}"
            )
            _live_assert(
                readiness_response.status_code == 200,
                "output_readiness_failed",
            )
            after_jobs_response = client.get(f"{base}/jobs")
            _live_assert(
                after_jobs_response.status_code == 200
                and not _output_jobs(
                    after_jobs_response.json().get("jobs", [])
                ),
                "output_job_created",
            )
            copied_asset_after = client.get(copied_asset_content_path)
            _live_assert(
                copied_asset_after.status_code == 200
                and sha256(copied_asset_after.content).hexdigest()
                == original_source_sha,
                "registered_source_media_changed",
            )

        _live_assert(
            sample.is_file()
            and copied_sample.is_file()
            and _sha256(sample) == original_source_sha
            and _sha256(copied_sample) == copied_source_sha,
            "source_media_changed",
        )
        return {
            "explicit_apply": True,
            "session_revision_delta": 1,
            "caption_changes": 1,
            "playback_manifest_checked": True,
            "output_readiness_checked": True,
            "output_jobs": 0,
            "source_sha_unchanged": True,
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--base-uri", default="http://127.0.0.1:8000")
    parser.add_argument("--project-id")
    parser.add_argument("--session-id")
    parser.add_argument("--disposable-project-root")
    parser.add_argument("--sample-asset-path")
    parser.add_argument("--timeout-sec", type=float, default=20)
    arguments = parser.parse_args()
    if arguments.live:
        try:
            result = run_live(
                base_uri=arguments.base_uri,
                project_id=str(arguments.project_id or ""),
                session_id=str(arguments.session_id or ""),
                disposable_project_root=Path(
                    arguments.disposable_project_root or ""
                ),
                sample_asset_path=Path(arguments.sample_asset_path or ""),
                timeout_seconds=arguments.timeout_sec,
            )
        except LiveSmokeBlocked as error:
            print(str(error), file=sys.stderr)
            return 1
        except Exception:
            print(
                "HERMES_YUJIN_CREATOR_LIVE_FAILED:runtime_unavailable",
                file=sys.stderr,
            )
            return 1
        fields = " ".join(
            f"{key}={str(value).lower() if isinstance(value, bool) else value}"
            for key, value in result.items()
        )
        print(f"HERMES_YUJIN_CREATOR_LIVE_PASS {fields}")
        return 0
    try:
        result = run_non_live()
    except Exception as error:
        print(str(error), file=sys.stderr)
        return 1
    fields = " ".join(
        f"{key}={str(value).lower() if isinstance(value, bool) else value}"
        for key, value in result.items()
    )
    print(f"{PASS_MARKER} {fields}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
