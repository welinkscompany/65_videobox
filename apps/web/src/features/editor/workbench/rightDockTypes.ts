export type RightDockCandidate = Readonly<{
  candidateId: string;
  visibleReferenceCode: string;
  mediaType: string;
  previewUrl: string | null;
  kind: "broll" | "bgm" | "sfx" | string;
  sourceMediaKind: "raw_video" | "broll_video" | "image" | "bgm" | "sfx" | string;
  targetSegmentId: string;
  /** 그 장면을 **사람이 아는 말로** 부르는 이름(`3번째 장면 · 자막 첫머리`).
   *  `targetSegmentId`는 내부 id라 카드에 그대로 쓸 수 없고, 그래서 2026-08-20까지
   *  카드가 장면을 아예 말하지 않았다 -- 같은 자산을 쓰는 후보 열세 개가 화면에서
   *  전부 똑같아 보였다. 장면을 모르면 **비워 둔다.** 지어낸 이름은 코드보다 나쁘다. */
  targetSceneLabel?: string;
  /** 카드에 보일 자산 이름. 없으면 코드로 떨어진다 -- 코드만으로는 고를 수 없다. */
  displayName?: string;
  previewSummary: string;
  supportedControls: Readonly<Record<string, unknown>>;
  availability: string;
  reviewStatus: string;
  actionable: boolean;
  readOnlyFinding?: boolean;
}>;

export type RightDockProposal = Readonly<{
  proposalId: string;
  status: string;
  baseSessionRevision: number;
  currentRevision: number;
  /** 뜻으로 찾았는지 단어로만 찾았는지. 임베딩 조회가 실패하면 조용히 단어
   *  매칭으로 떨어져서, 추천이 갑자기 나빠져도 owner가 원인을 알 수 없었다. */
  matchMode?: string;
  /** 여러 후보를 한 번에 적용할 수 있는 추천인가. **서버가 정한다** --
   *  유진이 직접 실행하는 추천은 한 번에 하나만 받으므로(`reject_yujin_direct_apply`)
   *  그런 추천에서 여러 개를 고르게 하면 고를 수는 있는데 적용이 거절된다. */
  allowsMultipleSelection?: boolean;
  candidates: readonly RightDockCandidate[];
}>;

export type RightDockMessage = Readonly<{
  id: string;
  role: "user" | "assistant";
  text: string;
}>;

/** 대화 하나가 실제로 적용됐을 때 남기는 기록. **캡컷 EditPilot이 하는 것과 같은
 *  자리다**(`docs/reference/capcut-observed-2026-08-22.ko.md` §6) -- 한 번 말하면
 *  한 번 실행하고, 무엇을 했는지 목록으로 남긴다. owner 지시 2026-08-22:
 *  "유진 대화창에 완료된 작업목록은 만들자."
 *
 *  자유 대화(`RightDockMessage`)와 나란히 두지 않고 따로 둔 이유는, EditPilot의
 *  체크리스트가 답장 문장과 다른 모양(항목별 완료 표시)이기 때문이다. */
export type RightDockCompletionEntry = Readonly<{
  id: string;
  appliedAt: string;
  items: readonly Readonly<{ label: string; sceneLabel?: string }>[];
}>;

export type YujinRunState =
  | { kind: "idle" }
  | {
    kind: "streaming";
    runId: string;
    routeEpoch: number;
    text: string;
    cancelWarning?: string;
  }
  | { kind: "complete"; runId: string; syncWarning?: string }
  | {
    kind: "unavailable";
    message: string;
    runId?: string;
    retryable?: boolean;
    cancelWarning?: string;
  };

export type RightDockConversationScroll = Readonly<{
  key: string;
  top: number;
  pinnedToBottom: boolean;
}>;

