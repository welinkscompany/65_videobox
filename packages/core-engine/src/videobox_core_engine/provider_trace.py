from __future__ import annotations

from typing import Any


def build_provider_trace(
    *,
    final_provider: str,
    fallback_reasons: list[str] | None = None,
    routing_mode: str = "local_only",
) -> dict[str, Any]:
    return {
        "routing_mode": routing_mode,
        "final_provider": final_provider,
        "fallback_reasons": list(fallback_reasons or []),
    }


def response_provider_trace(response: Any) -> dict[str, Any]:
    metadata = getattr(response, "metadata", {}) or {}
    trace = metadata.get("provider_trace")
    if isinstance(trace, dict):
        return build_provider_trace(
            final_provider=str(trace.get("final_provider") or getattr(response, "provider_name", "unknown")),
            fallback_reasons=[str(item) for item in trace.get("fallback_reasons", []) if str(item).strip()],
            routing_mode=str(trace.get("routing_mode") or "local_only"),
        )
    return build_provider_trace(final_provider=str(getattr(response, "provider_name", "unknown")))


def with_final_provider(
    trace: dict[str, Any],
    *,
    final_provider: str,
    additional_reason: str | None = None,
) -> dict[str, Any]:
    fallback_reasons = [str(item) for item in trace.get("fallback_reasons", []) if str(item).strip()]
    if additional_reason and additional_reason not in fallback_reasons:
        fallback_reasons.append(additional_reason)
    return build_provider_trace(
        final_provider=final_provider,
        fallback_reasons=fallback_reasons,
        routing_mode=str(trace.get("routing_mode") or "local_only"),
    )
