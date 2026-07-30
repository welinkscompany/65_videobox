from __future__ import annotations

import base64
import inspect
import json
import sqlite3
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from videobox_agent_gateway.context_capabilities import (
    YujinCapabilityClaims,
    YujinCapabilityIssuer,
)
from videobox_api.hermes_capabilities import (
    ExpectedCapability,
    HermesCapabilityError,
    HermesCapabilityVerifier,
)
from videobox_domain_models.director_proposals import (
    DirectorCandidate,
    DirectorProposal,
)
from videobox_storage.local_project_store import LocalProjectStore


NOW = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)
NOW_EPOCH = int(NOW.timestamp())
KEY_ID = "yujin-c3-test-2026-07"
PRIVATE_KEY_RAW = bytes(range(1, 33))
PRIVATE_KEY = Ed25519PrivateKey.from_private_bytes(PRIVATE_KEY_RAW)
PUBLIC_KEY_RAW = PRIVATE_KEY.public_key().public_bytes_raw()
EXPECTED_CLAIMS = {
    "schema_version",
    "iss",
    "sub",
    "aud",
    "capability_id",
    "project_id",
    "conversation_id",
    "run_id",
    "session_id",
    "session_revision",
    "asset_index_revision",
    "action",
    "iat",
    "nbf",
    "exp",
}


class _AuthorityIdentifierSubclass(str):
    pass


def _b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _decode_part(value: str) -> dict[str, Any]:
    decoded = json.loads(_b64url_decode(value))
    assert isinstance(decoded, dict)
    return decoded


