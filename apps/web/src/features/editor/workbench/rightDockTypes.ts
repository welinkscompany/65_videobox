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
