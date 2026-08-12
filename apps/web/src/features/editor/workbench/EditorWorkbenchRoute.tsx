import { useEffect, useRef, useState } from "react";

import { ApiConflictError, DirectorProposalBlockedError, api, type BrollAsset, type DirectorCandidate, type DirectorMessage, type DirectorProposal, type MediaLibraryAsset, type PartialRegenerationJob, type PartialRegenerationPreflight, type PartialRegenerationRun, type YujinMemoryCandidate, type YujinMemoryCategory, type YujinMemoryStoreResult } from "../../../api";
import { Button } from "../../../components/ui/button";
import { findLatestSucceededJob } from "../../../lib/formatters";
import { projectEditorAssets, type EditorAssetCard } from "../assets/editorAssetProjection";
import { createEditorCommandPort, type EditorCommandPort } from "../editorCommandPort";
import { joinEditorSnapshot, type EditorSessionSnapshot } from "../editorSnapshot";
import type { EditorCaptionStyle, EditorControls, EditorViewModel } from "../editorViewModel";
import type { InspectorAction } from "../inspector/InspectorControls";
import { canRestorePartialRegenerationResult, canRunPartialRegeneration, createPartialRegenerationTicket, PARTIAL_REGENERATION_FIELDS, preflightMatchesPartialRegenerationTicket, runMatchesPartialRegenerationTicket, type PartialRegenerationTicket } from "../partialRegenerationController";
import { EditorWorkbench } from "./EditorWorkbench";
import type { RightDockDirector, RightDockMessage, RightDockProposal } from "./rightDockTypes";

