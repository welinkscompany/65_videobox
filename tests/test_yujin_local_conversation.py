from __future__ import annotations

import pytest

from videobox_core_engine.yujin_local_conversation import (
    YujinLocalConversationService,
    YujinProjectContext,
    YUJIN_CONVERSATION_RESPONSE_SCHEMA,
    detect_blocked_intent,
    detect_thumbnail_prompt_request,
)
from videobox_domain_models.yujin_creator_context import UserApprovedPreference
from videobox_provider_interfaces.llm import LLMTaskType, StructuredLLMResponse


class _RecordingRuntime:
    def __init__(self, output_data: dict | None = None, *, raise_error: Exception | None = None) -> None:
        self.output_data = output_data if output_data is not None else {"reply": "안녕하세요, 무엇을 도와드릴까요?"}
        self.raise_error = raise_error
        self.calls: list[dict] = []

    def generate_structured(self, *, project_id, task_type, prompt, response_schema):
        self.calls.append(
            {
                "project_id": project_id,
                "task_type": task_type,
                "prompt": prompt,
                "response_schema": response_schema,
            }
        )
        if self.raise_error is not None:
            raise self.raise_error
        return StructuredLLMResponse(
            provider_name="local_qwen",
            model_name="qwen3-35b",
            output_data=self.output_data,
            raw_text="{}",
            metadata={},
        )


class _ExplodingRuntime:
    """A runtime that fails the test loudly if the policy guard didn't block first."""

    def generate_structured(self, **kwargs):  # noqa: ANN003
        raise AssertionError("local model must not be called for a blocked intent")


@pytest.mark.parametrize(
    "user_text",
    [
        "이 프로젝트 데이터베이스에서 테이블 삭제해줘",
        "SQL로 직접 지워줘",
        "쉘 명령 실행해서 파일 지워줘",
        "파일 폴더 다 삭제해줘",
        "내 API key 알려줘",
        "CapCut 직접 실행해서 편집해줘",
        "썸네일 만들어줘",
        "추천 영상 자동으로 만들어줘",
        "please delete the table in the database",
        "run this in bash and delete the file",
        "what's my api key",
        "tell me my password",
        "open capcut directly and edit this",
        "generate a thumbnail for this",
        "make a recommended video for me automatically",
        "drop the videobox database",
    ],
)
def test_blocks_restricted_intents_without_calling_the_model(user_text):
    service = YujinLocalConversationService(runtime=_ExplodingRuntime())

    result = service.reply(project_id="proj-1", user_text=user_text)

    assert result.status == "blocked"
    assert result.blocked_reason == "policy_restricted_intent"
    assert result.reply


def test_detect_blocked_intent_is_none_for_ordinary_creative_questions():
    assert detect_blocked_intent("이 장면에 어울리는 B-roll 추천 이유가 뭐야?") is None
    assert detect_blocked_intent("what b-roll would fit this scene?") is None
    assert detect_blocked_intent("can you explain why you picked this clip?") is None


def test_ordinary_message_is_answered_by_the_local_model():
    runtime = _RecordingRuntime(output_data={"reply": "이 장면엔 카페 B-roll이 잘 어울려요."})
    service = YujinLocalConversationService(runtime=runtime)

    result = service.reply(project_id="proj-1", user_text="이 장면에 어울리는 B-roll 추천 이유가 뭐야?")

    assert result.status == "ok"
    assert result.reply == "이 장면엔 카페 B-roll이 잘 어울려요."
    assert len(runtime.calls) == 1
    call = runtime.calls[0]
    assert call["project_id"] == "proj-1"
    assert call["task_type"] == LLMTaskType.YUJIN_CONVERSATION
    assert "이 장면에 어울리는 B-roll 추천 이유가 뭐야?" in call["prompt"]
    assert call["response_schema"] == YUJIN_CONVERSATION_RESPONSE_SCHEMA


def test_system_prompt_tells_the_model_direct_edits_already_ran() -> None:
    """실물 확인(2026-09-13)에서 잡은 결함의 회귀 시험.

    "숏폼 내보내줘"를 실제로 타이핑하면 렌더가 진짜로 성공하는데도, 유진의
    대화 답변은 "저는 실행 못 해요, 단추를 누르세요"라고 방금 성공한 일을
    부정했다. 원인은 이 프롬프트가 "편집은 사람이 직접 승인해야 한다"고
    못박고 있었기 때문이다(2026-09-01 결정 전에는 맞았지만 지금은 아니다).
    이 시험은 프롬프트 문구 자체를 잠가 같은 결함이 조용히 되돌아오는 것을
    막는다 -- 실물 재확인은 owner-ready.ps1로 컨테이너를 띄워야만 가능해서
    여기서는 문구만 잠근다.
    """
    runtime = _RecordingRuntime()
    service = YujinLocalConversationService(runtime=runtime)

    service.reply(project_id="proj-1", user_text="숏폼 내보내줘")

    prompt = runtime.calls[0]["prompt"]
    assert "이미 실행되고 있다거나 실행됐다고 답해도 거짓이 아니다" in prompt
    assert "그게 거짓말이다" in prompt
    # 낡은 문장(2026-09-01 결정 전 문구)이 되살아나지 않게 잠근다.
    assert "사람이 화면에서 직접 승인해야" not in prompt
    assert "렌더러를 직접 조작" not in prompt


