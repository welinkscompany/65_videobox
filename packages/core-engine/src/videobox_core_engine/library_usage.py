"""Pure usage inspection for global personal-library assets.

The personal-library row is global, while project assets, editing sessions and
render variants live in separate stores.  Deletion guards therefore need a
small read-only helper that can inspect all of those payloads without knowing
their persistence implementation.  This module deliberately has no store or
web-framework imports: callers pass the current snapshots they already own.

The result is a list of stable, navigable locations.  ``path`` is a JSONPath-
style path into the supplied snapshot and the identifying fields are copied
from the snapshot when present.  A caller can expose these dictionaries in an
API response or map them to a UI route without exposing source paths.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any


# ``asset_id`` is included intentionally.  Older editing-session/timeline
# payloads stored a global library identity directly in that field rather than
# using the newer explicit ``library_asset_id`` field.  Matching is exact, so
# this cannot claim unrelated assets unless they share the same opaque ID.
_REFERENCE_KEYS = frozenset(
    {
        "asset_id",
        "library_asset_id",
        "source_library_asset_id",
        "asset_ids",
        "library_asset_ids",
        "source_library_asset_ids",
    }
)
_COLLECTIONS = (
    ("project", "projects"),
    ("editing_session", "editing_sessions"),
    ("timeline", "timelines"),
    ("variant", "variants"),
    ("derived_sequence", "derived_sequences"),
)


def scan_library_asset_usage(
    library_asset_id: str,
    *,
    projects: Iterable[object] = (),
    editing_sessions: Iterable[object] = (),
    timelines: Iterable[object] = (),
    variants: Iterable[object] = (),
    derived_sequences: Iterable[object] = (),
) -> list[dict[str, Any]]:
    """Find exact references to one global library asset in current snapshots.

    The function is deliberately conservative about input shape: malformed or
    scalar records are ignored, while nested mappings/lists are traversed
    recursively.  It never reads or mutates a store and never treats a file
    path as an asset identity.  The output order is deterministic (collection
    order, then depth-first payload order) and duplicate sightings at the same
    location are collapsed.

    ``asset_id`` is accepted for backwards compatibility with older timeline
    snapshots.  New writes should prefer ``library_asset_id`` or
    ``source_library_asset_id`` so a project-local materialized ID remains
    unambiguous.
    """

    target = str(library_asset_id).strip()
    if not target:
        raise ValueError("library_asset_id is required")

    snapshots = {
        "project": projects,
        "editing_session": editing_sessions,
        "timeline": timelines,
        "variant": variants,
        "derived_sequence": derived_sequences,
    }
    found: list[dict[str, Any]] = []
    seen: set[tuple[str, int, str, str]] = set()
    for kind, _ in _COLLECTIONS:
        for record_index, record in enumerate(_as_records(snapshots[kind])):
            if not isinstance(record, Mapping):
                continue
            context = _context_ids(record)
            _walk(
                value=record,
                target=target,
                path="$",
                kind=kind,
                record_index=record_index,
                context=context,
                found=found,
                seen=seen,
            )
    return found


def _as_records(value: Iterable[object] | object) -> Iterable[object]:
    """Treat one mapping as one snapshot instead of iterating its keys."""

    if isinstance(value, Mapping) or isinstance(value, (str, bytes, bytearray)):
        return (value,)
    try:
        return iter(value)  # type: ignore[arg-type]
    except TypeError:
        return (value,)


def _context_ids(record: Mapping[str, Any]) -> dict[str, str]:
    """Copy only navigational opaque IDs from a root snapshot."""

    context: dict[str, str] = {}
    for key in ("project_id", "session_id", "timeline_id", "variant_id", "sequence_id", "derived_sequence_id"):
        value = record.get(key)
        if isinstance(value, (str, int)) and str(value).strip():
            context[key] = str(value)
    return context


def _walk(
    *,
    value: object,
    target: str,
    path: str,
    kind: str,
    record_index: int,
    context: Mapping[str, str],
    found: list[dict[str, Any]],
    seen: set[tuple[str, int, str, str]],
) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            field = str(key)
            child_path = f"{path}.{field}" if _path_identifier(field) else f"{path}[{field!r}]"
            if field in _REFERENCE_KEYS:
                for index, candidate in _reference_values(child):
                    if candidate != target:
                        continue
                    match_path = child_path if index is None else f"{child_path}[{index}]"
                    dedupe_key = (kind, record_index, match_path, field)
                    if dedupe_key in seen:
                        continue
                    seen.add(dedupe_key)
                    location: dict[str, Any] = {
                        "kind": kind,
                        "path": match_path,
                        "field": field,
                        "record_index": record_index,
                    }
                    location.update(context)
                    found.append(location)
            _walk(
                value=child,
                target=target,
                path=child_path,
                kind=kind,
                record_index=record_index,
                context=context,
                found=found,
                seen=seen,
            )
        return
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, child in enumerate(value):
            _walk(
                value=child,
                target=target,
                path=f"{path}[{index}]",
                kind=kind,
                record_index=record_index,
                context=context,
                found=found,
                seen=seen,
            )


def _reference_values(value: object) -> tuple[tuple[int | None, str], ...]:
    """Return scalar references and list members without coercing objects."""

    if isinstance(value, (str, int)):
        return ((None, str(value)),)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return tuple((index, str(item)) for index, item in enumerate(value) if isinstance(item, (str, int)))
    return ()


def _path_identifier(value: str) -> bool:
    return value.replace("_", "").isalnum() and not value[:1].isdigit()


__all__ = ["scan_library_asset_usage"]