export type RightDockMemoryCandidate = Readonly<{
  candidateId: string;
  text: string;
  category: YujinMemoryCategory;
  status: YujinMemoryConsentStatus;
  storageStatus: YujinMemoryStorageStatus;
  retryable: boolean;
  action: "idle" | "approving" | "rejecting" | "saving" | "deleting";
  error: "save" | "delete" | "not_configured" | null;
}>;

export type RightDockMemory = Readonly<{
  candidates: readonly RightDockMemoryCandidate[];
  loadError: string | null;
  candidateDraft: string;
  candidateCategory: YujinMemoryCategory;
  createAction: "idle" | "creating";
  createError: string | null;
  canCreateCandidate: boolean;
  onCandidateDraftChange: (draft: string) => void;
  onCandidateCategoryChange: (category: YujinMemoryCategory) => void;
  onCreateCandidate: () => void | Promise<void>;
  onApproveAndStore: (candidateId: string) => void | Promise<void>;
  onReject: (candidateId: string) => void | Promise<void>;
  onStore: (candidateId: string) => void | Promise<void>;
  onDelete: (candidateId: string) => void | Promise<void>;
}>;

export type RightDockEditingProposal = Readonly<{
  proposalId: string;
  summary: string;
  operationSummaries: readonly string[];
  followUpQuestions: readonly string[];
  previewTarget: Readonly<{ segmentId: string; startSec: number; endSec: number }> | null;
  isApplying: boolean;
  error: string | null;
}>;

export type RightDockDirector = Readonly<{
  state: "script_required" | "idle" | "analysis_running" | "proposal_ready" | "applying" | "blocked" | "error";
  messages: readonly RightDockMessage[];
  completions?: readonly RightDockCompletionEntry[];
  proposal: RightDockProposal | null;
  draft: string;
  runState: YujinRunState;
  selectedCandidateIds: readonly string[];
  conversationScroll: RightDockConversationScroll;
  memory?: RightDockMemory;
  composerDisabled?: boolean;
  onDraftChange: (draft: string) => void;
  onSelectedCandidateIdsChange: (candidateIds: readonly string[]) => void;
  onConversationScrollChange: (scroll: RightDockConversationScroll) => void;
  onSendMessage: (draft: string) => void | Promise<void>;
  /** 대화를 자동 편집으로 바꾸지 않는다. 창작자가 눌렀을 때만 읽기 전용 편집안을 만든다. */
  onCreateEditingProposal?: () => void | Promise<void>;
  editingProposal?: RightDockEditingProposal | null;
  editingProposalCreating?: boolean;
  onPreviewEditingProposal?: () => void | Promise<void>;
  onApplyEditingProposal?: () => void | Promise<void>;
  onApplyProposal: (proposalId: string, candidateIds: readonly string[]) => void | Promise<void>;
  /** 낡은 추천에서 유진에게 돌아가는 길. 추천이 있을 때만 있다. */
  onRefreshProposal?: () => void | Promise<void>;
  onManualEdit: () => void;
  /** 붙여 넣은 글을 이 프로젝트의 대본으로 받는다. **확정은 사람이 한다** --
   *  이 경로는 대본을 만들 뿐 장면을 바로 만들지 않는다. */
  onUseDraftAsScript?: (script: string) => void | Promise<void>;
  /** 편집 작업판이 미리 듣기 자리를 물려 준다. 경로 자체는 재생하지 않는다. */
  onPreviewCandidate?: (candidate: RightDockCandidate) => void;
  onStart?: () => void | Promise<void>;
  /** 추천 시작이 거절된 이유. 다시 누를 수 있는 상태로 함께 보인다. */
  startFailure?: string | null;
  onRetryMessage?: () => void | Promise<void>;
  onCancelRun?: () => void | Promise<void>;
  onRetryRun?: () => void | Promise<void>;
  retryAfterSeconds?: number | null;
}>;
import type {
  YujinMemoryCategory,
  YujinMemoryConsentStatus,
  YujinMemoryStorageStatus,
} from "../../../api";