def _sign(
    claims: Mapping[str, Any],
    *,
    header: Mapping[str, Any] | None = None,
    private_key: Ed25519PrivateKey = PRIVATE_KEY,
) -> str:
    encoded_header = _b64url_encode(
        json.dumps(
            dict(header or {"alg": "EdDSA", "kid": KEY_ID, "typ": "VBC"}),
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
    )
    encoded_claims = _b64url_encode(
        json.dumps(
            dict(claims),
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
    )
    signing_input = f"{encoded_header}.{encoded_claims}".encode("ascii")
    return f"{encoded_header}.{encoded_claims}.{_b64url_encode(private_key.sign(signing_input))}"


def _issuer(*, lifetime_seconds: int = 300) -> YujinCapabilityIssuer:
    capability_ids = iter(("cap-read-0001", "cap-publish-0001"))
    return YujinCapabilityIssuer(
        key_id=KEY_ID,
        private_key=PRIVATE_KEY_RAW,
        now=lambda: NOW,
        capability_id_factory=lambda: next(capability_ids),
        lifetime_seconds=lifetime_seconds,
    )


def _issue_read() -> str:
    return _issuer().issue_read_context(
        project_id="project-1",
        conversation_id="conversation-1",
        run_id="run-1",
        session_id="session-1",
        session_revision=3,
        asset_index_revision=7,
    )


def _verifier() -> HermesCapabilityVerifier:
    return HermesCapabilityVerifier(
        key_id=KEY_ID,
        public_key=PUBLIC_KEY_RAW,
        now=lambda: NOW,
    )


def _expected(*, action: str = "read_context") -> ExpectedCapability:
    return ExpectedCapability(
        capability_id="cap-read-0001",
        project_id="project-1",
        conversation_id="conversation-1",
        run_id="run-1",
        session_id="session-1",
        session_revision=3,
        asset_index_revision=7,
        action=action,
    )


def _capability_metadata(
    *,
    read_id: str = "cap-read-0001",
    publish_id: str = "cap-publish-0001",
) -> tuple[dict[str, Any], dict[str, Any]]:
    return (
        {
            "capability_id": read_id,
            "action": "read_context",
            "expires_at": NOW_EPOCH + 300,
        },
        {
            "capability_id": publish_id,
            "action": "publish_proposal",
            "expires_at": NOW_EPOCH + 300,
        },
    )


def _register_capabilities(
    store: LocalProjectStore,
    project_id: str,
    *,
    conversation_id: str = "conversation-1",
    run_id: str = "run-1",
    read_id: str = "cap-read-0001",
    publish_id: str = "cap-publish-0001",
) -> None:
    store.register_hermes_run_capabilities(
        project_id=project_id,
        conversation_id=conversation_id,
        run_id=run_id,
        session_id="session-1",
        session_revision=3,
        asset_index_revision=7,
        capabilities=_capability_metadata(
            read_id=read_id,
            publish_id=publish_id,
        ),
    )


def _terminal_capability_scope(
    store: LocalProjectStore,
    *,
    project_name: str,
) -> tuple[str, dict[str, Any], str, dict[str, Any], DirectorProposal]:
    project = store.bootstrap_project(project_name)
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id="timeline-1",
        session_payload={
            "segments": [
                {
                    "segment_id": "segment-1",
                    "start_sec": 0.0,
                    "end_sec": 3.0,
                    "caption_text": "장면",
                }
            ],
            "history": [],
        },
    )
    conversation_id = "conversation-terminal"
    store.create_director_conversation(
        project_id=project.project_id,
        session_id=session["session_id"],
        conversation_id=conversation_id,
    )
    durable = store.begin_director_hermes_run(
        project_id=project.project_id,
        session_id=session["session_id"],
        conversation_id=conversation_id,
        client_message_id="terminal-message",
        user_text="추천",
        expected_session_revision=session["session_revision"],
        expected_asset_index_revision=0,
    )
    issued = _issuer().issue_run_capabilities(
        project_id=project.project_id,
        conversation_id=conversation_id,
        run_id=durable["run_id"],
        session_id=session["session_id"],
        session_revision=session["session_revision"],
        asset_index_revision=0,
    )
    store.register_hermes_run_capabilities(
        project_id=project.project_id,
        conversation_id=conversation_id,
        run_id=durable["run_id"],
        session_id=session["session_id"],
        session_revision=session["session_revision"],
        asset_index_revision=0,
        capabilities=(
            issued.read_context.metadata.as_dict(),
            issued.publish_proposal.metadata.as_dict(),
        ),
    )
    expected_payload = store.get_expected_hermes_capability(
        project_id=project.project_id,
        conversation_id=conversation_id,
        run_id=durable["run_id"],
        action="publish_proposal",
    )
    assert expected_payload is not None
    verified = _verifier().verify(
        issued.publish_proposal.token,
        expected=ExpectedCapability(
            capability_id=expected_payload["capability_id"],
            project_id=expected_payload["project_id"],
            conversation_id=expected_payload["conversation_id"],
            run_id=expected_payload["run_id"],
            session_id=expected_payload["session_id"],
            session_revision=expected_payload["session_revision"],
            asset_index_revision=expected_payload[
                "asset_index_revision"
            ],
            action=expected_payload["action"],
        ),
    )
    candidate = DirectorCandidate(
        candidate_id="candidate-terminal",
        visible_reference_code="P00-C01",
        media_type="broll",
        asset_id="candidate-only-asset",
        library_asset_id=None,
        reason_chips=("후보",),
        scores={},
        availability="candidate_only",
        review_status="pending",
        preview_uri=None,
        controls={},
        expected_content_sha256=None,
        media_revision="candidate-r1",
        canonical_metadata={},
    )
    proposal = DirectorProposal(
        proposal_id="proposal-terminal",
        revision_code="P00",
        revision=0,
        base_session_revision=session["session_revision"],
        asset_index_revision=0,
        source_session_id=session["session_id"],
        target_segment_ids=("segment-1",),
        source_script_segment_ids=("segment-1",),
        status="candidate_only",
        diff={"proposal_mode": "candidate_only"},
        expires_at=None,
        candidates=(candidate,),
    )
    return (
        project.project_id,
        session,
        conversation_id,
        {
            "durable": durable,
            "verified_publish_capability": asdict(verified),
        },
        proposal,
    )


def _valid_claims() -> dict[str, Any]:
    return _decode_part(_issue_read().split(".")[1])


def _assert_reason(token: str, reason: str, *, expected: ExpectedCapability | None = None) -> None:
    with pytest.raises(HermesCapabilityError, match=f"^{reason}$"):
        _verifier().verify(token, expected=expected or _expected())


def test_issue_has_exact_eddsa_header_claims_and_one_action() -> None:
    issuer = _issuer()
    read_token = issuer.issue_read_context(
        project_id="project-1",
        conversation_id="conversation-1",
        run_id="run-1",
        session_id="session-1",
        session_revision=3,
        asset_index_revision=7,
    )
    publish_token = issuer.issue_publish_proposal(
        project_id="project-1",
        conversation_id="conversation-1",
        run_id="run-1",
        session_id="session-1",
        session_revision=3,
        asset_index_revision=7,
    )

    read_parts = read_token.split(".")
    assert len(read_parts) == 3
    assert _decode_part(read_parts[0]) == {"alg": "EdDSA", "kid": KEY_ID, "typ": "VBC"}
    read_claims = _decode_part(read_parts[1])
    assert set(read_claims) == EXPECTED_CLAIMS
    assert read_claims == {
        "schema_version": "videobox.yujin-capability.v1",
        "iss": "videobox-agent-gateway",
        "sub": "yujin-video-director",
        "aud": "videobox-api",
        "capability_id": "cap-read-0001",
        "project_id": "project-1",
        "conversation_id": "conversation-1",
        "run_id": "run-1",
        "session_id": "session-1",
        "session_revision": 3,
        "asset_index_revision": 7,
        "action": "read_context",
        "iat": NOW_EPOCH,
        "nbf": NOW_EPOCH,
        "exp": NOW_EPOCH + 300,
    }
    assert _decode_part(publish_token.split(".")[1])["action"] == "publish_proposal"

    verified = _verifier().verify(read_token, expected=_expected())
    assert verified.capability_id == "cap-read-0001"
    assert verified.action == "read_context"
    assert verified.expires_at == NOW_EPOCH + 300


@pytest.mark.parametrize("key_length", [0, 31, 33])
def test_issuer_rejects_non_raw_32_byte_private_keys(key_length: int) -> None:
    with pytest.raises(ValueError, match="hermes_capability_issuer_invalid"):
        YujinCapabilityIssuer(
            key_id=KEY_ID,
            private_key=b"x" * key_length,
            now=lambda: NOW,
            capability_id_factory=lambda: "capability-1",
        )


@pytest.mark.parametrize("key_length", [0, 31, 33])
def test_verifier_rejects_non_raw_32_byte_public_keys(key_length: int) -> None:
    with pytest.raises(ValueError, match="hermes_capability_verifier_invalid"):
        HermesCapabilityVerifier(
            key_id=KEY_ID,
            public_key=b"x" * key_length,
            now=lambda: NOW,
        )


def test_api_verifier_exposes_only_public_key_api_and_defers_runtime_key_ownership() -> None:
    parameters = inspect.signature(HermesCapabilityVerifier).parameters
    assert "public_key" in parameters
    assert "private_key" not in parameters
    with pytest.raises(TypeError):
        HermesCapabilityVerifier(  # type: ignore[call-arg]
            key_id=KEY_ID,
            private_key=PRIVATE_KEY_RAW,
            now=lambda: NOW,
        )

    seed_as_public_key = HermesCapabilityVerifier(
        key_id=KEY_ID,
        public_key=PRIVATE_KEY_RAW,
        now=lambda: NOW,
    )
    with pytest.raises(
        HermesCapabilityError,
        match="^hermes_capability_signature_invalid$",
    ):
        seed_as_public_key.verify(_issue_read(), expected=_expected())

    plan = Path(
        "docs/superpowers/plans/"
        "2026-07-30-videobox-hermes-yujin-c3-capability-lifecycle.md"
    ).read_text(encoding="utf-8")
    assert "API verifier exposes no `private_key` parameter" in plan
    assert "runtime key ownership is verified in Task 7" in plan


def test_lifetime_is_capped_at_300_seconds_for_issue_and_verify() -> None:
    assert _valid_claims()["exp"] - _valid_claims()["iat"] == 300
    with pytest.raises(ValueError, match="hermes_capability_lifetime_invalid"):
        _issuer(lifetime_seconds=301)

    claims = _valid_claims()
    claims["exp"] = claims["iat"] + 301
    _assert_reason(_sign(claims), "hermes_capability_malformed")


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        (lambda claims: claims.pop("run_id"), "hermes_capability_malformed"),
        (lambda claims: claims.update({"unexpected": "value"}), "hermes_capability_malformed"),
        (lambda claims: claims.update({"session_revision": True}), "hermes_capability_malformed"),
        (lambda claims: claims.update({"asset_index_revision": -1}), "hermes_capability_malformed"),
        (lambda claims: claims.update({"schema_version": "unknown"}), "hermes_capability_scope_forbidden"),
        (lambda claims: claims.update({"iss": "other-issuer"}), "hermes_capability_scope_forbidden"),
        (lambda claims: claims.update({"sub": "other-subject"}), "hermes_capability_scope_forbidden"),
        (lambda claims: claims.update({"aud": "other-audience"}), "hermes_capability_scope_forbidden"),
        (lambda claims: claims.update({"conversation_id": "other"}), "hermes_capability_scope_forbidden"),
    ],
)
def test_unknown_missing_wrong_type_and_wrong_scope_claims_fail_closed(
    mutation: Any,
    reason: str,
) -> None:
    claims = _valid_claims()
    mutation(claims)
    _assert_reason(_sign(claims), reason)


