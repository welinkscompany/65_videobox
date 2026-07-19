from __future__ import annotations

import base64
import hashlib
import hmac
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Lock
from typing import Any


class HermesCapabilityError(ValueError):
    """A fail-closed error suitable for the internal Hermes boundary."""


class HermesCapabilityUnavailableError(RuntimeError):
    """The durable replay ledger cannot make a safe authorization decision."""


def _b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    if not value or any(char not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_" for char in value):
        raise HermesCapabilityError("hermes_capability_malformed")
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _canonical_json(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, separators=(",", ":"), sort_keys=True, ensure_ascii=True).encode("ascii")


def _as_object(encoded: str) -> dict[str, Any]:
    try:
        value = json.loads(_b64url_decode(encoded))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise HermesCapabilityError("hermes_capability_malformed") from exc
    if not isinstance(value, dict):
        raise HermesCapabilityError("hermes_capability_malformed")
    return value


@dataclass(frozen=True)
class HermesCapability:
    principal: str
    operation: str
    project_id: str
    expires_at: int
    jti: str


class HermesCapabilitySigner:
    """Owned by a future Agent Gateway, never registered as an API route."""

    def __init__(self, *, key_id: str, key: bytes, now: Callable[[], datetime] | None = None) -> None:
        if not key_id or not isinstance(key, bytes) or len(key) < 32:
            raise ValueError("hermes_capability_signer_invalid")
        self._header = {"alg": "HS256", "kid": key_id, "typ": "VBC"}
        self._key = key
        self._now = now or (lambda: datetime.now(UTC))

    def sign(self, claims: Mapping[str, Any]) -> str:
        issued_at = claims.get("iat")
        if not isinstance(issued_at, int) or isinstance(issued_at, bool):
            raise ValueError("hermes_capability_iat_required")
        header = _b64url_encode(_canonical_json(self._header))
        payload = _b64url_encode(_canonical_json(dict(claims)))
        signing_input = f"{header}.{payload}".encode("ascii")
        signature = hmac.new(self._key, signing_input, hashlib.sha256).digest()
        return f"{header}.{payload}.{_b64url_encode(signature)}"


class HermesCapabilityVerifier:
    """Verifies one short-lived, project-scoped, replay-protected capability."""

    _REQUIRED_CLAIMS = frozenset({"iss", "sub", "aud", "op", "project_id", "iat", "nbf", "exp", "jti"})
    _ALLOWED_CLAIMS = _REQUIRED_CLAIMS

    def __init__(
        self,
        *,
        keys: Mapping[str, bytes],
        revoked_jtis: set[str] | None = None,
        consume_jti: Callable[[str, str, int], str] | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        if not keys or any(not key_id or not isinstance(key, bytes) or len(key) < 32 for key_id, key in keys.items()):
            raise ValueError("hermes_capability_verifier_invalid")
        self._keys = dict(keys)
        self._revoked_jtis = set(revoked_jtis or ())
        self._now = now or (lambda: datetime.now(UTC))
        self._consumed_jtis: dict[str, int] = {}
        self._consume_jti = consume_jti
        self._lock = Lock()

    def bind_durable_ledger(self, consume_jti: Callable[[str, str, int], str]) -> None:
        self._consume_jti = consume_jti

    def verify_for_project_status(self, token: str, *, project_id: str) -> HermesCapability:
        header, claims, signature, signing_input = self._parse(token)
        if header != {"alg": "HS256", "kid": header.get("kid"), "typ": "VBC"}:
            raise HermesCapabilityError("hermes_capability_header_invalid")
        key_id = header.get("kid")
        if not isinstance(key_id, str) or key_id not in self._keys:
            raise HermesCapabilityError("hermes_capability_key_unknown")
        expected = hmac.new(self._keys[key_id], signing_input, hashlib.sha256).digest()
        if not hmac.compare_digest(expected, signature):
            raise HermesCapabilityError("hermes_capability_signature_invalid")
        if set(claims) != self._ALLOWED_CLAIMS:
            raise HermesCapabilityError("hermes_capability_claims_invalid")
        self._validate_claim_types(claims)
        now = int(self._now().timestamp())
        if claims["iss"] != "videobox-agent-gateway" or claims["aud"] != "videobox-api":
            raise HermesCapabilityError("hermes_capability_audience_forbidden")
        if claims["sub"] != "yujin-video-director":
            raise HermesCapabilityError("hermes_capability_principal_forbidden")
        if claims["op"] != "get_project_status":
            raise HermesCapabilityError("hermes_capability_operation_forbidden")
        if claims["project_id"] != project_id:
            raise HermesCapabilityError("hermes_capability_project_forbidden")
        if claims["nbf"] > now:
            raise HermesCapabilityError("hermes_capability_not_yet_valid")
        if claims["exp"] <= now:
            raise HermesCapabilityError("hermes_capability_expired")
        if claims["iat"] > now or claims["exp"] - claims["iat"] > 300:
            raise HermesCapabilityError("hermes_capability_lifetime_invalid")
        jti = claims["jti"]
        if self._consume_jti is not None:
            try:
                state = self._consume_jti(project_id, jti, claims["exp"])
            except Exception as exc:
                raise HermesCapabilityUnavailableError("hermes_capability_unavailable") from exc
            if state == "unavailable":
                raise HermesCapabilityUnavailableError("hermes_capability_unavailable")
            if state == "revoked":
                raise HermesCapabilityError("hermes_capability_revoked")
            if state != "accepted":
                raise HermesCapabilityError("hermes_capability_replayed")
        else:
            self._consume_in_memory(jti=jti, expires_at=claims["exp"], now=now)
        return HermesCapability(
            principal=claims["sub"], operation=claims["op"], project_id=claims["project_id"],
            expires_at=claims["exp"], jti=jti,
        )

    def _consume_in_memory(self, *, jti: str, expires_at: int, now: int) -> None:
        with self._lock:
            self._consumed_jtis = {known: expiry for known, expiry in self._consumed_jtis.items() if expiry > now}
            if jti in self._revoked_jtis:
                raise HermesCapabilityError("hermes_capability_revoked")
            if jti in self._consumed_jtis:
                raise HermesCapabilityError("hermes_capability_replayed")
            self._consumed_jtis[jti] = expires_at

    def _parse(self, token: str) -> tuple[dict[str, Any], dict[str, Any], bytes, bytes]:
        parts = token.split(".")
        if len(parts) != 3:
            raise HermesCapabilityError("hermes_capability_malformed")
        header, claims = _as_object(parts[0]), _as_object(parts[1])
        try:
            signature = _b64url_decode(parts[2])
        except ValueError as exc:
            raise HermesCapabilityError("hermes_capability_malformed") from exc
        if len(signature) != hashlib.sha256().digest_size:
            raise HermesCapabilityError("hermes_capability_malformed")
        return header, claims, signature, f"{parts[0]}.{parts[1]}".encode("ascii")

    @staticmethod
    def _validate_claim_types(claims: Mapping[str, Any]) -> None:
        for field in ("iss", "sub", "aud", "op", "project_id", "jti"):
            if not isinstance(claims[field], str) or not claims[field]:
                raise HermesCapabilityError("hermes_capability_claims_invalid")
        if len(claims["jti"]) < 16:
            raise HermesCapabilityError("hermes_capability_claims_invalid")
        for field in ("iat", "nbf", "exp"):
            if not isinstance(claims[field], int) or isinstance(claims[field], bool):
                raise HermesCapabilityError("hermes_capability_claims_invalid")
