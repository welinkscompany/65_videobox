from __future__ import annotations

from math import isfinite
from datetime import datetime, timedelta
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from videobox_core_engine.overlay_shapes import (
    SHAPE_OVERLAY_MOTION_SET,
    SHAPE_OVERLAY_MOTIONS,
    SHAPE_OVERLAY_SHAPES,
    canonical_shape_overlay_shape,
)
from videobox_core_engine.scene_video_service import SceneVideoQuality
from videobox_domain_models.yujin_memory import YujinMemoryCandidate


class CreateProjectRequest(BaseModel):
    name: str = Field(min_length=1)


class RenameProjectRequest(BaseModel):
    # `extra="forbid"`: a caller that also sends `status` or `project_id` gets
    # told, rather than watching the request succeed while those fields were
    # silently dropped. Only the display name is editable here.
    model_config = ConfigDict(extra="forbid", strict=True)

    name: str = Field(min_length=1, max_length=200)


class OutputVariantCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    source_session_id: str = Field(min_length=1, max_length=256)
    kind: Literal["vertical_highlight"]
    variant_id: str | None = Field(default=None, min_length=1, max_length=256)


class OutputVariantPatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    expected_variant_revision: int = Field(ge=0)
    patch: dict[str, Any]


class OutputVariantRebaseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    new_master_revision: int = Field(ge=1)
    changed_fields: list[str] = Field(default_factory=list, max_length=32)


class OutputVariantMaterializeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    expected_master_session_revision: int | None = Field(default=None, ge=1)


class CreationBriefCreateRequest(BaseModel):
    script_filename: str = Field(min_length=1)
    script_text: str
    idempotency_key: str = Field(min_length=1)
    capability_profile: dict[str, Any] = Field(default_factory=dict)
    script_asset_id: str | None = None


class CreationBriefRevisionRequest(BaseModel):
    expected_revision: int = Field(ge=1)


class CreationBriefPreviousQuestionRequest(CreationBriefRevisionRequest):
    pass


class CreationBriefAnswerRequest(CreationBriefRevisionRequest):
    question_id: str | None = None
    answer: str = Field(min_length=1)


class CreationBriefSummaryRequest(CreationBriefRevisionRequest):
    summary: str = Field(min_length=1)


class DraftReadinessCreateRequest(BaseModel):
    brief_id: str = Field(min_length=1)
    narration_choice: dict[str, Any]
    idempotency_key: str = Field(min_length=1)
    expected_brief_revision: int = Field(ge=1)
    capability: dict[str, Any] = Field(default_factory=dict)


class DraftReadinessRevisionRequest(CreationBriefRevisionRequest):
    pass


class DraftReadinessCandidateRequest(DraftReadinessRevisionRequest):
    asset_id: str
    skipped: bool


class DraftReadinessCandidateRangeRequest(DraftReadinessRevisionRequest):
    asset_id: str
    start_sec: float = Field(ge=0)
    end_sec: float = Field(gt=0)


class AtomicDraftBundleCreateRequest(BaseModel):
    brief_id: str = Field(min_length=1)
    readiness_id: str = Field(min_length=1)
    expected_brief_revision: int = Field(ge=1)
    expected_readiness_revision: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1)
    allow_placeholder: bool = False
    # Task 33: long-form is the default; shortform asks for vertical here.
    orientation: Literal["landscape", "vertical"] | None = None


class ProjectResponse(BaseModel):
    project_id: str
    name: str
    status: str
    root_storage_uri: str


class ProjectListResponse(BaseModel):
    projects: list[ProjectResponse]


class HermesProjectStatusResponse(BaseModel):
    project_id: str
    name: str
    status: str
    updated_at: str
    has_editing_session: bool
    latest_session_revision: int | None = None


class HermesYujinStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    state: Literal[
        "not_configured",
        "stopped",
        "starting",
        "http_ready",
        "provider_ready",
        "chat_verified",
        "degraded",
    ]
    http_ready: bool
    provider_ready: bool
    chat_verified: bool
    checked_at: datetime
    last_chat_verified_at: datetime | None = None
    restart_available: Literal[False] = False
    status_basis: Literal["application_path"] = "application_path"

    @model_validator(mode="after")
    def timestamps_are_aware_and_ordered(
        self,
    ) -> "HermesYujinStatusResponse":
        timestamps = (self.checked_at, self.last_chat_verified_at)
        if any(
            value is not None
            and (
                value.tzinfo is None
                or value.utcoffset() is None
                or value.utcoffset() != timedelta(0)
            )
            for value in timestamps
        ) or (
            self.last_chat_verified_at is not None
            and self.last_chat_verified_at > self.checked_at
        ):
            raise ValueError("hermes_yujin_status_timestamp_invalid")
        exact = {
            "not_configured": (False, False, False),
            "stopped": (False, False, False),
            "starting": (False, False, False),
            "http_ready": (True, False, False),
            "provider_ready": (True, True, False),
            "chat_verified": (True, True, True),
        }
        readiness = (
            self.http_ready,
            self.provider_ready,
            self.chat_verified,
        )
        if (
            self.state in exact
            and readiness != exact[self.state]
        ) or (
            self.state == "degraded"
            and (self.provider_ready or self.chat_verified)
        ):
            raise ValueError("hermes_yujin_status_invariant_invalid")
        return self


MemorySourceMessageId = Annotated[
    str,
    Field(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$",
        strict=True,
    ),
]


class YujinMemoryCandidateCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conversation_id: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$",
        strict=True,
    )
    client_request_id: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$",
        strict=True,
    )
    source_message_ids: tuple[MemorySourceMessageId, ...] = Field(
        min_length=1,
        max_length=8,
    )
    memory_scope: Literal["creator"]
    category: Literal["pacing", "caption", "audio", "tone", "workflow"]
    proposed_text: str = Field(
        min_length=1,
        max_length=280,
        strict=True,
    )

    @model_validator(mode="after")
    def source_ids_are_unique(
        self,
    ) -> "YujinMemoryCandidateCreateRequest":
        if len(set(self.source_message_ids)) != len(self.source_message_ids):
            raise ValueError("memory_candidate_source_ids_invalid")
        return self


class YujinMemoryCandidateResponse(YujinMemoryCandidate):
    storage_status: Literal[
        "not_requested",
        "claimed",
        "event_pending",
        "stored",
        "failed_retryable",
        "ambiguous",
        "deleted",
    ]
    retryable: bool


class YujinMemoryCandidateListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidates: list[YujinMemoryCandidateResponse]


class YujinMemoryStoreRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_request_id: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$",
        strict=True,
    )


class YujinMemoryStoreResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    status: Literal["approved"]
    storage_status: Literal[
        "not_requested",
        "claimed",
        "event_pending",
        "stored",
        "failed_retryable",
        "ambiguous",
        "deleted",
    ]
    retryable: bool


class DirectorConversationCreateRequest(BaseModel):
    session_id: str = Field(min_length=1)


class DirectorConversationResponse(BaseModel):
    conversation_id: str
    project_id: str
    session_id: str


class DirectorMessageSubmitRequest(BaseModel):
    session_id: str = Field(min_length=1)
    client_message_id: str = Field(min_length=1)
    text: str = Field(min_length=1)


class HermesRunCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(min_length=1, max_length=128)
    client_message_id: str = Field(min_length=1, max_length=128)
    text: str = Field(min_length=1, max_length=20_000)
    expected_session_revision: int = Field(ge=1, strict=True)
    selected_segment_id: str | None = Field(default=None, min_length=1, max_length=256)


class HermesRunCreateResponse(BaseModel):
    run_id: str
    conversation_id: str
    events_url: str


