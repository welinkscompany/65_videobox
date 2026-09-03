import { useEffect, useRef, useState } from "react";
import { flushSync } from "react-dom";

import { voiceFailureMessage } from "./voiceFailureMessage";
import { voiceSampleLabel } from "./voiceSampleLabel";
import { dubbingOutcomeMessage, runDubbingWithProgress, type DubbingOutcome } from "./dubbingProgress";

import { ApiConflictError, ApiRequestError, DirectorProposalBlockedError, api, type BrollAsset, type DirectorCandidate, type DirectorMessage, type DirectorProposal, type LibraryAsset, type MediaLibraryAsset, type OutputVariant, type YujinEditingProposalPreview, type OutputVariantPatch, type PartialRegenerationJob, type PartialRegenerationPreflight, type PartialRegenerationRun, type SceneTransitionSuggestion, type YujinEditingProposal, type YujinMemoryCandidate, type YujinMemoryCategory, type YujinMemoryStoreResult } from "../../../api";
import { Button } from "../../../components/ui/button";
import { findLatestSucceededJob } from "../../../lib/formatters";
import { resolveWorkspaceLocation } from "../../../app/routeManifest";
import { creationBriefStorageKey, pastedScriptSummary } from "../../creation/pastedScriptSummary";
import { projectEditorAssets, type EditorAssetCard } from "../assets/editorAssetProjection";
import { createEditorCommandPort, type EditorCommandPort } from "../editorCommandPort";
import { joinEditorSnapshot, type EditorSessionSnapshot } from "../editorSnapshot";
import type { EditorCaptionStyle, EditorControls, EditorViewModel } from "../editorViewModel";
import type { InspectorAction } from "../inspector/InspectorControls";
import { sceneFilterLabel } from "../inspector/sceneFilters";
import { sceneLabelsBySegmentId, sceneNumbersBySegmentId } from "../sceneNames";
import { canRestorePartialRegenerationResult, canRunPartialRegeneration, createPartialRegenerationTicket, PARTIAL_REGENERATION_FIELDS, preflightMatchesPartialRegenerationTicket, runMatchesPartialRegenerationTicket, type PartialRegenerationTicket } from "../partialRegenerationController";
import { EditorWorkbench } from "./EditorWorkbench";
import { buildQualityFollowUps } from "./qualityFollowUps";
import type { RightDockCompletionEntry, RightDockDirector, RightDockEditingProposalPreview, RightDockMessage, RightDockProposal } from "./rightDockTypes";

type MutationState = Readonly<{ isSaving: boolean; message?: string }>;
type AssetState = Readonly<{
  key: string;
  brollAssets: readonly BrollAsset[];
  libraryAssets: readonly MediaLibraryAsset[];
  /** 여러 프로젝트가 나눠 쓰는 라이브러리의 그림 (owner 승인 2026-08-20). */
  libraryImageAssets: readonly LibraryAsset[];
  error: string | null;
}>;
/** 편집안 창이 보여 줄 **후보 결과** 영상의 상태. 저장된 편집본 미리보기와 완전히
 *  다른 자리이며, 적용 전에는 저장을 바꾸는 어떤 호출도 하지 않는다.
 *  `tick`은 같은 `pending`이 다시 와도 기다리는 효과가 다시 돌게 하는 표시다 --
 *  값이 같으면 상태 객체가 그대로라 폴링이 한 번에 멈춘다. */
type EditingProposalPreviewState =
  | Readonly<{ kind: "idle" }>
  | Readonly<{ kind: "working"; generationId: string | null; tick: number }>
  | Readonly<{ kind: "ready"; videoUrl: string }>
  | Readonly<{ kind: "unavailable"; message: string }>;

const editingProposalPreviewWorkingMessage = "편집안 미리보기를 만들고 있어요.";
const editingProposalPreviewFailedMessage = "편집안 미리보기를 만들지 못했어요. 잠시 뒤 다시 눌러 주세요.";

/** 서버가 돌려준 후보 결과 상태를 화면 상태로 옮긴다.
 *  낡았으면 **영상을 주지 않고** 무엇을 하면 되는지만 말한다 -- 서버가 준 안내
 *  문장(`action`)을 그대로 붙인다. 안내가 비어 있으면 우리가 아는 말로 채운다. */
function nextEditingProposalPreviewState(
  result: YujinEditingProposalPreview,
  tick: number,
): EditingProposalPreviewState {
  if (result.status === "stale") {
    const action = result.action?.trim() ? result.action.trim() : "새 편집안을 받아 보세요.";
    return { kind: "unavailable", message: `편집본이 바뀌었어요. ${action}` };
  }
  if (result.status === "succeeded") {
    return result.contentUrl
      ? { kind: "ready", videoUrl: result.contentUrl }
      : { kind: "unavailable", message: editingProposalPreviewFailedMessage };
  }
  if (result.status === "failed") return { kind: "unavailable", message: editingProposalPreviewFailedMessage };
  return { kind: "working", generationId: result.generationId, tick: tick + 1 };
}

function editingProposalPreviewForDock(state: EditingProposalPreviewState): RightDockEditingProposalPreview {
  return state.kind === "working"
    ? { kind: "working", message: editingProposalPreviewWorkingMessage }
    : state;
}

type DirectorState = Readonly<{
  key: string;
  state: RightDockDirector["state"];
  conversationId: string | null;
  messages: readonly RightDockMessage[];
  /** 유진 대화창의 완료 목록(2026-08-22). 원본은 서버 대화가 아니라 이 프로젝트
   *  세션 안에서 실제로 적용에 성공한 것만 쌓는다 -- 새로고침하면 비워진다.
   *  캡컷 EditPilot도 대화창을 새로 열면 그 안의 목록이었지 영구 기록이 아니다. */
  completions: readonly RightDockCompletionEntry[];
  proposal: DirectorProposal | null;
  editingProposal: YujinEditingProposal | null;
  editingProposalCreating: boolean;
  editingProposalApplying: boolean;
  editingProposalError: string | null;
  editingProposalPreview: EditingProposalPreviewState;
  draft: string;
  runState: RightDockDirector["runState"];
  selectedCandidateIds: readonly string[];
  conversationScroll: RightDockDirector["conversationScroll"];
  memorySourceMessageIds: readonly string[];
  isSending?: boolean;
  /** 추천 시작이 거절된 이유. 다시 누를 수 있어야 하므로 상태는 `idle`로 남긴다. */
  startFailure: string | null;
}>;
type MemoryCandidateState = Readonly<{
  candidate: YujinMemoryCandidate;
  action: "idle" | "approving" | "rejecting" | "saving" | "deleting";
  error: "save" | "delete" | "not_configured" | null;
}>;
type MemoryState = Readonly<{
  key: string;
  conversationId: string | null;
  candidates: readonly MemoryCandidateState[];
  loadError: string | null;
  candidateDraft: string;
  candidateCategory: YujinMemoryCategory;
  createAction: "idle" | "creating";
  createError: string | null;
}>;
type PartialState = Readonly<{
  key: string;
  ticket: PartialRegenerationTicket | null;
  preflight: PartialRegenerationPreflight | null;
  run: PartialRegenerationRun | null;
  jobId: string | null;
  result: PartialRegenerationJob | null;
  isResultOpen: boolean;
  message: string | null;
}>;
type ActiveHermesRouteRun = Readonly<{
  projectId: string;
  conversationId: string;
  runId: string;
  controller: AbortController;
}>;
type VariantState = Readonly<{
  key: string;
  items: readonly OutputVariant[];
  message: string | null;
  busy: boolean;
}>;

const assetLoadError = "일부 미디어를 불러오지 못했어요. 편집은 계속할 수 있어요. 잠시 후 다시 확인해 주세요.";
const yujinUnavailableMessage = "유진의 답을 받지 못했어요.";
const hermesUnavailableTechnicalText = "Hermes is temporarily unavailable. Manual Director remains available.";
const maxDirectorMessages = 200;

// 백엔드가 내는 값은 내부 이름이다(`segment copy`, `subtitle render`,
// `capcut export`). 그대로 화면에 찍혀서 owner가 영어 개발 용어를 읽고 있었다.
// 값 자체는 그대로 두고 보여줄 때만 옮긴다 -- 저장된 기록을 다시 쓰지 않는다.
const affectedAreaLabels: Readonly<Record<string, string>> = {
  "segment copy": "장면 대본",
  "b-roll track": "영상 트랙",
  "music bed": "배경 음악",
  "visual overlays": "화면 요소",
  "narration track": "내레이션",
  "timeline preview": "미리보기",
  "subtitle render": "자막 입히기",
  "capcut export": "CapCut 내보내기",
};

export function affectedAreaLabel(area: string): string {
  return affectedAreaLabels[area] ?? "영상 일부";
}

const partialStatusLabels: Readonly<Record<string, string>> = {
  succeeded: "완료",
  failed: "실패",
  running: "만드는 중",
  queued: "차례 기다리는 중",
};

export function partialStatusLabel(status: string): string {
  return partialStatusLabels[status] ?? "상태 확인 중";
}

const partialFieldLabels: Readonly<Record<string, string>> = {
  caption: "자막",
  cut_action: "컷 판단",
  broll: "영상",
  visual_overlay: "화면 요소",
  music: "배경 음악",
  sfx: "효과음",
  tts_replacement: "내레이션 음성",
};

export function partialFieldLabel(field: string): string {
  return partialFieldLabels[field] ?? "일부 항목";
}

function waitForAssetBrowserPreview(delayMs: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) { reject(new DOMException("Aborted", "AbortError")); return; }
    const timeout = window.setTimeout(() => { signal.removeEventListener("abort", abort); resolve(); }, delayMs);
    const abort = () => { window.clearTimeout(timeout); reject(new DOMException("Aborted", "AbortError")); };
    signal.addEventListener("abort", abort, { once: true });
  });
}

export async function prepareProjectAssetBrowserPreview(
  projectId: string,
  assetId: string,
  signal: AbortSignal,
  options: { sleep?: (delayMs: number, signal: AbortSignal) => Promise<void>; maxPolls?: number } = {},
): Promise<string> {
  const sleep = options.sleep ?? waitForAssetBrowserPreview;
  const maxPolls = options.maxPolls ?? 76;
  let state = await api.prepareAssetBrowserPreview(projectId, assetId, signal);
  for (let poll = 0; poll <= maxPolls; poll += 1) {
    if (state.status === "ready" && state.content_url) return state.content_url;
    if (state.status === "failed") throw new Error(state.error_code ?? "PREVIEW_RENDER_FAILED");
    if (poll === maxPolls) break;
    const delay = [100, 200, 400, 800][Math.min(poll, 3)];
    await sleep(delay, signal);
    state = await api.getAssetBrowserPreview(projectId, assetId, signal);
  }
  throw new Error("PREVIEW_PREPARATION_TIMEOUT");
}

function directorDraftStorageKey(requestKey: string) {
  return `videobox.editor-workbench.eugene-draft:${encodeURIComponent(requestKey)}`;
}

function readDirectorDraft(requestKey: string) {
  try { return window.localStorage.getItem(directorDraftStorageKey(requestKey)) ?? ""; } catch { return ""; }
}

function createDirectorState(requestKey: string, sessionId: string | null): DirectorState {
  return {
    key: requestKey,
    state: sessionId ? "analysis_running" : "script_required",
    conversationId: null,
    messages: [],
    completions: [],
    proposal: null,
    editingProposal: null,
    editingProposalCreating: false,
    editingProposalApplying: false,
    editingProposalError: null,
    editingProposalPreview: { kind: "idle" },
    draft: readDirectorDraft(requestKey),
    runState: { kind: "idle" },
    selectedCandidateIds: [],
    conversationScroll: { key: requestKey, top: 0, pinnedToBottom: true },
    memorySourceMessageIds: [],
    startFailure: null,
  };
}

/** 유진이 추천 시작을 거절한 이유를 창작자 말로 옮긴다. 이유를 모르면 그대로 말한다 --
 *  "실패했다"만 남기는 것이 지금까지의 문제였다. */
function directorStartFailureMessage(error: unknown) {
  return error instanceof DirectorProposalBlockedError
    ? "촬영본 확인이 아직 끝나지 않아서 추천을 만들 수 없어요. 미디어 화면에서 확인한 뒤 다시 눌러 주세요."
    : "유진에게 추천을 받지 못했어요. 잠시 뒤 다시 눌러 주세요.";
}

function createMemoryState(requestKey: string): MemoryState {
  return {
    key: requestKey,
    conversationId: null,
    candidates: [],
    loadError: null,
    candidateDraft: "",
    candidateCategory: "pacing",
    createAction: "idle",
    createError: null,
  };
}

function capDirectorMessages(messages: readonly RightDockMessage[]) {
  return messages.slice(-maxDirectorMessages);
}