def test_wrong_algorithm_key_and_signature_fail_closed() -> None:
    claims = _valid_claims()
    _assert_reason(
        _sign(claims, header={"alg": "HS256", "kid": KEY_ID, "typ": "VBC"}),
        "hermes_capability_malformed",
    )
    _assert_reason(
        _sign(claims, header={"alg": "EdDSA", "kid": "unknown", "typ": "VBC"}),
        "hermes_capability_key_unknown",
    )
    _assert_reason(
        _sign(claims, private_key=Ed25519PrivateKey.generate()),
        "hermes_capability_signature_invalid",
    )


def test_noncanonical_signature_base64url_alias_is_malformed() -> None:
    header, claims, signature = _issue_read().split(".")
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
    canonical_index = alphabet.index(signature[-1])
    assert canonical_index % 16 == 0
    alias = f"{signature[:-1]}{alphabet[canonical_index + 1]}"
    assert alias != signature
    assert _b64url_decode(alias) == _b64url_decode(signature)

    _assert_reason(
        f"{header}.{claims}.{alias}",
        "hermes_capability_malformed",
    )


def test_duplicate_or_noncanonical_claim_json_is_malformed() -> None:
    encoded_header, encoded_claims, _signature = _issue_read().split(".")
    canonical_claims = _b64url_decode(encoded_claims).decode("ascii")
    malformed_claims = (
        canonical_claims.replace(
            '"run_id":"run-1"',
            '"run_id":"run-1","run_id":"run-1"',
            1,
        ),
        canonical_claims.replace("{", "{ ", 1),
    )

    for raw_claims in malformed_claims:
        malformed_payload = _b64url_encode(raw_claims.encode("ascii"))
        signing_input = f"{encoded_header}.{malformed_payload}".encode("ascii")
        token = (
            f"{encoded_header}.{malformed_payload}."
            f"{_b64url_encode(PRIVATE_KEY.sign(signing_input))}"
        )
        _assert_reason(token, "hermes_capability_malformed")


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("capability_id", " ", "hermes_capability_expected_invalid"),
        ("project_id", "", "hermes_capability_expected_invalid"),
        ("conversation_id", "\t", "hermes_capability_expected_invalid"),
        ("run_id", " run-1", "hermes_capability_expected_invalid"),
        ("session_id", "session-1 ", "hermes_capability_expected_invalid"),
        ("action", "apply", "hermes_capability_action_forbidden"),
        ("session_revision", True, "hermes_capability_expected_invalid"),
        ("session_revision", 3.0, "hermes_capability_expected_invalid"),
        ("session_revision", 0, "hermes_capability_expected_invalid"),
        ("asset_index_revision", False, "hermes_capability_expected_invalid"),
        ("asset_index_revision", 7.0, "hermes_capability_expected_invalid"),
        ("asset_index_revision", -1, "hermes_capability_expected_invalid"),
    ],
)
def test_expected_capability_rejects_invalid_runtime_scope(
    field: str,
    value: object,
    reason: str,
) -> None:
    with pytest.raises(ValueError, match=f"^{reason}$"):
        replace(_expected(), **{field: value})


def test_future_and_expired_tokens_fail_closed() -> None:
    future = _valid_claims()
    future["iat"] = NOW_EPOCH + 1
    future["nbf"] = NOW_EPOCH + 1
    future["exp"] = NOW_EPOCH + 60
    _assert_reason(_sign(future), "hermes_capability_not_yet_valid")

    expired = _valid_claims()
    expired["iat"] = NOW_EPOCH - 301
    expired["nbf"] = NOW_EPOCH - 301
    expired["exp"] = NOW_EPOCH
    _assert_reason(_sign(expired), "hermes_capability_expired")