class HermesStreamEvent(BaseModel):
    event_id: int
    event_type: Literal[
        "run_started", "text_delta", "blocked", "run_completed"
    ]
    text: str = ""
    retryable: bool = False


class DirectorReferenceResponse(BaseModel):
    reference_code: str
    immutable_id: str | dict[str, str]
    source: str


class DirectorDisambiguationResponse(BaseModel):
    status: str
    options: list[DirectorReferenceResponse]


class DirectorActionIntentResponse(BaseModel):
    action: str
    target: DirectorReferenceResponse
    proposal_preflight: dict[str, str | int] | None = None


class DirectorMessageResponse(BaseModel):
    message_id: str
    conversation_id: str
    project_id: str
    session_id: str
    role: str
    text: str
    proposal_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    client_message_id: str | None = None
    created_at: str


class DirectorMessageListResponse(BaseModel):
    messages: list[DirectorMessageResponse]


class DirectorMessageExchangeResponse(BaseModel):
    user_message: DirectorMessageResponse
    assistant_message: DirectorMessageResponse
    disambiguation: DirectorDisambiguationResponse | None = None
    reference: DirectorReferenceResponse | None = None
    action_intent: DirectorActionIntentResponse | None = None


class AssetRegistrationRequest(BaseModel):
    source_path: str = Field(min_length=1)


class BrollAssetRegistrationRequest(AssetRegistrationRequest):
    title: str | None = None
    tags: list[str] = Field(default_factory=list)


class SourceVideoStartResponse(BaseModel):
    """찍어 둔 영상으로 시작할 때 화면이 받는 것."""

    asset_id: str
    script_text: str
    #: 자막이 어디에 놓일지는 받아쓴 구간이 정한다. 문장만 돌려주면 자막이
    #: 말한 자리에 안 붙는다.
    spoken_segment_count: int


class RetakeCandidateResponse(BaseModel):
    """다시 들어볼 구간 하나. owner 요청(2026-08-29): 잘못 발음한 곳을 컷 편집으로
    날리기 전에, 어디를 왜 후보로 골랐는지부터 말해 줘야 한다."""

    segment_index: int
    start_sec: float
    end_sec: float
    text: str
    reason: Literal["low_confidence", "retry_cue", "retry_cue_precursor"]


class SourceVoiceSegmentResponse(BaseModel):
    """받아쓴 구간 하나. 화면이 다시 들어볼 후보만 빼고 나머지를 이어 붙여
    대본을 다시 만들 수 있도록, `script_text`(전체 이어 붙인 글)와 별개로
    구간 하나하나를 그대로 내려준다 -- 문자열 치환으로 지우면 같은 문장이
    두 번 나올 때 엉뚱한 곳이 지워질 수 있다."""

    segment_index: int
    text: str


class SourceVoiceStartResponse(BaseModel):
    """녹음한 목소리만으로 시작할 때 화면이 받는 것 -- `SourceVideoStartResponse`와
    같은 모양에 다시 들어볼 구간 후보와 구간별 원문을 얹었다."""

    asset_id: str
    script_text: str
    spoken_segment_count: int
    segments: list[SourceVoiceSegmentResponse]
    retake_candidates: list[RetakeCandidateResponse]


class SceneImageCreateRequest(BaseModel):
    """대본의 한 장면에 얹을 그림 하나. §10.14 조항 2-C."""

    prompt: str = Field(min_length=1)
    segment_id: str = Field(min_length=1)
    # 세로가 기본이 되면 F-9가 재발한다 -- 롱폼까지 전부 세로로 렌더된 적이 있다.
    vertical: bool = False
    duration_sec: float = Field(default=5.0, gt=0)
    gap_slot_id: str | None = None


class SceneImageResponse(BaseModel):
    image_asset_id: str
    scene_asset_id: str
    segment_id: str
    title: str
    #: owner가 쓴 줄. 한국어일 수 있다.
    prompt: str
    #: 실제로 그림 모델에 들어간 영어 묘사. 둘이 다를 수 있어 따로 남긴다.
    image_prompt: str = ""
    seed: int
    elapsed_sec: float | None = None
    # 상업 이용이 열려 있는지. **모르면 `None`이다** -- 아는 척하지 않는다.
    commercial_use_is_unrestricted: bool | None = None


class SceneImageListResponse(BaseModel):
    images: list[SceneImageResponse]


class SceneVideoCreateRequest(BaseModel):
    """대본의 한 장면에 얹을 짧은 실제 동영상 하나. owner 결정 2026-08-29(2회차) --
    `SceneImageCreateRequest`(정지 이미지+zoompan)와는 별개 경로다."""

    prompt: str = Field(min_length=1)
    segment_id: str = Field(min_length=1)
    vertical: bool = False
    gap_slot_id: str | None = None
    make_gif: bool = False
    #: 빠른 미리보기(owner 요청 2026-08-29, 3회차). 실측: preview는 약 12초,
    #: full은 약 18~23분(1920x1080·81프레임·20스텝).
    quality: SceneVideoQuality = "full"


class SceneVideoStartResponse(BaseModel):
    """실측(2026-08-29): 1920x1080·81프레임·20스텝이 5분을 넘겨 nginx 330초
    타임아웃보다 오래 걸린다 -- 그래서 이 요청은 작업만 걸고 바로 202로 돌아온다."""

    job_id: str
    status: Literal["processing"]


class SceneVideoResult(BaseModel):
    scene_asset_id: str
    gif_asset_id: str | None = None
    #: 자료실(여러 프로젝트가 나눠 쓰는 라이브러리) 등록 결과. owner 요청
    #: (2026-08-29 3회차) -- 프로젝트 자산과 별개로 검색 가능하게 남긴다.
    #: 등록에 실패해도 위 프로젝트 자산은 그대로라 `None`일 수 있다.
    library_asset_id: str | None = None
    gif_library_asset_id: str | None = None
    #: 코드리뷰(2026-08-30)로 잡힌 결함 -- 등록 실패가 어디에도 안 남아서
    #: 왜 안 됐는지 알 방법이 없었다. `library_ingest`가 아예 꺼져 있는
    #: 정상 상태(`library_asset_id is None`이지만 오류는 아님)와 실제 등록
    #: 실패를 구분하려면 이 필드가 필요하다.
    library_ingest_error: str | None = None
    gif_library_ingest_error: str | None = None
    segment_id: str
    title: str
    prompt: str
    video_prompt: str = ""
    quality: SceneVideoQuality = "full"
    seed: int
    elapsed_sec: float | None = None


class SceneVideoStatusResponse(BaseModel):
    job_id: str
    status: Literal["processing", "succeeded", "failed"]
    result: SceneVideoResult | None = None
    error_detail: str | None = None


class ScriptDraftCreateRequest(BaseModel):
    """주제 한 줄에서 대본 초안을 받는다.

    길이와 장면 수를 함께 싣는다 -- 60초 다섯 장면과 3분 열 장면은 전혀 다른
    글이라, 안 물어보면 매번 다른 길이가 돌아온다.
    """

    topic: str = Field(min_length=1, max_length=500)
    duration_sec: int = Field(default=60, ge=5, le=1800)
    scene_count: int = Field(default=5, ge=1, le=20)

    @field_validator("topic")
    @classmethod
    def _topic_is_not_blank(cls, value: str) -> str:
        # 공백만 적어 보내면 모델을 깨우기 전에 막는다.
        if not value.strip():
            raise ValueError("topic must not be blank")
        return value.strip()