export function EditorWorkbenchRoute({ projectId, sessionId, requestedSegmentId = null }: { projectId: string; sessionId: string | null; requestedSegmentId?: string | null }) {
  const requestKey = `${projectId}:${sessionId ?? "missing"}`;
  const [refreshToken, setRefreshToken] = useState(0);
  const [state, setState] = useState<Readonly<{ key: string; view: EditorViewModel | null; session: EditorSessionSnapshot | null; error: string | null }>>({ key: requestKey, view: null, session: null, error: sessionId ? null : "편집 세션을 찾을 수 없어요. 다시 열어 주세요." });
  const [variants, setVariants] = useState<VariantState>({ key: requestKey, items: [], message: null, busy: false });
  const [transitionSuggestions, setTransitionSuggestions] = useState<Readonly<{ key: string; items: readonly SceneTransitionSuggestion[] }>>({ key: requestKey, items: [] });
  const [assets, setAssets] = useState<AssetState>({ key: requestKey, brollAssets: [], libraryAssets: [], libraryImageAssets: [], error: null });
  /** 편집기 안에서 미디어를 더하면 목록을 다시 읽는다. 더한 것이 바로 안 보이면
   *  창작자는 실패한 줄 안다(owner 승인 2026-08-27). */
  const [assetRefreshToken, setAssetRefreshToken] = useState(0);
  const [mutation, setMutation] = useState<MutationState>({ isSaving: false });
  const captionPreflightInFlight = useRef(false);
  const [director, setDirector] = useState<DirectorState>(() => createDirectorState(requestKey, sessionId));
  const [memory, setMemory] = useState<MemoryState>(() => createMemoryState(requestKey));
  const [partial, setPartial] = useState<PartialState>({ key: requestKey, ticket: null, preflight: null, run: null, jobId: null, result: null, isResultOpen: false, message: null });
  const [partialRecoveryRetryToken, setPartialRecoveryRetryToken] = useState(0);
  const [partialRecoveryError, setPartialRecoveryError] = useState(false);
  const mutationInFlight = useRef(false);
  const routeEpoch = useRef({ key: requestKey, value: 0 });
  const manifestOperationId = useRef(0);
  const mutationOperationId = useRef(0);
  const previewOperationId = useRef(0);
  const pollOperationId = useRef(0);
  /** 편집안 후보 결과 미리보기. 저장 편집본 미리보기(`previewOperationId`)와 **따로**
   *  센다 -- 두 경로가 같은 번호를 쓰면 한쪽이 다른 쪽 응답을 버린다. */
  const proposalPreviewOperationId = useRef(0);
  const directorOperationId = useRef(0);
  const memoryListOperationId = useRef(0);
  const memoryMutationOperationId = useRef(0);
  const partialOperationId = useRef(0);
  const variantOperationId = useRef(0);
  const variantMutationInFlight = useRef(false);
  const partialRecoveryOperationId = useRef(0);
  const directorMutationInFlight = useRef(false);
  const memoryMutationInFlight = useRef(false);
  const hermesRunInFlight = useRef(false);
  const hermesAbort = useRef<AbortController | null>(null);
  const assetPreviewAbort = useRef<AbortController | null>(null);
  const activeHermesRouteRun = useRef<ActiveHermesRouteRun | null>(null);
  const lastDirectorSubmission = useRef<{ conversationId: string; clientMessageId: string; text: string } | null>(null);
  const hermesOperationId = useRef(0);
  const currentDirectorConversationId = useRef<string | null>(null);
  const partialInFlight = useRef(false);
  const currentEditorRevision = useRef(state.view?.expectedRevision ?? null);
  currentEditorRevision.current = state.view?.expectedRevision ?? null;
  const cancelActiveRouteRun = () => {
    const active = activeHermesRouteRun.current;
    if (!active) return;
    activeHermesRouteRun.current = null;
    // Local chat has no server-side run to notify -- aborting the client
    // fetch is the entire cancellation.
    active.controller.abort();
  };
  useEffect(() => {
    if (routeEpoch.current.key === requestKey) return;
    cancelActiveRouteRun();
    hermesOperationId.current += 1;
    hermesRunInFlight.current = false;
    hermesAbort.current?.abort();
    hermesAbort.current = null;
    assetPreviewAbort.current?.abort();
    assetPreviewAbort.current = null;
    routeEpoch.current = { key: requestKey, value: routeEpoch.current.value + 1 };
    mutationOperationId.current += 1;
    directorOperationId.current += 1;
    memoryListOperationId.current += 1;
    memoryMutationOperationId.current += 1;
    partialOperationId.current += 1;
    variantOperationId.current += 1;
    directorMutationInFlight.current = false;
    memoryMutationInFlight.current = false;
    currentDirectorConversationId.current = null;
    partialInFlight.current = false;
    variantMutationInFlight.current = false;
    setVariants({ key: requestKey, items: [], message: null, busy: false });
    mutationInFlight.current = false;
    setMutation({ isSaving: false });
    setDirector(createDirectorState(requestKey, sessionId));
    setMemory(createMemoryState(requestKey));
    setPartial({ key: requestKey, ticket: null, preflight: null, run: null, jobId: null, result: null, isResultOpen: false, message: null });
    setPartialRecoveryError(false);
  }, [requestKey]);
  useEffect(() => () => {
    cancelActiveRouteRun();
    hermesOperationId.current += 1;
    hermesRunInFlight.current = false;
    hermesAbort.current?.abort();
    hermesAbort.current = null;
    assetPreviewAbort.current?.abort();
    assetPreviewAbort.current = null;
  }, []);
  useEffect(() => {
    if (director.key !== requestKey) return;
    try { window.localStorage.setItem(directorDraftStorageKey(requestKey), director.draft); } catch { /* best effort only */ }
  }, [director.draft, director.key, requestKey]);
  useEffect(() => {
    if (!sessionId) return;
    const epoch = routeEpoch.current.value;
    const operationId = directorOperationId.current + 1;
    directorOperationId.current = operationId;
    let active = true;
    const isCurrent = () => active && routeEpoch.current.value === epoch && directorOperationId.current === operationId;
    setDirector((current) => current.key === requestKey ? { ...current, state: "analysis_running", conversationId: null, messages: [], proposal: null, runState: { kind: "idle" }, memorySourceMessageIds: [] } : current);
    void api.reloadDirectorSession(projectId, sessionId).then((recovered) => {
      if (!isCurrent()) return;
      setDirector((current) => current.key === requestKey ? {
        ...current,
        state: recovered.proposal ? "proposal_ready" : "idle",
        conversationId: recovered.conversation?.conversation_id ?? null,
        messages: projectDirectorMessages(recovered.messages),
        memorySourceMessageIds: completedDurableMemoryMessageIds(
          recovered.messages,
        ),
        proposal: recovered.proposal,
        runState: { kind: "idle" },
        selectedCandidateIds: initialDirectorCandidateIds(recovered.proposal),
      } : current);
    }).catch((error: unknown) => {
      if (isCurrent()) setDirector((current) => current.key === requestKey ? { ...current, state: error instanceof SyntaxError || error instanceof TypeError ? "error" : "blocked", conversationId: null, messages: [], proposal: null, memorySourceMessageIds: [] } : current);
    });
    return () => { active = false; };
  }, [projectId, requestKey, sessionId]);
  useEffect(() => {
    if (!sessionId) { setState({ key: requestKey, view: null, session: null, error: "편집 세션을 찾을 수 없어요. 다시 열어 주세요." }); return; }
    const epoch = routeEpoch.current.value;
    const operationId = manifestOperationId.current + 1;
    manifestOperationId.current = operationId;
    let active = true;
    const isCurrent = () => active && routeEpoch.current.value === epoch && manifestOperationId.current === operationId;
    setState((current) => current.key === requestKey && current.view && current.session
      ? { ...current, error: null }
      : { key: requestKey, view: null, session: null, error: null });
    void Promise.all([
      api.getEditorPlaybackManifest(projectId, sessionId),
      api.getEditingSession(projectId, sessionId),
    ]).then(([manifest, editingSession]) => {
      if (!isCurrent()) return;
      const next = joinEditorSnapshot(manifest, editingSession);
      if (next.view.projectId !== projectId || next.view.sessionId !== sessionId) throw new Error("editor_snapshot_identity_mismatch");
      setState({ key: requestKey, view: next.view, session: next.session, error: null });
    }).catch((error: unknown) => {
      if (!isCurrent()) return;
      const message = error instanceof Error && error.message === "editor_snapshot_identity_mismatch"
          ? "편집 세션 정보가 일치하지 않아요. 다시 열어 주세요."
          : "재생 내용을 불러오지 못했어요. 새로고침 후 다시 확인해 주세요.";
      const identityMismatch = error instanceof Error && error.message === "editor_snapshot_identity_mismatch";
      setState((current) => !identityMismatch && current.key === requestKey && current.view && current.session
        ? { ...current, error: message }
        : { key: requestKey, view: null, session: null, error: message });
    });
    return () => { active = false; };
  }, [projectId, requestKey, refreshToken, sessionId]);
  useEffect(() => {
    if (!sessionId) {
      setVariants({ key: requestKey, items: [], message: null, busy: false });
      return;
    }
    const operationId = variantOperationId.current + 1;
    variantOperationId.current = operationId;
    let active = true;
    const isCurrent = () => active && variantOperationId.current === operationId && routeEpoch.current.key === requestKey;
    void api.listOutputVariants(projectId, sessionId).then((result) => {
      if (!isCurrent()) return;
      setVariants({ key: requestKey, items: result.variants, message: null, busy: false });
    }).catch(() => {
      if (isCurrent()) setVariants({ key: requestKey, items: [], message: "출력 변형 서버 상태를 불러오지 못했어요.", busy: false });
    });
    return () => { active = false; };
  }, [projectId, requestKey, sessionId, refreshToken]);
  useEffect(() => {
    if (!sessionId) {
      setTransitionSuggestions({ key: requestKey, items: [] });
      return;
    }
    let active = true;
    // `session_revision`을 의존값으로 쓴다 -- `refreshToken`은 짧은 영상의
    // 정확 미리보기가 성공했을 때만 조건부로 올라가서(위 코드 참고), 그것에
    // 기대면 긴 영상이나 미리보기 실패 뒤에는 방금 적용한 전환이 추천 목록에
    // 그대로 남는다. 리비전은 성공한 편집마다 예외 없이 바뀐다.
    void api.getSceneTransitionSuggestions(projectId, sessionId).then((result) => {
      if (active) setTransitionSuggestions({ key: requestKey, items: result.suggestions });
    }).catch(() => {
      // 추천은 거들 뿐이다 -- 못 불러와도 화면은 그대로 쓸 수 있어야 한다.
      if (active) setTransitionSuggestions({ key: requestKey, items: [] });
    });
    return () => { active = false; };
  }, [projectId, requestKey, sessionId, state.session?.expectedRevision]);
  useEffect(() => {
    const currentView = state.key === requestKey ? state.view : null;
    const currentVariants = variants.key === requestKey ? variants.items : [];
    if (!currentView || !sessionId || !currentVariants.length) return;
    const stale = currentVariants.filter((variant) => variant.source_session_revision < currentView.expectedRevision);
    if (!stale.length || variantMutationInFlight.current) return;
    variantMutationInFlight.current = true;
    const operationId = variantOperationId.current + 1;
    variantOperationId.current = operationId;
    let active = true;
    const isCurrent = () => active && variantOperationId.current === operationId && routeEpoch.current.key === requestKey;
    setVariants((current) => current.key === requestKey ? { ...current, busy: true } : current);
    void Promise.all(stale.map((variant) => api.rebaseOutputVariant(projectId, variant.variant_id, {
      new_master_revision: currentView.expectedRevision,
      changed_fields: ["story"],
    }))).then((updated) => {
      if (!isCurrent()) return;
      const byId = new Map(updated.map(({ variant }) => [variant.variant_id, variant]));
      setVariants((current) => current.key !== requestKey ? current : {
        ...current,
        items: current.items.map((variant) => byId.get(variant.variant_id) ?? variant),
        message: "마스터 변경을 확인했어요. 출력 변형 충돌을 검토해 주세요.",
        busy: false,
      });
    }).catch(() => {
      if (isCurrent()) setVariants((current) => current.key === requestKey ? { ...current, message: "마스터 변경 후 출력 변형을 다시 맞추지 못했어요.", busy: false } : current);
    }).finally(() => {
      if (isCurrent()) variantMutationInFlight.current = false;
    });
    return () => { active = false; };
  }, [projectId, requestKey, sessionId, state.key, state.view, variants.items, variants.key]);
  useEffect(() => {
    if (!sessionId || !state.session?.updatedAt) return;
    const epoch = routeEpoch.current.value;
    const operationId = partialRecoveryOperationId.current + 1;
    partialRecoveryOperationId.current = operationId;
    const mutationGeneration = mutationOperationId.current;
    let active = true;
    const isCurrent = () => (
      active
      && routeEpoch.current.value === epoch
      && partialRecoveryOperationId.current === operationId
      && mutationOperationId.current === mutationGeneration
    );
    void api.listJobs(projectId).then(async (jobs) => {
      const latest = findLatestSucceededJob(jobs, "partial_regeneration", sessionId);
      if (!latest) return null;
      return {
        expectedJobId: latest.job_id,
        result: await api.getPartialRegenerationResult(projectId, latest.job_id),
      };
    }).then((recovered) => {
      if (!isCurrent()) return;
      if (!recovered) {
        setPartialRecoveryError(false);
        setPartial((current) => current.key === requestKey
          && current.message === "이전 재생성 결과를 찾지 못했어요. 직접 편집은 계속할 수 있어요."
          ? { ...current, message: "저장된 이전 재생성 결과가 없어요." }
          : current);
        return;
      }
      const { expectedJobId, result } = recovered;
      const recoveredSegmentId = result.segment_ids.length === 1 ? result.segment_ids[0] : "";
      const canRecover = canRestorePartialRegenerationResult({
        sessionId,
        sessionUpdatedAt: state.session?.updatedAt ?? "",
        jobId: expectedJobId,
        segmentId: recoveredSegmentId,
        fields: result.fields,
      }, result) && state.session!.segments.some((segment) => segment.segmentId === recoveredSegmentId);
      if (!canRecover) {
        setPartialRecoveryError(false);
        setPartial((current) => current.key === requestKey && current.jobId !== null
          ? {
            ...current,
            jobId: null,
            result: null,
            isResultOpen: false,
            message: "현재 편집본과 맞지 않는 이전 결과를 닫았어요.",
          }
          : current);
        return;
      }
      setPartialRecoveryError(false);
      setPartial((current) => (
        current.key === requestKey && current.ticket === null && !partialInFlight.current
          ? {
            ...current,
            jobId: result.job_id,
            result,
            isResultOpen: current.isResultOpen && current.jobId === result.job_id,
            message: current.message === "이전 재생성 결과를 찾지 못했어요. 직접 편집은 계속할 수 있어요."
              ? "이전 재생성 결과를 다시 찾았어요."
              : current.message,
          }
          : current
      ));
    }).catch(() => {
      if (!isCurrent()) return;
      setPartialRecoveryError(true);
      setPartial((current) => current.key === requestKey
        ? { ...current, message: "이전 재생성 결과를 찾지 못했어요. 직접 편집은 계속할 수 있어요." }
        : current);
    });
    return () => { active = false; };
  }, [partialRecoveryRetryToken, projectId, requestKey, sessionId, state.session?.updatedAt]);
  useEffect(() => {
    if (!sessionId) {
      setAssets({ key: requestKey, brollAssets: [], libraryAssets: [], libraryImageAssets: [], error: null });
      return;
    }
    const epoch = routeEpoch.current.value;
    let active = true;
    const isCurrent = () => active && routeEpoch.current.value === epoch;
    setAssets({ key: requestKey, brollAssets: [], libraryAssets: [], libraryImageAssets: [], error: null });
    void api.listBrollAssets(projectId).then((brollAssets) => {
      if (!isCurrent()) return;
      setAssets((current) => current.key === requestKey ? { ...current, brollAssets } : current);
    }).catch(() => {
      if (!isCurrent()) return;
      setAssets((current) => current.key === requestKey ? { ...current, error: assetLoadError } : current);
    });
    void api.listMediaLibraryAssets().then(({ assets: libraryAssets }) => {
      if (!isCurrent()) return;
      setAssets((current) => current.key === requestKey ? { ...current, libraryAssets } : current);
    }).catch(() => {
      if (!isCurrent()) return;
      setAssets((current) => current.key === requestKey ? { ...current, error: assetLoadError } : current);
    });
    // 라이브러리 그림. 프로젝트마다 다시 넣지 않고 한 번 넣어 여러 프로젝트가
    // 나눠 쓴다. 얹기 전까지는 이 프로젝트 자산이 아니다.
    void api.listLibraryAssets({ mediaType: "image", limit: 500 }).then(({ assets: libraryImageAssets }) => {
      if (!isCurrent()) return;
      setAssets((current) => current.key === requestKey ? { ...current, libraryImageAssets } : current);
    }).catch(() => {
      if (!isCurrent()) return;
      setAssets((current) => current.key === requestKey ? { ...current, error: assetLoadError } : current);
    });
    return () => { active = false; };
  }, [assetRefreshToken, projectId, requestKey, sessionId]);
  const memoryConversationId = director.key === requestKey
    ? director.conversationId
    : null;
  currentDirectorConversationId.current = memoryConversationId;
  useEffect(() => {
    if (!sessionId || !memoryConversationId) {
      setMemory((current) => (
        current.key === requestKey
        && current.conversationId === null
        && current.candidates.length === 0
        && current.loadError === null
          ? current
          : createMemoryState(requestKey)
      ));
      return;
    }
    const epoch = routeEpoch.current.value;
    const operationId = memoryListOperationId.current + 1;
    memoryListOperationId.current = operationId;
    let active = true;
    const isCurrent = () => (
      active
      && routeEpoch.current.value === epoch
      && memoryListOperationId.current === operationId
      && currentDirectorConversationId.current === memoryConversationId
    );
    setMemory((current) => (
      current.key === requestKey
      && current.conversationId === memoryConversationId
        ? { ...current, candidates: [], loadError: null }
        : {
          ...createMemoryState(requestKey),
          conversationId: memoryConversationId,
        }
    ));
    void api.listYujinMemoryCandidates(
      projectId,
      memoryConversationId,
    ).then((candidates) => {
      if (!isCurrent()) return;
      if (candidates.some((candidate) => (
        candidate.project_id !== projectId
        || candidate.conversation_id !== memoryConversationId
      ))) {
        throw new Error("yujin_memory_candidate_identity_mismatch");
      }
      setMemory((current) => (
        current.key === requestKey
        && current.conversationId === memoryConversationId
          ? {
            ...current,
            candidates: candidates.map((candidate) => ({
              candidate,
              action: "idle",
              error: null,
            })),
            loadError: null,
          }
          : current
      ));
    }).catch(() => {
      if (!isCurrent()) return;
      setMemory((current) => (
        current.key === requestKey
        && current.conversationId === memoryConversationId
          ? {
            ...current,
            candidates: [],
            loadError: "기억을 불러오지 못했어요. 편집과 대화는 계속할 수 있어요.",
          }
          : current
      ));
    });
    return () => { active = false; };
  }, [memoryConversationId, projectId, requestKey, sessionId]);
  // 열었을 때 화면이 비어 있지 않게 한 번 만든다.
  //
  // 예전에는 **편집을 한 번 해야** 미리보기가 생겼다(아래 mutation 뒤의 자동
  // 생성). 편집기를 처음 열면 `아직 편집본 미리보기가 없어요`와 단추뿐이었다 --
  // 캡컷은 열면 항상 화면이 살아 있다.
  //
  // **편집본 하나에 한 번뿐이다.** 편집 뒤의 생성은 mutation 쪽이 맡는다. 판수를
  // 열쇠에 넣으면 편집할 때마다 두 곳이 같은 일을 시킨다(실측으로 확인했다).
  //
  // 길이 경계는 mutation 쪽과 **같은 것**을 쓴다. 120초를 넘는 영상은 여전히
  // 사람이 눌러야 한다 -- 열기만 해도 몇 분짜리 FFmpeg가 도는 것은 고친 게 아니다.
  const autoPreviewStartedFor = useRef<string | null>(null);
  const [autoPreviewWaiting, setAutoPreviewWaiting] = useState(false);
  useEffect(() => {
    const view = state.view;
    if (!sessionId || !view) return;
    if (view.playback.exactPreview.status !== "unavailable") return;
    if (view.output.durationSec > 120) return;
    if (autoPreviewStartedFor.current === sessionId) return;
    autoPreviewStartedFor.current = sessionId;
    const epoch = routeEpoch.current.value;
    void api.startExactPreview(projectId, sessionId, { expected_revision: view.expectedRevision })
      .then(() => { if (routeEpoch.current.value === epoch) setAutoPreviewWaiting(true); })
      // 조용히 실패한다. `미리보기 새로 만들기` 단추가 그대로 남는다.
      .catch(() => {});
  }, [projectId, sessionId, state.view?.playback.exactPreview.status, state.view?.output.durationSec]);

  useEffect(() => {
    const status = state.view?.playback.exactPreview.status;
    // 방금 우리가 시킨 것도 기다린다. 아직 편집본에는 `unavailable`로 남아 있다.
    if (status !== "pending" && status !== "running" && !(status === "unavailable" && autoPreviewWaiting)) return;
    const epoch = routeEpoch.current.value;
    const operationId = pollOperationId.current + 1;
    pollOperationId.current = operationId;
    const poll = window.setTimeout(() => {
      if (routeEpoch.current.value === epoch && pollOperationId.current === operationId) {
        setRefreshToken((current) => current + 1);
      }
    }, 1200);
    return () => window.clearTimeout(poll);
  }, [autoPreviewWaiting, refreshToken, requestKey, state.view?.playback.exactPreview.status, state.view?.playback.exactPreview.generationId]);

  // 후보 결과 미리보기가 끝날 때까지 기다린다. **상태만 물어본다** -- 이 경로는
  // 저장된 편집본을 바꾸는 호출을 하나도 하지 않는다. 기다리는 간격은 편집본
  // 미리보기와 같은 것을 쓴다.
  useEffect(() => {
    if (director.key !== requestKey) return;
    const preview = director.editingProposalPreview;
    if (preview.kind !== "working" || !preview.generationId) return;
    const generationId = preview.generationId;
    const tick = preview.tick;
    const epoch = routeEpoch.current.value;
    const operationId = proposalPreviewOperationId.current;
    const isCurrent = () => routeEpoch.current.value === epoch && proposalPreviewOperationId.current === operationId;
    const poll = window.setTimeout(() => {
      if (!isCurrent()) return;
      void api.getYujinEditingProposalPreviewStatus(projectId, generationId)
        .then((result) => {
          if (!isCurrent()) return;
          setDirector((current) => current.key === requestKey
            ? { ...current, editingProposalPreview: nextEditingProposalPreviewState(result, tick) }
            : current);
        })
        .catch(() => {
          if (!isCurrent()) return;
          setDirector((current) => current.key === requestKey
            ? { ...current, editingProposalPreview: { kind: "unavailable", message: editingProposalPreviewFailedMessage } }
            : current);
        });
    }, 1200);
    return () => window.clearTimeout(poll);
  }, [projectId, requestKey, director.key, director.editingProposalPreview]);
  if (state.key !== requestKey) return <section aria-live="polite"><p>편집 내용을 불러오는 중이에요.</p></section>;
  if (!state.view) return <section aria-live="polite"><p>{state.error ?? "편집 내용을 불러오는 중이에요."}</p></section>;
  const refreshPreview = async () => {
    if (!sessionId || !state.view) return;
    const epoch = routeEpoch.current.value;
    const operationId = previewOperationId.current + 1;
    previewOperationId.current = operationId;
    await api.startExactPreview(projectId, sessionId, { expected_revision: state.view.expectedRevision });
    if (routeEpoch.current.value === epoch && previewOperationId.current === operationId) {
      setRefreshToken((current) => current + 1);
    }
  };
  const previewSelectedRange = async ({ startSec, endSec }: { segmentId: string; startSec: number; endSec: number }) => {
    if (!sessionId || !state.view) return;
    const epoch = routeEpoch.current.value;
    const operationId = previewOperationId.current + 1;
    previewOperationId.current = operationId;
    try {
      await api.previewEditingSessionSelectedRange(projectId, sessionId, { start_sec: startSec, end_sec: endSec });
      if (routeEpoch.current.value !== epoch || previewOperationId.current !== operationId) return;
      await api.startExactPreview(projectId, sessionId, {
        expected_revision: state.view.expectedRevision,
        start_sec: startSec,
        end_sec: endSec,
      });
      if (routeEpoch.current.value === epoch && previewOperationId.current === operationId) {
        setRefreshToken((current) => current + 1);
      }
    } catch {
      if (routeEpoch.current.value === epoch && previewOperationId.current === operationId && !mutationInFlight.current && !captionPreflightInFlight.current) {
        setMutation({ isSaving: false, message: "선택 구간 미리보기를 만들지 못했어요. 최신 편집본을 확인해 주세요." });
      }
    }
  };
  /** 아직 적용하지 않은 **후보 결과**를 만들어 보여 준다.
   *
   *  2026-08-26까지 편집안 창의 미리보기는 `previewSelectedRange`를 불렀다 --
   *  그것은 **저장된 편집본**을 잘라 보여 주는 길이라, 창작자는 바뀐 결과를
   *  확인했다고 믿었지만 실제로는 바뀌기 전 영상을 봤다. 이 경로는 저장을 건드리는
   *  호출을 하나도 하지 않는다. */
  const previewYujinEditingProposal = async (proposalId: string) => {
    if (!sessionId) return;
    const epoch = routeEpoch.current.value;
    const operationId = proposalPreviewOperationId.current + 1;
    proposalPreviewOperationId.current = operationId;
    const isCurrent = () => routeEpoch.current.value === epoch && proposalPreviewOperationId.current === operationId;
    setDirector((current) => current.key === requestKey
      ? { ...current, editingProposalPreview: { kind: "working", generationId: null, tick: 0 } }
      : current);
    try {
      const result = await api.startYujinEditingProposalPreview(projectId, sessionId, proposalId);
      if (!isCurrent()) return;
      setDirector((current) => current.key === requestKey
        ? { ...current, editingProposalPreview: nextEditingProposalPreviewState(result, 0) }
        : current);
    } catch {
      if (!isCurrent()) return;
      setDirector((current) => current.key === requestKey
        ? { ...current, editingProposalPreview: { kind: "unavailable", message: editingProposalPreviewFailedMessage } }
        : current);
    }
  };
  const commitTimelineMutation = async (run: (port: EditorCommandPort, isCurrent: () => boolean) => Promise<unknown>) => {
    if (!sessionId || !state.view || mutationInFlight.current || captionPreflightInFlight.current) return;
    const epoch = routeEpoch.current.value;
    const operationId = mutationOperationId.current + 1;
    mutationOperationId.current = operationId;
    const isCurrent = () => routeEpoch.current.value === epoch && mutationOperationId.current === operationId;
    const currentView = state.view;
    mutationInFlight.current = true;
    setMutation({ isSaving: true, message: "변경 내용을 저장하고 있어요." });
    // Any successful mutation invalidates the current exact-preview artifact
    // in the same backend transaction. Unmount it before issuing the request
    // so the browser cannot re-fetch a now-fenced URL and emit a transient 404.
    flushSync(() => {
      setState((current) => current.key === requestKey && current.view
        ? {
            ...current,
            view: {
              ...current.view,
              playback: {
                ...current.view.playback,
                exactPreview: { ...current.view.playback.exactPreview, status: "stale", url: null },
              },
            },
          }
        : current);
    });
    // Let the committed removal reach the media element lifecycle before the
    // backend can fence the artifact. This ordering prevents even a very fast
    // mutation response from racing a final browser range request.
    await new Promise<void>((resolve) => window.setTimeout(resolve, 0));
    if (!isCurrent()) {
      mutationInFlight.current = false;
      return;
    }
    const port = createEditorCommandPort({
      projectId,
      sessionId,
      expectedRevision: currentView.expectedRevision,
    });
    let resultMessage = "변경 내용을 저장했어요.";
    let mutationSucceeded = true;
    try {
      // 성공한 편집이 **자기 사정을 직접 말할 수 있게** 한다. 더빙처럼 "됐다"만으로는
      // 모자란 편집이 있다 -- 못 넣은 장면이 있으면 그것까지 말해 줘야 한다.
      const spoken = await run(port, isCurrent);
      if (typeof spoken === "string" && spoken.trim()) resultMessage = spoken;
      if (isCurrent()) {
        setMutation({ isSaving: true, message: "변경 내용을 저장했어요. 최신 내용을 불러오고 있어요." });
      }
    } catch (error) {
      mutationSucceeded = false;
      resultMessage = error instanceof ApiConflictError
        ? "다른 변경이 먼저 저장됐어요. 최신 내용을 확인한 뒤 다시 시도해 주세요."
        : voiceFailureMessage(error)
          ?? "변경 내용을 저장하지 못했어요. 최신 내용을 확인한 뒤 다시 시도해 주세요.";
      if (isCurrent()) setMutation({ isSaving: true, message: resultMessage });
    }
    if (!isCurrent()) return;
    const refreshOperationId = manifestOperationId.current + 1;
    manifestOperationId.current = refreshOperationId;
    const isCurrentRefresh = () => isCurrent() && manifestOperationId.current === refreshOperationId;
    try {
      const [manifest, editingSession] = await Promise.all([
        api.getEditorPlaybackManifest(projectId, sessionId),
        api.getEditingSession(projectId, sessionId),
      ]);
      if (!isCurrentRefresh()) return;
      const next = joinEditorSnapshot(manifest, editingSession);
      if (next.view.projectId !== projectId || next.view.sessionId !== sessionId) {
        throw new Error("editor_snapshot_identity_mismatch");
      } else {
        setState({ key: requestKey, view: next.view, session: next.session, error: null });
        // Auto-refresh the preview after a successful edit instead of leaving
        // the creator to notice it's stale and press the manual button
        // themselves (F-4). A failure here is silent -- the manual refresh
        // button in preview-stage.tsx stays as the fallback.
        // A full exact render is cheap enough to keep automatic for short
        // projects. Long-form sources stay explicit so a sequence of caption,
        // undo, or placement edits cannot queue overlapping multi-minute
        // FFmpeg jobs. The manual refresh control remains available.
        if (mutationSucceeded && next.view.output.durationSec <= 120) {
          void api.startExactPreview(projectId, sessionId, { expected_revision: next.view.expectedRevision })
            .then(() => { if (isCurrentRefresh()) setRefreshToken((current) => current + 1); })
            .catch(() => {});
        }
      }
    } catch (error) {
      if (isCurrent()) {
        if (error instanceof Error && error.message === "editor_snapshot_identity_mismatch") {
          resultMessage = "최신 편집 상태가 일치하지 않아요. 새로고침한 뒤 다시 시도해 주세요.";
        } else {
          resultMessage = "최신 편집 내용을 불러오지 못했어요. 새로고침한 뒤 다시 시도해 주세요.";
        }
        // A failed post-mutation refresh leaves server-application status
        // ambiguous. Keep the editor fail-closed instead of restoring a view
        // whose preview and revision may already be invalid.
        setState({ key: requestKey, view: null, session: null, error: resultMessage });
      }
    } finally {
      if (isCurrent()) {
        mutationInFlight.current = false;
        setMutation({ isSaving: false, message: resultMessage });
        setPartialRecoveryRetryToken((current) => current + 1);
      }
    }
  };
  // 이미지 자산을 장면 **위에** 얹는다. `적용`(B-roll 교체)과 다른 길이다.
  // 오버레이 endpoint와 렌더는 처음부터 있었는데 화면에 부르는 자리가 없었다.
  // 문구는 나중에 편집 항목의 `이미지` 절에서 붙일 수 있으므로 빈 값으로 만든다.
  // 라이브러리 그림은 아직 이 프로젝트 자산이 아니다. 오버레이는 프로젝트
  // 자산 식별자만 읽으므로 먼저 복사한다. 복사는 내용 해시로 이미 있는 것을
  // 다시 쓰므로, 같은 그림을 여러 장면에 얹어도 사본이 늘지 않는다.
  const applyImageOverlay = (card: EditorAssetCard, segmentId: string) =>
    commitTimelineMutation(async (port, isCurrent) => {
      let assetId = card.assetId;
      if (!assetId && card.libraryAssetId) {
        const materialized = await api.materializeLibraryAsset(card.libraryAssetId, projectId);
        if (!isCurrent()) return;
        assetId = materialized.asset.asset_id;
      }
      if (!assetId) throw new Error("asset identifier is missing");
      return port.applyOverlay({ kind: "image", segmentId, assetId, text: "" });
    });
  const applyAssetCard = (card: EditorAssetCard, segmentId: string) => card.kind === "broll"
    ? commitTimelineMutation((port) => port.applyMedia({ kind: "broll", segmentId, assetId: card.assetId }))
    : commitTimelineMutation(async (port, isCurrent) => {
      // 그림은 장면을 갈아 끼우지 않고 그 위에 얹는다. 화면에도 `적용` 단추가
      // 없지만, 이 갈래가 열려 있으면 다른 호출자가 조용히 잘못 들어온다.
      if (card.kind === "image") throw new Error("pictures are laid over a scene, not applied to it");
      if (!card.libraryAssetId) throw new Error("library asset identifier is missing");
      const materialized = await api.materializeMediaLibraryAsset(card.libraryAssetId, projectId);
      if (!isCurrent()) return;
      return port.applyMedia({ kind: card.kind, segmentId, assetId: materialized.asset_id });
    });
  const activePartial = partial.key === requestKey
    ? partial
    : { key: requestKey, ticket: null, preflight: null, run: null, jobId: null, result: null, isResultOpen: false, message: null };
  const partialScope = (action: Extract<InspectorAction, { kind: "partial-preflight" | "partial-run" | "partial-resume" }>) => {
    if (!sessionId || !state.view || action.segmentIds.length !== 1) return null;
    return {
      projectId,
      sessionId,
      routeEpoch: routeEpoch.current.value,
      revision: state.view.expectedRevision,
      segmentId: action.segmentIds[0],
      fields: action.fields,
    };
  };
  const preflightPartialRegeneration = async (action: Extract<InspectorAction, { kind: "partial-preflight" }>) => {
    const scope = partialScope(action);
    const ticket = scope ? createPartialRegenerationTicket(scope) : null;
    if (!scope || !ticket || partialInFlight.current || mutationInFlight.current) return;
    const epoch = routeEpoch.current.value;
    const operationId = partialOperationId.current + 1;
    partialOperationId.current = operationId;
    const isCurrent = () => routeEpoch.current.value === epoch && partialOperationId.current === operationId;
    partialInFlight.current = true;
    setPartial({ key: requestKey, ticket: null, preflight: null, run: null, jobId: null, result: null, isResultOpen: false, message: "바뀌는 범위를 확인하고 있어요." });
    try {
      const preflight = await api.previewPartialRegeneration(projectId, sessionId!, {
        segment_ids: [ticket.segmentId],
        fields: [...ticket.fields],
      });
      if (!preflightMatchesPartialRegenerationTicket(ticket, preflight)) {
        throw new Error("partial_regeneration_preflight_identity_mismatch");
      }
      if (isCurrent()) {
        setPartial({ key: requestKey, ticket, preflight, run: null, jobId: null, result: null, isResultOpen: false, message: "영향 범위를 확인했어요. 실행 버튼을 눌러야 실제로 다시 만듭니다." });
      }
    } catch {
      if (isCurrent()) setPartial({ key: requestKey, ticket: null, preflight: null, run: null, jobId: null, result: null, isResultOpen: false, message: "영향 범위를 확인하지 못했어요. 직접 편집은 계속할 수 있어요." });
    } finally {
      if (isCurrent()) partialInFlight.current = false;
    }
  };
  const runPartialRegeneration = async (action: Extract<InspectorAction, { kind: "partial-run" }>) => {
    const scope = partialScope(action);
    if (!scope || !canRunPartialRegeneration(activePartial.ticket, scope) || partialInFlight.current || mutationInFlight.current) return;
    partialInFlight.current = true;
    setPartial((current) => current.key === requestKey ? { ...current, message: "선택한 범위를 다시 만들고 있어요." } : current);
    try {
      await commitTimelineMutation(async (_port, isCurrent) => {
        try {
          const ticket = activePartial.ticket!;
          const result = await api.runPartialRegeneration(projectId, sessionId!, {
            expected_revision: scope.revision,
            segment_ids: [scope.segmentId],
            fields: [...ticket.fields],
          });
          if (!runMatchesPartialRegenerationTicket(ticket, result)) {
            throw new Error("partial_regeneration_run_identity_mismatch");
          }
          if (isCurrent()) {
            setPartial({
              key: requestKey,
              ticket: null,
              preflight: null,
              run: result,
              jobId: result.job_id!.trim(),
              result: null,
              isResultOpen: false,
              message: "부분 재생성을 마쳤어요. 이전 결과 열기에서 결과 범위를 확인할 수 있어요.",
            });
          }
        } catch (error) {
          if (isCurrent()) {
            setPartial({
              key: requestKey,
              ticket: null,
              preflight: null,
              run: null,
              jobId: null,
              result: null,
              isResultOpen: false,
              message: "부분 재생성을 완료하지 못했어요. 영향 범위를 다시 확인해 주세요.",
            });
          }
          throw error;
        }
      });
    } finally {
      if (routeEpoch.current.value === scope.routeEpoch) partialInFlight.current = false;
    }
  };
  const resumePartialRegeneration = async (action: Extract<InspectorAction, { kind: "partial-resume" }>) => {
    const scope = partialScope(action);
    const jobId = activePartial.jobId;
    if (!scope || !jobId || !state.session || partialInFlight.current || mutationInFlight.current) return;
    const epoch = routeEpoch.current.value;
    const mutationGeneration = mutationOperationId.current;
    const operationId = partialOperationId.current + 1;
    partialOperationId.current = operationId;
    const ownsOperation = () => routeEpoch.current.value === epoch && partialOperationId.current === operationId;
    const isCurrent = () => (
      ownsOperation()
      && mutationOperationId.current === mutationGeneration
    );
    partialInFlight.current = true;
    try {
      const result = await api.getPartialRegenerationResult(projectId, jobId);
      if (!isCurrent()) return;
      const canRestore = canRestorePartialRegenerationResult({
        sessionId: state.session.sessionId,
        sessionUpdatedAt: state.session.updatedAt ?? "",
        jobId,
        segmentId: scope.segmentId,
        fields: scope.fields,
      }, result);
      setPartial((current) => current.key === requestKey
        ? {
          ...current,
          result: canRestore ? result : current.result,
          isResultOpen: canRestore,
          message: canRestore ? "현재 편집본과 맞는 이전 결과를 열었어요." : "현재 편집본의 구간·항목과 맞지 않는 이전 결과는 열지 않았어요.",
        }
        : current);
    } catch {
      if (isCurrent()) setPartial((current) => current.key === requestKey ? { ...current, message: "이전 결과를 확인하지 못했어요. 직접 편집은 계속할 수 있어요." } : current);
    } finally {
      if (ownsOperation()) partialInFlight.current = false;
    }
  };
  const preflightCaptionStyle = async (action: Extract<InspectorAction, { kind: "preflight-caption-style" }>) => {
    if (!sessionId || !state.view || mutationInFlight.current || captionPreflightInFlight.current) return;
    const epoch = routeEpoch.current.value;
    const currentView = state.view;
    captionPreflightInFlight.current = true;
    setMutation({ isSaving: true, message: "자막 적용 범위를 확인하고 있어요." });
    try {
      const port = createEditorCommandPort({ projectId, sessionId, expectedRevision: currentView.expectedRevision });
      await port.previewCaptionStyle({ segmentIds: action.segmentIds, scope: action.scope, style: action.style });
      if (routeEpoch.current.value !== epoch) return;
      captionPreflightInFlight.current = false;
      await commitTimelineMutation((nextPort) => nextPort.setCaptionStyle({ segmentIds: action.segmentIds, scope: action.scope, style: action.style }));
    } catch {
      if (routeEpoch.current.value === epoch) setMutation({ isSaving: false, message: "자막 모양을 적용할 범위를 확인하지 못했어요." });
    } finally {
      captionPreflightInFlight.current = false;
    }
  };
  const handleInspectorAction = (action: InspectorAction) => {
    if (action.kind === "preflight-caption-style") return preflightCaptionStyle(action);
    // 더빙은 **편집 한 번이 아니라 오래 도는 작업이다.** 장면당 13초라
    // 스무 장면이면 사 분이 넘는다. 다른 편집과 같은 통로로 보내면 "저장하고
    // 있어요"만 뜬 채로 몇 분이 흐르고, 프록시가 먼저 끊는다.
    if (action.kind === "dub-narration") return dubNarration(action);
    if (action.kind === "partial-preflight") return preflightPartialRegeneration(action);
    if (action.kind === "partial-run") return runPartialRegeneration(action);
    if (action.kind === "partial-resume") return resumePartialRegeneration(action);
    return commitTimelineMutation(async (port) => {
      if (action.kind === "split-narration") return port.splitNarration({ segmentId: action.segmentId, splitSec: action.splitSec });
      if (action.kind === "merge-narration") return port.mergeNarration({ leftSegmentId: action.leftSegmentId, rightSegmentId: action.rightSegmentId });
      if (action.kind === "set-cut-action") return port.setCutAction({ segmentId: action.segmentId, cutAction: action.cutAction });
      if (action.kind === "set-transition") return port.setSceneTransition({ segmentId: action.segmentId, transition: action.transition });
      if (action.kind === "save-media") return port.updateMediaControls({ kind: action.mediaKind, segmentId: action.segmentId, assetId: action.assetId, controls: action.controls });
      if (action.kind === "clear-media") return port.clearMedia({ kind: action.mediaKind, segmentId: action.segmentId });
      if (action.kind === "apply-tts-candidate") return port.applyTtsCandidate({ segmentId: action.segmentId, candidateId: action.candidateId, assetId: action.assetId });
      if (action.kind === "clear-tts-candidate") return port.clearTtsCandidate({ segmentId: action.segmentId });
      if (action.kind === "clear-overlay") return port.clearOverlay({ kind: action.overlayKind, segmentId: action.segmentId });
      // 자막 번역은 장면 하나가 아니라 편집본 전체에 걸린다. 다른 편집과
      // 같은 통로로 보내서 되돌리기·충돌 확인을 그대로 받는다.
      if (action.kind === "translate-captions") {
        const translated = await port.translateCaptions({ language: action.language });
        // **못 옮긴 장면이 있으면 말해 준다.** 안 말하면 그 장면은 원래 자막
        // 그대로 완성본에 나가는데, 창작자는 다 옮겨진 줄 안다 -- 243장면이면
        // 스물한 묶음이라 한 묶음만 어긋나도 영어 영상 한가운데 한국어가 뜬다.
        //
        // 다시 눌러도 손해가 없다는 것까지 말한다. 이미 옮긴 장면은 건너뛰고
        // 남은 장면만 다시 시도한다.
        const missing = translated.segments.filter(
          (segment) =>
            String(segment.caption_text ?? "").trim() &&
            !String(segment.caption_translations?.[action.language] ?? "").trim(),
        ).length;
        return missing > 0
          ? `${missing}개 장면은 옮기지 못했어요. 그 장면은 원래 자막 그대로 나가요. 다시 눌러 주시면 남은 장면만 다시 해 봐요.`
          : undefined;
      }
      if (action.kind === "set-caption-language") return port.setCaptionLanguage({ language: action.language });
      if (action.overlayKind === "explanation-card") return port.applyOverlay({ kind: action.overlayKind, segmentId: action.segmentId, title: action.title, body: action.body, text: action.text });
      if (action.overlayKind === "image") return port.applyOverlay({ kind: action.overlayKind, segmentId: action.segmentId, assetId: action.assetId, text: action.text });
      if (action.overlayKind === "shape") return port.applyOverlay({ kind: action.overlayKind, segmentId: action.segmentId, shape: action.shape, vertical: action.vertical, horizontal: action.horizontal, size: action.size, motion: action.motion });
      return port.applyOverlay({ kind: action.overlayKind, segmentId: action.segmentId, columns: action.columns, rows: action.rows, text: action.text });
    });
  };
  /** 더빙에 쓸 목소리 후보. 이름은 창작자가 알아볼 수 있는 것으로 준다.
   *
   *  **여기서 `useCallback`을 쓰면 안 된다** -- 이 자리는 early return 아래라
   *  hook을 부르면 렌더마다 hook 개수가 달라진다(2026-09-02에 실제로 그렇게
   *  깨뜨렸고 프런트 시험 147건이 잡았다). 바로 아래 `loadApprovedTtsCandidates`가
   *  평범한 함수인 것도 같은 이유다.
   *
   *  대신 **읽는 쪽이 이 함수의 정체성에 의존하지 않는다**(`InspectorControls`).
   */
  /** 더빙을 걸고, 진행 상황을 화면에 계속 알리고, 끝나면 편집본을 다시 읽는다.
   *
   *  다른 편집과 통로를 나눈 이유: 장면당 13초라 스무 장면이면 사 분이 넘는다.
   *  "저장하고 있어요"만 띄운 채로 그 시간을 흘려보내면 창작자는 멈춘 줄 안다.
   */
  const dubNarration = async (action: { language: string; voiceSampleAssetId: string | null }) => {
    if (!sessionId || !state.session || mutationInFlight.current) return;
    const epoch = routeEpoch.current.value;
    const isCurrent = () => routeEpoch.current.value === epoch;
    mutationInFlight.current = true;
    setMutation({ isSaving: true, message: "목소리를 만들 준비를 하고 있어요." });
    let outcome: DubbingOutcome;
    try {
      outcome = await runDubbingWithProgress({
        projectId,
        sessionId,
        expectedRevision: state.session.expectedRevision,
        language: action.language,
        voiceSampleAssetId: action.voiceSampleAssetId,
        isStillRelevant: isCurrent,
        onProgress: (done, total) => {
          if (!isCurrent()) return;
          setMutation({
            isSaving: true,
            message: total > 0
              ? `목소리를 만들고 있어요. ${total}개 장면 중 ${done}개 했어요.`
              : "목소리를 만들고 있어요.",
          });
        },
      });
    } catch (error) {
      // **사유는 원문 그대로 들고 있는다.** 여기서 미리 옮겨 두면 아래에서 또
      // 옮기려다 못 알아보고 일반 안내로 떨어진다 -- 옮기는 자리는 한 곳이다.
      outcome = { kind: "failed", detail: error instanceof ApiRequestError ? error.detail : null };
    } finally {
      mutationInFlight.current = false;
    }
    if (!isCurrent()) return;
    // 실패 사유는 **반드시 창작자 말로 옮겨서** 쓴다. 서버가 준 사유는 영어
    // 기술 문구라 그대로 내보내면 안 된다(§10.13). 옮길 말이 없으면 일반 안내로
    // 돌아간다 -- 못 옮긴 영어를 보여 주느니 그 편이 낫다.
    const message = outcome.kind === "failed"
      ? voiceFailureMessage(outcome.detail) ?? dubbingOutcomeMessage(outcome)
      : dubbingOutcomeMessage(outcome);
    // 편집본을 다시 읽고 결과를 알리는 일은 **기존 통로가 이미 한다.**
    // 여기서 서버를 또 건드릴 필요는 없다 -- 더빙은 이미 끝났다.
    await commitTimelineMutation(async () => message);
  };

  const loadVoiceSamples = async () => {
    const assets = await api.listVoiceSamples(projectId);
    // 자산 응답에는 파일 이름이 없다. 저장 위치의 끝 이름을 쓰되, 알아보기 어려운
    // 해시뿐이면 **번호를 붙인 사람 말**로 부른다(§10.13 창작자 언어).
    return assets.map((asset, index) => ({ assetId: asset.asset_id, label: voiceSampleLabel(asset, index) }));
  };

  const loadApprovedTtsCandidates = async (segmentId: string) => {
    const epoch = routeEpoch.current.value;
    const result = await api.listTtsCandidates(projectId, segmentId);
    if (routeEpoch.current.value !== epoch) return [];
    return result.candidates
      .filter((candidate) => candidate.technical_status === "accepted" && candidate.operator_review_status === "approved")
      .map((candidate) => ({
        assetId: candidate.asset_id,
        candidateId: candidate.candidate_id,
        sourceText: candidate.source_text,
      }));
  };
  const assetCards = assets.key === requestKey
    ? projectEditorAssets({ projectId, brollAssets: assets.brollAssets, libraryAssets: assets.libraryAssets, libraryImageAssets: assets.libraryImageAssets })
    : [];
  const prepareAssetPreview = async (card: EditorAssetCard) => {
    assetPreviewAbort.current?.abort();
    const controller = new AbortController();
    assetPreviewAbort.current = controller;
    const epoch = routeEpoch.current.value;
    const routeKey = requestKey;
    try {
      const previewUrl = await prepareProjectAssetBrowserPreview(projectId, card.assetId, controller.signal);
      if (controller !== assetPreviewAbort.current || routeEpoch.current.value !== epoch || routeEpoch.current.key !== routeKey) {
        throw new DOMException("Aborted", "AbortError");
      }
      return previewUrl;
    } finally {
      if (assetPreviewAbort.current === controller) assetPreviewAbort.current = null;
    }
  };
  const partialTicketIsCurrent = activePartial.ticket !== null && canRunPartialRegeneration(activePartial.ticket, {
    projectId,
    sessionId: sessionId ?? "",
    routeEpoch: routeEpoch.current.value,
    revision: state.view.expectedRevision,
    segmentId: activePartial.ticket.segmentId,
    fields: activePartial.ticket.fields,
  });
  const partialResultIsCurrent = Boolean(
    activePartial.jobId
    && activePartial.result
    && state.session
    && activePartial.result.segment_ids.length === 1
    && state.session.segments.some((segment) => segment.segmentId === activePartial.result!.segment_ids[0])
    && canRestorePartialRegenerationResult({
      sessionId: state.session.sessionId,
      sessionUpdatedAt: state.session.updatedAt ?? "",
      jobId: activePartial.jobId,
      segmentId: activePartial.result.segment_ids[0],
      fields: activePartial.result.fields,
    }, activePartial.result),
  );
  const activeVariants = variants.key === requestKey ? variants.items : [];
  const patchOutputVariant = async (variant: OutputVariant, patch: OutputVariantPatch) => {
    if (variantMutationInFlight.current || !sessionId || routeEpoch.current.key !== requestKey) return;
    variantMutationInFlight.current = true;
    const operationId = variantOperationId.current + 1;
    variantOperationId.current = operationId;
    const isCurrent = () => routeEpoch.current.key === requestKey && variantOperationId.current === operationId;
    setVariants((current) => current.key === requestKey ? { ...current, busy: true } : current);
    setVariants((current) => current.key === requestKey ? { ...current, message: "출력 변형을 저장하는 중이에요.", busy: true } : current);
    try {
      const result = await api.patchOutputVariant(projectId, variant.variant_id, {
        expected_variant_revision: variant.variant_revision,
        patch,
      });
      if (!isCurrent()) return;
      setVariants((current) => current.key !== requestKey ? current : {
        ...current,
        items: current.items.map((item) => item.variant_id === result.variant.variant_id ? result.variant : item),
        message: "출력 변형을 저장했어요.",
        busy: false,
      });
    } catch {
      if (isCurrent()) setVariants((current) => current.key === requestKey ? { ...current, message: "출력 변형을 저장하지 못했어요. 최신 상태를 다시 확인해 주세요.", busy: false } : current);
    } finally {
      if (isCurrent()) variantMutationInFlight.current = false;
    }
  };
  const materializeOutputVariant = async (variant: OutputVariant) => {
    if (variantMutationInFlight.current || !sessionId || routeEpoch.current.key !== requestKey) return;
    variantMutationInFlight.current = true;
    const operationId = variantOperationId.current + 1;
    variantOperationId.current = operationId;
    const isCurrent = () => routeEpoch.current.key === requestKey && variantOperationId.current === operationId;
    setVariants((current) => current.key === requestKey ? { ...current, message: "출력 변형을 준비하는 중이에요.", busy: true } : current);
    try {
      const result = await api.materializeOutputVariant(projectId, variant.variant_id, { expected_master_session_revision: variant.source_session_revision });
      if (isCurrent()) setVariants((current) => current.key === requestKey ? { ...current, message: `출력 변형을 준비했어요. ${result.materialization.timeline_id}`, busy: false } : current);
    } catch {
      if (isCurrent()) setVariants((current) => current.key === requestKey ? { ...current, message: "출력 변형을 준비하지 못했어요. 충돌과 최신 상태를 확인해 주세요.", busy: false } : current);
    } finally {
      if (isCurrent()) variantMutationInFlight.current = false;
    }
  };
  const createHighlightVariant = async () => {
    if (variantMutationInFlight.current || !sessionId || activeVariants.some((variant) => variant.kind === "vertical_highlight")) return;
    variantMutationInFlight.current = true;
    const operationId = variantOperationId.current + 1;
    variantOperationId.current = operationId;
    const isCurrent = () => routeEpoch.current.key === requestKey && variantOperationId.current === operationId;
    setVariants((current) => current.key === requestKey ? { ...current, message: "하이라이트 변형을 만드는 중이에요.", busy: true } : current);
    try {
      const result = await api.createOutputVariant(projectId, { source_session_id: sessionId, kind: "vertical_highlight" });
      if (isCurrent()) setVariants((current) => current.key === requestKey ? { ...current, items: [...current.items, result.variant], message: "하이라이트 변형을 만들었어요. 자막이 많은 장면 위주로 자동으로 골랐어요 -- 마음에 안 들면 전체 장면으로 되돌릴 수 있어요.", busy: false } : current);
    } catch {
      if (isCurrent()) setVariants((current) => current.key === requestKey ? { ...current, message: "하이라이트 변형을 만들지 못했어요.", busy: false } : current);
    } finally {
      if (isCurrent()) variantMutationInFlight.current = false;
    }
  };
  const activeDirector = director.key === requestKey ? director : createDirectorState(requestKey, sessionId);
  const activeMemory = memory.key === requestKey
    && memory.conversationId === activeDirector.conversationId
    ? memory
    : createMemoryState(requestKey);
  const updateMemoryCandidate = (
    candidateId: string,
    update: (current: MemoryCandidateState) => MemoryCandidateState,
  ) => {
    setMemory((current) => (
      current.key === requestKey
      && current.conversationId === activeDirector.conversationId
        ? {
          ...current,
          candidates: current.candidates.map((candidate) => (
            candidate.candidate.candidate_id === candidateId
              ? update(candidate)
              : candidate
          )),
        }
        : current
    ));
  };
  const mergeMemoryStorageResult = (
    current: MemoryCandidateState,
    result: YujinMemoryStoreResult,
  ): MemoryCandidateState => ({
    candidate: {
      ...current.candidate,
      status: result.status,
      storage_status: result.storage_status,
      retryable: result.retryable,
    },
    action: "idle",
    error: null,
  });
  const beginMemoryMutation = () => {
    if (
      memoryMutationInFlight.current
      || !activeDirector.conversationId
    ) return null;
    const operationId = memoryMutationOperationId.current + 1;
    memoryMutationOperationId.current = operationId;
    memoryMutationInFlight.current = true;
    return {
      conversationId: activeDirector.conversationId,
      epoch: routeEpoch.current.value,
      operationId,
    };
  };
  const isCurrentMemoryMutation = (ownership: Readonly<{
    conversationId: string;
    epoch: number;
    operationId: number;
  }>) => (
    routeEpoch.current.value === ownership.epoch
    && memoryMutationOperationId.current === ownership.operationId
    && currentDirectorConversationId.current === ownership.conversationId
  );
  const finishMemoryMutation = (ownership: Readonly<{
    conversationId: string;
    epoch: number;
    operationId: number;
  }>) => {
    if (!isCurrentMemoryMutation(ownership)) return;
    memoryMutationInFlight.current = false;
  };
  const createMemoryCandidate = async () => {
    const proposedText = activeMemory.candidateDraft.trim();
    const sourceMessageIds = Array.from(new Set(
      activeDirector.memorySourceMessageIds,
    )).slice(-8);
    if (
      activeMemory.createAction !== "idle"
      || !proposedText
      || proposedText.length > 280
      || sourceMessageIds.length < 1
    ) return;
    const requestUuid = globalThis.crypto?.randomUUID?.();
    if (!requestUuid) {
      setMemory((current) => (
        current.key === requestKey
        && current.conversationId === activeDirector.conversationId
          ? {
            ...current,
            createError: "기억 후보를 만들지 못했어요. 대화와 편집은 계속할 수 있어요.",
          }
          : current
      ));
      return;
    }
    const ownership = beginMemoryMutation();
    if (!ownership) return;
    setMemory((current) => (
      current.key === requestKey
      && current.conversationId === ownership.conversationId
        ? {
          ...current,
          createAction: "creating",
          createError: null,
        }
        : current
    ));
    try {
      const created = await api.createYujinMemoryCandidate(projectId, {
        conversation_id: ownership.conversationId,
        client_request_id: `memory-create-${requestUuid}`,
        source_message_ids: sourceMessageIds,
        memory_scope: "creator",
        category: activeMemory.candidateCategory,
        proposed_text: proposedText,
      });
      if (!isCurrentMemoryMutation(ownership)) return;
      if (
        created.project_id !== projectId
        || created.conversation_id !== ownership.conversationId
      ) {
        throw new Error("yujin_memory_candidate_identity_mismatch");
      }
      const listOperationId = memoryListOperationId.current + 1;
      memoryListOperationId.current = listOperationId;
      const candidates = await api.listYujinMemoryCandidates(
        projectId,
        ownership.conversationId,
      );
      if (
        !isCurrentMemoryMutation(ownership)
        || memoryListOperationId.current !== listOperationId
      ) return;
      if (candidates.some((candidate) => (
        candidate.project_id !== projectId
        || candidate.conversation_id !== ownership.conversationId
      ))) {
        throw new Error("yujin_memory_candidate_identity_mismatch");
      }
      setMemory((current) => (
        current.key === requestKey
        && current.conversationId === ownership.conversationId
          ? {
            ...current,
            candidates: candidates.map((candidate) => ({
              candidate,
              action: "idle",
              error: null,
            })),
            candidateDraft: "",
            createAction: "idle",
            createError: null,
            loadError: null,
          }
          : current
      ));
    } catch {
      if (!isCurrentMemoryMutation(ownership)) return;
      setMemory((current) => (
        current.key === requestKey
        && current.conversationId === ownership.conversationId
          ? {
            ...current,
            createAction: "idle",
            createError: "기억 후보를 만들지 못했어요. 대화와 편집은 계속할 수 있어요.",
          }
          : current
      ));
    } finally {
      finishMemoryMutation(ownership);
    }
  };
  const storeMemoryCandidate = async (candidateId: string) => {
    const selected = activeMemory.candidates.find(
      (candidate) => candidate.candidate.candidate_id === candidateId,
    );
    if (
      !selected
      || selected.action !== "idle"
      || selected.candidate.status !== "approved"
      || ![
        "not_requested",
        "claimed",
        "event_pending",
        "failed_retryable",
        "ambiguous",
      ].includes(selected.candidate.storage_status)
      || (
        selected.candidate.storage_status === "claimed"
        && !selected.candidate.retryable
      )
    ) return;
    const requestUuid = globalThis.crypto?.randomUUID?.();
    if (!requestUuid) {
      updateMemoryCandidate(candidateId, (current) => ({
        ...current,
        error: "save",
      }));
      return;
    }
    const ownership = beginMemoryMutation();
    if (!ownership) return;
    updateMemoryCandidate(candidateId, (current) => ({
      ...current,
      action: "saving",
      error: null,
    }));
    try {
      const result = await api.storeYujinMemoryCandidate(
        projectId,
        candidateId,
        `memory-store-${requestUuid}`,
      );
      if (!isCurrentMemoryMutation(ownership)) return;
      if (result.candidate_id !== candidateId) {
        throw new Error("yujin_memory_store_identity_mismatch");
      }
      updateMemoryCandidate(
        candidateId,
        (current) => mergeMemoryStorageResult(current, result),
      );
    } catch (failure) {
      if (!isCurrentMemoryMutation(ownership)) return;
      updateMemoryCandidate(candidateId, (current) => ({
        ...current,
        action: "idle",
        // 기억 기능이 켜져 있지 않은 것은 저장 실패가 아니다. owner가 할 일이
        // 다르다 -- 다시 누르는 게 아니라 켜는 것이다.
        error: failure instanceof ApiRequestError && failure.detail === "memory_not_configured" ? "not_configured" : "save",
      }));
    } finally {
      finishMemoryMutation(ownership);
    }
  };
  const approveAndStoreMemoryCandidate = async (candidateId: string) => {
    const selected = activeMemory.candidates.find(
      (candidate) => candidate.candidate.candidate_id === candidateId,
    );
    if (
      !selected
      || selected.action !== "idle"
      || selected.candidate.status !== "pending"
      || selected.candidate.storage_status !== "not_requested"
    ) return;
    const ownership = beginMemoryMutation();
    if (!ownership) return;
    let approvalCompleted = false;
    updateMemoryCandidate(candidateId, (current) => ({
      ...current,
      action: "approving",
      error: null,
    }));
    try {
      const approved = await api.approveYujinMemoryCandidate(
        projectId,
        candidateId,
      );
      if (!isCurrentMemoryMutation(ownership)) return;
      if (
        approved.candidate_id !== candidateId
        || approved.project_id !== projectId
        || approved.conversation_id !== ownership.conversationId
        || approved.status !== "approved"
      ) {
        throw new Error("yujin_memory_approval_identity_mismatch");
      }
      approvalCompleted = true;
      updateMemoryCandidate(candidateId, () => ({
        candidate: approved,
        action: "saving",
        error: null,
      }));
      const requestUuid = globalThis.crypto?.randomUUID?.();
      if (!requestUuid) {
        throw new Error("yujin_memory_request_id_unavailable");
      }
      const result = await api.storeYujinMemoryCandidate(
        projectId,
        candidateId,
        `memory-store-${requestUuid}`,
      );
      if (!isCurrentMemoryMutation(ownership)) return;
      if (result.candidate_id !== candidateId) {
        throw new Error("yujin_memory_store_identity_mismatch");
      }
      updateMemoryCandidate(
        candidateId,
        (current) => mergeMemoryStorageResult(current, result),
      );
    } catch {
      if (!isCurrentMemoryMutation(ownership)) return;
      updateMemoryCandidate(candidateId, (current) => ({
        ...current,
        action: "idle",
        error: approvalCompleted ? "save" : null,
      }));
    } finally {
      finishMemoryMutation(ownership);
    }
  };
  const rejectMemoryCandidate = async (candidateId: string) => {
    const selected = activeMemory.candidates.find(
      (candidate) => candidate.candidate.candidate_id === candidateId,
    );
    if (
      !selected
      || selected.action !== "idle"
      || selected.candidate.status !== "pending"
      || selected.candidate.storage_status !== "not_requested"
    ) return;
    const ownership = beginMemoryMutation();
    if (!ownership) return;
    updateMemoryCandidate(candidateId, (current) => ({
      ...current,
      action: "rejecting",
      error: null,
    }));
    try {
      const rejected = await api.rejectYujinMemoryCandidate(
        projectId,
        candidateId,
      );
      if (!isCurrentMemoryMutation(ownership)) return;
      if (
        rejected.candidate_id !== candidateId
        || rejected.project_id !== projectId
        || rejected.conversation_id !== ownership.conversationId
        || rejected.status !== "rejected"
      ) {
        throw new Error("yujin_memory_rejection_identity_mismatch");
      }
      updateMemoryCandidate(candidateId, () => ({
        candidate: rejected,
        action: "idle",
        error: null,
      }));
    } catch {
      if (!isCurrentMemoryMutation(ownership)) return;
      updateMemoryCandidate(candidateId, (current) => ({
        ...current,
        action: "idle",
        error: null,
      }));
    } finally {
      finishMemoryMutation(ownership);
    }
  };
  const deleteMemoryCandidate = async (candidateId: string) => {
    const selected = activeMemory.candidates.find(
      (candidate) => candidate.candidate.candidate_id === candidateId,
    );
    if (
      !selected
      || selected.action !== "idle"
      || selected.candidate.status !== "approved"
      || selected.candidate.storage_status !== "stored"
    ) return;
    const ownership = beginMemoryMutation();
    if (!ownership) return;
    updateMemoryCandidate(candidateId, (current) => ({
      ...current,
      action: "deleting",
      error: null,
    }));
    try {
      const result = await api.deleteYujinMemoryCandidate(
        projectId,
        candidateId,
      );
      if (!isCurrentMemoryMutation(ownership)) return;
      if (result.candidate_id !== candidateId) {
        throw new Error("yujin_memory_delete_identity_mismatch");
      }
      updateMemoryCandidate(
        candidateId,
        (current) => mergeMemoryStorageResult(current, result),
      );
    } catch {
      if (!isCurrentMemoryMutation(ownership)) return;
      updateMemoryCandidate(candidateId, (current) => ({
        ...current,
        action: "idle",
        error: "delete",
      }));
    } finally {
      finishMemoryMutation(ownership);
    }
  };
  const isCurrentDirector = (epoch: number, operationId: number) => routeEpoch.current.value === epoch && directorOperationId.current === operationId;
  // Local-first Yujin chat (docs/decisions/2026-08-05-local-first-assistant-decision.ko.md):
  // this is a single synchronous local request/response, not a Hermes agent-gateway run.
  // There is no server-side "run" object to stream or cancel, so submitDirectorMessage
  // resolves in one round trip and cancellation is a plain client-side fetch abort.
  const submitDirectorMessage = async (submittedDraft: string, clientMessageId: string) => {
    const currentView = state.view;
    if (
      !sessionId
      || !currentView
      || hermesRunInFlight.current
      || directorMutationInFlight.current
      || activeHermesRouteRun.current !== null
    ) return;
    const epoch = routeEpoch.current.value;
    const operationId = hermesOperationId.current + 1;
    const expectedDirectorOperationId = directorOperationId.current;
    hermesOperationId.current = operationId;
    hermesRunInFlight.current = true;
    const controller = new AbortController();
    hermesAbort.current = controller;
    const optimisticUserId = `hermes-user:${clientMessageId}`;
    const isCurrentHermes = () => (
      routeEpoch.current.value === epoch
      && hermesOperationId.current === operationId
      && currentEditorRevision.current === currentView.expectedRevision
      && directorOperationId.current === expectedDirectorOperationId
      && !controller.signal.aborted
    );
    setDirector((current) => current.key === requestKey ? {
      ...current,
      isSending: true,
      runState: { kind: "idle" },
      // A new request changes the conversational context, so never let the
      // creator apply the candidate derived from the previous instruction.
      editingProposal: null,
      editingProposalCreating: false,
      editingProposalApplying: false,
      editingProposalError: null,
      editingProposalPreview: { kind: "idle" },
      messages: capDirectorMessages([...current.messages, { id: optimisticUserId, role: "user", text: submittedDraft }]),
    } : current);
    try {
      let conversationId = activeDirector.conversationId;
      if (!conversationId) {
        const conversation = await api.createDirectorConversation(projectId, { session_id: sessionId });
        if (!isCurrentHermes()) return;
        conversationId = conversation.conversation_id;
        currentDirectorConversationId.current = conversationId;
      }
      activeHermesRouteRun.current = {
        projectId,
        conversationId,
        runId: clientMessageId,
        controller,
      };
      lastDirectorSubmission.current = { conversationId, clientMessageId, text: submittedDraft };
      const result = await api.sendDirectorMessage(projectId, conversationId, {
        session_id: sessionId,
        client_message_id: clientMessageId,
        text: submittedDraft,
      }, controller.signal);
      if (!isCurrentHermes()) return;
      if (result.kind === "in_progress") {
        setDirector((current) => current.key === requestKey ? {
          ...current,
          messages: current.messages.filter((message) => message.id !== optimisticUserId),
          runState: { kind: "unavailable", message: "이미 처리 중이에요. 잠시 후 다시 시도해주세요.", retryable: true },
        } : current);
        return;
      }
      const { exchange } = result;
      setDirector((current) => current.key === requestKey ? {
        ...current,
        conversationId,
        draft: current.draft === submittedDraft ? "" : current.draft,
        messages: capDirectorMessages([
          ...current.messages.filter((message) => message.id !== optimisticUserId),
          { id: exchange.user_message.message_id, role: "user", text: exchange.user_message.text },
          { id: exchange.assistant_message.message_id, role: "assistant", text: exchange.assistant_message.text },
        ]),
        runState: { kind: "complete", runId: exchange.assistant_message.message_id },
      } : current);
    } catch (error) {
      if (isAbortError(error) || !isCurrentHermes()) return;
      setDirector((current) => current.key === requestKey ? {
        ...current,
        messages: current.messages.filter((message) => message.id !== optimisticUserId),
        runState: { kind: "unavailable", message: yujinUnavailableMessage, retryable: true },
        isSending: false,
      } : current);
    } finally {
      if (routeEpoch.current.value === epoch && hermesOperationId.current === operationId) {
        hermesRunInFlight.current = false;
        activeHermesRouteRun.current = null;
        if (hermesAbort.current === controller) hermesAbort.current = null;
        setDirector((current) => current.key === requestKey ? { ...current, isSending: false } : current);
      }
    }
  };
  const sendDirectorMessage = async (text: string) => {
    const submittedDraft = text.trim();
    if (!submittedDraft) return;
    const clientMessageId = globalThis.crypto?.randomUUID?.();
    if (!clientMessageId) {
      setDirector((current) => current.key === requestKey ? { ...current, runState: { kind: "unavailable", message: yujinUnavailableMessage } } : current);
      return;
    }
    await submitDirectorMessage(submittedDraft, clientMessageId);
    await interpretAndApplySpokenEdit(submittedDraft);
  };
  /** 편집안 하나를 지금 편집본에 적용한다.
   *
   *  대화에서 저절로 부르는 자리와 `편집안 보기` 대화상자의 `적용` 단추가 같은
   *  경로를 쓴다 -- 낡음 확인(preflight)과 되돌릴 수 있는 한 번의 저장을 두 벌로
   *  갈라 두지 않는다. 갈라 두면 한쪽만 고쳐지는 사고가 난다. */
  const applyEditingProposalNow = async (proposal: YujinEditingProposal, revision: number): Promise<boolean> => {
    if (!sessionId || !state.view) return false;
    const view = state.view;
    setDirector((current) => current.key === requestKey ? { ...current, editingProposalApplying: true, editingProposalError: null } : current);
    try {
      const preflight = await api.preflightYujinEditingProposal(projectId, sessionId, proposal.proposal_id);
      if (preflight.status === "stale") {
        setDirector((current) => current.key === requestKey ? { ...current, editingProposalApplying: false, editingProposalError: "편집본이 바뀌어서 이 편집안은 다시 만들어야 해요." } : current);
        return false;
      }
      let applied = false;
      await commitTimelineMutation(async () => {
        await api.applyYujinEditingProposal(projectId, sessionId, proposal.proposal_id, { expected_revision: revision });
        applied = true;
        setDirector((current) => current.key === requestKey ? {
          ...current,
          editingProposal: null,
          editingProposalApplying: false,
          editingProposalPreview: { kind: "idle" },
          completions: [...current.completions, editingProposalCompletionEntry(proposal, view)],
        } : current);
      });
      if (!applied) setDirector((current) => current.key === requestKey ? { ...current, editingProposalApplying: false } : current);
      return applied;
    } catch {
      setDirector((current) => current.key === requestKey ? { ...current, editingProposalApplying: false, editingProposalError: "편집안을 적용하지 못했어요. 최신 편집본을 확인해 주세요." } : current);
      return false;
    }
  };
  /** 말로 시킨 편집을 그대로 적용한다 (owner 2026-09-01: "바로 적용하자").
   *
   *  예전에는 대화가 **답만 하고 끝났다** -- 편집으로 옮기려면 `이 대화로 편집안
   *  만들기`를 따로 누르고, 다시 `적용`을 눌러야 했다. owner는 실제로 써 보고
   *  "말로 컷 편집이 되는지 확인한 적이 없는 것 같다"고 지적했고, 두 번 더 누르는
   *  단계를 없애기로 결정했다(`decisions/2026-09-01-yujin-chat-applies-edits-directly.ko.md`).
   *
   *  안전장치는 사람의 클릭이 아니라 **되돌리기**다. 이 저장은 되돌릴 수 있는
   *  변경 한 건으로 쌓이고, 무엇이 바뀌었는지 완료 목록에 남는다. 편집 요청이
   *  아니었으면 편집안이 만들어지지 않으므로(`proposal: null`) 아무 일도 없다. */
  const interpretAndApplySpokenEdit = async (instruction: string) => {
    // 여기서 `activeDirector.editingProposal`을 보지 않는다. 이 값은 **보내기
    // 이전 화면**의 것이고, 보내기가 이미 그것을 지웠다(`submitDirectorMessage`:
    // "새 요청은 대화 맥락을 바꾸므로 이전 지시에서 나온 후보를 적용하게 두지
    // 않는다"). 옛 값으로 막으면 화면에 후보가 떠 있던 상태에서 보낸 **첫
    // 메시지만** 조용히 적용되지 않는다 -- 사람이 재현하기 어려운 종류의 결함이다.
    if (!sessionId || !state.view) return;
    const epoch = routeEpoch.current.value;
    const revision = currentEditorRevision.current;
    if (revision === null) return;
    let result: Awaited<ReturnType<typeof api.createYujinEditingProposal>>;
    try {
      result = await api.createYujinEditingProposal(projectId, sessionId, { instruction });
    } catch {
      // 창작자가 누른 동작이 아니라 우리가 덧붙인 해석이다. 대화 답변은 이미
      // 화면에 있으니 조용히 둔다 -- 직접 만드는 단추가 그대로 남아 있다.
      return;
    }
    if (routeEpoch.current.value !== epoch || currentEditorRevision.current !== revision) return;
    // 편집 요청이 아니었거나 유진이 되물어야 하는 경우다. 대화 답변으로 충분하다.
    if ("proposal" in result) return;
    const applied = await applyEditingProposalNow(result, revision);
    // 적용이 막혔으면 후보를 화면에 남긴다 -- 창작자가 내용을 보고 다시 누를 수 있다.
    if (!applied) {
      setDirector((current) => current.key === requestKey
        ? { ...current, editingProposal: result, editingProposalPreview: { kind: "idle" } }
        : current);
    }
  };
  const createYujinEditingProposal = async () => {
    if (
      !sessionId
      || !state.view
      || activeDirector.editingProposal
      || activeDirector.editingProposalCreating
      || activeDirector.isSending
      || mutationInFlight.current
    ) return;
    const instruction = [...activeDirector.messages]
      .reverse()
      .find((message) => message.role === "user")?.text.trim();
    if (!instruction) return;
    const epoch = routeEpoch.current.value;
    const revision = state.view.expectedRevision;
    setDirector((current) => current.key === requestKey
      ? { ...current, editingProposalCreating: true, startFailure: null }
      : current);
    try {
      const result = await api.createYujinEditingProposal(projectId, sessionId, { instruction });
      if (
        routeEpoch.current.value !== epoch
        || currentEditorRevision.current !== revision
      ) return;
      if ("proposal" in result) {
        setDirector((current) => current.key === requestKey
          ? { ...current, editingProposalCreating: false, startFailure: result.reply_text }
          : current);
        return;
      }
      setDirector((current) => current.key === requestKey
        ? { ...current, editingProposal: result, editingProposalCreating: false, editingProposalPreview: { kind: "idle" }, startFailure: null }
        : current);
    } catch {
      if (routeEpoch.current.value !== epoch) return;
      setDirector((current) => current.key === requestKey
        ? { ...current, editingProposalCreating: false, startFailure: "편집안을 만들지 못했어요. 잠시 뒤 다시 눌러 주세요." }
        : current);
    }
  };
  const cancelDirectorRun = () => {
    const ownedRun = activeHermesRouteRun.current;
    if (
      !ownedRun
      || ownedRun.projectId !== projectId
      || ownedRun.conversationId !== activeDirector.conversationId
    ) return;
    const epoch = routeEpoch.current.value;
    const operationId = hermesOperationId.current;
    // No server-side run to notify -- aborting the fetch is the cancellation.
    ownedRun.controller.abort();
    if (
      routeEpoch.current.value !== epoch
      || hermesOperationId.current !== operationId
      || activeHermesRouteRun.current !== ownedRun
    ) return;
    hermesOperationId.current += 1;
    hermesRunInFlight.current = false;
    activeHermesRouteRun.current = null;
    if (hermesAbort.current === ownedRun.controller) {
      hermesAbort.current = null;
    }
    setDirector((current) => current.key === requestKey ? {
      ...current,
      isSending: false,
      messages: current.messages.filter((message) => message.id !== `hermes-user:${ownedRun.runId}`),
      runState: {
        kind: "unavailable",
        message: yujinUnavailableMessage,
        retryable: true,
      },
    } : current);
  };
  const retryDirectorRun = async () => {
    const sourceRunState = activeDirector.runState;
    const submission = lastDirectorSubmission.current;
    if (
      sourceRunState.kind !== "unavailable"
      || !sourceRunState.retryable
      || !submission
      || !activeDirector.conversationId
      || submission.conversationId !== activeDirector.conversationId
    ) return;
    await submitDirectorMessage(submission.text, submission.clientMessageId);
  };
  const startDirector = async () => {
    if (
      !sessionId
      || activeDirector.proposal
      || activeDirector.state !== "idle"
      || directorMutationInFlight.current
      || hermesRunInFlight.current
      || activeHermesRouteRun.current !== null
    ) return;
    const epoch = routeEpoch.current.value;
    const operationId = directorOperationId.current + 1;
    directorOperationId.current = operationId;
    directorMutationInFlight.current = true;
    setDirector({ ...activeDirector, state: "analysis_running", startFailure: null });
    try {
      let conversationId = activeDirector.conversationId;
      if (!conversationId) {
        const conversation = await api.createDirectorConversation(projectId, { session_id: sessionId });
        if (!isCurrentDirector(epoch, operationId)) return;
        conversationId = conversation.conversation_id;
      }
      // 방금 한 말을 함께 보낸다. 무엇을 청했는지가 후보에 닿지 않으면 "음악
      // 추천해 줘"에 영상만 오는 일이 생긴다(owner 2026-08-19). **판단은 백엔드가**
      // 한다 -- 같은 규칙을 여기에도 두면 두 벌이 조용히 어긋난다.
      const lastRequest = [...activeDirector.messages].reverse().find((message) => message.role === "user")?.text;
      const proposal = await api.createDirectorProposal(projectId, { session_id: sessionId, request_text: lastRequest });
      if (isCurrentDirector(epoch, operationId)) setDirector((current) => current.key === requestKey ? { ...current, state: "proposal_ready", conversationId, proposal, startFailure: null, selectedCandidateIds: proposal.candidates[0]?.candidate_id ? [proposal.candidates[0].candidate_id] : [] } : current);
    } catch (error) {
      // 상태를 `blocked`으로 떨어뜨리지 않는다. 그러면 이유는 보여도 다시 누를
      // 자리가 사라져서, 말은 하되 나갈 길이 없는 화면이 된다.
      if (isCurrentDirector(epoch, operationId)) setDirector({ ...activeDirector, state: "idle", startFailure: directorStartFailureMessage(error) });
    } finally {
      if (isCurrentDirector(epoch, operationId)) directorMutationInFlight.current = false;
    }
  };
  /** 낡은 추천에서 유진에게 돌아가는 유일한 길.
   *
   * 편집본이 바뀐 뒤 적용을 누르면 서버는 "다시 받으라"고 답하고 화면은 막힌
   * 상태가 된다. 그런데 새 추천 받기는 이미 추천이 있으면 눌리지 않으므로,
   * 이 자리가 없으면 owner는 유진에게 돌아갈 방법이 없었다.
   */
  const refreshDirectorProposal = async () => {
    const proposal = activeDirector.proposal;
    if (
      !proposal
      || directorMutationInFlight.current
      || mutationInFlight.current
      || activeDirector.state === "analysis_running"
      || activeDirector.state === "applying"
    ) return;
    const epoch = routeEpoch.current.value;
    const operationId = directorOperationId.current + 1;
    directorOperationId.current = operationId;
    directorMutationInFlight.current = true;
    setDirector({ ...activeDirector, state: "analysis_running" });
    try {
      const refreshed = await api.refreshDirectorProposal(projectId, proposal.proposal_id);
      if (isCurrentDirector(epoch, operationId)) {
        setDirector((current) => current.key === requestKey ? {
          ...current,
          state: "proposal_ready",
          proposal: refreshed,
          selectedCandidateIds: initialDirectorCandidateIds(refreshed),
        } : current);
      }
    } catch {
      if (isCurrentDirector(epoch, operationId)) setDirector({ ...activeDirector, state: "blocked" });
    } finally {
      if (isCurrentDirector(epoch, operationId)) directorMutationInFlight.current = false;
    }
  };
  const applyDirectorProposal = async (proposalId: string, candidateIds: readonly string[]) => {
    if (!sessionId || !state.view || activeDirector.proposal?.proposal_id !== proposalId || !candidateIds.length || directorMutationInFlight.current || mutationInFlight.current) return;
    const proposal = activeDirector.proposal;
    const yujinActionable = isYujinActionableProposal(proposal);
    const selectedYujinCandidate = yujinActionable && candidateIds.length === 1
      ? proposal.candidates.find((candidate) => candidate.candidate_id === candidateIds[0]) ?? null
      : null;
    if (yujinActionable && (
      proposal.base_session_revision !== state.view.expectedRevision
      || !selectedYujinCandidate
      || !isActionableYujinCandidate(selectedYujinCandidate)
    )) return;
    const epoch = routeEpoch.current.value;
    const operationId = directorOperationId.current + 1;
    directorOperationId.current = operationId;
    directorMutationInFlight.current = true;
    const currentRevision = state.view.expectedRevision;
    // 완료 목록에 쓸 장면 이름표를 여기서 미리 잡아 둔다 -- await 뒤에서
    // `state.view`를 다시 읽으면 그사이 갱신됐을 수 있고, 타입도 다시 좁혀지지 않는다.
    const sceneLabelsForCompletion = sceneLabelsBySegmentId(state.view);
    setDirector({ ...activeDirector, state: "applying" });
    try {
      await commitTimelineMutation(async (port, isCurrentMutation) => {
        try {
          const preflight = await api.preflightDirectorProposal(projectId, proposalId);
          const isCurrentApply = () => (
            isCurrentMutation()
            && isCurrentDirector(epoch, operationId)
            && currentEditorRevision.current === currentRevision
          );
          if (!isCurrentApply()) return;
          if (preflight.status === "stale" || preflight.code === "stale_proposal") {
            setDirector({ ...activeDirector, state: "blocked" });
            throw new Error("stale director proposal");
          }
           if (selectedYujinCandidate && isActionableYujinVariantCandidate(selectedYujinCandidate)) {
             await api.batchApplyDirectorProposal(projectId, proposalId, {
               candidate_ids: [...candidateIds],
               expected_revision: currentRevision,
             });
           } else if (selectedYujinCandidate && isActionableYujinMediaCandidate(selectedYujinCandidate)) {
            const materialized = await api.materializeDirectorCandidate(
              projectId,
              proposalId,
              selectedYujinCandidate.candidate_id,
            );
            if (!isCurrentApply()) return;
            await port.applyMedia({
              kind: selectedYujinCandidate.media_type as "broll" | "bgm" | "sfx",
              segmentId: String(selectedYujinCandidate.canonical_metadata.target_segment_id),
              assetId: materialized.asset_id,
              controls: editorControlsFromCandidate(selectedYujinCandidate),
            });
          } else if (selectedYujinCandidate) {
            await applyYujinB4Candidate(port, proposalId, selectedYujinCandidate);
          } else {
            await api.batchApplyDirectorProposal(projectId, proposalId, { candidate_ids: [...candidateIds], expected_revision: currentRevision });
          }
          if (isCurrentApply()) {
            // **여기서만 완료로 적는다.** 실패는 catch로 빠지므로 이 줄에 왔다는
            // 것 자체가 성공이다 -- 성공/실패를 따로 판단하지 않는다.
            const completionEntry = buildCompletionEntry(
              projectDirectorProposal(projectId, proposal, currentRevision, sceneLabelsForCompletion),
              candidateIds,
            );
            setDirector({
              ...activeDirector,
              state: "proposal_ready",
              completions: completionEntry
                ? [...(activeDirector.completions ?? []), completionEntry]
                : activeDirector.completions,
            });
          }
        } catch (error) {
          if (isCurrentMutation() && isCurrentDirector(epoch, operationId)) setDirector({ ...activeDirector, state: "blocked" });
          throw error;
        }
      });
    } finally {
      if (isCurrentDirector(epoch, operationId)) {
        directorMutationInFlight.current = false;
      }
    }
  };
  const ownsActiveHermesRouteRun = Boolean(
    activeHermesRouteRun.current
    && activeHermesRouteRun.current.projectId === projectId
    && activeHermesRouteRun.current.conversationId === activeDirector.conversationId,
  );
  const rightDock: RightDockDirector = {
    state: mutation.isSaving ? "applying" : activeDirector.state,
    messages: activeDirector.messages,
    completions: activeDirector.completions,
    proposal: projectDirectorProposal(projectId, activeDirector.proposal, state.view.expectedRevision, sceneLabelsBySegmentId(state.view)),
    draft: activeDirector.draft,
    runState: activeDirector.runState,
    selectedCandidateIds: activeDirector.selectedCandidateIds,
    conversationScroll: activeDirector.conversationScroll,
    memory: {
      candidates: activeMemory.candidates.map((candidate) => ({
        candidateId: candidate.candidate.candidate_id,
        text: candidate.candidate.proposed_text,
        category: candidate.candidate.category,
        status: candidate.candidate.status,
        storageStatus: candidate.candidate.storage_status,
        retryable: candidate.candidate.retryable,
        action: candidate.action,
        error: candidate.error,
      })),
      loadError: activeMemory.loadError,
      candidateDraft: activeMemory.candidateDraft,
      candidateCategory: activeMemory.candidateCategory,
      createAction: activeMemory.createAction,
      createError: activeMemory.createError,
      canCreateCandidate: Boolean(
        activeMemory.candidateDraft.trim()
        && activeDirector.memorySourceMessageIds.length,
      ),
      onCandidateDraftChange: (candidateDraft) => setMemory((current) => (
        current.key === requestKey
        && current.conversationId === activeDirector.conversationId
          ? { ...current, candidateDraft, createError: null }
          : current
      )),
      onCandidateCategoryChange: (candidateCategory) => setMemory((current) => (
        current.key === requestKey
        && current.conversationId === activeDirector.conversationId
          ? { ...current, candidateCategory, createError: null }
          : current
      )),
      onCreateCandidate: createMemoryCandidate,
      onApproveAndStore: approveAndStoreMemoryCandidate,
      onReject: rejectMemoryCandidate,
      onStore: storeMemoryCandidate,
      onDelete: deleteMemoryCandidate,
    },
    composerDisabled: mutation.isSaving || activeDirector.isSending === true || activeDirector.state === "analysis_running" || activeDirector.state === "applying" || ownsActiveHermesRouteRun,
    onDraftChange: (draft) => setDirector((current) => current.key === requestKey ? { ...current, draft } : current),
    onSelectedCandidateIdsChange: (selectedCandidateIds) => setDirector((current) => current.key === requestKey ? { ...current, selectedCandidateIds } : current),
    onConversationScrollChange: (conversationScroll) => setDirector((current) => current.key === requestKey ? { ...current, conversationScroll } : current),
    onSendMessage: sendDirectorMessage,
    // 답변이 끝날 때마다 이어서 해볼 것 셋. 대화를 시작하기 전에는 대화
    // 스타터가 그 자리를 맡으므로, 주고받은 것이 있을 때만 낸다.
    //
    // `useMemo`로 감싸지 않았다. 이 컴포넌트는 hook을 전부 이른 반환(`state.view`
    // 확인) 앞에 두고 있어서 여기에 hook을 새로 끼우려면 그 위로 올려야 하는데,
    // 2,600줄짜리 컴포넌트에서 hook 순서를 옮기는 것이 이 계산을 아끼는 것보다
    // 위험하다. 비용은 클립 수에 한 번 비례하는 정도이고(같은 렌더에서
    // `sceneLabelsBySegmentId`가 이미 같은 일을 한다), 대화 전에는 아예 돌지 않는다.
    qualityFollowUps: activeDirector.messages.length && state.view
      ? buildQualityFollowUps({ view: state.view, selectedSegmentId: state.view.local.selectedSegmentId })
      : [],
    onCreateEditingProposal: createYujinEditingProposal,
    editingProposal: activeDirector.editingProposal ? {
      proposalId: activeDirector.editingProposal.proposal_id,
      summary: yujinEditingProposalSummary(activeDirector.editingProposal, state.view),
      operationSummaries: activeDirector.editingProposal.diff.operations.map(yujinEditingOperationSummary),
      followUpQuestions: activeDirector.editingProposal.diff.follow_up_questions.slice(0, 3),
      previewTarget: yujinEditingProposalPreviewTarget(activeDirector.editingProposal, state.view),
      isApplying: activeDirector.editingProposalApplying,
      error: activeDirector.editingProposalError,
      preview: editingProposalPreviewForDock(activeDirector.editingProposalPreview),
    } : null,
    editingProposalCreating: activeDirector.editingProposalCreating,
    onPreviewEditingProposal: activeDirector.editingProposal
      ? () => previewYujinEditingProposal(activeDirector.editingProposal!.proposal_id)
      : undefined,
    onApplyEditingProposal: activeDirector.editingProposal
      ? () => void applyEditingProposalNow(activeDirector.editingProposal!, state.view!.expectedRevision)
      : undefined,
    onCancelRun: ownsActiveHermesRouteRun
      ? cancelDirectorRun
      : undefined,
    onRetryRun: activeDirector.runState.kind === "unavailable"
      && activeDirector.runState.retryable
      && !ownsActiveHermesRouteRun
      ? retryDirectorRun
      : undefined,
    onApplyProposal: applyDirectorProposal,
    onRefreshProposal: activeDirector.proposal ? refreshDirectorProposal : undefined,
    transitionSuggestions: transitionSuggestions.key === requestKey ? transitionSuggestions.items.map((suggestion) => ({
      segmentId: suggestion.segment_id,
      type: suggestion.type,
      durationSec: suggestion.duration_sec,
      reason: suggestion.reason,
    })) : [],
    onApplyTransitionSuggestion: (suggestion) => commitTimelineMutation((port) => port.setSceneTransition({
      segmentId: suggestion.segmentId,
      transition: { type: suggestion.type, durationSec: suggestion.durationSec, chosenBy: "yujin" },
    })),
    onManualEdit: () => setDirector((current) => current.key === requestKey ? { ...current, state: "idle" } : current),
    // 붙여 넣은 글을 이 프로젝트의 대본으로 받는다(owner 2026-08-19). 대본을
    // 통째로 받는 경로는 이미 있었고(`creation-briefs/upload`) **부르는 자리만
    // 없었다** -- 대본은 `/plan`의 문답형 인터뷰로만 들어왔다.
    //
    // **여기서 장면을 만들지 않는다.** 대본을 만들어 두고 확정 화면으로 보낸다 --
    // 확정은 owner가 누르는 게이트이고, 그것을 없애지 않기로 승인돼 있다
    // (`decisions/2026-08-16-autonomous-creator-loop-scope-expansion.ko.md`).
    onUseDraftAsScript: async (script: string) => {
      const trimmed = script.trim();
      if (!trimmed) return;
      const file = new File([trimmed], "붙여넣은-대본.txt", { type: "text/plain" });
      let brief = await api.uploadCreationBrief(projectId, file, {
        idempotency_key: `paste:${Date.now()}`,
        capability_profile: {},
      });
      // 대본을 이미 가진 사람에게 **다시 묻지 않는다.** 붙여 넣고 나면 브리프는
      // `interviewing`으로 시작해 "누구에게 보여줄까요" 같은 질문 다섯 개를 세우고,
      // 요약이 비어 있으면 확정이 400으로 거절된다(2026-08-19에 끝까지 돌려 보고
      // 알았다). 둘 다 여기서 넘겨 두고 **확정만 사람에게 남긴다.**
      if (brief.status === "interviewing") {
        brief = await api.bypassCreationBriefInterview(projectId, brief.brief_id, { expected_revision: brief.revision });
      }
      if (!brief.summary?.trim()) {
        brief = await api.updateCreationBriefSummary(projectId, brief.brief_id, {
          summary: pastedScriptSummary(trimmed),
          expected_revision: brief.revision,
        });
      }
      // **확정 화면이 이 브리프를 찾을 수 있게 남긴다.** 이걸 빼먹었더니 대본은
      // 서버에 만들어졌는데 화면은 빈 폼을 보여 줬다 -- 붙여 넣은 글을 다시
      // 만날 길이 없었다(2026-08-19, 배포 뒤에 발견). 기획 화면은 이 키로만
      // 브리프를 되찾는다.
      try { window.localStorage.setItem(creationBriefStorageKey(projectId), brief.brief_id); } catch { /* 저장이 막혀도 이동은 한다 */ }
      // 확정 화면으로 보낸다. 전역 메뉴와 같은 평범한 주소 이동이다 -- 이
      // 컴포넌트는 라우터를 갖고 있지 않고, 갖게 하려고 결합을 늘리지 않는다.
      window.location.assign(resolveWorkspaceLocation(projectId, "create"));
    },
    // 재생은 편집 작업판이 가진 미리 듣기 자리가 맡는다. 여기서 빈 함수를
    // 넘기고 있었는데, 그 값은 작업판이 어차피 덮어쓴다 -- 남겨 두면 화면이
    // 미리 보기를 안 한다는 잘못된 인상만 준다.
    onStart: activeDirector.state === "idle"
      && !activeDirector.proposal
      && activeDirector.runState.kind !== "streaming"
      && !ownsActiveHermesRouteRun
      ? startDirector
      : undefined,
    startFailure: activeDirector.startFailure,
  };
  return <>
    {state.error ? <p role="status">{state.error}</p> : null}
    {assets.key === requestKey && assets.error ? <p role="status">{assets.error}</p> : null}
    {activePartial.message ? <p role="status">{activePartial.message}</p> : null}
    {partialRecoveryError ? <Button onClick={() => setPartialRecoveryRetryToken((current) => current + 1)} type="button">이전 결과 다시 찾기</Button> : null}
    {activePartial.preflight?.affected_output_areas.length ? <ul aria-label="부분 재생성 영향 범위">{activePartial.preflight.affected_output_areas.map((area) => <li key={area}>{affectedAreaLabel(area)}</li>)}</ul> : null}
    {activePartial.isResultOpen && activePartial.result && partialResultIsCurrent ? <dl aria-label="부분 재생성 결과">
      <dt>상태</dt><dd>{partialStatusLabel(activePartial.result.status)}</dd>
      <dt>대상 구간 수</dt><dd>{activePartial.result.segment_ids.length}</dd>
      <dt>다시 만든 항목</dt><dd>{activePartial.result.fields.map(partialFieldLabel).join(", ")}</dd>
    </dl> : null}
    {variants.key === requestKey && variants.message ? <p role="status">{variants.message}</p> : null}
    <EditorWorkbench
    assetCards={assetCards}
    isSavingTimeline={mutation.isSaving}
    loadApprovedTtsCandidates={loadApprovedTtsCandidates}
    loadVoiceSamples={loadVoiceSamples}
    onApplyAssetCard={applyAssetCard}
    onApplyImageOverlay={applyImageOverlay}
    onPrepareAssetPreview={prepareAssetPreview}
    onInspectorAction={handleInspectorAction}
    onPreviewRefresh={refreshPreview}
    onPreviewSelectedRange={previewSelectedRange}
    onMediaAdded={() => setAssetRefreshToken((current) => current + 1)}
    onReorderNarration={(input) => commitTimelineMutation((port) => port.reorderNarration(input))}
    onRedo={() => commitTimelineMutation((port) => port.redo())}
    onTrimNarration={(input) => commitTimelineMutation((port) => port.setNarrationBounds(input))}
    onSetSegmentRippleSpeed={(input) => commitTimelineMutation((port) => port.setSegmentRippleSpeed(input))}
    onUndo={() => commitTimelineMutation((port) => port.undo())}
    onUpdateCaption={(input) => commitTimelineMutation((port) => port.setCaptionText({
      ...input,
      // **화면이 보여 주는 언어를 같이 보낸다.** 영어를 보면서 고치는데 이걸
      // 빼면 한국어 원본이 영어로 덮여 사라지고, 완성본에 나가는 영어는
      // 그대로다(2026-09-03 실측). 유진이 고치는 길은 이걸 안 보낸다 --
      // 유진은 한국어 원문을 보고 말하므로 원본을 고치는 것이 맞다.
      language: state.session?.captionLanguage ?? null,
    }))}
    onUpdatePlacements={(input) => commitTimelineMutation((port) => port.setTimelinePlacements(input))}
    onUpdateTrackStates={(states) => commitTimelineMutation((port) => port.setTrackStates(states))}
    partialRegeneration={{
      fields: PARTIAL_REGENERATION_FIELDS,
      defaultFields: ["caption", "music"],
      preparedFields: activePartial.ticket?.fields,
      preparedSegmentId: activePartial.ticket?.segmentId,
      canRun: partialTicketIsCurrent,
      canResume: partialResultIsCurrent,
    }}
    session={state.session}
    ttsCandidateScopeKey={requestKey}
    timelineMutationMessage={mutation.message}
    director={rightDock}
    requestedSegmentId={requestedSegmentId}
    serverVariants={activeVariants}
    onVariantMaterialize={materializeOutputVariant}
    onVariantPatch={patchOutputVariant}
    onVariantCreateHighlight={createHighlightVariant}
    variantBusy={variants.key === requestKey && variants.busy}
    view={state.view}
    />
  </>;
}

