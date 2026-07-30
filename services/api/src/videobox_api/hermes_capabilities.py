from __future__ import annotations

import base64
import binascii
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


_ALLOWED_ACTIONS = frozenset({"read_context", "publish_proposal"})
_EXACT_CLAIMS = frozenset(
    {
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
)


class HermesCapabilityError(ValueError):
    """A stable fail-closed denial at the internal Hermes boundary."""


class HermesCapabilityUnavailableError(RuntimeError):
    """The durable lifecycle authority cannot make a safe decision."""


def _strict_string(value: object) -> bool:
    return isinstance(value, str) and bool(value) and value == value.strip()


def _strict_integer(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    if (
        not value
        or "=" in value
        or any(
            char
            not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
            for char in value
        )
    ):
        raise HermesCapabilityError("hermes_capability_malformed")
    try:
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (binascii.Error, ValueError) as exc:
        raise HermesCapabilityError("hermes_capability_malformed") from exc


def _canonical_json(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_key")
        result[key] = value
    return result


def _as_canonical_object(encoded: str) -> dict[str, Any]:
    try:
        raw = _b64url_decode(encoded)
        value = json.loads(
            raw.decode("ascii"),
            object_pairs_hook=_reject_duplicate_keys,
        )
    except (
        HermesCapabilityError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        ValueError,
    ) as exc:
        raise HermesCapabilityError("hermes_capability_malformed") from exc
    if not isinstance(value, dict) or _b64url_encode(_canonical_json(value)) != encoded:
        raise HermesCapabilityError("hermes_capability_malformed")
    return value


@dataclass(frozen=True, slots=True)
class ExpectedCapability:
    """Trusted scope loaded from one already-known durable issued row."""

    capability_id: str
    project_id: str
    conversation_id: str
    run_id: str
    session_id: str
    session_revision: int
    asset_index_revision: int
    action: str

    def __post_init__(self) -> None:
        for value in (
            self.capability_id,
            self.project_id,
            self.conversation_id,
            self.run_id,
            self.session_id,
        ):
            if not _strict_string(value):
                raise ValueError("hermes_capability_expected_invalid")
        if self.action not in _ALLOWED_ACTIONS:
            raise ValueError("hermes_capability_action_forbidden")
        if not _strict_integer(self.session_revision) or self.session_revision <= 0:
            raise ValueError("hermes_capability_expected_invalid")
        if (
            not _strict_integer(self.asset_index_revision)
            or self.asset_index_revision < 0
        ):
            raise ValueError("hermes_capability_expected_invalid")


@dataclass(frozen=True, slots=True)
class VerifiedYujinCapability:
    capability_id: str
    project_id: str
    conversation_id: str
    run_id: str
    session_id: str
    session_revision: int
    asset_index_revision: int
    action: str
    issued_at: int
    not_before: int
    expires_at: int


class HermesCapabilityVerifier:
    """API-side Ed25519 verifier; it owns no private key or replay state."""

    def __init__(
        self,
        *,
        key_id: str,
        public_key: bytes,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        if (
            not _strict_string(key_id)
            or not isinstance(public_key, bytes)
            or len(public_key) != 32
        ):
            raise ValueError("hermes_capability_verifier_invalid")
        try:
            self._public_key = Ed25519PublicKey.from_public_bytes(public_key)
        except ValueError as exc:
            raise ValueError("hermes_capability_verifier_invalid") from exc
        self._key_id = key_id
        self._now = now or (lambda: datetime.now(UTC))

    def verify(
        self,
        token: str,
        *,
        expected: ExpectedCapability,
    ) -> VerifiedYujinCapability:
        header, claims, signature, signing_input = self._parse(token)
        if set(header) != {"alg", "kid", "typ"}:
            raise HermesCapabilityError("hermes_capability_malformed")
        if header.get("alg") != "EdDSA" or header.get("typ") != "VBC":
            raise HermesCapabilityError("hermes_capability_malformed")
        key_id = header.get("kid")
        if not _strict_string(key_id):
            raise HermesCapabilityError("hermes_capability_malformed")
        if key_id != self._key_id:
            raise HermesCapabilityError("hermes_capability_key_unknown")
        try:
            self._public_key.verify(signature, signing_input)
        except InvalidSignature as exc:
            raise HermesCapabilityError(
                "hermes_capability_signature_invalid"
            ) from exc

        if set(claims) != _EXACT_CLAIMS:
            raise HermesCapabilityError("hermes_capability_malformed")
        self._validate_claim_types(claims)
        if claims["action"] not in _ALLOWED_ACTIONS:
            raise HermesCapabilityError("hermes_capability_action_forbidden")
        if (
            claims["schema_version"] != "videobox.yujin-capability.v1"
            or claims["iss"] != "videobox-agent-gateway"
            or claims["sub"] != "yujin-video-director"
            or claims["aud"] != "videobox-api"
        ):
            raise HermesCapabilityError("hermes_capability_scope_forbidden")

        now = self._now()
        if now.tzinfo is None:
            raise HermesCapabilityUnavailableError("hermes_capability_unavailable")
        now_epoch = int(now.timestamp())
        if not claims["iat"] <= claims["nbf"] < claims["exp"]:
            raise HermesCapabilityError("hermes_capability_malformed")
        if claims["exp"] <= now_epoch:
            raise HermesCapabilityError("hermes_capability_expired")
        if claims["iat"] > now_epoch or claims["nbf"] > now_epoch:
            raise HermesCapabilityError("hermes_capability_not_yet_valid")
        if claims["exp"] - claims["iat"] > 300:
            raise HermesCapabilityError("hermes_capability_malformed")
        if claims["action"] != expected.action:
            raise HermesCapabilityError("hermes_capability_action_forbidden")
        if any(
            claims[field] != getattr(expected, field)
            for field in (
                "capability_id",
                "project_id",
                "conversation_id",
                "run_id",
                "session_id",
                "session_revision",
                "asset_index_revision",
            )
        ):
            raise HermesCapabilityError("hermes_capability_scope_forbidden")

        return VerifiedYujinCapability(
            capability_id=claims["capability_id"],
            project_id=claims["project_id"],
            conversation_id=claims["conversation_id"],
            run_id=claims["run_id"],
            session_id=claims["session_id"],
            session_revision=claims["session_revision"],
            asset_index_revision=claims["asset_index_revision"],
            action=claims["action"],
            issued_at=claims["iat"],
            not_before=claims["nbf"],
            expires_at=claims["exp"],
        )

    @staticmethod
    def _parse(
        token: str,
    ) -> tuple[dict[str, Any], dict[str, Any], bytes, bytes]:
        if not isinstance(token, str):
            raise HermesCapabilityError("hermes_capability_malformed")
        parts = token.split(".")
        if len(parts) != 3:
            raise HermesCapabilityError("hermes_capability_malformed")
        header = _as_canonical_object(parts[0])
        claims = _as_canonical_object(parts[1])
        signature = _b64url_decode(parts[2])
        if len(signature) != 64 or _b64url_encode(signature) != parts[2]:
            raise HermesCapabilityError("hermes_capability_malformed")
        signing_input = f"{parts[0]}.{parts[1]}".encode("ascii")
        return header, claims, signature, signing_input

    @staticmethod
    def _validate_claim_types(claims: Mapping[str, Any]) -> None:
        for field in (
            "schema_version",
            "iss",
            "sub",
            "aud",
            "capability_id",
            "project_id",
            "conversation_id",
            "run_id",
            "session_id",
            "action",
        ):
            if not _strict_string(claims[field]):
                raise HermesCapabilityError("hermes_capability_malformed")
        for field in (
            "session_revision",
            "asset_index_revision",
            "iat",
            "nbf",
            "exp",
        ):
            if not _strict_integer(claims[field]):
                raise HermesCapabilityError("hermes_capability_malformed")
        if claims["session_revision"] <= 0 or claims["asset_index_revision"] < 0:
            raise HermesCapabilityError("hermes_capability_malformed")