class ScriptDraftSceneResponse(BaseModel):
    scene_number: int
    narration: str
    #: 그 장면에서 보여 줄 그림. 비어 있을 수 있다.
    visual: str = ""


class ScriptDraftResponse(BaseModel):
    title: str
    #: owner가 고칠 글 한 덩이. 장면 줄을 이어 붙인 것이라 둘이 어긋나지 않는다.
    script_text: str
    scenes: list[ScriptDraftSceneResponse]


class CreationRecommendationSetRequest(BaseModel):
    """대본을 확정하기 전, 주제 하나로 만들 소재 세트를 미리 본다.

    owner 요청(2026-08-28): "주제 하나로 BGM+이미지스타일+AI보이스까지 세트로
    추천." `script_text`가 있으면 그걸로(더 정확하게) 찾고, 없으면 `topic`만으로도
    동작한다 -- 대본이 아직 없는 순간에도 미리 보여 줄 수 있어야 한다.
    """

    topic: str = Field(min_length=1, max_length=500)
    script_text: str = Field(default="", max_length=20000)


class BgmRecommendationResponse(BaseModel):
    library_asset_id: str
    description: str = ""
    duration_seconds: float | None = None
    score: float


class ImageStyleRecommendationResponse(BaseModel):
    style_id: str
    name: str
    #: 이미지 생성 프롬프트 뒤에 그대로 덧붙이는 영어 키워드. 실제로 적용하는
    #: 곳(`scene_image_service.py`)은 이번 범위 밖이다 -- 여기는 추천만 한다.
    prompt_suffix: str
    reason: str


class VoiceRecommendationResponse(BaseModel):
    asset_id: str | None = None
    filename: str | None = None
    #: 등록된 목소리가 없을 때 무엇을 하면 되는지. 화면이 빈 값을 보고 추측하지
    #: 않도록 말로 준다.
    note: str


class CreationRecommendationSetResponse(BaseModel):
    bgm: list[BgmRecommendationResponse]
    image_style: ImageStyleRecommendationResponse
    voice: VoiceRecommendationResponse
    #: 임베딩 모델이 없어 BGM 추천이 단어 매칭으로 떨어졌는지. 화면이 "뜻으로
    #: 찾음" 배지를 거짓으로 달지 않게 한다(`library_assets.py`의 `semantic`과 같은 뜻).
    bgm_semantic: bool


class TTSCandidateRequest(BaseModel):
    segment_text: str = Field(min_length=1)
    voice_sample_asset_id: str = Field(min_length=1)
    segment_id: str | None = None
    target_duration_sec: float | None = Field(default=None, gt=0)


class TTSCandidateRecordResponse(BaseModel):
    candidate_id: str
    project_id: str
    segment_id: str
    asset_id: str
    source_text: str
    technical_status: str = "legacy_unverified"
    operator_review_status: str = "pending"
    target_duration_sec: float | None = None
    actual_duration_sec: float | None = None
    failure_code: str | None = None
    created_at: str


class TTSCandidateListResponse(BaseModel):
    candidates: list[TTSCandidateRecordResponse]


class BrollBatchAssetRegistrationRequest(BaseModel):
    source_paths: list[str] = Field(default_factory=list)
    source_directory: str | None = None
    recursive: bool = False
    tags: list[str] = Field(default_factory=list)
    title_by_source_path: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_sources(self) -> "BrollBatchAssetRegistrationRequest":
        self.source_paths = [str(path).strip() for path in self.source_paths if str(path).strip()]
        if self.source_directory is not None:
            self.source_directory = self.source_directory.strip() or None
        self.tags = [str(tag).strip() for tag in self.tags if str(tag).strip()]
        self.title_by_source_path = {
            str(path).strip(): str(title).strip()
            for path, title in self.title_by_source_path.items()
            if str(path).strip() and str(title).strip()
        }
        if not self.source_paths and not self.source_directory:
            raise ValueError("source_paths or source_directory is required.")
        return self


class AssetResponse(BaseModel):
    asset_id: str
    asset_type: str
    storage_uri: str


class YoutubeReferenceImportRequest(BaseModel):
    """owner 요청(2026-08-29): "내 유튜브 영상 있는걸로 학습은 안돼?" 본인이
    이미 올린 본인 영상만 대상이라는 전제를 화면 문구가 말한다."""

    url: str = Field(min_length=1, max_length=2000)


class ReferencePacingResponse(BaseModel):
    """컷 빠르기만 잰 결과다 -- 지금은 화면에 보여주기만 하고, 실제 자동 컷
    설정에 자동으로 먹이지 않는다(전역 설정이라 프로젝트별로 못 바꾼다)."""

    average_clip_duration_sec: float
    clip_count: int
    shortest_clip_sec: float
    longest_clip_sec: float


class ReferenceColorResponse(BaseModel):
    """색감만 잰 결과다 -- 전문 색보정은 이 제품 범위 밖이라(CLAUDE.md §2.1)
    실제로 입히지 않는다. 숫자만 보여준다."""

    average_brightness: float
    average_colorfulness: float
    warm_cool_bias: float
    sample_count: int


class YoutubeReferenceImportResponse(BaseModel):
    voice_sample_asset_id: str
    pacing: ReferencePacingResponse
    color: ReferenceColorResponse


class YoutubeReferenceImportStartResponse(BaseModel):
    """`from-youtube`를 걸면 바로 이걸 받는다(owner 결정 2026-08-29: 비동기로).

    실제 결과는 `job_id`로 상태 확인 endpoint를 불러 받는다."""

    job_id: str
    status: Literal["processing"]


class YoutubeReferenceImportStatusResponse(BaseModel):
    job_id: str
    status: Literal["processing", "succeeded", "failed"]
    result: YoutubeReferenceImportResponse | None = None
    error_detail: str | None = None


class BrowserPreviewResponse(BaseModel):
    status: Literal["pending", "running", "ready", "failed"]
    job_id: str | None = None
    content_url: str | None = None
    source_sha256: str
    profile: str
    error_code: str | None = None


class TTSCandidateResponse(AssetResponse):
    candidate_id: str | None = None
    segment_id: str | None = None
    source_text: str | None = None
    technical_status: str = "legacy_unverified"
    operator_review_status: str = "pending"
    target_duration_sec: float | None = None
    actual_duration_sec: float | None = None
    failure_code: str | None = None


class AssetArchiveItemResponse(AssetResponse):
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str
    source_path: str | None = None


class MediaAnalysisReviewRequest(BaseModel):
    tags: dict[str, list[str]]


class AssetListResponse(BaseModel):
    assets: list[AssetArchiveItemResponse]


class AutoCutBlackRegionRequest(BaseModel):
    start: float = Field(ge=0)
    end: float = Field(ge=0)

    @model_validator(mode="after")
    def validate_bounds(self) -> "AutoCutBlackRegionRequest":
        if self.end <= self.start:
            raise ValueError("black_regions end must be greater than start.")
        return self


class AutoCutSegmentSampleRequest(BaseModel):
    start_sec: float = Field(ge=0)
    end_sec: float = Field(ge=0)
    avg_brightness: float | None = Field(default=None, ge=0)
    scene_change_count: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_bounds(self) -> "AutoCutSegmentSampleRequest":
        if self.end_sec <= self.start_sec:
            raise ValueError("segment_samples end_sec must be greater than start_sec.")
        return self


class AutoCutPlanRequest(BaseModel):
    raw_video_asset_id: str = Field(min_length=1)
    total_duration: float = Field(gt=0)
    scene_timestamps: list[float] = Field(default_factory=list)
    black_regions: list[AutoCutBlackRegionRequest] = Field(default_factory=list)
    segment_samples: list[AutoCutSegmentSampleRequest] = Field(default_factory=list)