/** 성공적으로 적용된 후보들을 완료 목록 한 줄로 묶는다. **찾지 못한 후보는
 *  버리지 않고 코드로 남긴다** -- 조용히 빠뜨리면 "완료됐다는데 몇 개는 안 보인다"는
 *  더 나쁜 화면이 된다. `projected`가 비었으면(제안이 그새 사라짐 등) 아무 기록도
 *  남기지 않는다 -- 빈 완료 카드는 EditPilot에도 없는, 뜻 없는 화면이다. */
function buildCompletionEntry(
  projected: RightDockProposal | null,
  candidateIds: readonly string[],
): RightDockCompletionEntry | null {
  if (!projected) return null;
  const byId = new Map(projected.candidates.map((candidate) => [candidate.candidateId, candidate]));
  const items = candidateIds.map((candidateId) => {
    const candidate = byId.get(candidateId);
    return {
      label: candidate?.displayName ?? candidate?.visibleReferenceCode ?? candidateId,
      sceneLabel: candidate?.targetSceneLabel,
    };
  });
  if (!items.length) return null;
  return { id: `completion-${candidateIds.join("-")}-${Date.now()}`, appliedAt: new Date().toISOString(), items };
}

/** 적용된 편집안을 완료 목록 한 줄로 남긴다.
 *
 *  말로 시킨 편집은 창작자가 `적용`을 누르지 않으므로, **무엇이 바뀌었는지
 *  화면에 남는 자리가 이것뿐이다.** 조용히 바뀌는 타임라인은 되돌리기가 있어도
 *  나쁜 화면이다 -- 무엇을 되돌려야 하는지 알 수 없기 때문이다. */