type MutationState = Readonly<{ isSaving: boolean; message?: string }>;
type AssetState = Readonly<{
  key: string;
  brollAssets: readonly BrollAsset[];
  libraryAssets: readonly MediaLibraryAsset[];
  error: string | null;
}>;
type DirectorState = Readonly<{
  key: string;
  state: RightDockDirector["state"];
  conversationId: string | null;
  messages: readonly RightDockMessage[];
  proposal: DirectorProposal | null;
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
  error: "save" | "delete" | null;
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

const assetLoadError = "일부 자산을 불러오지 못했어요. 편집은 계속할 수 있어요. 잠시 후 다시 확인해 주세요.";
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
    proposal: null,
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
    ? "촬영본 확인이 아직 끝나지 않아서 추천을 만들 수 없어요. 자산 화면에서 확인한 뒤 다시 눌러 주세요."
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
  const [assets, setAssets] = useState<AssetState>({ key: requestKey, brollAssets: [], libraryAssets: [], error: null });
  const [mutation, setMutation] = useState<MutationState>({ isSaving: false });
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
  const directorOperationId = useRef(0);
  const memoryListOperationId = useRef(0);
  const memoryMutationOperationId = useRef(0);
  const partialOperationId = useRef(0);
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
    directorMutationInFlight.current = false;
    memoryMutationInFlight.current = false;
    currentDirectorConversationId.current = null;
    partialInFlight.current = false;
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
      setState((current) => current.key === requestKey && current.view && current.session
        ? { ...current, error: message }
        : { key: requestKey, view: null, session: null, error: message });
    });
    return () => { active = false; };
  }, [projectId, requestKey, refreshToken, sessionId]);
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
      setAssets({ key: requestKey, brollAssets: [], libraryAssets: [], error: null });
      return;
    }
    const epoch = routeEpoch.current.value;
    let active = true;
    const isCurrent = () => active && routeEpoch.current.value === epoch;
    setAssets({ key: requestKey, brollAssets: [], libraryAssets: [], error: null });
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
    return () => { active = false; };
  }, [projectId, requestKey, sessionId]);
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
  useEffect(() => {
    const status = state.view?.playback.exactPreview.status;
    if (status !== "pending" && status !== "running") return;
    const epoch = routeEpoch.current.value;
    const operationId = pollOperationId.current + 1;
    pollOperationId.current = operationId;
    const poll = window.setTimeout(() => {
      if (routeEpoch.current.value === epoch && pollOperationId.current === operationId) {
        setRefreshToken((current) => current + 1);
      }
    }, 1200);
    return () => window.clearTimeout(poll);
  }, [refreshToken, requestKey, state.view?.playback.exactPreview.status, state.view?.playback.exactPreview.generationId]);
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
  const commitTimelineMutation = async (run: (port: EditorCommandPort, isCurrent: () => boolean) => Promise<unknown>) => {
    if (!sessionId || !state.view || mutationInFlight.current) return;
    const epoch = routeEpoch.current.value;
    const operationId = mutationOperationId.current + 1;
    mutationOperationId.current = operationId;
    const isCurrent = () => routeEpoch.current.value === epoch && mutationOperationId.current === operationId;
    const currentView = state.view;
    mutationInFlight.current = true;
    setMutation({ isSaving: true, message: "변경 내용을 저장하고 있어요." });
    const port = createEditorCommandPort({
      projectId,
      sessionId,
      expectedRevision: currentView.expectedRevision,
    });
    let resultMessage = "변경 내용을 저장했어요.";
    let mutationSucceeded = true;
    try {
      await run(port, isCurrent);
      if (isCurrent()) {
        setMutation({ isSaving: true, message: "변경 내용을 저장했어요. 최신 내용을 불러오고 있어요." });
      }
    } catch (error) {
      mutationSucceeded = false;
      resultMessage = error instanceof ApiConflictError
        ? "다른 변경이 먼저 저장됐어요. 최신 내용을 확인한 뒤 다시 시도해 주세요."
        : "변경 내용을 저장하지 못했어요. 최신 내용을 확인한 뒤 다시 시도해 주세요.";
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
        resultMessage = "최신 편집 내용을 확인하지 못했어요. 새로고침한 뒤 다시 시도해 주세요.";
      } else {
        setState({ key: requestKey, view: next.view, session: next.session, error: null });
        // Auto-refresh the preview after a successful edit instead of leaving
        // the creator to notice it's stale and press the manual button
        // themselves (F-4). A failure here is silent -- the manual refresh
        // button in preview-stage.tsx stays as the fallback.
        if (mutationSucceeded) {
          void api.startExactPreview(projectId, sessionId, { expected_revision: next.view.expectedRevision })
            .then(() => { if (isCurrentRefresh()) setRefreshToken((current) => current + 1); })
            .catch(() => {});
        }
      }
    } catch {
      if (isCurrent()) {
        resultMessage = "최신 편집 내용을 불러오지 못했어요. 새로고침한 뒤 다시 시도해 주세요.";
      }
    } finally {
      if (isCurrent()) {
        mutationInFlight.current = false;
        setMutation({ isSaving: false, message: resultMessage });
        setPartialRecoveryRetryToken((current) => current + 1);
      }
    }
  };
  const applyAssetCard = (card: EditorAssetCard, segmentId: string) => card.kind === "broll"
    ? commitTimelineMutation((port) => port.applyMedia({ kind: "broll", segmentId, assetId: card.assetId }))
    : commitTimelineMutation(async (port, isCurrent) => {
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
  const handleInspectorAction = (action: InspectorAction) => {
    if (action.kind === "partial-preflight") return preflightPartialRegeneration(action);
    if (action.kind === "partial-run") return runPartialRegeneration(action);
    if (action.kind === "partial-resume") return resumePartialRegeneration(action);
    return commitTimelineMutation((port) => {
      if (action.kind === "split-narration") return port.splitNarration({ segmentId: action.segmentId, splitSec: action.splitSec });
      if (action.kind === "merge-narration") return port.mergeNarration({ leftSegmentId: action.leftSegmentId, rightSegmentId: action.rightSegmentId });
      if (action.kind === "set-cut-action") return port.setCutAction({ segmentId: action.segmentId, cutAction: action.cutAction });
      if (action.kind === "save-media") return port.updateMediaControls({ kind: action.mediaKind, segmentId: action.segmentId, assetId: action.assetId, controls: action.controls });
      if (action.kind === "clear-media") return port.clearMedia({ kind: action.mediaKind, segmentId: action.segmentId });
      if (action.kind === "save-caption-style") return port.setCaptionStyle({ segmentIds: action.segmentIds, scope: action.scope, style: action.style });
      if (action.kind === "apply-tts-candidate") return port.applyTtsCandidate({ segmentId: action.segmentId, candidateId: action.candidateId, assetId: action.assetId });
      if (action.kind === "clear-tts-candidate") return port.clearTtsCandidate({ segmentId: action.segmentId });
      if (action.kind === "clear-overlay") return port.clearOverlay({ kind: action.overlayKind, segmentId: action.segmentId });
      if (action.overlayKind === "explanation-card") return port.applyOverlay({ kind: action.overlayKind, segmentId: action.segmentId, title: action.title, body: action.body, text: action.text });
      if (action.overlayKind === "image") return port.applyOverlay({ kind: action.overlayKind, segmentId: action.segmentId, assetId: action.assetId, text: action.text });
      return port.applyOverlay({ kind: action.overlayKind, segmentId: action.segmentId, columns: action.columns, rows: action.rows, text: action.text });
    });
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
    ? projectEditorAssets({ projectId, brollAssets: assets.brollAssets, libraryAssets: assets.libraryAssets })
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
    } catch {
      if (!isCurrentMemoryMutation(ownership)) return;
      updateMemoryCandidate(candidateId, (current) => ({
        ...current,
        action: "idle",
        error: "save",
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
      const proposal = await api.createDirectorProposal(projectId, { session_id: sessionId });
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
          if (selectedYujinCandidate && isActionableYujinMediaCandidate(selectedYujinCandidate)) {
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
          if (isCurrentApply()) setDirector({ ...activeDirector, state: "proposal_ready" });
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
    proposal: projectDirectorProposal(projectId, activeDirector.proposal, state.view.expectedRevision),
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
    onManualEdit: () => setDirector((current) => current.key === requestKey ? { ...current, state: "idle" } : current),
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
    <EditorWorkbench
    assetCards={assetCards}
    isSavingTimeline={mutation.isSaving}
    loadApprovedTtsCandidates={loadApprovedTtsCandidates}
    onApplyAssetCard={applyAssetCard}
    onPrepareAssetPreview={prepareAssetPreview}
    onInspectorAction={handleInspectorAction}
    onPreviewRefresh={refreshPreview}
    onReorderNarration={(input) => commitTimelineMutation((port) => port.reorderNarration(input))}
    onRedo={() => commitTimelineMutation((port) => port.redo())}
    onTrimNarration={(input) => commitTimelineMutation((port) => port.setNarrationBounds(input))}
    onUndo={() => commitTimelineMutation((port) => port.undo())}
    onUpdateCaption={(input) => commitTimelineMutation((port) => port.setCaptionText(input))}
    onUpdatePlacements={(input) => commitTimelineMutation((port) => port.setTimelinePlacements(input))}
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
    view={state.view}
    />
  </>;
}

function projectDirectorProposal(projectId: string, proposal: DirectorProposal | null, currentRevision: number): RightDockProposal | null {
  if (!proposal) return null;
  const isYujin = isYujinProposal(proposal);
  return {
    proposalId: proposal.proposal_id,
    status: proposal.status,
    baseSessionRevision: proposal.base_session_revision,
    currentRevision,
    // 뜻으로 찾았는지 단어로만 찾았는지. 없으면 화면이 아무 말도 하지 않는다.
    matchMode: typeof proposal.diff?.match_mode === "string" ? proposal.diff.match_mode : undefined,
    candidates: proposal.candidates.map((candidate) => {
      const metadata = candidate.canonical_metadata ?? {};
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
        targetSegmentId: String(metadata.target_segment_id ?? proposal.target_segment_ids[0] ?? ""),
        previewSummary: String(metadata.preview_summary ?? candidate.reason_chips[0] ?? "추천 세부 내용을 확인해 주세요."),
        supportedControls: candidate.controls ?? {},
        availability: isYujin ? candidate.availability : actionable ? "actionable" : candidate.availability,
        reviewStatus: isYujin ? candidate.review_status : actionable ? "approved" : candidate.review_status,
        actionable,
        readOnlyFinding: metadata.yujin_read_only_finding === true,
      };
    }),
  };
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
  return isActionableYujinMediaCandidate(candidate)
    || isActionableYujinB4Candidate(candidate);
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