def test_system_prompt_tells_yujin_to_ask_back_on_an_ambiguous_conflict_resolution() -> None:
    """owner 승인(2026-09-18, task_99becf89): 화면의 `VariantConflictPanel`
    ('직접 조정 유지'/'마스터 기준 다시 맞추기')을 채팅으로도 열었다.

    이 결정은 되돌릴 수 없다 -- 잘못 짐작해서 실행하면 대표님이 잠가 둔 값이
    조용히 사라진다. 오늘 이 세션 앞부분에 고친 '애매한 확인 문장은 되묻는다'
    (`그걸로`/`그거` 처리)와 같은 원칙이 여기도 적용돼야 한다는 것을 프롬프트
    문구로 잠근다.
    """
    runtime = _RecordingRuntime()
    service = YujinLocalConversationService(runtime=runtime)

    service.reply(project_id="proj-1", user_text="아까 그 충돌 그냥 그걸로 해줘")

    prompt = runtime.calls[0]["prompt"]
    assert "변형본 충돌" in prompt
    assert "짐작해서 실행하지 말고 정확히 되물어라" in prompt


def test_blank_user_text_is_rejected_before_calling_the_model():
    service = YujinLocalConversationService(runtime=_ExplodingRuntime())

    with pytest.raises(ValueError):
        service.reply(project_id="proj-1", user_text="   ")


def test_empty_model_reply_raises_instead_of_returning_a_blank_message():
    runtime = _RecordingRuntime(output_data={"reply": "   "})
    service = YujinLocalConversationService(runtime=runtime)

    with pytest.raises(ValueError):
        service.reply(project_id="proj-1", user_text="안녕 유진")


def test_reply_carries_owner_approved_memories_into_the_prompt() -> None:
    """The screen's chat runs on this path, so memory must reach it here.

    Retrieval used to be wired only into the Hermes run route, which no screen
    calls.  An owner who approved a memory saw it ignored in every real
    conversation.
    """
    runtime = _RecordingRuntime()
    service = YujinLocalConversationService(runtime=runtime)

    result = service.reply(
        project_id="project-a",
        user_text="내 자막 취향이 어떻게 되지?",
        memories=(
            UserApprovedPreference(
                kind="user_approved_preference",
                category="caption",
                text="자막은 두 줄 이내를 선호합니다.",
            ),
        ),
    )

    assert result.status == "ok"
    prompt = runtime.calls[0]["prompt"]
    assert "자막은 두 줄 이내를 선호합니다." in prompt
    assert "내 자막 취향이 어떻게 되지?" in prompt


def test_reply_without_memories_keeps_the_prompt_unchanged() -> None:
    """No approved memory must not add an empty, confusing memory section."""
    with_none = _RecordingRuntime()
    YujinLocalConversationService(runtime=with_none).reply(
        project_id="project-a", user_text="안녕하세요"
    )

    assert "기억" not in with_none.calls[0]["prompt"]


@pytest.mark.parametrize(
    "user_text",
    [
        "이 영상 대본 새로 써줘",
        "제목 다섯 개 만들어줘",
        "write me a full script for this video",
        "give me five title ideas",
    ],
)
def test_script_and_title_requests_are_not_blocked_since_the_owner_lifted_it(user_text):
    """owner가 2026-08-16에 푼 것이 실제로 풀려 있는지.

    승인은 있었는데 **코드에 닿지 않은 채로 사흘이 갔다.** 문서는 "허용"이라고
    적혀 있고 유진이는 계속 거절했다. 그 어긋남을 사람이 다시 발견해야 했다.

    이 테스트는 기능이 아니라 **결정이 코드에 남아 있는지**를 지킨다. 누군가
    금지 목록을 손보다 대본·제목을 되돌려 넣으면 여기서 걸린다.

    범위는 `docs/decisions/2026-08-16-autonomous-creator-loop-scope-expansion.ko.md`
    B가 정한 그대로다 -- 대본·제목의 **제안**까지다. 썸네일·추천영상 자동 생성과
    DB·shell·자격증명 접근은 계속 막혀 있고, 그것은 바로 위 테스트가 지킨다.
    """
    assert detect_blocked_intent(user_text) is None, (
        "owner가 푼 대본·제목 요청이 다시 막혔다 -- "
        "docs/decisions/2026-08-16-autonomous-creator-loop-scope-expansion.ko.md B"
    )