function editingProposalCompletionEntry(proposal: YujinEditingProposal, view: EditorViewModel): RightDockCompletionEntry {
  const sceneNumbers = sceneNumbersBySegmentId(view);
  return {
    id: `completion-${proposal.proposal_id}-${Date.now()}`,
    appliedAt: new Date().toISOString(),
    items: proposal.diff.operations.map((operation) => {
      const sceneNumber = typeof operation.segment_id === "string" ? sceneNumbers.get(operation.segment_id) : undefined;
      return { label: yujinEditingOperationSummary(operation), sceneLabel: sceneNumber ? `${sceneNumber}번 장면` : undefined };
    }),
  };
}

function yujinEditingProposalSummary(proposal: YujinEditingProposal, view: EditorViewModel): string {
  const speed = proposal.diff.operations.find((operation) => operation.intent === "set_scene_speed");
  if (!speed || typeof speed.segment_id !== "string" || typeof speed.rate !== "number") {
    return "편집안을 준비했어요.";
  }
  const clips = view.tracks.flatMap((track) => track.clips)
    .filter((clip) => clip.segmentId === speed.segment_id);
  if (!clips.length || speed.rate <= 0) return "편집안을 준비했어요.";
  const start = Math.min(...clips.map((clip) => clip.startSec));
  const end = Math.max(...clips.map((clip) => clip.endSec));
  const sceneNumber = sceneNumbersBySegmentId(view).get(speed.segment_id);
  if (!sceneNumber) return "편집안을 준비했어요.";
  const formatSeconds = (seconds: number) => Number.isInteger(seconds) ? String(seconds) : String(Number(seconds.toFixed(1)));
  const before = formatSeconds(end - start);
  const after = formatSeconds((end - start) / speed.rate);
  return `${sceneNumber}번 장면 · ${before}초 → ${after}초`;
}

