from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from enum import Enum


class GeminiKeyStatus(str, Enum):
    ACTIVE = "active"
    COOLDOWN = "cooldown"
    DISABLED = "disabled"
    INVALID = "invalid"


@dataclass(slots=True, frozen=True)
class GeminiApiKeyRecord:
    key_id: str
    label: str
    api_key: str
    primary_model: str
    cheap_model: str
    high_quality_model: str
    status: GeminiKeyStatus = GeminiKeyStatus.ACTIVE
    cooldown_until: datetime | None = None
    consecutive_failures: int = 0
    last_error: str | None = None
    last_used_at: datetime | None = None

    def is_available(self, *, now: datetime) -> bool:
        if self.status is GeminiKeyStatus.ACTIVE:
            return True
        if self.status is GeminiKeyStatus.COOLDOWN and self.cooldown_until and now >= self.cooldown_until:
            return True
        return False

    def public_state(self) -> dict[str, str | int | None]:
        return {
            "key_id": self.key_id,
            "label": self.label,
            "status": self.status.value,
            "primary_model": self.primary_model,
            "cheap_model": self.cheap_model,
            "high_quality_model": self.high_quality_model,
            "consecutive_failures": self.consecutive_failures,
            "last_error": self.last_error,
            "cooldown_until": self.cooldown_until.isoformat() if self.cooldown_until else None,
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
        }


@dataclass(slots=True, frozen=True)
class GeminiApiKeyPool:
    keys: tuple[GeminiApiKeyRecord, ...]
    max_keys: int = 10

    @classmethod
    def empty(cls) -> GeminiApiKeyPool:
        return cls(keys=())

    def add_key(
        self,
        *,
        key_id: str,
        label: str,
        api_key: str,
        primary_model: str,
        cheap_model: str,
        high_quality_model: str,
    ) -> GeminiApiKeyPool:
        if len(self.keys) >= self.max_keys:
            raise ValueError(f"Gemini key pool supports at most {self.max_keys} keys.")
        key = GeminiApiKeyRecord(
            key_id=key_id,
            label=label,
            api_key=api_key,
            primary_model=primary_model,
            cheap_model=cheap_model,
            high_quality_model=high_quality_model,
        )
        return GeminiApiKeyPool(keys=(*self.keys, key), max_keys=self.max_keys)

    def get_key(self, key_id: str) -> GeminiApiKeyRecord:
        for key in self.keys:
            if key.key_id == key_id:
                return key
        raise KeyError(f"Gemini key not found: {key_id}")

    def available_keys(self, *, now: datetime) -> list[GeminiApiKeyRecord]:
        available: list[GeminiApiKeyRecord] = []
        for key in self.keys:
            if key.status is GeminiKeyStatus.COOLDOWN and key.cooldown_until and now >= key.cooldown_until:
                available.append(replace(key, status=GeminiKeyStatus.ACTIVE, cooldown_until=None))
            elif key.status is GeminiKeyStatus.ACTIVE:
                available.append(key)
        return available

    def mark_rate_limited(
        self,
        key_id: str,
        *,
        now: datetime,
        cooldown_seconds: int,
    ) -> GeminiApiKeyPool:
        return self._replace_key(
            key_id,
            lambda key: replace(
                key,
                status=GeminiKeyStatus.COOLDOWN,
                cooldown_until=now + timedelta(seconds=cooldown_seconds),
                last_error="rate_limited",
            ),
        )

    def mark_failure(self, key_id: str, *, now: datetime, error_message: str) -> GeminiApiKeyPool:
        def apply(key: GeminiApiKeyRecord) -> GeminiApiKeyRecord:
            failures = key.consecutive_failures + 1
            status = GeminiKeyStatus.DISABLED if failures >= 3 else key.status
            cooldown_until = None if status is GeminiKeyStatus.DISABLED else key.cooldown_until
            return replace(
                key,
                status=status,
                cooldown_until=cooldown_until,
                consecutive_failures=failures,
                last_error=error_message,
                last_used_at=now,
            )

        return self._replace_key(key_id, apply)

    def mark_success(self, key_id: str, *, now: datetime) -> GeminiApiKeyPool:
        return self._replace_key(
            key_id,
            lambda key: replace(
                key,
                status=GeminiKeyStatus.ACTIVE,
                cooldown_until=None,
                consecutive_failures=0,
                last_error=None,
                last_used_at=now,
            ),
        )

    def _replace_key(
        self,
        key_id: str,
        transform: callable,
    ) -> GeminiApiKeyPool:
        updated: list[GeminiApiKeyRecord] = []
        found = False
        for key in self.keys:
            if key.key_id == key_id:
                updated.append(transform(key))
                found = True
            else:
                updated.append(key)
        if not found:
            raise KeyError(f"Gemini key not found: {key_id}")
        return GeminiApiKeyPool(keys=tuple(updated), max_keys=self.max_keys)
