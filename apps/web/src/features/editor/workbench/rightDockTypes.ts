export type RightDockCandidate = Readonly<{
  candidateId: string;
  visibleReferenceCode: string;
  mediaType: string;
  previewUrl: string | null;
  kind: "broll" | "bgm" | "sfx" | string;
  sourceMediaKind: "raw_video" | "broll_video" | "image" | "bgm" | "sfx" | string;
  targetSegmentId: string;
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
  candidates: readonly RightDockCandidate[];
}>;

export type RightDockMessage = Readonly<{
  id: string;
  role: "user" | "assistant";
  text: string;
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
  error: "save" | "delete" | null;
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

export type RightDockDirector = Readonly<{
  state: "script_required" | "idle" | "analysis_running" | "proposal_ready" | "applying" | "blocked" | "error";
  messages: readonly RightDockMessage[];
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
  onApplyProposal: (proposalId: string, candidateIds: readonly string[]) => void | Promise<void>;
  onManualEdit: () => void;
  onPreviewCandidate: (candidate: RightDockCandidate) => void;
  onStart?: () => void | Promise<void>;
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