function yujinEditingOperationSummary(operation: YujinEditingProposal["diff"]["operations"][number]): string {
  if (operation.intent === "set_scene_speed" && typeof operation.rate === "number") return `${operation.rate}배로 속도를 바꿔요.`;
  if (operation.intent === "set_cut_action") return "장면 포함 여부를 바꿔요.";
  if (operation.intent === "set_caption_text") return "자막을 고쳐요.";
  // 넣는 것과 빼는 것을 한 줄로 뭉치지 않는다. 말로 시킨 편집은 창작자가 `적용`을
  // 누르지 않으므로 **이 줄이 무엇을 했는지 알려 주는 유일한 자리다**(2026-09-01
  // 실사용 확인: "승인된 미디어 배치를 바꿔요"만 보고는 넣었는지 뺐는지 알 수 없었다).
  if (operation.intent === "apply_media" || operation.intent === "remove_media") {
    const what = operation.media_type === "bgm" ? "배경 음악" : operation.media_type === "sfx" ? "효과음" : "영상";
    return operation.intent === "apply_media" ? `골라 둔 ${what}을 넣어요.` : `넣어 둔 ${what}을 빼요.`;
  }
  if (operation.intent === "set_segment_bounds") return "장면 길이를 조정해요.";
  // 색감은 코드가 아니라 화면에 쓰는 이름으로 적는다(§10.13). 목록에 없는
  // 코드는 검증기가 막으므로 여기 오지 않지만, 와도 코드를 그대로 내보이지
  // 않는다 -- 창작자에게 `vintage`는 아무 뜻이 없다.
  if (operation.intent === "set_scene_look") {
    const label = typeof operation.look === "string" ? sceneFilterLabel(operation.look) : null;
    return label ? `색감을 ${label} 바꿔요.` : "색감을 바꿔요.";
  }
  if (operation.intent === "reorder_segments") return "장면 순서를 바꿔요.";
  return "편집 항목을 바꿔요.";
}