@pytest.mark.parametrize(
    "action",
    ["apply", "render", "export", "database", "filesystem", "raw_media"],
)
def test_forbidden_actions_cannot_be_issued_or_verified(action: str) -> None:
    with pytest.raises(ValueError, match="hermes_capability_action_forbidden"):
        YujinCapabilityClaims(
            capability_id="cap-forbidden",
            project_id="project-1",
            conversation_id="conversation-1",
            run_id="run-1",
            session_id="session-1",
            session_revision=3,
            asset_index_revision=7,
            action=action,
            iat=NOW_EPOCH,
            nbf=NOW_EPOCH,
            exp=NOW_EPOCH + 300,
        )
    assert not hasattr(_issuer(), f"issue_{action}")

    claims = _valid_claims()
    claims["action"] = action
    _assert_reason(_sign(claims), "hermes_capability_action_forbidden")


def test_sqlite_hermes_capability_registers_exactly_two_scoped_issued_rows(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path, now=lambda: NOW)
    project = store.bootstrap_project("C3 registration")

    _register_capabilities(store, project.project_id)

    expected = store.get_expected_hermes_capability(
        project_id=project.project_id,
        conversation_id="conversation-1",
        run_id="run-1",
        action="read_context",
    )
    assert expected == {
        "capability_id": "cap-read-0001",
        "project_id": project.project_id,
        "conversation_id": "conversation-1",
        "run_id": "run-1",
        "session_id": "session-1",
        "session_revision": 3,
        "asset_index_revision": 7,
        "action": "read_context",
        "state": "issued",
        "expires_at": NOW_EPOCH + 300,
    }
    with sqlite3.connect(store.database_path(project.project_id)) as connection:
        rows = connection.execute(
            """
            SELECT lifecycle_version, jti, conversation_id, run_id, session_id,
                   session_revision, asset_index_revision, action, state,
                   expires_at, recorded_at, updated_at
            FROM hermes_capability_ledger
            ORDER BY action
            """
        ).fetchall()
    assert len(rows) == 2
    assert {row[0] for row in rows} == {"videobox.yujin-capability.v1"}
    assert {row[7] for row in rows} == {"read_context", "publish_proposal"}
    assert {row[8] for row in rows} == {"issued"}
    assert all(row[10] == row[11] for row in rows)


def test_sqlite_hermes_capability_registration_is_atomic_on_duplicate_or_conflict(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path, now=lambda: NOW)
    project = store.bootstrap_project("C3 atomic registration")

    duplicate = (
        _capability_metadata()[0],
        {
            "capability_id": "cap-read-0001",
            "action": "publish_proposal",
            "expires_at": NOW_EPOCH + 300,
        },
    )
    with pytest.raises(ValueError, match="^hermes_capability_registration_invalid$"):
        store.register_hermes_run_capabilities(
            project_id=project.project_id,
            conversation_id="conversation-1",
            run_id="run-invalid",
            session_id="session-1",
            session_revision=3,
            asset_index_revision=7,
            capabilities=duplicate,
        )

    _register_capabilities(
        store,
        project.project_id,
        conversation_id="conversation-existing",
        run_id="run-existing",
        read_id="cap-existing-read",
        publish_id="cap-conflict",
    )
    with pytest.raises(ValueError, match="^hermes_capability_registration_conflict$"):
        _register_capabilities(
            store,
            project.project_id,
            conversation_id="conversation-new",
            run_id="run-new",
            read_id="cap-new-read",
            publish_id="cap-conflict",
        )

    with sqlite3.connect(store.database_path(project.project_id)) as connection:
        identifiers = {
            row[0]
            for row in connection.execute(
                "SELECT jti FROM hermes_capability_ledger"
            ).fetchall()
        }
    assert identifiers == {"cap-existing-read", "cap-conflict"}
    assert "cap-new-read" not in identifiers


