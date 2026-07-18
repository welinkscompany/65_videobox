from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from videobox_storage.local_project_store import LocalProjectStore
from videobox_core_engine.creation_interview import CreationInterviewQuestion


def test_creation_brief_persists_adaptive_questions_answers_and_idempotency(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project("Eugene brief")

    first = store.create_creation_brief(
        project_id=project.project_id,
        script_filename="launch.txt",
        script_text="서울에서 새 제품을 소개하는 30초 영상입니다.",
        idempotency_key="brief-001",
        capability_profile={"ai_execution": "disabled"},
    )
    repeated = store.create_creation_brief(
        project_id=project.project_id,
        script_filename="launch.txt",
        script_text="ignored because the key is idempotent",
        idempotency_key="brief-001",
        capability_profile={"ai_execution": "disabled"},
    )

    assert repeated["brief_id"] == first["brief_id"]
    assert first["questions"][0]["field"] == "audience"
    assert "location" not in [question["field"] for question in first["questions"]]

    answered = store.answer_creation_brief_question(
        project_id=project.project_id,
        brief_id=first["brief_id"],
        question_id=first["questions"][0]["question_id"],
        answer="처음 방문한 고객",
        expected_revision=first["revision"],
    )
    restarted = LocalProjectStore(tmp_path).get_creation_brief(
        project_id=project.project_id, brief_id=first["brief_id"]
    )

    assert answered["revision"] == 2
    assert restarted["answers"] == {"audience": "처음 방문한 고객"}
    assert restarted["current_step"] == 1


def test_creation_brief_accepts_only_current_question_with_cas_and_never_mutates_after_approval(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project("CAS")
    brief = store.create_creation_brief(project_id=project.project_id, script_filename="script.txt", script_text="소개", idempotency_key="cas", capability_profile={})
    first, second = brief["questions"][:2]

    with pytest.raises(ValueError, match="creation_brief_question_not_current"):
        store.answer_creation_brief_question(project_id=project.project_id, brief_id=brief["brief_id"], question_id=second["question_id"], answer="x", expected_revision=brief["revision"])
    answered = store.answer_creation_brief_question(project_id=project.project_id, brief_id=brief["brief_id"], question_id=first["question_id"], answer="x", expected_revision=brief["revision"])
    with pytest.raises(ValueError, match="creation_brief_revision_conflict"):
        store.answer_creation_brief_question(project_id=project.project_id, brief_id=brief["brief_id"], question_id=second["question_id"], answer="x", expected_revision=brief["revision"])
    bypassed = store.bypass_creation_interview(project_id=project.project_id, brief_id=brief["brief_id"], expected_revision=answered["revision"])
    edited = store.update_creation_brief_summary(project_id=project.project_id, brief_id=brief["brief_id"], summary="요약", expected_revision=bypassed["revision"])
    approved = store.approve_creation_brief(project_id=project.project_id, brief_id=brief["brief_id"], expected_revision=edited["revision"])
    with pytest.raises(ValueError, match="creation_brief_immutable"):
        store.update_creation_brief_summary(project_id=project.project_id, brief_id=brief["brief_id"], summary="바꾸기", expected_revision=approved["revision"])


def test_creation_brief_can_return_to_the_previous_question_and_preserve_its_saved_answer(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project("Interview navigation")
    brief = store.create_creation_brief(
        project_id=project.project_id,
        script_filename="script.txt",
        script_text="새 영상을 소개합니다.",
        idempotency_key="previous-question",
        capability_profile={},
    )
    first = store.answer_creation_brief_question(
        project_id=project.project_id,
        brief_id=brief["brief_id"],
        question_id=brief["questions"][0]["question_id"],
        answer="처음 방문한 고객",
        expected_revision=brief["revision"],
    )

    returned = store.previous_creation_brief_question(
        project_id=project.project_id,
        brief_id=brief["brief_id"],
        expected_revision=first["revision"],
    )

    assert returned["current_step"] == 0
    assert returned["status"] == "interviewing"
    assert returned["answers"]["audience"] == "처음 방문한 고객"


def test_creation_brief_materializes_owned_script_asset_and_delete_erases_it(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project("Retained asset")
    brief = store.create_creation_brief(project_id=project.project_id, script_filename="script.txt", script_text="보관할 대본", idempotency_key="asset", capability_profile={})
    asset = store.get_asset(project_id=project.project_id, asset_id=brief["script_asset_id"])
    path = store.resolve_storage_uri(project_id=project.project_id, storage_uri=asset["storage_uri"])
    assert path.read_text(encoding="utf-8") == "보관할 대본"
    store.delete_creation_brief(project_id=project.project_id, brief_id=brief["brief_id"])
    assert not path.exists()
    with pytest.raises(KeyError):
        store.get_asset(project_id=project.project_id, asset_id=asset["asset_id"])


def test_creation_brief_uses_injected_deterministic_runtime_without_provider_calls(tmp_path: Path) -> None:
    class CountingRuntime:
        calls = 0
        def plan_questions(self, *, script_text: str) -> list[CreationInterviewQuestion]:
            self.calls += 1
            return [CreationInterviewQuestion("goal", "무엇을 이루고 싶나요?")]

    runtime = CountingRuntime()
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project("Runtime")
    brief = store.create_creation_brief(project_id=project.project_id, script_filename="runtime.txt", script_text="로컬", idempotency_key="runtime", capability_profile={}, runtime=runtime)
    assert runtime.calls == 1
    assert brief["questions"][0]["field"] == "goal"


def test_creation_brief_cleans_materialized_asset_when_injected_runtime_planning_fails(tmp_path: Path) -> None:
    class FailingRuntime:
        def plan_questions(self, *, script_text: str) -> list[CreationInterviewQuestion]:
            raise RuntimeError("planning failed")

    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project("Failed planning")
    with pytest.raises(RuntimeError, match="planning failed"):
        store.create_creation_brief(
            project_id=project.project_id, script_filename="script.txt", script_text="대본",
            idempotency_key="fail", capability_profile={}, runtime=FailingRuntime(),
        )
    assert store.list_assets(project_id=project.project_id) == []
    assert store.list_creation_briefs(project_id=project.project_id) == []


@pytest.mark.parametrize(
    ("questions", "error"),
    [
        ([SimpleNamespace(field="field", prompt="질문", question_id="same"), SimpleNamespace(field="other", prompt="다른 질문", question_id="same")], "creation_brief_question_id_duplicate"),
        ([SimpleNamespace(field="same-field", prompt="첫 질문", question_id="q-1"), SimpleNamespace(field="same-field", prompt="둘째 질문", question_id="q-2")], "creation_brief_question_field_duplicate"),
        ([SimpleNamespace(field="field", prompt="질문", question_id="")], "creation_brief_question_id_invalid"),
        ([SimpleNamespace(field=f"field-{index}", prompt="질문", question_id=f"q-{index}") for index in range(6)], "creation_brief_questions_too_many"),
    ],
    ids=["duplicate-id", "duplicate-field", "blank-id", "over-max"],
)
def test_creation_brief_validates_injected_runtime_question_boundaries(
    tmp_path: Path, questions: list[object], error: str
) -> None:
    class Runtime:
        def plan_questions(self, *, script_text: str) -> list[object]:
            return questions

    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project("Question boundary")
    with pytest.raises(ValueError, match=error):
        store.create_creation_brief(
            project_id=project.project_id, script_filename="script.txt", script_text="대본",
            idempotency_key=error, capability_profile={}, runtime=Runtime(),
        )
    assert store.list_assets(project_id=project.project_id) == []


def test_creation_brief_asks_about_contradictory_script_format_even_when_format_terms_exist(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project("Contradiction")
    brief = store.create_creation_brief(project_id=project.project_id, script_filename="format.txt", script_text="YouTube Shorts와 Instagram Reels 형식으로 동시에 만듭니다.", idempotency_key="format", capability_profile={})
    assert "format" in [question["field"] for question in brief["questions"]]


@pytest.mark.parametrize(
    ("filename", "text", "error"),
    [
        ("script.pdf", "hello", "creation_brief_script_extension_invalid"),
        ("script.txt", "x" * (1024 * 1024 + 1), "creation_brief_script_too_large"),
        ("script.txt", b"\xff".decode("utf-8", errors="surrogateescape"), "creation_brief_script_not_utf8"),
    ],
    ids=["extension", "size", "utf8"],
)
def test_creation_brief_rejects_invalid_retained_script_input(
    tmp_path: Path, filename: str, text: str, error: str
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project("Validation")

    with pytest.raises(ValueError, match=error):
        store.create_creation_brief(
            project_id=project.project_id,
            script_filename=filename,
            script_text=text,
            idempotency_key="validation",
            capability_profile={"ai_execution": "disabled"},
        )


def test_creation_brief_delete_removes_retained_input_and_never_crosses_project_boundary(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    first_project = store.bootstrap_project("First")
    second_project = store.bootstrap_project("Second")
    brief = store.create_creation_brief(
        project_id=first_project.project_id,
        script_filename="first.md",
        script_text="# First",
        idempotency_key="first-brief",
        capability_profile={"ai_execution": "disabled"},
    )

    with pytest.raises(KeyError):
        store.get_creation_brief(project_id=second_project.project_id, brief_id=brief["brief_id"])
    store.delete_creation_brief(project_id=first_project.project_id, brief_id=brief["brief_id"])
    with pytest.raises(KeyError):
        store.get_creation_brief(project_id=first_project.project_id, brief_id=brief["brief_id"])


def test_creation_brief_manual_bypass_then_editable_summary_requires_revision_matched_approval(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project("Approval")
    brief = store.create_creation_brief(
        project_id=project.project_id, script_filename="script.txt", script_text="소개 영상",
        idempotency_key="approval", capability_profile={"ai_execution": "disabled"},
    )

    bypassed = store.bypass_creation_interview(project_id=project.project_id, brief_id=brief["brief_id"])
    edited = store.update_creation_brief_summary(
        project_id=project.project_id, brief_id=brief["brief_id"], summary="제품을 쉽게 소개하는 영상",
        expected_revision=bypassed["revision"],
    )
    with pytest.raises(ValueError, match="creation_brief_revision_conflict"):
        store.approve_creation_brief(project_id=project.project_id, brief_id=brief["brief_id"], expected_revision=bypassed["revision"])
    approved = store.approve_creation_brief(project_id=project.project_id, brief_id=brief["brief_id"], expected_revision=edited["revision"])

    assert bypassed["status"] == "ready_for_approval"
    assert approved["status"] == "approved"
    assert approved["summary"] == "제품을 쉽게 소개하는 영상"


def test_creation_brief_lists_only_its_project_in_newest_first_order(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project("List")
    store.create_creation_brief(project_id=project.project_id, script_filename="one.txt", script_text="첫 소개", idempotency_key="one", capability_profile={})
    store.create_creation_brief(project_id=project.project_id, script_filename="two.txt", script_text="둘 소개", idempotency_key="two", capability_profile={})

    assert [item["idempotency_key"] for item in store.list_creation_briefs(project_id=project.project_id)] == ["two", "one"]