function yujinEditingProposalPreviewTarget(proposal: YujinEditingProposal, view: EditorViewModel): { segmentId: string; startSec: number; endSec: number } | null {
  const segmentId = proposal.target_segment_ids[0];
  if (!segmentId) return null;
  const clip = view.tracks.flatMap((track) => track.clips).find((candidate) => candidate.segmentId === segmentId);
  return clip ? { segmentId, startSec: clip.startSec, endSec: clip.endSec } : null;
}

function projectDirectorProposal(projectId: string, proposal: DirectorProposal | null, currentRevision: number, sceneLabels: ReadonlyMap<string, string> = new Map()): RightDockProposal | null {
  if (!proposal) return null;
  const isYujin = isYujinProposal(proposal);
  return {
    proposalId: proposal.proposal_id,
    status: proposal.status,
    baseSessionRevision: proposal.base_session_revision,
    currentRevision,
    // 뜻으로 찾았는지 단어로만 찾았는지. 없으면 화면이 아무 말도 하지 않는다.
    matchMode: typeof proposal.diff?.match_mode === "string" ? proposal.diff.match_mode : undefined,
    // 서버가 여러 후보를 한 번에 받는 추천에서만 여러 개를 고르게 한다. 유진이
    // 직접 실행하는 추천은 `reject_yujin_direct_apply`가 422로 막으므로, 여기서
    // 열어 주면 고를 수는 있는데 적용이 거절되는 화면이 된다.
    allowsMultipleSelection: !isYujinActionableProposal(proposal),
    candidates: proposal.candidates.map((candidate) => {
      const metadata = candidate.canonical_metadata ?? {};
      const targetSegmentId = String(candidate.target_segment_id ?? metadata.target_segment_id ?? proposal.target_segment_ids[0] ?? "");
      const actionable = isYujin
        ? isActionableYujinCandidate(candidate)
        : proposal.status === "ready";
      return {
        candidateId: candidate.candidate_id,
        visibleReferenceCode: candidate.visible_reference_code,
        mediaType: candidate.media_type,
        // 후보의 `preview_uri`는 늘 비어 온다. 그것만 보고 있었기 때문에 "추천
        // 미리 보기" 단추가 한 번도 그려지지 않았다. 실제 파일을 흘려 주는
        // 주소는 따로 있다.
        previewUrl: isPreviewableMediaCandidate(candidate, isYujin, proposal.status === "ready")
          ? api.directorCandidatePreviewUrl(projectId, proposal.proposal_id, candidate.candidate_id)
          : candidate.preview_uri,
        kind: candidate.media_type,
        sourceMediaKind: String(metadata.source_media_kind ?? candidate.media_type),
        // 후보마다 겨냥한 장면이 다르다. 예전에는 제안의 **첫 장면**으로 떨어져서
        // 카드가 전부 같은 장면을 가리켰다(2026-08-19 owner 지적).
        targetSegmentId,
        // **부품은 있는데 부르는 자리가 없었다.** `targetSegmentId`는 2026-08-19에
        // 후보별로 정확해졌지만 카드가 그것을 한 번도 읽지 않아, 같은 자산을
        // 열세 장면에 추천하면 카드 열세 개가 화면에서 완전히 똑같아 보였다.
        // 내부 id는 창작자에게 보일 수 없으므로 편집판이 쓰는 장면 이름으로 바꾼다.
        targetSceneLabel: sceneLabels.get(targetSegmentId),
        displayName: typeof metadata.display_name === "string" && metadata.display_name.trim() ? metadata.display_name.trim() : undefined,
        previewSummary: String(metadata.preview_summary ?? "").trim() || candidateReason(candidate.reason_chips),
        supportedControls: candidate.controls ?? {},
        availability: isYujin ? candidate.availability : actionable ? "actionable" : candidate.availability,
        reviewStatus: isYujin ? candidate.review_status : actionable ? "approved" : candidate.review_status,
        actionable,
        readOnlyFinding: metadata.yujin_read_only_finding === true,
      };
    }),
  };
}