class AutoCutDetectRequest(BaseModel):
    raw_video_asset_id: str = Field(min_length=1)


class AutoCutPlannedSegmentResponse(BaseModel):
    start_sec: float
    end_sec: float


class AutoCutKeptSegmentResponse(AutoCutPlannedSegmentResponse):
    duration_sec: float
    avg_brightness: float | None = None
    scene_change_count: int | None = None
    reasons: list[str] = Field(default_factory=list)


class AutoCutPlanResponse(BaseModel):
    asset_id: str
    storage_uri: str
    should_auto_cut: bool
    scene_detection_filter: str
    blackdetect_filter: str
    planned_segments: list[AutoCutPlannedSegmentResponse] = Field(default_factory=list)
    kept_segments: list[AutoCutKeptSegmentResponse] = Field(default_factory=list)


class StartTranscriptionRequest(BaseModel):
    narration_asset_id: str = Field(min_length=1)


class StartJobResponse(BaseModel):
    job_id: str
    status: str


class JobRecordResponse(BaseModel):
    job_id: str
    project_id: str
    job_type: str
    status: str
    input_ref: str | None = None
    output_ref: str | None = None
    error_message: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    progress_percent: int | None = None


class JobListResponse(BaseModel):
    jobs: list[JobRecordResponse]


class HomeSummaryResponse(BaseModel):
    """What the three home cards need, so none of them has to guess."""

    finished_video_count: int
    has_draft: bool
    asset_gap_count: int


class WorkspaceNextActionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    label: str = Field(min_length=1)
    href: str = Field(min_length=1)


class ProjectWorkspaceSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    project_id: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    updated_at: str = Field(min_length=1)
    current_stage: Literal["plan", "assets", "edit", "review", "output"]
    state: Literal["ready", "attention", "blocked"]
    thumbnail_url: str | None = None
    finished_video_count: int = Field(ge=0)
    next_action: WorkspaceNextActionResponse


class JobRecordWithProjectResponse(JobRecordResponse):
    project_name: str


class AllJobsResponse(BaseModel):
    jobs: list[JobRecordWithProjectResponse]


class TranscriptionJobResponse(StartJobResponse):
    transcript_uri: str


class StartSegmentAnalysisRequest(BaseModel):
    transcription_job_id: str = Field(min_length=1)
    script_asset_id: str | None = None


class StartRecommendationRequest(BaseModel):
    segment_analysis_job_id: str = Field(min_length=1)


class BuildTimelineRequest(BaseModel):
    segment_analysis_job_id: str = Field(min_length=1)
    recommendation_job_ids: list[str] = Field(default_factory=list)
    orientation: Literal["landscape", "vertical"] | None = None


class OutputJobRequest(BaseModel):
    timeline_job_id: str = Field(min_length=1)


class VariantRenderRequest(BaseModel):
    session_id: str = Field(min_length=1)
    variant_ids: list[str] = Field(default_factory=list, max_length=3)

    @field_validator("variant_ids")
    @classmethod
    def variant_ids_are_unique(cls, value: list[str]) -> list[str]:
        normalized = [item.strip() for item in value]
        if any(not item for item in normalized) or len(set(normalized)) != len(normalized):
            raise ValueError("variant_ids_must_be_unique")
        return normalized


class CreateEditingSessionRequest(BaseModel):
    timeline_job_id: str = Field(min_length=1)


class CreateScriptDraftEditingSessionRequest(BaseModel):
    script_asset_id: str = Field(min_length=1)


class NarrationAlignmentSegmentRequest(BaseModel):
    source_script_segment_id: str = Field(min_length=1)
    start_sec: float
    end_sec: float


class NarrationRecordingSyncRequest(BaseModel):
    """Sync a script draft to a recording the owner actually made."""

    narration_asset_id: str = Field(min_length=1)
    expected_revision: int = Field(ge=1)


class NarrationAlignmentRequest(BaseModel):
    expected_revision: int = Field(ge=1)
    aligned_segments: list[NarrationAlignmentSegmentRequest] = Field(min_length=1)


class EditorPresetRequest(BaseModel):
    name: str = Field(min_length=1)
    style: dict[str, Any]
    global_scope: bool = False


class EditorFavoriteRequest(BaseModel):
    favorite_type: str = Field(pattern="^(media|preset)$")
    enabled: bool


class OptionalYujinCandidateAttestation(BaseModel):
    proposal_id: str | None = Field(default=None, min_length=1, max_length=256)
    candidate_id: str | None = Field(default=None, min_length=1, max_length=256)

    @model_validator(mode="after")
    def validate_optional_yujin_candidate_attestation(
        self,
    ) -> "OptionalYujinCandidateAttestation":
        if (self.proposal_id is None) != (self.candidate_id is None):
            raise ValueError("proposal_id and candidate_id must be provided together.")
        if self.proposal_id is not None:
            self.proposal_id = self.proposal_id.strip()
            self.candidate_id = self.candidate_id.strip() if self.candidate_id else None
            if not self.proposal_id or not self.candidate_id:
                raise ValueError("proposal_id and candidate_id must not be blank.")
        return self


class CaptionOverrideRequest(OptionalYujinCandidateAttestation):
    expected_revision: int = Field(ge=1)
    caption_text: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_caption_text(self) -> "CaptionOverrideRequest":
        caption_text = self.caption_text.strip()
        if not caption_text:
            raise ValueError("caption_text must not be blank.")
        self.caption_text = caption_text
        return self


class CaptionStyleMutationRequest(OptionalYujinCandidateAttestation):
    expected_revision: int = Field(ge=1)
    scope: str = Field(pattern="^(current_caption|selected_captions|from_current|whole_project|project_default)$")
    segment_ids: list[str] = Field(default_factory=list)
    style: dict[str, Any]


class CutActionOverrideRequest(BaseModel):
    expected_revision: int = Field(ge=1)
    cut_action: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_cut_action(self) -> "CutActionOverrideRequest":
        cut_action = self.cut_action.strip()
        if cut_action not in {"keep", "remove", "trim"}:
            raise ValueError("cut_action must be one of: keep, remove, trim.")
        self.cut_action = cut_action
        return self


class SegmentTransitionRequest(BaseModel):
    """이 장면으로 넘어올 때 쓸 전환.

    ``transition``이 ``None``이거나 ``{"type": "none"}``이면 전환을 끈다.
    실제 허용 값 검사는 `videobox_core_engine.transitions`가 한 벌만 갖는다 --
    여기서 목록을 또 적으면 두 벌이 어긋난다.
    """

    expected_revision: int = Field(ge=1)
    transition: dict[str, object] | None = None


class BrollOverrideRequest(BaseModel):
    expected_revision: int = Field(ge=1)
    asset_id: str = Field(min_length=1)
    media_controls: dict[str, object] | None = None

    @model_validator(mode="after")
    def validate_asset_id(self) -> "BrollOverrideRequest":
        asset_id = self.asset_id.strip()
        if not asset_id:
            raise ValueError("asset_id must not be blank.")
        self.asset_id = asset_id
        return self


class SegmentSplitRequest(BaseModel):
    expected_revision: int = Field(ge=1)
    split_sec: float = Field(ge=0, allow_inf_nan=False)


class SegmentMergeRequest(BaseModel):
    expected_revision: int = Field(ge=1)
    left_segment_id: str = Field(min_length=1)
    right_segment_id: str = Field(min_length=1)


class SegmentBoundsRequest(BaseModel):
    expected_revision: int = Field(ge=1)
    start_sec: float = Field(ge=0, allow_inf_nan=False)
    end_sec: float = Field(gt=0, allow_inf_nan=False)


