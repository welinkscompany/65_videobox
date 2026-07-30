from __future__ import annotations

import base64
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field as dataclass_field
from datetime import UTC, datetime
from typing import Any, ClassVar

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


_ALLOWED_ACTIONS = frozenset({"read_context", "publish_proposal"})


def _b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _canonical_json(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")


def _strict_string(value: object) -> bool:
    return isinstance(value, str) and bool(value) and value == value.strip()


def _strict_integer(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


@dataclass(frozen=True, slots=True)
class YujinCapabilityClaims:
    """Immutable exact wire claims for one Yujin capability action."""

    SCHEMA_VERSION: ClassVar[str] = "videobox.yujin-capability.v1"
    ISSUER: ClassVar[str] = "videobox-agent-gateway"
    SUBJECT: ClassVar[str] = "yujin-video-director"
    AUDIENCE: ClassVar[str] = "videobox-api"

    capability_id: str
    project_id: str
    conversation_id: str
    run_id: str
    session_id: str
    session_revision: int
    asset_index_revision: int
    action: str
    iat: int
    nbf: int
    exp: int

    def __post_init__(self) -> None:
        for value in (
            self.capability_id,
            self.project_id,
            self.conversation_id,
            self.run_id,
            self.session_id,
        ):
            if not _strict_string(value):
                raise ValueError("hermes_capability_claims_invalid")
        if self.action not in _ALLOWED_ACTIONS:
            raise ValueError("hermes_capability_action_forbidden")
        if not _strict_integer(self.session_revision) or self.session_revision <= 0:
            raise ValueError("hermes_capability_claims_invalid")
        if not _strict_integer(self.asset_index_revision) or self.asset_index_revision < 0:
            raise ValueError("hermes_capability_claims_invalid")
        if any(not _strict_integer(value) for value in (self.iat, self.nbf, self.exp)):
            raise ValueError("hermes_capability_claims_invalid")
        if not self.iat <= self.nbf < self.exp or self.exp - self.iat > 300:
            raise ValueError("hermes_capability_lifetime_invalid")

    def as_wire_claims(self) -> dict[str, str | int]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "iss": self.ISSUER,
            "sub": self.SUBJECT,
            "aud": self.AUDIENCE,
            "capability_id": self.capability_id,
            "project_id": self.project_id,
            "conversation_id": self.conversation_id,
            "run_id": self.run_id,
            "session_id": self.session_id,
            "session_revision": self.session_revision,
            "asset_index_revision": self.asset_index_revision,
            "action": self.action,
            "iat": self.iat,
            "nbf": self.nbf,
            "exp": self.exp,
        }


@dataclass(frozen=True, slots=True)
class YujinCapabilityMetadata:
    capability_id: str
    action: str
    expires_at: int

    def as_dict(self) -> dict[str, str | int]:
        return {
            "capability_id": self.capability_id,
            "action": self.action,
            "expires_at": self.expires_at,
        }


@dataclass(frozen=True, slots=True)
class YujinIssuedCapability:
    metadata: YujinCapabilityMetadata
    issued_at: int
    token: str = dataclass_field(repr=False)


@dataclass(frozen=True, slots=True)
class YujinRunCapabilities:
    read_context: YujinIssuedCapability
    publish_proposal: YujinIssuedCapability


class YujinCapabilityIssuer:
    """Gateway-only Ed25519 issuer with two explicit one-action entry points."""

    def __init__(
        self,
        *,
        key_id: str,
        private_key: bytes,
        now: Callable[[], datetime] | None = None,
        capability_id_factory: Callable[[], str],
        lifetime_seconds: int = 300,
    ) -> None:
        if (
            not _strict_string(key_id)
            or not isinstance(private_key, bytes)
            or len(private_key) != 32
        ):
            raise ValueError("hermes_capability_issuer_invalid")
        if (
            not _strict_integer(lifetime_seconds)
            or lifetime_seconds <= 0
            or lifetime_seconds > 300
        ):
            raise ValueError("hermes_capability_lifetime_invalid")
        self._header = {"alg": "EdDSA", "kid": key_id, "typ": "VBC"}
        self._private_key = Ed25519PrivateKey.from_private_bytes(private_key)
        self._now = now or (lambda: datetime.now(UTC))
        self._capability_id_factory = capability_id_factory
        self._lifetime_seconds = lifetime_seconds

    def issue_read_context(
        self,
        *,
        project_id: str,
        conversation_id: str,
        run_id: str,
        session_id: str,
        session_revision: int,
        asset_index_revision: int,
    ) -> str:
        return self._issue(
            action="read_context",
            project_id=project_id,
            conversation_id=conversation_id,
            run_id=run_id,
            session_id=session_id,
            session_revision=session_revision,
            asset_index_revision=asset_index_revision,
        )

    def issue_publish_proposal(
        self,
        *,
        project_id: str,
        conversation_id: str,
        run_id: str,
        session_id: str,
        session_revision: int,
        asset_index_revision: int,
    ) -> str:
        return self._issue(
            action="publish_proposal",
            project_id=project_id,
            conversation_id=conversation_id,
            run_id=run_id,
            session_id=session_id,
            session_revision=session_revision,
            asset_index_revision=asset_index_revision,
        )

    def issue_run_capabilities(
        self,
        *,
        project_id: str,
        conversation_id: str,
        run_id: str,
        session_id: str,
        session_revision: int,
        asset_index_revision: int,
    ) -> YujinRunCapabilities:
        scope = {
            "project_id": project_id,
            "conversation_id": conversation_id,
            "run_id": run_id,
            "session_id": session_id,
            "session_revision": session_revision,
            "asset_index_revision": asset_index_revision,
        }
        read_context = self._issue_record(action="read_context", **scope)
        publish_proposal = self._issue_record(
            action="publish_proposal",
            **scope,
        )
        if (
            read_context.metadata.capability_id
            == publish_proposal.metadata.capability_id
        ):
            raise ValueError("hermes_capability_id_collision")
        return YujinRunCapabilities(
            read_context=read_context,
            publish_proposal=publish_proposal,
        )

    def _issue(
        self,
        *,
        action: str,
        project_id: str,
        conversation_id: str,
        run_id: str,
        session_id: str,
        session_revision: int,
        asset_index_revision: int,
    ) -> str:
        return self._issue_record(
            action=action,
            project_id=project_id,
            conversation_id=conversation_id,
            run_id=run_id,
            session_id=session_id,
            session_revision=session_revision,
            asset_index_revision=asset_index_revision,
        ).token

    def _issue_record(
        self,
        *,
        action: str,
        project_id: str,
        conversation_id: str,
        run_id: str,
        session_id: str,
        session_revision: int,
        asset_index_revision: int,
    ) -> YujinIssuedCapability:
        issued_at = self._now()
        if issued_at.tzinfo is None:
            raise ValueError("hermes_capability_clock_invalid")
        issued_at_epoch = int(issued_at.timestamp())
        claims = YujinCapabilityClaims(
            capability_id=self._capability_id_factory(),
            project_id=project_id,
            conversation_id=conversation_id,
            run_id=run_id,
            session_id=session_id,
            session_revision=session_revision,
            asset_index_revision=asset_index_revision,
            action=action,
            iat=issued_at_epoch,
            nbf=issued_at_epoch,
            exp=issued_at_epoch + self._lifetime_seconds,
        )
        encoded_header = _b64url_encode(_canonical_json(self._header))
        encoded_claims = _b64url_encode(_canonical_json(claims.as_wire_claims()))
        signing_input = f"{encoded_header}.{encoded_claims}".encode("ascii")
        signature = self._private_key.sign(signing_input)
        return YujinIssuedCapability(
            metadata=YujinCapabilityMetadata(
                capability_id=claims.capability_id,
                action=claims.action,
                expires_at=claims.exp,
            ),
            issued_at=claims.iat,
            token=(
                f"{encoded_header}.{encoded_claims}."
                f"{_b64url_encode(signature)}"
            ),
        )