/** 순위 매기기는 **자막과 겹치는 말이 하나도 없을 때** 이 한 단어를 남긴다.
 *  값 자체는 서버 계약이라 그대로 두고, 화면에서만 창작자의 말로 바꾼다 --
 *  2026-08-20에 이 단어가 카드 열세 개에 그대로 찍혀 나갔다(§10.13). */
const RANKED_WITHOUT_MATCHING_WORDS = "metadata";

function candidateReason(reasonChips: readonly string[]): string {
  const words = reasonChips.map((chip) => chip.trim()).filter((chip) => chip && chip !== RANKED_WITHOUT_MATCHING_WORDS);
  if (words.length) return `자막과 겹치는 말: ${words.join(", ")}`;
  if (reasonChips.includes(RANKED_WITHOUT_MATCHING_WORDS)) return "자막과 겹치는 말은 없어요. 영상 길이와 내용을 보고 골랐어요.";
  return "추천 세부 내용을 확인해 주세요.";
}

function isYujinMediaProposal(proposal: DirectorProposal) {
  return proposal.diff.proposal_mode === "yujin_actionable_media_v1";
}

function isYujinActionableProposal(proposal: DirectorProposal) {
  return isYujinMediaProposal(proposal)
    || proposal.diff.proposal_mode === "yujin_actionable_v1";
}