class RipplePlaybackRateRequest(BaseModel):
    expected_revision: int = Field(ge=1)
    rate: Literal[1.0, 1.5, 2.0]


class SegmentOrderRequest(BaseModel):
    expected_revision: int = Field(ge=1)
    segment_ids: list[str] = Field(min_length=1)
    bounds_by_id: dict[str, dict[str, float]] | None = None

    @model_validator(mode="after")
    def validate_finite_bounds(self) -> "SegmentOrderRequest":
        for bounds in (self.bounds_by_id or {}).values():
            if not isinstance(bounds, dict) or not isfinite(float(bounds.get("start_sec", float("nan")))) or not isfinite(float(bounds.get("end_sec", float("nan")))):
                raise ValueError("segment_bounds_must_be_finite")
        return self


class TimelinePlacementChangeRequest(BaseModel):
    placement_id: str = Field(min_length=3)
    kind: Literal["broll", "bgm", "sfx", "overlay", "caption"]
    start_sec: float = Field(ge=0, allow_inf_nan=False)
    end_sec: float = Field(gt=0, allow_inf_nan=False)


class TimelinePlacementPatchRequest(BaseModel):
    expected_revision: int = Field(ge=1)
    changes: list[TimelinePlacementChangeRequest] = Field(min_length=1)


class TrackStateRequest(BaseModel):
    """한 트랙의 눈·음소거. 그 트랙에 뜻이 없는 값은 코어가 거절한다.

    `extra="forbid"`가 **꼭 필요하다.** pydantic 기본값(`ignore`)이면 오타 난
    키(`hiden`)가 조용히 버려져 빈 dict로 코어에 닿는다 -- 코어의 "뜻 없는
    값은 거절한다"가 영영 안 걸리고, 200에 revision까지 올라가는데 저장된 건
    없다(2026-08-23 코드리뷰에서 발견).
    """

    hidden: bool | None = None
    muted: bool | None = None
    model_config = {"extra": "forbid"}


class TrackStatesPatchRequest(BaseModel):
    """트랙 눈·음소거 전체. 보낸 것이 곧 전체 상태다(조각 병합 아님)."""

    expected_revision: int = Field(ge=1)
    track_states: dict[str, TrackStateRequest]


class EditingSessionRevisionRequest(BaseModel):
    expected_revision: int = Field(ge=1)


class SelectedRangePreviewRequest(BaseModel):
    start_sec: float = Field(ge=0)
    end_sec: float = Field(gt=0)


class VisualOverlayRequest(BaseModel):
    expected_revision: int = Field(ge=1)
    overlay_type: str = Field(min_length=1)
    asset_id: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_visual_overlay(self) -> "VisualOverlayRequest":
        overlay_type = self.overlay_type.strip()
        asset_id = self.asset_id.strip()
        if not overlay_type:
            raise ValueError("overlay_type must not be blank.")
        if not asset_id:
            raise ValueError("asset_id must not be blank.")
        self.overlay_type = overlay_type
        self.asset_id = asset_id
        return self


class ExplanationCardRequest(OptionalYujinCandidateAttestation):
    expected_revision: int = Field(ge=1)
    title: str = ""
    body: str = ""
    text: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_explanation_card(self) -> "ExplanationCardRequest":
        title = self.title.strip()
        body = self.body.strip()
        text = self.text.strip()
        if not text:
            raise ValueError("text must not be blank.")
        self.title = title
        self.body = body
        self.text = text
        return self


class ImageOverlayRequest(BaseModel):
    expected_revision: int = Field(ge=1)
    asset_id: str = Field(min_length=1)
    text: str = ""
    proposal_id: str | None = Field(default=None, min_length=1, max_length=256)
    candidate_id: str | None = Field(default=None, min_length=1, max_length=256)

    @model_validator(mode="after")
    def validate_image_overlay(self) -> "ImageOverlayRequest":
        if (self.proposal_id is None) != (self.candidate_id is None):
            raise ValueError("proposal_id and candidate_id must be provided together.")
        if not self.asset_id.strip():
            raise ValueError("asset_id must not be blank.")
        if self.proposal_id is None:
            self.asset_id = self.asset_id.strip()
            self.text = self.text.strip()
        else:
            self.proposal_id = self.proposal_id.strip()
            self.candidate_id = self.candidate_id.strip() if self.candidate_id else None
            if not self.proposal_id or not self.candidate_id:
                raise ValueError("proposal_id and candidate_id must not be blank.")
        return self


class ShapeOverlayRequest(BaseModel):
    """정지 도형·아이콘("여기를 보세요"). 프리셋만 받는다 -- 자유 좌표는 계획서 §4가
    범위 밖으로 못박았다.

    `motion`은 2026-08-20 승인(5항)으로 열린 **등장·퇴장·이동**이다. 여기서도
    프리셋만 받는다: 초 단위 시간이나 좌표를 받기 시작하면 그게 곧 승인 범위 밖인
    키프레임 편집기다.

    고를 수 있는 이름은 `overlay_shapes`가 정한 목록 하나뿐이다. 여기에 사본을
    적어 두면 렌더가 그리는 목록과 화면이 보내는 목록이 조용히 갈라진다.
    """

    expected_revision: int = Field(ge=1)
    shape: str
    vertical: Literal["top", "middle", "bottom"]
    horizontal: Literal["left", "center", "right"]
    size: Literal["small", "medium", "large"]
    # 안 보내면 `그대로`. 이 기능이 생기기 전 화면이 보내던 요청이 그대로 통한다.
    motion: str = "none"

    @field_validator("shape")
    @classmethod
    def validate_shape(cls, value: str) -> str:
        normalized = canonical_shape_overlay_shape(value)
        if normalized not in SHAPE_OVERLAY_SHAPES:
            raise ValueError(f"shape must be one of {sorted(SHAPE_OVERLAY_SHAPES)}: {value!r}")
        return normalized

    @field_validator("motion")
    @classmethod
    def validate_motion(cls, value: str) -> str:
        normalized = str(value or "none").strip().lower()
        if normalized not in SHAPE_OVERLAY_MOTION_SET:
            raise ValueError(
                f"motion must be one of {list(SHAPE_OVERLAY_MOTIONS)}: {value!r}"
            )
        return normalized


class TableOverlayRequest(OptionalYujinCandidateAttestation):
    expected_revision: int = Field(ge=1)
    columns: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)
    text: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_table_overlay(self) -> "TableOverlayRequest":
        text = self.text.strip()
        if not text:
            raise ValueError("text must not be blank.")
        self.columns = [str(item).strip() for item in self.columns]
        self.rows = [[str(cell).strip() for cell in row] for row in self.rows]
        self.text = text
        return self


class TTSReplacementRequest(OptionalYujinCandidateAttestation):
    expected_revision: int = Field(ge=1)
    recommendation_id: str = Field(min_length=1)
    asset_id: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_tts_replacement(self) -> "TTSReplacementRequest":
        recommendation_id = self.recommendation_id.strip()
        asset_id = self.asset_id.strip()
        if not recommendation_id:
            raise ValueError("recommendation_id must not be blank.")
        if not asset_id:
            raise ValueError("asset_id must not be blank.")
        self.recommendation_id = recommendation_id
        self.asset_id = asset_id
        return self


class TTSListeningReviewRequest(BaseModel):
    decision: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_decision(self) -> "TTSListeningReviewRequest":
        decision = self.decision.strip().lower()
        if decision not in {"approved", "rejected"}:
            raise ValueError("decision must be approved or rejected.")
        self.decision = decision
        return self