def test_sqlite_hermes_capability_same_scope_fresh_ids_conflict_without_partial_rows(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path, now=lambda: NOW)
    project = store.bootstrap_project("C3 same-scope registration conflict")
    _register_capabilities(store, project.project_id)

    with pytest.raises(
        ValueError,
        match="^hermes_capability_registration_conflict$",
    ):
        _register_capabilities(
            store,
            project.project_id,
            read_id="cap-read-fresh",
            publish_id="cap-publish-fresh",
        )

    with sqlite3.connect(store.database_path(project.project_id)) as connection:
        rows = connection.execute(
            """
            SELECT jti, action FROM hermes_capability_ledger
            WHERE lifecycle_version = 'videobox.yujin-capability.v1'
            ORDER BY action
            """
        ).fetchall()
        registered_audits = connection.execute(
            """
            SELECT COUNT(*) FROM hermes_capability_audit
            WHERE reason = 'hermes_capability_registered'
            """
        ).fetchone()[0]
        index = connection.execute(
            """
            SELECT sql FROM sqlite_master
            WHERE type = 'index'
              AND name = 'uq_hermes_capability_v1_scope_action'
            """
        ).fetchone()
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO hermes_capability_ledger (
                    project_id, jti, lifecycle_version, conversation_id,
                    run_id, session_id, session_revision,
                    asset_index_revision, action, state, expires_at,
                    recorded_at, updated_at
                )
                SELECT project_id, 'direct-duplicate',
                       lifecycle_version, conversation_id, run_id, session_id,
                       session_revision, asset_index_revision, action, 'issued',
                       expires_at, recorded_at, updated_at
                FROM hermes_capability_ledger
                WHERE action = 'read_context'
                """
            )
    assert set(rows) == {
        ("cap-read-0001", "read_context"),
        ("cap-publish-0001", "publish_proposal"),
    }
    assert registered_audits == 2
    assert index is not None
    assert "CREATE UNIQUE INDEX" in index[0]
    assert "WHERE lifecycle_version" in index[0]


@pytest.mark.parametrize(
    "capability_id",
    [
        "Bearer capability-secret",
        "prompt\ninjection",
        "token=capability-secret",
        "control\x00character",
        "x" * 256,
        _AuthorityIdentifierSubclass("str-subclass"),
    ],
    ids=[
        "bearer",
        "newline",
        "token-equals",
        "control",
        "overlength",
        "str-subclass",
    ],
)
def test_sqlite_hermes_capability_registration_rejects_unsafe_capability_ids_without_mutation(
    tmp_path: Path,
    capability_id: object,
) -> None:
    store = LocalProjectStore(tmp_path, now=lambda: NOW)
    project = store.bootstrap_project("C3 unsafe capability ID")

    with pytest.raises(
        ValueError,
        match="^hermes_capability_registration_invalid$",
    ):
        store.register_hermes_run_capabilities(
            project_id=project.project_id,
            conversation_id="conversation-1",
            run_id="run-1",
            session_id="session-1",
            session_revision=3,
            asset_index_revision=7,
            capabilities=(
                {
                    "capability_id": capability_id,
                    "action": "read_context",
                    "expires_at": NOW_EPOCH + 300,
                },
                {
                    "capability_id": "cap-publish-safe",
                    "action": "publish_proposal",
                    "expires_at": NOW_EPOCH + 300,
                },
            ),
        )

    with sqlite3.connect(store.database_path(project.project_id)) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM hermes_capability_ledger"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM hermes_capability_audit"
        ).fetchone()[0] == 0


def test_sqlite_hermes_capability_consume_requires_exact_registered_scope_and_never_inserts(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path, now=lambda: NOW)
    project = store.bootstrap_project("C3 exact consume")
    _register_capabilities(store, project.project_id)

    wrong_scope = store.consume_registered_hermes_capability(
        project_id=project.project_id,
        capability_id="cap-read-0001",
        conversation_id="conversation-1",
        run_id="run-1",
        session_id="session-1",
        session_revision=4,
        asset_index_revision=7,
        action="read_context",
    )
    missing = store.consume_registered_hermes_capability(
        project_id=project.project_id,
        capability_id="cap-missing",
        conversation_id="conversation-1",
        run_id="run-1",
        session_id="session-1",
        session_revision=3,
        asset_index_revision=7,
        action="read_context",
    )
    accepted = store.consume_registered_hermes_capability(
        project_id=project.project_id,
        capability_id="cap-read-0001",
        conversation_id="conversation-1",
        run_id="run-1",
        session_id="session-1",
        session_revision=3,
        asset_index_revision=7,
        action="read_context",
    )
    replay = store.consume_registered_hermes_capability(
        project_id=project.project_id,
        capability_id="cap-read-0001",
        conversation_id="conversation-1",
        run_id="run-1",
        session_id="session-1",
        session_revision=3,
        asset_index_revision=7,
        action="read_context",
    )

    assert wrong_scope == "hermes_capability_scope_forbidden"
    assert missing == "hermes_capability_scope_forbidden"
    assert accepted == "accepted"
    assert replay == "hermes_capability_replayed"
    with sqlite3.connect(store.database_path(project.project_id)) as connection:
        rows = connection.execute(
            "SELECT jti, state FROM hermes_capability_ledger ORDER BY jti"
        ).fetchall()
    assert rows == [
        ("cap-publish-0001", "issued"),
        ("cap-read-0001", "consumed"),
    ]


def test_sqlite_hermes_capability_expired_issued_consume_denies_without_state_change(
    tmp_path: Path,
) -> None:
    clock = [NOW]
    store = LocalProjectStore(tmp_path, now=lambda: clock[0])
    project = store.bootstrap_project("C3 expired issued consume")
    _register_capabilities(store, project.project_id)
    clock[0] = datetime.fromtimestamp(NOW_EPOCH + 301, tz=UTC)

    result = store.consume_registered_hermes_capability(
        project_id=project.project_id,
        capability_id="cap-read-0001",
        conversation_id="conversation-1",
        run_id="run-1",
        session_id="session-1",
        session_revision=3,
        asset_index_revision=7,
        action="read_context",
    )

    assert result == "hermes_capability_expired"
    with sqlite3.connect(store.database_path(project.project_id)) as connection:
        state = connection.execute(
            """
            SELECT state FROM hermes_capability_ledger
            WHERE project_id = ? AND jti = 'cap-read-0001'
            """,
            (project.project_id,),
        ).fetchone()[0]
        denial = connection.execute(
            """
            SELECT capability_id, project_id, conversation_id, run_id, action,
                   outcome, reason
            FROM hermes_capability_audit
            WHERE capability_id = 'cap-read-0001'
              AND reason = 'hermes_capability_expired'
            """
        ).fetchone()
    assert state == "issued"
    assert denial == (
        "cap-read-0001",
        project.project_id,
        "conversation-1",
        "run-1",
        "read_context",
        "denied",
        "hermes_capability_expired",
    )


def test_sqlite_hermes_capability_concurrent_consume_has_one_winner(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path, now=lambda: NOW)
    project = store.bootstrap_project("C3 concurrent consume")
    _register_capabilities(store, project.project_id)
    payload = {
        "project_id": project.project_id,
        "capability_id": "cap-read-0001",
        "conversation_id": "conversation-1",
        "run_id": "run-1",
        "session_id": "session-1",
        "session_revision": 3,
        "asset_index_revision": 7,
        "action": "read_context",
    }

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda _index: store.consume_registered_hermes_capability(
                    **payload
                ),
                range(2),
            )
        )

    assert sorted(results) == ["accepted", "hermes_capability_replayed"]


def test_sqlite_hermes_capability_revoke_is_issued_only_and_idempotent(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path, now=lambda: NOW)
    project = store.bootstrap_project("C3 revoke")
    _register_capabilities(store, project.project_id)
    assert store.consume_registered_hermes_capability(
        project_id=project.project_id,
        capability_id="cap-read-0001",
        conversation_id="conversation-1",
        run_id="run-1",
        session_id="session-1",
        session_revision=3,
        asset_index_revision=7,
        action="read_context",
    ) == "accepted"

    first = store.revoke_issued_hermes_capabilities(
        project_id=project.project_id,
        conversation_id="conversation-1",
        run_id="run-1",
        reason="hermes_capability_revoked",
    )
    second = store.revoke_issued_hermes_capabilities(
        project_id=project.project_id,
        conversation_id="conversation-1",
        run_id="run-1",
        reason="hermes_capability_revoked",
    )

    assert (first, second) == (1, 0)
    with sqlite3.connect(store.database_path(project.project_id)) as connection:
        states = dict(
            connection.execute(
                "SELECT jti, state FROM hermes_capability_ledger"
            ).fetchall()
        )
    assert states == {
        "cap-read-0001": "consumed",
        "cap-publish-0001": "revoked",
    }


def test_sqlite_hermes_capability_audit_is_exact_redacted_and_trusted(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path, now=lambda: NOW)
    project = store.bootstrap_project("C3 audit")
    _register_capabilities(store, project.project_id)
    parameters = inspect.signature(
        store.record_hermes_capability_denial
    ).parameters
    assert {"capability_id", "token", "body", "secret"}.isdisjoint(parameters)

    trusted = store.record_hermes_capability_denial(
        project_id=project.project_id,
        conversation_id="conversation-1",
        run_id="run-1",
        action="read_context",
        reason="hermes_capability_signature_invalid",
    )
    unknown = store.record_hermes_capability_denial(
        project_id=project.project_id,
        conversation_id="conversation-unknown",
        run_id="run-unknown",
        action="read_context",
        reason="hermes_capability_signature_invalid",
    )

    expected_fields = {
        "audit_event_id",
        "capability_id",
        "project_id",
        "conversation_id",
        "run_id",
        "action",
        "outcome",
        "reason",
        "occurred_at",
    }
    assert set(trusted) == expected_fields
    assert trusted["capability_id"] == "cap-read-0001"
    assert unknown["capability_id"] is None
    with sqlite3.connect(store.database_path(project.project_id)) as connection:
        columns = {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(hermes_capability_audit)"
            ).fetchall()
        }
        audit_rows = [
            dict(zip(sorted(expected_fields), row, strict=True))
            for row in connection.execute(
                f"SELECT {', '.join(sorted(expected_fields))} "
                "FROM hermes_capability_audit"
            ).fetchall()
        ]
    assert columns == expected_fields
    serialized = json.dumps(audit_rows, sort_keys=True)
    for forbidden in (
        _issue_read(),
        _b64url_encode(PRIVATE_KEY_RAW),
        "prompt-secret-canary",
        "proposal-secret-canary",
        "assistant-secret-canary",
        "provider-body-secret-canary",
        "storage-uri-secret-canary",
        "raw-media-secret-canary",
        "credential-secret-canary",
    ):
        assert forbidden not in serialized


@pytest.mark.parametrize("operation", ["denial", "revoke"])
def test_sqlite_hermes_capability_audit_rejects_untrusted_reason_text(
    tmp_path: Path,
    operation: str,
) -> None:
    store = LocalProjectStore(tmp_path, now=lambda: NOW)
    project = store.bootstrap_project("C3 audit reason allowlist")
    _register_capabilities(store, project.project_id)

    with pytest.raises(
        ValueError,
        match="^hermes_capability_audit_reason_invalid$",
    ):
        if operation == "denial":
            store.record_hermes_capability_denial(
                project_id=project.project_id,
                conversation_id="conversation-1",
                run_id="run-1",
                action="read_context",
                reason=_issue_read(),
            )
        else:
            store.revoke_issued_hermes_capabilities(
                project_id=project.project_id,
                conversation_id="conversation-1",
                run_id="run-1",
                reason=_issue_read(),
            )

    with sqlite3.connect(store.database_path(project.project_id)) as connection:
        reasons = {
            row[0]
            for row in connection.execute(
                "SELECT reason FROM hermes_capability_audit"
            ).fetchall()
        }
    assert _issue_read() not in reasons


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("project_id", "Bearer project-secret", "hermes_capability_expected_invalid"),
        ("conversation_id", "prompt\ninjection", "hermes_capability_expected_invalid"),
        ("run_id", "token=run-secret", "hermes_capability_expected_invalid"),
        ("action", "read_context\x00", "hermes_capability_action_forbidden"),
        ("conversation_id", "x" * 256, "hermes_capability_expected_invalid"),
        (
            "run_id",
            _AuthorityIdentifierSubclass("run-subclass"),
            "hermes_capability_expected_invalid",
        ),
        (
            "action",
            _AuthorityIdentifierSubclass("read_context"),
            "hermes_capability_action_forbidden",
        ),
    ],
)
def test_sqlite_hermes_capability_denial_rejects_unsafe_trusted_scope_without_mutation(
    tmp_path: Path,
    field: str,
    value: object,
    reason: str,
) -> None:
    store = LocalProjectStore(tmp_path, now=lambda: NOW)
    project = store.bootstrap_project("C3 unsafe denial scope")
    _register_capabilities(store, project.project_id)
    payload: dict[str, object] = {
        "project_id": project.project_id,
        "conversation_id": "conversation-1",
        "run_id": "run-1",
        "action": "read_context",
        "reason": "hermes_capability_signature_invalid",
    }
    payload[field] = value

    with pytest.raises(ValueError, match=f"^{reason}$"):
        store.record_hermes_capability_denial(**payload)

    with sqlite3.connect(store.database_path(project.project_id)) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM hermes_capability_ledger"
        ).fetchone()[0] == 2
        assert connection.execute(
            "SELECT COUNT(*) FROM hermes_capability_audit"
        ).fetchone()[0] == 2


def test_sqlite_hermes_capability_migrates_pre_c3_rows_as_non_authorizing_tombstones(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path, now=lambda: NOW)
    project = store.bootstrap_project("C3 legacy migration")
    with sqlite3.connect(store.database_path(project.project_id)) as connection:
        connection.execute("DROP TABLE hermes_capability_audit")
        connection.execute("DROP TABLE hermes_capability_ledger")
        connection.execute(
            """
            CREATE TABLE hermes_capability_ledger (
                project_id TEXT NOT NULL,
                jti TEXT NOT NULL,
                state TEXT NOT NULL,
                expires_at INTEGER NOT NULL,
                recorded_at TEXT NOT NULL,
                PRIMARY KEY (project_id, jti)
            )
            """
        )
        connection.execute(
            """
            INSERT INTO hermes_capability_ledger (
                project_id, jti, state, expires_at, recorded_at
            ) VALUES (?, 'legacy-jti', 'consumed', ?, ?)
            """,
            (project.project_id, NOW_EPOCH + 300, NOW.isoformat()),
        )
        connection.commit()

    connection = store._connection(project.project_id)
    connection.close()
    with sqlite3.connect(store.database_path(project.project_id)) as connection:
        connection.row_factory = sqlite3.Row
        legacy = dict(
            connection.execute(
                "SELECT * FROM hermes_capability_ledger WHERE jti = 'legacy-jti'"
            ).fetchone()
        )
        audit_count = connection.execute(
            "SELECT COUNT(*) FROM hermes_capability_audit"
        ).fetchone()[0]
    assert legacy["lifecycle_version"] == "legacy_retired"
    assert legacy["state"] == "consumed"
    assert all(
        legacy[field] is None
        for field in (
            "conversation_id",
            "run_id",
            "session_id",
            "session_revision",
            "asset_index_revision",
            "action",
        )
    )
    assert legacy["updated_at"] == legacy["recorded_at"]
    assert audit_count == 0
    assert store.get_expected_hermes_capability(
        project_id=project.project_id,
        conversation_id="conversation-1",
        run_id="run-1",
        action="read_context",
    ) is None
    assert store.consume_registered_hermes_capability(
        project_id=project.project_id,
        capability_id="legacy-jti",
        conversation_id="conversation-1",
        run_id="run-1",
        session_id="session-1",
        session_revision=3,
        asset_index_revision=7,
        action="read_context",
    ) == "hermes_capability_scope_forbidden"


def test_sqlite_publish_consume_commits_with_proposal_message_and_terminal(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path, now=lambda: NOW)
    (
        project_id,
        session,
        conversation_id,
        authority,
        proposal,
    ) = _terminal_capability_scope(
        store,
        project_name="C3 atomic publish terminal",
    )
    durable = authority["durable"]

    assert store.complete_director_hermes_run(
        project_id=project_id,
        run_id=durable["run_id"],
        owner_token=durable["owner_token"],
        status="completed",
        assistant_text="후보를 준비했습니다.",
        retryable=False,
        proposal=proposal,
        verified_publish_capability=authority[
            "verified_publish_capability"
        ],
    )

    with sqlite3.connect(store.database_path(project_id)) as connection:
        publish_state = connection.execute(
            """
            SELECT state FROM hermes_capability_ledger
            WHERE project_id = ? AND action = 'publish_proposal'
            """,
            (project_id,),
        ).fetchone()[0]
        accepted_audits = connection.execute(
            """
            SELECT COUNT(*) FROM hermes_capability_audit
            WHERE action = 'publish_proposal'
              AND outcome = 'accepted'
              AND reason = 'hermes_capability_consumed'
            """,
        ).fetchone()[0]
    assert publish_state == "consumed"
    assert accepted_audits == 1
    assert store.get_director_proposal(
        project_id,
        proposal.proposal_id,
    ).status == "candidate_only"
    messages = store.list_director_messages(
        project_id=project_id,
        conversation_id=conversation_id,
    )
    assert messages[-1]["proposal_id"] == proposal.proposal_id
    events = store.list_director_hermes_run_events(
        project_id=project_id,
        conversation_id=conversation_id,
        run_id=durable["run_id"],
    )
    assert [event["event_type"] for event in events].count(
        "run_completed"
    ) == 1
    unchanged = store.get_editing_session(
        project_id=project_id,
        session_id=session["session_id"],
    )
    assert unchanged["session_revision"] == session["session_revision"]
    assert unchanged["history"] == []


def test_sqlite_proposal_without_verified_publish_authority_mutates_nothing(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path, now=lambda: NOW)
    (
        project_id,
        _session,
        conversation_id,
        authority,
        proposal,
    ) = _terminal_capability_scope(
        store,
        project_name="C3 missing publish authority",
    )
    durable = authority["durable"]

    result = store.complete_director_hermes_run(
        project_id=project_id,
        run_id=durable["run_id"],
        owner_token=durable["owner_token"],
        status="completed",
        assistant_text="권한 없는 후보",
        retryable=False,
        proposal=proposal,
    )

    assert result == "publish_capability_denied"
    assert store.get_director_hermes_run(
        project_id=project_id,
        run_id=durable["run_id"],
    )["status"] == "pending"
    assert store.list_director_proposals(project_id) == []
    assert [
        message["role"]
        for message in store.list_director_messages(
            project_id=project_id,
            conversation_id=conversation_id,
        )
    ] == ["user"]


def test_sqlite_completed_without_proposal_revokes_unused_publish(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path, now=lambda: NOW)
    (
        project_id,
        _session,
        _conversation_id,
        authority,
        _proposal,
    ) = _terminal_capability_scope(
        store,
        project_name="C3 no proposal terminal",
    )
    durable = authority["durable"]

    assert store.complete_director_hermes_run(
        project_id=project_id,
        run_id=durable["run_id"],
        owner_token=durable["owner_token"],
        status="completed",
        assistant_text="제안 없이 답변합니다.",
        retryable=False,
        proposal=None,
    )

    with sqlite3.connect(store.database_path(project_id)) as connection:
        publish = connection.execute(
            """
            SELECT state FROM hermes_capability_ledger
            WHERE project_id = ? AND action = 'publish_proposal'
            """,
            (project_id,),
        ).fetchone()[0]
    assert publish == "revoked"


@pytest.mark.parametrize("race", ["session_revision", "asset_index"])
def test_sqlite_publish_proposal_current_truth_failure_mutates_nothing(
    tmp_path: Path,
    race: str,
) -> None:
    store = LocalProjectStore(tmp_path, now=lambda: NOW)
    (
        project_id,
        session,
        conversation_id,
        authority,
        proposal,
    ) = _terminal_capability_scope(
        store,
        project_name=f"C3 publish current truth {race}",
    )
    durable = authority["durable"]
    if race == "session_revision":
        store.update_editing_session(
            project_id=project_id,
            session_id=session["session_id"],
            expected_revision=session["session_revision"],
            session_payload=session,
        )
    else:
        store.bump_asset_index_revision(project_id)

    result = store.complete_director_hermes_run(
        project_id=project_id,
        run_id=durable["run_id"],
        owner_token=durable["owner_token"],
        status="completed",
        assistant_text="오래된 후보",
        retryable=False,
        proposal=proposal,
        verified_publish_capability=authority[
            "verified_publish_capability"
        ],
    )

    assert result == "publish_capability_denied"
    assert store.get_director_hermes_run(
        project_id=project_id,
        run_id=durable["run_id"],
    )["status"] == "pending"
    assert store.list_director_proposals(project_id) == []
    assert [
        item["role"]
        for item in store.list_director_messages(
            project_id=project_id,
            conversation_id=conversation_id,
        )
    ] == ["user"]
    with sqlite3.connect(store.database_path(project_id)) as connection:
        state = connection.execute(
            """
            SELECT state FROM hermes_capability_ledger
            WHERE action = 'publish_proposal'
            """
        ).fetchone()[0]
        denial = connection.execute(
            """
            SELECT reason FROM hermes_capability_audit
            WHERE action = 'publish_proposal' AND outcome = 'denied'
            """
        ).fetchone()[0]
    assert state == "issued"
    assert denial == "hermes_capability_scope_forbidden"


def test_sqlite_publish_proposal_transaction_fault_rolls_back_every_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = LocalProjectStore(tmp_path, now=lambda: NOW)
    (
        project_id,
        _session,
        conversation_id,
        authority,
        proposal,
    ) = _terminal_capability_scope(
        store,
        project_name="C3 publish transaction rollback",
    )
    durable = authority["durable"]
    original_append = store._append_hermes_capability_audit

    def fail_after_accepted_audit(connection, **kwargs):
        event = original_append(connection, **kwargs)
        if kwargs["reason"] == "hermes_capability_consumed":
            raise OSError("publish audit fault")
        return event

    monkeypatch.setattr(
        store,
        "_append_hermes_capability_audit",
        fail_after_accepted_audit,
    )

    with pytest.raises(OSError, match="publish audit fault"):
        store.complete_director_hermes_run(
            project_id=project_id,
            run_id=durable["run_id"],
            owner_token=durable["owner_token"],
            status="completed",
            assistant_text="원자적 후보",
            retryable=False,
            proposal=proposal,
            verified_publish_capability=authority[
                "verified_publish_capability"
            ],
        )

    assert store.get_director_hermes_run(
        project_id=project_id,
        run_id=durable["run_id"],
    )["status"] == "pending"
    assert store.list_director_proposals(project_id) == []
    assert [
        item["role"]
        for item in store.list_director_messages(
            project_id=project_id,
            conversation_id=conversation_id,
        )
    ] == ["user"]
    with sqlite3.connect(store.database_path(project_id)) as connection:
        state = connection.execute(
            """
            SELECT state FROM hermes_capability_ledger
            WHERE action = 'publish_proposal'
            """
        ).fetchone()[0]
        consumed_audit_count = connection.execute(
            """
            SELECT COUNT(*) FROM hermes_capability_audit
            WHERE action = 'publish_proposal'
              AND reason = 'hermes_capability_consumed'
            """
        ).fetchone()[0]
        terminal_event_count = connection.execute(
            """
            SELECT COUNT(*) FROM director_hermes_run_events
            WHERE project_id = ? AND run_id = ?
              AND event_type IN ('run_completed', 'blocked')
            """,
            (project_id, durable["run_id"]),
        ).fetchone()[0]
    assert state == "issued"
    assert consumed_audit_count == 0
    assert terminal_event_count == 0