function isYujinProposal(proposal: DirectorProposal) {
  return isYujinActionableProposal(proposal)
    || proposal.candidates.some(
      (candidate) => candidate.canonical_metadata?.schema_version === "videobox.yujin-response.v1",
    );
}

function initialDirectorCandidateIds(proposal: DirectorProposal | null) {
  if (!proposal || isYujinProposal(proposal)) return [];
  return proposal.candidates[0]?.candidate_id
    ? [proposal.candidates[0].candidate_id]
    : [];
}

function isActionableYujinCandidate(candidate: DirectorCandidate) {
  return isActionableYujinVariantCandidate(candidate)
    || isActionableYujinMediaCandidate(candidate)
    || isActionableYujinB4Candidate(candidate);
}

function isActionableYujinVariantCandidate(candidate: DirectorCandidate) {
  const metadata = candidate.canonical_metadata ?? {};
  return (
    candidate.availability === "actionable"
    && candidate.review_status === "approved"
    && candidate.media_type === "output_variant"
    && metadata.yujin_actionable_variant === true
    && typeof metadata.variant_id === "string"
    && typeof metadata.base_variant_revision === "number"
  );
}

function isActionableYujinMediaCandidate(candidate: DirectorCandidate) {
  const metadata = candidate.canonical_metadata ?? {};
  const sourceMediaKind = metadata.source_media_kind;
  const sourceKindMatches = candidate.media_type === "broll"
    ? sourceMediaKind === "raw_video" || sourceMediaKind === "broll_video"
    : sourceMediaKind === candidate.media_type;
  return (
    candidate.availability === "actionable"
    && candidate.review_status === "approved"
    && (candidate.media_type === "broll" || candidate.media_type === "bgm" || candidate.media_type === "sfx")
    && metadata.yujin_actionable_media === true
    && sourceKindMatches
    && typeof metadata.target_segment_id === "string"
    && metadata.target_segment_id.length > 0
  );
}

/** 후보를 눌러 볼 수 있는가.
 *
 * 유진 경로는 "유진이 바로 적용할 수 있는 미디어 후보"만 연다 -- 그 밖의 후보는
 * 서버가 내줄 원본이 없어서 단추를 띄워도 열리지 않는다.
 *
 * 그런데 화면이 기본으로 쓰는 것은 유진 경로가 아니라 로컬 경로다. 그 후보들은
 * 위 조건을 하나도 만족하지 못해 **미리보기 단추가 한 번도 뜬 적이 없었다.**
 * 서버에 직접 물어보니 로컬 경로 후보도 원본을 그대로 내준다(200, mp4). 즉 막고
 * 있던 것은 서버가 아니라 이 조건이었다. 추천이 `ready`인 미디어 후보면 연다.
 */
function isPreviewableMediaCandidate(candidate: DirectorCandidate, isYujin: boolean, proposalIsReady: boolean) {
  if (isYujin) return isActionableYujinMediaCandidate(candidate);
  // 적용 가능 여부는 화면이 이미 따로 본다(`candidateIsActionable`). 여기서는
  // "원본이 있는 미디어 후보인가"만 판단한다.
  return (
    proposalIsReady
    && (candidate.media_type === "broll" || candidate.media_type === "bgm" || candidate.media_type === "sfx")
  );
}

function isActionableYujinB4Candidate(candidate: DirectorCandidate) {
  const metadata = candidate.canonical_metadata ?? {};
  return (
    candidate.availability === "actionable"
    && candidate.review_status === "approved"
    && (candidate.media_type === "caption" || candidate.media_type === "voice" || candidate.media_type === "overlay")
    && metadata.yujin_actionable_operation === true
    && typeof metadata.target_segment_id === "string"
    && metadata.target_segment_id.length > 0
    && metadata.requires_materialization === false
    && parseYujinB4Command(candidate) !== null
  );
}

async function applyYujinB4Candidate(port: EditorCommandPort, proposalId: string, candidate: DirectorCandidate) {
  const metadata = candidate.canonical_metadata ?? {};
  const segmentId = String(metadata.target_segment_id ?? "");
  const command = parseYujinB4Command(candidate);
  if (!isActionableYujinB4Candidate(candidate) || !segmentId || !command) throw new Error("yujin_candidate_unavailable");
  const attestation = { proposalId, candidateId: candidate.candidate_id };
  if (command.kind === "caption-text") {
    return port.setCaptionText({ segmentId, text: command.text, attestation });
  }
  if (command.kind === "caption-style") {
    return port.setCaptionStyle({
      segmentIds: [segmentId],
      scope: "current_caption",
      style: command.style,
      attestation,
    });
  }
  if (command.kind === "voice") {
    return port.applyTtsCandidate({ segmentId, candidateId: command.candidateId, assetId: command.assetId, attestation });
  }
  if (command.kind === "explanation-card") {
    return port.applyOverlay({ kind: "explanation-card", segmentId, title: command.title, body: command.body, text: command.text, attestation });
  }
  if (command.kind === "image") {
    return port.applyOverlay({
      kind: "image",
      segmentId,
      assetId: command.assetId,
      text: command.text,
      attestation,
    });
  }
  return port.applyOverlay({ kind: "table", segmentId, columns: command.columns, rows: command.rows, text: command.text, attestation });
}

type ParsedYujinB4Command =
  | Readonly<{ kind: "caption-text"; text: string }>
  | Readonly<{ kind: "caption-style"; style: EditorCaptionStyle }>
  | Readonly<{ kind: "voice"; candidateId: string; assetId: string }>
  | Readonly<{ kind: "explanation-card"; title: string; body: string; text: string }>
  | Readonly<{ kind: "image"; assetId: string; text: string }>
  | Readonly<{ kind: "table"; columns: string[]; rows: string[][]; text: string }>;

function parseYujinB4Command(candidate: DirectorCandidate): ParsedYujinB4Command | null {
  const metadata = candidate.canonical_metadata ?? {};
  const controls = candidate.controls ?? {};
  if (
    candidate.media_type === "caption"
    && metadata.command_kind === "set_caption_text"
    && hasExactKeys(controls, ["text"])
    && isBoundedString(controls.text, 1, 1024)
    && new TextEncoder().encode(controls.text).length <= 2048
  ) {
    return { kind: "caption-text", text: controls.text };
  }
  if (
    candidate.media_type === "caption"
    && metadata.command_kind === "set_caption_style"
    && hasExactKeys(controls, ["scope", "style"])
    && controls.scope === "current_caption"
    && isRecord(controls.style)
  ) {
    const style = captionStyleFromCandidate(controls.style);
    return style ? { kind: "caption-style", style } : null;
  }
  if (
    candidate.media_type === "voice"
    && metadata.command_kind === "apply_tts_candidate"
    && hasExactKeys(controls, ["candidate_id", "asset_id"])
    && isBoundedString(controls.candidate_id, 1, 256)
    && /^tts_candidate_[A-Za-z0-9_-]+$/.test(controls.candidate_id)
    && controls.candidate_id === metadata.candidate_id
    && isBoundedString(controls.asset_id, 1, 256)
    && controls.asset_id === candidate.asset_id
  ) {
    return { kind: "voice", candidateId: controls.candidate_id, assetId: controls.asset_id };
  }
  if (candidate.media_type !== "overlay" || metadata.command_kind !== "apply_overlay") return null;
  if (
    controls.overlay_kind === "explanation-card"
    && hasExactKeys(controls, ["overlay_kind", "title", "body", "text"])
    && isBoundedString(controls.title, 0, 256)
    && isBoundedString(controls.body, 0, 1024)
    && isBoundedString(controls.text, 1, 1024)
  ) {
    return { kind: "explanation-card", title: controls.title, body: controls.body, text: controls.text };
  }
  if (
    controls.overlay_kind === "image"
    && hasExactKeys(controls, ["overlay_kind", "asset_id", "text"])
    && isBoundedString(controls.asset_id, 1, 256)
    && controls.asset_id === candidate.asset_id
    && isBoundedString(controls.text, 0, 1024)
  ) {
    return { kind: "image", assetId: controls.asset_id, text: controls.text };
  }
  if (
    controls.overlay_kind === "table"
    && hasExactKeys(controls, ["overlay_kind", "columns", "rows", "text"])
  ) {
    const columns = controls.columns;
    const rows = controls.rows;
    if (
      !isStringArray(columns)
      || columns.length === 0
      || columns.length > 32
      || !columns.every(isBoundedTableItem)
      || !isStringMatrix(rows)
      || rows.length > 128
      || !rows.every(
        (row) => row.length === columns.length && row.every(isBoundedTableItem),
      )
      || !isBoundedString(controls.text, 1, 1024)
    ) return null;
    return {
      kind: "table",
      columns: [...columns],
      rows: rows.map((row) => [...row]),
      text: controls.text,
    };
  }
  return null;
}

function captionStyleFromCandidate(raw: Record<string, unknown>): EditorCaptionStyle | null {
  const required = [
    "font_family", "font_size_px", "text_color", "outline_color", "outline_width_px",
    "background_color", "position_x_percent", "position_y_percent", "horizontal_align",
    "safe_area_enabled", "shadow_blur_px",
  ];
  if (!hasExactKeys(raw, required)) return null;
  if (
    !isBoundedString(raw.font_family, 1, 128)
    || !isBoundedInteger(raw.font_size_px, 12, 160)
    || !isRgbaColor(raw.text_color)
    || !isRgbaColor(raw.outline_color)
    || !isBoundedInteger(raw.outline_width_px, 0, 12)
    || !isRgbaColor(raw.background_color)
    || !isBoundedInteger(raw.position_x_percent, 0, 100)
    || !isBoundedInteger(raw.position_y_percent, 0, 100)
    || (raw.horizontal_align !== "left" && raw.horizontal_align !== "center" && raw.horizontal_align !== "right")
    || typeof raw.safe_area_enabled !== "boolean"
    || typeof raw.shadow_blur_px !== "number"
    || !Number.isInteger(raw.shadow_blur_px)
    || raw.shadow_blur_px < 0
  ) return null;
  return {
    fontFamily: raw.font_family,
    fontSizePx: raw.font_size_px,
    textColor: raw.text_color,
    outlineColor: raw.outline_color,
    outlineWidthPx: raw.outline_width_px,
    backgroundColor: raw.background_color,
    positionXPercent: raw.position_x_percent,
    positionYPercent: raw.safe_area_enabled && raw.position_y_percent > 94
      ? 94
      : raw.position_y_percent,
    horizontalAlign: raw.horizontal_align,
    safeAreaEnabled: raw.safe_area_enabled,
    shadowBlurPx: raw.shadow_blur_px,
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function hasExactKeys(value: Record<string, unknown>, expected: readonly string[]) {
  const actual = Object.keys(value);
  return actual.length === expected.length && expected.every((field) => field in value);
}

function isBoundedString(value: unknown, minimum: number, maximum: number): value is string {
  return typeof value === "string" && value.length >= minimum && value.length <= maximum;
}

function isBoundedInteger(value: unknown, minimum: number, maximum: number): value is number {
  return typeof value === "number" && Number.isInteger(value) && value >= minimum && value <= maximum;
}

function isBoundedTableItem(value: unknown): value is string {
  if (typeof value !== "string" || value.trim().length === 0) return false;
  const codePoints = Array.from(value).length;
  return codePoints >= 1
    && codePoints <= 256
    && new TextEncoder().encode(value).length <= 1024;
}

function isRgbaColor(value: unknown): value is string {
  return typeof value === "string" && /^#[0-9A-Fa-f]{8}$/.test(value);
}

function isStringArray(value: unknown): value is readonly string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string");
}

function isStringMatrix(value: unknown): value is readonly (readonly string[])[] {
  return Array.isArray(value) && value.every(isStringArray);
}

function editorControlsFromCandidate(candidate: DirectorCandidate): EditorControls {
  const controls = candidate.controls ?? {};
  if (candidate.media_type === "broll") {
    return controls.fit === "fit" || controls.fit === "crop"
      ? { fit: controls.fit }
      : {};
  }
  if (candidate.media_type === "bgm") {
    return {
      volume: typeof controls.volume === "number" ? controls.volume : undefined,
      fadeInSec: typeof controls.fade_in_sec === "number" ? controls.fade_in_sec : undefined,
      fadeOutSec: typeof controls.fade_out_sec === "number" ? controls.fade_out_sec : undefined,
    };
  }
  return {
    volume: typeof controls.volume === "number" ? controls.volume : undefined,
  };
}

export function findHermesRunProposalId(
  messages: readonly DirectorMessage[],
  runId: string,
): string | null {
  return messages.find(
    (message) => message.role === "assistant"
      && message.metadata.hermes_run_id === runId,
  )?.proposal_id ?? null;
}

function completedDurableMemoryMessageIds(
  messages: readonly DirectorMessage[],
): readonly string[] {
  const completed: string[] = [];
  let pendingUserIds: string[] = [];
  messages.forEach((message) => {
    if (message.role === "user") {
      pendingUserIds = [message.message_id];
      return;
    }
    // A Hermes run says "completed" explicitly.  The local-first route -- the
    // one this screen actually chats through -- has no run object at all, so
    // its completed turn is simply a reply that was not blocked.  Requiring a
    // run id here left the owner unable to save a memory from any conversation
    // they really had. Mirrors the server rule in
    // `local_project_store._completed_yujin_memory_source_rows`.
    const fromCompletedRun = message.metadata.hermes_status === "completed"
      && typeof message.metadata.hermes_run_id === "string";
    const fromLocalExchange = message.metadata.hermes_status === undefined
      && message.metadata.hermes_run_id === undefined
      && message.metadata.status !== "blocked"
      && pendingUserIds.length > 0;
    if (message.role === "assistant" && (fromCompletedRun || fromLocalExchange)) {
      completed.push(...pendingUserIds, message.message_id);
    }
    if (message.role === "assistant") pendingUserIds = [];
  });
  return Array.from(new Set(completed)).slice(-8);
}

function projectDirectorMessages(messages: readonly DirectorMessage[]): readonly RightDockMessage[] {
  return capDirectorMessages(messages.flatMap((message) => message.role === "user" || message.role === "assistant"
    ? [{
      id: message.message_id,
      role: message.role,
      text: message.role === "assistant"
        ? localizeDirectorAssistantText(message.text)
        : message.text,
    }]
    : []));
}

function localizeDirectorAssistantText(text: string) {
  if (text === hermesUnavailableTechnicalText) {
    return yujinUnavailableMessage;
  }
  const technicalSuffix = `\n\n${hermesUnavailableTechnicalText}`;
  return text.endsWith(technicalSuffix)
    ? `${text.slice(0, -technicalSuffix.length)}\n\n${yujinUnavailableMessage}`
    : text;
}

function isAbortError(error: unknown) {
  return error instanceof DOMException
    ? error.name === "AbortError"
    : error instanceof Error && error.name === "AbortError";
}