class PartialRegenerationRequest(BaseModel):
    expected_revision: int = Field(ge=1)
    segment_ids: list[str] = Field(min_length=1)
    fields: list[str] = Field(min_length=1)


class PartialRegenerationPreflightRequest(BaseModel):
    segment_ids: list[str] = Field(min_length=1)
    fields: list[str] = Field(min_length=1)


class PartialRegenerationResponse(BaseModel):
    job_id: str | None = None
    status: str | None = None
    session_id: str | None = None
    segment_ids: list[str] = Field(default_factory=list)
    fields: list[str] = Field(default_factory=list)
    downstream_steps: list[str] = Field(default_factory=list)
    targeted_segments: list[dict[str, object]] = Field(default_factory=list)
    affected_output_areas: list[str] = Field(default_factory=list)
    predicted_review_status_after_rerun: str = "unknown"
    prediction_reasons: list[str] = Field(default_factory=list)
    delta: dict[str, object] | None = None


class PartialRegenerationJobResponse(StartJobResponse):
    partial_regeneration_id: str
    session_id: str
    session_updated_at: str | None = None
    source_timeline_id: str
    timeline_id: str
    segment_ids: list[str] = Field(default_factory=list)
    fields: list[str] = Field(default_factory=list)
    downstream_steps: list[str] = Field(default_factory=list)
    regenerated_segments: list[dict[str, object]] = Field(default_factory=list)
    timeline: "TimelinePayloadResponse"
    created_at: str | None = None


class EditingSessionSegmentResponse(BaseModel):
    segment_id: str
    caption_text: str
    start_sec: float
    end_sec: float
    cut_action: str
    review_required: bool
    broll_override: dict[str, object] | None = None
    visual_overlays: list[dict[str, object]] = Field(default_factory=list)
    music_override: dict[str, object] | None = None
    sfx_override: dict[str, object] | None = None
    tts_replacement: dict[str, object] | None = None
    caption_style: dict[str, object] | None = None
    ripple_playback_rate: Literal[1.5, 2.0] | None = Field(default=None, exclude_if=lambda value: value is None)
    # 앞 장면에서 이 장면으로 넘어오는 방법.
    #
    # **안 고른 장면에는 이 칸이 아예 없다**(`source_script_segment_id`와 같은
    # 방식). 늘 실어 보내면 전환을 안 쓰는 장면의 응답 모양까지 바뀌고,
    # 실제로 그 모양을 그대로 비교하던 시험 둘이 깨졌다.
    transition_in: dict[str, object] | None = Field(default=None, exclude_if=lambda value: value is None)
    source_script_segment_id: str | None = Field(default=None, exclude_if=lambda value: value is None)


class MaterializeLibraryAssetRequest(BaseModel):
    project_id: str


class MediaInboxImportRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255)


class LibraryFavoriteRequest(BaseModel):
    enabled: bool


class LibraryAudioSearchRequest(BaseModel):
    """Ask the music and effects library what suits a scene."""

    query: str = Field(min_length=1)
    # A scene needs music, an effect, or footage -- never whichever kind
    # happens to score highest -- so the kind is required rather than optional.
    media_type: Literal["music", "sfx", "broll"]
    # Only footage has an orientation. Silently ignoring it elsewhere would let
    # the owner believe a filter was applied.
    orientation: Literal["가로", "세로"] | None = None
    limit: int = Field(default=5, ge=1, le=50)

    @model_validator(mode="after")
    def _orientation_only_for_footage(self) -> "LibraryAudioSearchRequest":
        if self.orientation is not None and self.media_type != "broll":
            raise ValueError("orientation_only_applies_to_broll")
        return self


class EditingSessionHistoryEntryResponse(BaseModel):
    mutation_type: str
    segment_id: str
    action_id: str | None = None
    label: str | None = None
    created_at: str | None = None
    reversible: bool | None = None
    blocked_reason: str | None = None
    caption_text: str | None = None
    cut_action: str | None = None
    asset_id: str | None = None
    overlay_type: str | None = None
    recommendation_id: str | None = None
    inverse_payload: dict[str, object] | None = None
    forward_payload: dict[str, object] | None = None


class EditingSessionResponse(BaseModel):
    session_id: str
    project_id: str
    timeline_id: str
    session_revision: int
    caption_style: dict[str, object] | None = None
    segments: list[EditingSessionSegmentResponse]
    history: list[EditingSessionHistoryEntryResponse] = Field(default_factory=list)
    undo_count: int = 0
    redo_count: int = 0
    created_at: str | None = None
    updated_at: str | None = None
    script_asset_id: str | None = Field(default=None, exclude_if=lambda value: value is None)
    timing_source: str | None = Field(default=None, exclude_if=lambda value: value is None)
    narration_alignment_required: bool | None = Field(default=None, exclude_if=lambda value: value is None)
    stale_proposal_source_script_segment_ids: list[str] | None = Field(default=None, exclude_if=lambda value: value is None)


class EditorFpsResponse(BaseModel):
    num: int = Field(gt=0)
    den: int = Field(gt=0)


class EditorOutputResponse(BaseModel):
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    sample_aspect_ratio: str
    rotation: int
    duration_sec: float = Field(ge=0)


class EditorMediaControlsResponse(BaseModel):
    volume: float | None = None
    crop: str | None = None
    speed: float | None = None
    gain_db: float | None = None
    fade_in_sec: float | None = None
    fade_out_sec: float | None = None
    ducking: bool | None = None
    fit: Literal["fit", "crop"] | None = None
    loop: bool | None = None
    pad: bool | None = None
    trim_start_sec: float | None = Field(default=None, ge=0)
    preserve_source_audio: bool | None = None
    in_sec: float | None = Field(default=None, ge=0)
    out_sec: float | None = Field(default=None, gt=0)
    # 색감(`filters.py`). 이 모델은 `extra="forbid"`라 여기 없으면 색감이 실린
    # 클립의 응답이 통째로 터진다 -- 조용히 빠지는 게 아니다.
    filter: dict[str, str] | None = None
    # 캡컷 대조로 들어온 것들(2026-09-01). **바로 위 경고가 가리키는 자리가
    # 여기다** -- `normalize_media_controls`에 칸을 늘리면 이 모델도 같이
    # 늘려야 한다. 2026-09-01에 손떨림 보정을 넣으면서 실제로 빠뜨렸고,
    # 그 클립의 설정을 한 번 저장한 뒤로는 편집기 화면이 통째로 안 열렸다.
    # 화면·단위 테스트로는 안 잡히고 전체 pytest에서만 나왔다.
    normalize_loudness: bool | None = None
    denoise: bool | None = None
    stabilize: bool | None = None
    preserve_pitch: bool | None = None
    zoom: float | None = None
    position_x_percent: float | None = None
    position_y_percent: float | None = None
    rotation_deg: float | None = None
    model_config = {"extra": "forbid"}


class EditorClipResponse(BaseModel):
    clip_id: str
    segment_id: str
    placement_id: str | None = None
    clip_type: Literal["narration", "broll", "bgm", "sfx", "overlay"]
    asset_id: str | None = None
    asset_uri: str | None = None
    start_sec: float = Field(ge=0)
    end_sec: float = Field(ge=0)
    media_controls: EditorMediaControlsResponse
    expected_content_sha256: str | None = None
    media_revision: str | None = None
    overlay_type: Literal["explanation_card", "image_overlay", "table_overlay", "shape_overlay"] | None = None
    overlay_payload: dict[str, object] = Field(default_factory=dict)


