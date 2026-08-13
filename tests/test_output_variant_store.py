from __future__ import annotations

from pathlib import Path

import pytest

from videobox_domain_models.output_variants import OutputVariant
from videobox_storage.local_project_store import (
    EditingSessionRevisionConflict,
    LocalProjectStore,
)


def _store(tmp_path: Path) -> LocalProjectStore:
    return LocalProjectStore(tmp_path / "projects")


def _session(store: LocalProjectStore, name: str = "variant store") -> tuple[object, dict]:
    project = store.bootstrap_project(name)
    saved = store.save_editing_session(
        project_id=project.project_id,
        timeline_id="timeline-1",
        session_payload={
            "segments": [
                {"segment_id": "seg-a", "text": "a"},
                {"segment_id": "seg-b", "text": "b"},
            ],
            "history": [],
        },
    )
    return project, saved


def _domain_payload(variant: dict) -> dict:
    return {
        key: value
        for key, value in variant.items()
        if key not in {"project_id", "created_at", "updated_at"}
    }


def test_latest_session_lazily_seeds_two_default_variants_without_highlight(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    project, session = _session(store)

    variants = store.ensure_output_variants(
        project_id=project.project_id,
        session_id=session["session_id"],
    )

    assert [item["kind"] for item in variants] == ["horizontal", "vertical_full"]
    assert {item["source_session_id"] for item in variants} == {session["session_id"]}
    assert {item["source_session_revision"] for item in variants} == {1}
    assert all(item["variant_revision"] == 1 for item in variants)
    assert store.list_output_variants(project_id=project.project_id) == variants


def test_legacy_seed_is_idempotent_and_does_not_rewrite_session_json(tmp_path: Path) -> None:
    store = _store(tmp_path)
    project, session = _session(store)
    before = store.get_editing_session(
        project_id=project.project_id, session_id=session["session_id"]
    )

    first = store.ensure_output_variants(project_id=project.project_id)
    second = store.ensure_output_variants(project_id=project.project_id)

    assert first == second
    assert store.get_editing_session(
        project_id=project.project_id, session_id=session["session_id"]
    ) == before


def test_variant_patch_persists_revision_locks_and_conflicts(tmp_path: Path) -> None:
    store = _store(tmp_path)
    project, session = _session(store)
    [variant] = store.ensure_output_variants(
        project_id=project.project_id,
        session_id=session["session_id"],
    )[:1]

    updated = store.update_output_variant(
        project_id=project.project_id,
        variant_id=variant["variant_id"],
        expected_variant_revision=1,
        variant=OutputVariant.model_validate(
            {
                **_domain_payload(variant),
                "variant_revision": 2,
                "overrides": {"crop": {"mode": "cover"}},
                "locks": [{"field": "crop", "base_master_revision": 1}],
                "conflicts": [
                    {
                        "field": "crop",
                        "base_master_revision": 1,
                        "current_master_revision": 2,
                        "reason": "master_changed_while_locked",
                    }
                ],
            }
        ),
    )

    assert updated["variant_revision"] == 2
    loaded = store.get_output_variant(
        project_id=project.project_id, variant_id=variant["variant_id"]
    )
    assert loaded["locks"][0]["field"] == "crop"
    assert loaded["conflicts"][0]["current_master_revision"] == 2


def test_variant_update_rejects_stale_revision_without_mutation(tmp_path: Path) -> None:
    store = _store(tmp_path)
    project, session = _session(store)
    [variant] = store.ensure_output_variants(
        project_id=project.project_id,
        session_id=session["session_id"],
    )[:1]
    replacement = OutputVariant.model_validate(
        {
            **_domain_payload(variant),
            "variant_revision": 2,
            "overrides": {"audio": {"gain_db": -1}},
        }
    )

    with pytest.raises(EditingSessionRevisionConflict, match="variant"):
        store.update_output_variant(
            project_id=project.project_id,
            variant_id=variant["variant_id"],
            expected_variant_revision=0,
            variant=replacement,
        )

    assert store.get_output_variant(
        project_id=project.project_id, variant_id=variant["variant_id"]
    )["variant_revision"] == 1


def test_variant_update_requires_project_scoped_identity(tmp_path: Path) -> None:
    store = _store(tmp_path)
    project, _ = _session(store)

    with pytest.raises(KeyError):
        store.get_output_variant(
            project_id=project.project_id, variant_id="missing-variant"
        )


def test_latest_session_seed_does_not_replace_variants_from_older_session(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    project, first = _session(store, "two sessions")
    second = store.save_editing_session(
        project_id=project.project_id,
        timeline_id="timeline-2",
        session_payload={"segments": [{"segment_id": "new"}], "history": []},
    )

    seeded = store.ensure_output_variants(project_id=project.project_id)
    assert {item["source_session_id"] for item in seeded} == {second["session_id"]}
    assert store.list_output_variants(project_id=project.project_id, session_id=first["session_id"]) == []


def test_variant_materialization_is_revision_keyed_and_round_trips(tmp_path: Path) -> None:
    store = _store(tmp_path)
    project, session = _session(store)
    [variant] = store.ensure_output_variants(
        project_id=project.project_id,
        session_id=session["session_id"],
    )[:1]
    materialization = store.save_variant_materialization(
        project_id=project.project_id,
        variant_id=variant["variant_id"],
        source_session_id=session["session_id"],
        source_session_revision=1,
        source_variant_revision=1,
        timeline_id="derived-timeline-1",
        segments=[{"segment_id": "seg-a"}],
    )

    assert materialization["timeline_id"] == "derived-timeline-1"
    assert store.get_variant_materialization(
        project_id=project.project_id,
        variant_id=variant["variant_id"],
        source_variant_revision=1,
    )["segments"] == [{"segment_id": "seg-a"}]


def test_variant_materialization_rejects_mismatched_source_identity(tmp_path: Path) -> None:
    store = _store(tmp_path)
    project, session = _session(store)
    [variant] = store.ensure_output_variants(
        project_id=project.project_id,
        session_id=session["session_id"],
    )[:1]

    with pytest.raises(ValueError, match="source_session"):
        store.save_variant_materialization(
            project_id=project.project_id,
            variant_id=variant["variant_id"],
            source_session_id="wrong-session",
            source_session_revision=1,
            source_variant_revision=1,
            timeline_id="derived-timeline-1",
            segments=[],
        )