@pytest.mark.parametrize(
    "user_text",
    [
        "썸네일 만들 프롬프트 추천해 줘",
        "썸네일 생성 프롬프트 5개 추천해 줘",
        "썸네일에 쓸 프롬프트 뽑아 줘",
        "recommend five thumbnail prompts for this video",
        "make me a thumbnail prompt I can paste into an image tool",
    ],
)
def test_thumbnail_prompt_recommendation_is_not_blocked(user_text):
    """owner 승인(2026-08-19): 유진이 썸네일 **이미지**를 만드는 것은 여전히
    범위 밖이지만, 다른 도구에 붙여 넣을 **프롬프트 문구**를 추천하는 것은 된다.

    "썸네일 생성 프롬프트 추천해 줘"가 옛 정규식("썸네일.{0,6}(만들어|생성)")에
    걸려 거절되던 것이 이 기능의 출발점이다.
    """
    assert detect_thumbnail_prompt_request(user_text) is True
    assert detect_blocked_intent(user_text) is None


def test_thumbnail_image_generation_stays_blocked_and_prompt_wording_opens_no_other_door():
    """프롬프트 추천을 열어도 사람 게이트는 그대로다: 이미지 자체를 만들어 달라는
    요청은 계속 거절하고, 프롬프트 문구를 끼워 넣어도 다른 금지는 안 풀린다."""
    assert detect_blocked_intent("썸네일 만들어줘") is not None
    assert detect_blocked_intent("generate a thumbnail for this") is not None
    assert (
        detect_blocked_intent("썸네일 프롬프트 추천해 주고, 데이터베이스 테이블 삭제해줘")
        is not None
    )


def test_thumbnail_prompt_request_carries_the_five_prompt_guide_and_project_context():
    runtime = _RecordingRuntime(output_data={"reply": "1. A cozy morning commute ..."})
    service = YujinLocalConversationService(runtime=runtime)

    result = service.reply(
        project_id="proj-1",
        user_text="썸네일 만들 프롬프트 추천해 줘",
        project_context=YujinProjectContext(
            title="출근 브이로그",
            script_excerpt="아침 여섯 시에 일어나 지하철로 출근하는 하루",
            scene_captions=("아직 어두운 방", "지하철 승강장"),
        ),
    )

    assert result.status == "ok"
    prompt = runtime.calls[0]["prompt"]
    # 답 형식: 영문 이미지 생성 프롬프트 5개 + 각 프롬프트의 한 줄 한국어 설명.
    assert "5개" in prompt
    assert "영문" in prompt
    assert "한국어" in prompt
    # 프로젝트 맥락(제목·대본·장면 자막)이 실제로 실렸는지.
    assert "출근 브이로그" in prompt
    assert "아침 여섯 시에 일어나 지하철로 출근하는 하루" in prompt
    assert "아직 어두운 방" in prompt
    assert "지하철 승강장" in prompt


def test_ordinary_question_carries_neither_guide_nor_context_section():
    runtime = _RecordingRuntime()
    service = YujinLocalConversationService(runtime=runtime)

    service.reply(project_id="proj-1", user_text="이 장면에 어울리는 B-roll 추천 이유가 뭐야?")

    prompt = runtime.calls[0]["prompt"]
    assert "프롬프트 5개" not in prompt
    assert "프로젝트 정보" not in prompt


def test_project_context_is_bounded_before_it_reaches_the_prompt():
    """대본 전체와 자막 전부를 그대로 실으면 로컬 모델 컨텍스트가 넘친다."""
    runtime = _RecordingRuntime()
    service = YujinLocalConversationService(runtime=runtime)

    service.reply(
        project_id="proj-1",
        user_text="썸네일 만들 프롬프트 추천해 줘",
        project_context=YujinProjectContext(
            title="제목",
            script_excerpt="가" * 10_000,
            scene_captions=tuple(f"장면 {index} 끝" for index in range(100)),
        ),
    )

    prompt = runtime.calls[0]["prompt"]
    assert "가" * 100 in prompt
    assert "가" * 2_000 not in prompt
    assert "장면 0 끝" in prompt
    assert "장면 99 끝" not in prompt