class EditorTrackResponse(BaseModel):
    track_id: str
    track_type: Literal["narration", "broll", "bgm", "sfx", "overlay"]
    clips: list[EditorClipResponse]
    # 눈·음소거는 여기 싣지 않는다. 화면은 맨 위 `track_states` 하나만 읽는다
    # (자막 트랙은 이 목록에 아예 안 실려 트랙 쪽으로는 못 읽는다).


class EditorCaptionStyleResponse(BaseModel):
    font_family: str
    font_size_px: int = Field(ge=12, le=160)
    text_color: str
    outline_color: str
    outline_width_px: int = Field(ge=0, le=12)
    background_color: str
    position_x_percent: int = Field(ge=0, le=100)
    position_y_percent: int = Field(ge=0, le=100)
    horizontal_align: Literal["left", "center", "right"]
    safe_area_enabled: bool
    shadow_blur_px: int = Field(ge=0)
    model_config = {"extra": "forbid"}


class EditorCaptionResponse(BaseModel):
    segment_id: str
    caption_id: str
    placement_id: str
    text: str
    start_sec: float = Field(ge=0)
    end_sec: float = Field(ge=0)
    style: EditorCaptionStyleResponse


class EditorGapSlotResponse(BaseModel):
    gap_id: str
    segment_id: str
    start_sec: float = Field(ge=0)
    end_sec: float = Field(ge=0)
    reason: str


class EditorSourceStatusResponse(BaseModel):
    status: Literal["current", "stale"]
    source_session_id: str | None = None
    source_session_revision: int | None = None


class EditorAuditionResponse(BaseModel):
    asset_urls: dict[str, str]


class EditorExactPreviewResponse(BaseModel):
    status: Literal["pending", "running", "succeeded", "failed", "stale", "unavailable"]
    url: str | None = None
    source_session_id: str | None = None
    source_session_revision: int | None = None
    generation_id: str | None = None
    timeline_start_sec: float | None = None
    timeline_end_sec: float | None = None
    artifact_revision: int | None = None
    fingerprint: str | None = None


class ExactPreviewRequestBody(BaseModel):
    expected_revision: int = Field(ge=1)
    start_sec: float | None = Field(default=None, ge=0)
    end_sec: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def _paired_range(self) -> "ExactPreviewRequestBody":
        if (self.start_sec is None) != (self.end_sec is None) or (
            self.start_sec is not None and self.end_sec is not None and self.end_sec <= self.start_sec
        ):
            raise ValueError("exact_preview_invalid_range")
        return self


class ExactPreviewResponse(BaseModel):
    status: Literal["pending", "running", "succeeded", "failed", "stale", "unavailable"]
    generation_id: str
    timeline_start_sec: float = Field(ge=0)
    timeline_end_sec: float = Field(gt=0)
    artifact_revision: int = Field(ge=1)
    fingerprint: str
    content_url: str | None = None
    error_message: str | None = None


class EditorPlaybackManifestResponse(BaseModel):
    """The editor boundary intentionally exposes seconds, never stored frames."""
    project_id: str
    session_id: str
    timeline_id: str
    session_revision: int
    timeline_version: str
    timebase: str
    fps: EditorFpsResponse
    output: EditorOutputResponse
    tracks: list[EditorTrackResponse]
    # 눈·음소거를 되읽는 단일 자리. 자막 트랙은 `tracks`에 안 실리므로
    # 트랙마다 붙은 값만으로는 자막 숨김을 읽을 수 없다(`track_states.py`).
    track_states: dict[str, dict[str, bool]] = {}
    captions: list[EditorCaptionResponse]
    gap_slots: list[EditorGapSlotResponse]
    source_status: EditorSourceStatusResponse
    audition: EditorAuditionResponse
    exact_preview: EditorExactPreviewResponse


class SegmentAnalysisRecord(BaseModel):
    segment_id: str | None = None
    text: str
    start_sec: float
    end_sec: float
    # Task 37: a silent draft is never transcribed, so its segments have no
    # confidence score and no cleanup decision. Requiring them made the review
    # screen fail to load for every draft the owner creates.
    confidence: float | None = None
    review_required: bool
    cleanup_decision: str | None = None
    review_reasons: list[str] = Field(default_factory=list)
    provider_trace: "ProviderTraceResponse"


class ProviderTraceResponse(BaseModel):
    routing_mode: str
    final_provider: str
    fallback_reasons: list[str] = Field(default_factory=list)


class RecommendationItemResponse(BaseModel):
    recommendation_id: str
    target_segment_id: str
    recommendation_type: str
    selected_asset_id: str | None = None
    score: float
    reason: str
    auto_apply_allowed: bool
    review_required: bool
    decision_state: str | None = None
    payload: dict[str, object]
    created_at: str
    provider_trace: ProviderTraceResponse


class SegmentAnalysisJobResponse(StartJobResponse):
    segments: list[SegmentAnalysisRecord]


class RecommendationJobResponse(StartJobResponse):
    recommendation_type: str
    recommendations: list[RecommendationItemResponse]


class TimelineClipResponse(BaseModel):
    clip_id: str
    segment_id: str
    # Task 36: caption clips are rendered from text and have no source file, so
    # requiring an asset_uri made every draft timeline unreadable. Clips that do
    # have one still carry it.
    asset_uri: str | None = None
    start_sec: float
    end_sec: float
    clip_type: str
    recommendation_id: str | None = None
    asset_id: str | None = None
    media_controls: dict[str, object] = Field(default_factory=dict)
    expected_content_sha256: str | None = None
    media_revision: str | None = None
    warning_provenance: list[str] = Field(default_factory=list)


class TimelineTrackResponse(BaseModel):
    track_id: str
    track_type: str
    clips: list[TimelineClipResponse]


class ReviewFlagResponse(BaseModel):
    code: str
    segment_id: str
    message: str


class TimelinePayloadResponse(BaseModel):
    timeline_id: str
    project_id: str
    version: str
    output_mode: str
    review_status: str = "draft"
    # Task 33/36: the canvas the draft renders to. Absent on older timelines
    # that never set one, which then fall back to CompositionPlan's default.
    output: dict[str, int] | None = None
    tracks: list[TimelineTrackResponse]
    review_flags: list[ReviewFlagResponse]
    applied_recommendations: list[RecommendationItemResponse] = Field(default_factory=list)
    pending_recommendations: list[RecommendationItemResponse] = Field(default_factory=list)
    created_at: str | None = None
    source_session_id: str | None = None
    source_session_revision: int | None = None
    source_variant_id: str | None = None
    source_variant_revision: int | None = None


class TimelineJobResponse(StartJobResponse):
    timeline: TimelinePayloadResponse


class ReviewSnapshotResponse(BaseModel):
    project_id: str
    timeline_id: str
    source_variant_id: str | None = None
    source_variant_revision: int | None = None
    review_status: str
    segments: list[SegmentAnalysisRecord]
    applied_recommendations: list[RecommendationItemResponse]
    pending_recommendations: list[RecommendationItemResponse]
    review_flags: list[ReviewFlagResponse]
    operator_guidance: "OperatorGuidanceResponse"


class OperatorGuidanceResponse(BaseModel):
    summary: str
    action_items: list[str]
    provider_trace: ProviderTraceResponse


class ReviewApprovalResponse(BaseModel):
    timeline_id: str
    project_id: str
    review_status: str
    approved_at: str | None = None
    updated_at: str
    source_session_id: str | None = None
    source_session_revision: int | None = None
    source_variant_id: str | None = None
    source_variant_revision: int | None = None
    is_current: bool = True
    invalidated_at: str | None = None
    invalidated_reason: str | None = None


