import { useEffect, useRef, useState } from "react";

import { ApiConflictError, api, type BrollAsset, type DirectorMessage, type DirectorMessageExchange, type DirectorProposal, type MediaLibraryAsset, type PartialRegenerationJob, type PartialRegenerationPreflight, type PartialRegenerationRun } from "../../../api";
import { Button } from "../../../components/ui/button";
import { findLatestSucceededJob } from "../../../lib/formatters";
import { projectEditorAssets, type EditorAssetCard } from "../assets/editorAssetProjection";
import { createEditorCommandPort, type EditorCommandPort } from "../editorCommandPort";
import { joinEditorSnapshot, type EditorSessionSnapshot } from "../editorSnapshot";
import type { EditorViewModel } from "../editorViewModel";
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
  isSending?: boolean;
  retryAfterSeconds?: number | null;
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

const assetLoadError = "일부 자산을 불러오지 못했어요. 편집은 계속할 수 있어요. 잠시 후 다시 확인해 주세요.";

export function EditorWorkbenchRoute({ projectId, sessionId, requestedSegmentId = null }: { projectId: string; sessionId: string | null; requestedSegmentId?: string | null }) {
  const requestKey = `${projectId}:${sessionId ?? "missing"}`;
  const [refreshToken, setRefreshToken] = useState(0);
  const [state, setState] = useState<Readonly<{ key: string; view: EditorViewModel | null; session: EditorSessionSnapshot | null; error: string | null }>>({ key: requestKey, view: null, session: null, error: sessionId ? null : "편집 세션을 찾을 수 없어요. 다시 열어 주세요." });
  const [assets, setAssets] = useState<AssetState>({ key: requestKey, brollAssets: [], libraryAssets: [], error: null });
  const [mutation, setMutation] = useState<MutationState>({ isSaving: false });
  const [director, setDirector] = useState<DirectorState>({ key: requestKey, state: sessionId ? "analysis_running" : "script_required", conversationId: null, messages: [], proposal: null });
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
  const partialOperationId = useRef(0);
  const partialRecoveryOperationId = useRef(0);
  const stableDirectorMessageId = useRef<string | null>(null);
  const directorMutationInFlight = useRef(false);
  const directorMessageInFlight = useRef(false);
  const partialInFlight = useRef(false);
  const directorRetry = useRef<Readonly<{ text: string; retry: () => Promise<{ kind: "exchange"; exchange: DirectorMessageExchange } | { kind: "in_progress"; retryAfterSeconds: number }> }> | null>(null);
  useEffect(() => {
    if (routeEpoch.current.key === requestKey) return;
    routeEpoch.current = { key: requestKey, value: routeEpoch.current.value + 1 };
    mutationOperationId.current += 1;
    directorOperationId.current += 1;
    partialOperationId.current += 1;
    stableDirectorMessageId.current = null;
    directorMutationInFlight.current = false;
    directorMessageInFlight.current = false;
    partialInFlight.current = false;
    directorRetry.current = null;
    mutationInFlight.current = false;
    setMutation({ isSaving: false });
    setDirector({ key: requestKey, state: sessionId ? "analysis_running" : "script_required", conversationId: null, messages: [], proposal: null });
    setPartial({ key: requestKey, ticket: null, preflight: null, run: null, jobId: null, result: null, isResultOpen: false, message: null });
    setPartialRecoveryError(false);
  }, [requestKey]);
  useEffect(() => {
    if (!sessionId) return;
    const epoch = routeEpoch.current.value;
    const operationId = directorOperationId.current + 1;
    directorOperationId.current = operationId;
    let active = true;
    const isCurrent = () => active && routeEpoch.current.value === epoch && directorOperationId.current === operationId;
    setDirector({ key: requestKey, state: "analysis_running", conversationId: null, messages: [], proposal: null });
    void api.reloadDirectorSession(projectId, sessionId).then((recovered) => {
      if (!isCurrent()) return;
      setDirector({ key: requestKey, state: recovered.proposal ? "proposal_ready" : "idle", conversationId: recovered.conversation?.conversation_id ?? null, messages: projectDirectorMessages(recovered.messages), proposal: recovered.proposal });
    }).catch((error: unknown) => {
      if (isCurrent()) setDirector({ key: requestKey, state: error instanceof SyntaxError || error instanceof TypeError ? "error" : "blocked", conversationId: null, messages: [], proposal: null });
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
  if (state.key !== requestKey) return <main aria-live="polite"><p>편집 내용을 불러오는 중이에요.</p></main>;
  if (!state.view) return <main aria-live="polite"><p>{state.error ?? "편집 내용을 불러오는 중이에요."}</p></main>;
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
    try {
      await run(port, isCurrent);
      if (isCurrent()) {
        setMutation({ isSaving: true, message: "변경 내용을 저장했어요. 최신 내용을 불러오고 있어요." });
      }
    } catch (error) {
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
  const activeDirector = director.key === requestKey ? director : { key: requestKey, state: "analysis_running" as const, conversationId: null, messages: [], proposal: null };
  const isCurrentDirector = (epoch: number, operationId: number) => routeEpoch.current.value === epoch && directorOperationId.current === operationId;
  const sendDirectorMessage = async (text: string, retryRequested = false) => {
    if (!sessionId || !activeDirector.conversationId || !text.trim() || directorMessageInFlight.current) return;
    const epoch = routeEpoch.current.value;
    const operationId = directorOperationId.current + 1;
    directorOperationId.current = operationId;
    const retry = retryRequested ? directorRetry.current : null;
    if (retryRequested && (!retry || retry.text !== text)) return;
    let clientMessageId: string | null = null;
    if (!retry) {
      clientMessageId = globalThis.crypto?.randomUUID?.() ?? `director-${Date.now()}`;
      stableDirectorMessageId.current = clientMessageId;
      directorRetry.current = null;
    }
    const prepared = retry ? null : api.prepareDirectorMessage(projectId, activeDirector.conversationId, { session_id: sessionId, client_message_id: clientMessageId!, text: text.trim() });
    directorMessageInFlight.current = true;
    setDirector({ ...activeDirector, isSending: true, retryAfterSeconds: null });
    try {
      const result = retry ? await retry.retry() : await prepared!.send();
      if (!isCurrentDirector(epoch, operationId)) return;
      if (result.kind === "in_progress") {
        directorRetry.current = { text: text.trim(), retry: prepared?.retry ?? retry!.retry };
        setDirector({ ...activeDirector, state: "idle", isSending: false, retryAfterSeconds: result.retryAfterSeconds });
        return;
      }
      stableDirectorMessageId.current = null;
      directorRetry.current = null;
      const proposalId = result.exchange.assistant_message.proposal_id ?? (typeof result.exchange.action_intent?.proposal_preflight?.proposal_id === "string" ? result.exchange.action_intent.proposal_preflight.proposal_id : null);
      const messages = [...activeDirector.messages, projectDirectorExchange(result.exchange)];
      if (!proposalId) { setDirector({ ...activeDirector, messages, isSending: false, retryAfterSeconds: null }); return; }
      const proposal = await api.getDirectorProposal(projectId, proposalId);
      if (isCurrentDirector(epoch, operationId)) setDirector({ ...activeDirector, state: "proposal_ready", messages, proposal, isSending: false, retryAfterSeconds: null });
    } catch {
      stableDirectorMessageId.current = null;
      directorRetry.current = null;
      if (isCurrentDirector(epoch, operationId)) setDirector({ ...activeDirector, state: "blocked", isSending: false, retryAfterSeconds: null });
    } finally {
      if (isCurrentDirector(epoch, operationId)) directorMessageInFlight.current = false;
    }
  };
  const retryDirectorMessage = async () => {
    const retry = directorRetry.current;
    if (retry) await sendDirectorMessage(retry.text, true);
  };
  const startDirector = async () => {
    if (!sessionId || activeDirector.proposal || activeDirector.state !== "idle" || directorMutationInFlight.current) return;
    const epoch = routeEpoch.current.value;
    const operationId = directorOperationId.current + 1;
    directorOperationId.current = operationId;
    directorMutationInFlight.current = true;
    setDirector({ ...activeDirector, state: "analysis_running" });
    try {
      let conversationId = activeDirector.conversationId;
      if (!conversationId) {
        const conversation = await api.createDirectorConversation(projectId, { session_id: sessionId });
        if (!isCurrentDirector(epoch, operationId)) return;
        conversationId = conversation.conversation_id;
      }
      const proposal = await api.createDirectorProposal(projectId, { session_id: sessionId });
      if (isCurrentDirector(epoch, operationId)) setDirector({ ...activeDirector, state: "proposal_ready", conversationId, proposal });
    } catch {
      if (isCurrentDirector(epoch, operationId)) setDirector({ ...activeDirector, state: "idle" });
    } finally {
      if (isCurrentDirector(epoch, operationId)) directorMutationInFlight.current = false;
    }
  };
  const applyDirectorProposal = async (proposalId: string, candidateIds: readonly string[]) => {
    if (!sessionId || !state.view || activeDirector.proposal?.proposal_id !== proposalId || !candidateIds.length || directorMutationInFlight.current || mutationInFlight.current) return;
    const epoch = routeEpoch.current.value;
    const operationId = directorOperationId.current + 1;
    directorOperationId.current = operationId;
    directorMutationInFlight.current = true;
    const currentRevision = state.view.expectedRevision;
    setDirector({ ...activeDirector, state: "applying" });
    try {
      await commitTimelineMutation(async (_port, isCurrentMutation) => {
        try {
          const preflight = await api.preflightDirectorProposal(projectId, proposalId);
          if (!isCurrentMutation() || !isCurrentDirector(epoch, operationId)) return;
          if (preflight.status === "stale" || preflight.code === "stale_proposal") {
            setDirector({ ...activeDirector, state: "blocked" });
            throw new Error("stale director proposal");
          }
          await api.batchApplyDirectorProposal(projectId, proposalId, { candidate_ids: [...candidateIds], expected_revision: currentRevision });
          if (isCurrentMutation() && isCurrentDirector(epoch, operationId)) setDirector({ ...activeDirector, state: "proposal_ready" });
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
  const rightDock: RightDockDirector = {
    state: mutation.isSaving ? "applying" : activeDirector.state,
    messages: activeDirector.messages,
    proposal: projectDirectorProposal(activeDirector.proposal),
    composerDisabled: mutation.isSaving || !activeDirector.conversationId || activeDirector.isSending === true || activeDirector.state === "analysis_running" || activeDirector.state === "applying",
    onSendMessage: sendDirectorMessage,
    onApplyProposal: applyDirectorProposal,
    onManualEdit: () => setDirector((current) => current.key === requestKey ? { ...current, state: "idle" } : current),
    onPreviewCandidate: () => undefined,
    onStart: activeDirector.state === "idle" && !activeDirector.proposal ? startDirector : undefined,
    onRetryMessage: activeDirector.retryAfterSeconds !== null && activeDirector.retryAfterSeconds !== undefined ? retryDirectorMessage : undefined,
    retryAfterSeconds: activeDirector.retryAfterSeconds,
  };
  return <>
    {state.error ? <p role="status">{state.error}</p> : null}
    {assets.key === requestKey && assets.error ? <p role="status">{assets.error}</p> : null}
    {activePartial.message ? <p role="status">{activePartial.message}</p> : null}
    {partialRecoveryError ? <Button onClick={() => setPartialRecoveryRetryToken((current) => current + 1)} type="button">이전 결과 다시 찾기</Button> : null}
    {activePartial.preflight?.affected_output_areas.length ? <ul aria-label="부분 재생성 영향 범위">{activePartial.preflight.affected_output_areas.map((area) => <li key={area}>{area}</li>)}</ul> : null}
    {activePartial.isResultOpen && activePartial.result && partialResultIsCurrent ? <dl aria-label="부분 재생성 결과">
      <dt>상태</dt><dd>{activePartial.result.status}</dd>
      <dt>대상 구간 수</dt><dd>{activePartial.result.segment_ids.length}</dd>
      <dt>다시 만든 항목</dt><dd>{activePartial.result.fields.join(", ")}</dd>
    </dl> : null}
    <EditorWorkbench
    assetCards={assetCards}
    isSavingTimeline={mutation.isSaving}
    loadApprovedTtsCandidates={loadApprovedTtsCandidates}
    onApplyAssetCard={applyAssetCard}
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

function projectDirectorProposal(proposal: DirectorProposal | null): RightDockProposal | null {
  return proposal ? { proposalId: proposal.proposal_id, status: proposal.status, candidates: proposal.candidates.map((candidate) => ({ candidateId: candidate.candidate_id, visibleReferenceCode: candidate.visible_reference_code, mediaType: candidate.media_type, previewUrl: candidate.preview_uri })) } : null;
}

function projectDirectorExchange(exchange: DirectorMessageExchange): RightDockMessage {
  return { id: exchange.assistant_message.message_id, userText: exchange.user_message.text, assistantText: exchange.assistant_message.text };
}

function projectDirectorMessages(messages: readonly DirectorMessage[]): readonly RightDockMessage[] {
  const exchanges: RightDockMessage[] = [];
  let pendingUser: DirectorMessage | null = null;
  for (const message of messages) {
    if (message.role === "user") { pendingUser = message; continue; }
    if (message.role === "assistant" && pendingUser) {
      exchanges.push({ id: message.message_id, userText: pendingUser.text, assistantText: message.text });
      pendingUser = null;
    }
  }
  return exchanges;
}