class PreviewArtifactResponse(BaseModel):
    preview_id: str
    project_id: str
    timeline_id: str
    file_uri: str
    player_uri: str | None = None
    status: str
    artifact_kind: str
    notes: list[str] = Field(default_factory=list)
    provider_trace: ProviderTraceResponse
    created_at: str | None = None
    source_session_id: str | None = None
    source_session_revision: int | None = None
    is_current: bool = True
    invalidated_at: str | None = None
    invalidated_reason: str | None = None


class PreviewJobResponse(StartJobResponse):
    preview: PreviewArtifactResponse


class PreviewShareCreateResponse(BaseModel):
    """owner 요청(2026-08-28): 프리뷰 공유 링크. 토큰은 이 응답에서만 나온다 --
    이후 목록(`PreviewShareSummaryResponse`)에는 다시 싣지 않는다."""

    share_id: str
    token: str
    url: str


class PreviewShareStatusResponse(BaseModel):
    status: Literal["active"]


class PreviewShareSummaryResponse(BaseModel):
    share_id: str
    project_id: str
    export_id: str
    created_at: str
    revoked_at: str | None = None


class ExportArtifactResponse(BaseModel):
    export_id: str
    project_id: str
    timeline_id: str
    export_type: str
    file_uri: str
    subtitle_file_uri: str | None = None
    status: str
    adapter: str | None = None
    capcut_tracks: list[dict[str, Any]] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    provider_trace: ProviderTraceResponse
    created_at: str | None = None
    source_session_id: str | None = None
    source_session_revision: int | None = None
    is_current: bool = True
    invalidated_at: str | None = None
    invalidated_reason: str | None = None


class ExportJobResponse(StartJobResponse):
    export: ExportArtifactResponse


class FinalRenderArtifactResponse(BaseModel):
    export_id: str
    timeline_id: str
    export_type: str
    file_uri: str
    status: str
    created_at: str | None = None
    source_session_id: str | None = None
    source_session_revision: int | None = None
    is_current: bool = True
    invalidated_at: str | None = None
    invalidated_reason: str | None = None
    # 렌더가 실제로 잰 결과. 재지 못했거나 옛 완성본이면 None이고, 그때 화면은
    # 소리에 대해 아무 말도 하지 않는다.
    has_sound: bool | None = None
    # 기계가 잰 것(quality_facts)과 사람이 정한 것(owner_verdict)을 갈라서 싣는다.
    # 나중에 무엇을 근거로 배웠는지 구분할 수 있어야 한다.
    quality_facts: dict[str, Any] = Field(default_factory=dict)
    owner_verdict: str | None = None
    owner_verdict_note: str | None = None
    owner_verdict_at: str | None = None


class FinalRenderVerdictRequest(BaseModel):
    verdict: Literal["good", "bad"]
    note: str | None = None


class FinalRenderJobResponse(StartJobResponse):
    render: FinalRenderArtifactResponse | None = None
    error_message: str | None = None


class VariantRenderItemResponse(BaseModel):
    variant_id: str
    variant_kind: str | None = None
    timeline_id: str | None = None
    timeline_job_id: str | None = None
    job_id: str | None = None
    status: str
    error_code: str | None = None
    content_url: str | None = None


class VariantRenderBatchResponse(BaseModel):
    project_id: str
    status: str
    items: list[VariantRenderItemResponse]


class CapCutDraftExportArtifactResponse(BaseModel):
    export_id: str
    timeline_id: str
    export_type: str
    file_uri: str
    status: str
    created_at: str | None = None
    notes: list[str] = Field(default_factory=list)
    handoff: "CapCutDraftHandoffResponse | None" = None
    source_session_id: str | None = None
    source_session_revision: int | None = None
    is_current: bool = True
    invalidated_at: str | None = None
    invalidated_reason: str | None = None


class CapCutDraftHandoffResponse(BaseModel):
    status: str
    source_file_uri: str
    registered_project_path: str | None = None
    error_message: str | None = None
    registered_at: str | None = None
    reused: bool = False
    recoverable: bool = False
    recoverable_at: str | None = None


class CapCutHandoffDiagnosticsResponse(BaseModel):
    status: str
    installation_path: str | None = None
    detected_version: str | None = None
    is_supported: bool
    project_root_path: str
    project_root_exists: bool
    write_access: bool
    recovery_message: str | None = None
    checked_at: str


class CapCutDraftExportJobResponse(StartJobResponse):
    export: CapCutDraftExportArtifactResponse | None = None
    error_message: str | None = None


class ProviderTraceAuditSummaryResponse(BaseModel):
    total_entries: int
    provider_counts: dict[str, int] = Field(default_factory=dict)
    fallback_entry_count: int
    fallback_reason_counts: dict[str, int] = Field(default_factory=dict)
    artifact_type_counts: dict[str, int] = Field(default_factory=dict)


class ProviderTraceAuditEntryResponse(BaseModel):
    artifact_type: str
    artifact_id: str
    job_type: str | None = None
    job_id: str | None = None
    source_job_id: str | None = None
    timeline_id: str | None = None
    status: str
    finished_at: str | None = None
    created_at: str | None = None
    error_message: str | None = None
    provider_trace: ProviderTraceResponse


class ProviderTraceAuditResponse(BaseModel):
    summary: ProviderTraceAuditSummaryResponse
    entries: list[ProviderTraceAuditEntryResponse]
    direct_entries: list[ProviderTraceAuditEntryResponse] = Field(default_factory=list)
    upstream_entries: list[ProviderTraceAuditEntryResponse] = Field(default_factory=list)


class SubtitleArtifactResponse(BaseModel):
    subtitle_id: str
    project_id: str
    timeline_id: str
    format: str
    file_uri: str
    status: str
    notes: list[str] = Field(default_factory=list)
    created_at: str | None = None
    source_session_id: str | None = None
    source_session_revision: int | None = None
    is_current: bool = True
    invalidated_at: str | None = None
    invalidated_reason: str | None = None


class SubtitleJobResponse(StartJobResponse):
    subtitle: SubtitleArtifactResponse


class FootageProposalCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    library_asset_id: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=1, max_length=256)
    analysis: dict[str, Any] | None = None


class YujinFootageInterpretRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    instruction: str = Field(min_length=1, max_length=2_048)
    response: dict[str, Any] | str | None = None


class FootageProposalEditRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    operation: Literal["move_boundary", "split", "merge", "exclude", "confirm"]
    expected_revision: int = Field(ge=1)
    segment_id: str | None = Field(default=None, min_length=1)
    segment_ids: list[str] = Field(default_factory=list)
    boundary_sec: float | None = None
    split_sec: float | None = None
    fields: dict[str, Any] = Field(default_factory=dict)


class FootageRevisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    expected_revision: int = Field(ge=1)


class FootageApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    expected_revision: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=256)


class VirtualSequenceItemRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    source_segment_id: str = Field(min_length=1)
    source_id: str | None = Field(default=None, min_length=1)
    item_order: int = Field(ge=1)
    start_sec: float | None = None
    end_sec: float | None = None


class VirtualSequenceCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    source_id: str = Field(min_length=1)
    name: str = ""
    items: list[VirtualSequenceItemRequest] = Field(min_length=1)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=256)


class VirtualSequenceReorderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    expected_revision: int = Field(ge=1)
    item_ids: list[str] = Field(min_length=1)


class VirtualSequenceApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    idempotency_key: str = Field(min_length=1, max_length=256)


class FootageDerivativeRenderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    source_kind: Literal["proposal", "sequence"]
    source_id: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=1, max_length=256)


PartialRegenerationJobResponse.model_rebuild()
