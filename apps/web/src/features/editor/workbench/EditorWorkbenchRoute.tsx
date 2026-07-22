import { useEffect, useRef, useState } from "react";

import { ApiConflictError, api } from "../../../api";
import { createEditorCommandPort, type EditorCommandPort } from "../editorCommandPort";
import { VideoBoxEditorAdapter, type EditorViewModel } from "../editorViewModel";
import { EditorWorkbench } from "./EditorWorkbench";

type MutationState = Readonly<{ isSaving: boolean; message?: string }>;

export function EditorWorkbenchRoute({ projectId, sessionId }: { projectId: string; sessionId: string | null }) {
  const requestKey = `${projectId}:${sessionId ?? "missing"}`;
  const [refreshToken, setRefreshToken] = useState(0);
  const [state, setState] = useState<Readonly<{ key: string; view: EditorViewModel | null; error: string | null }>>({ key: requestKey, view: null, error: sessionId ? null : "편집 세션을 찾을 수 없어요. 다시 열어 주세요." });
  const [mutation, setMutation] = useState<MutationState>({ isSaving: false });
  const mutationInFlight = useRef(false);
  const routeEpoch = useRef({ key: requestKey, value: 0 });
  const manifestOperationId = useRef(0);
  const mutationOperationId = useRef(0);
  const previewOperationId = useRef(0);
  const pollOperationId = useRef(0);
  useEffect(() => {
    if (routeEpoch.current.key === requestKey) return;
    routeEpoch.current = { key: requestKey, value: routeEpoch.current.value + 1 };
    mutationOperationId.current += 1;
    mutationInFlight.current = false;
    setMutation({ isSaving: false });
  }, [requestKey]);
  useEffect(() => {
    if (!sessionId) { setState({ key: requestKey, view: null, error: "편집 세션을 찾을 수 없어요. 다시 열어 주세요." }); return; }
    const epoch = routeEpoch.current.value;
    const operationId = manifestOperationId.current + 1;
    manifestOperationId.current = operationId;
    let active = true;
    const isCurrent = () => active && routeEpoch.current.value === epoch && manifestOperationId.current === operationId;
    setState({ key: requestKey, view: null, error: null });
    void api.getEditorPlaybackManifest(projectId, sessionId).then((manifest) => {
      if (!isCurrent()) return;
      const next = new VideoBoxEditorAdapter(manifest).viewModel;
      if (next.projectId !== projectId || next.sessionId !== sessionId) { setState({ key: requestKey, view: null, error: "편집 세션 정보가 일치하지 않아요. 다시 열어 주세요." }); return; }
      setState({ key: requestKey, view: next, error: null });
    }).catch(() => { if (isCurrent()) setState({ key: requestKey, view: null, error: "재생 내용을 불러오지 못했어요. 새로고침 후 다시 확인해 주세요." }); });
    return () => { active = false; };
  }, [projectId, requestKey, refreshToken, sessionId]);
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
  }, [requestKey, state.view?.playback.exactPreview.status, state.view?.playback.exactPreview.generationId]);
  if (state.key !== requestKey) return <main aria-live="polite"><p>편집 내용을 불러오는 중이에요.</p></main>;
  if (state.error) return <main aria-live="polite"><p>{state.error}</p></main>;
  if (!state.view) return <main aria-live="polite"><p>편집 내용을 불러오는 중이에요.</p></main>;
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
  const commitTimelineMutation = async (run: (port: EditorCommandPort) => Promise<unknown>) => {
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
      await run(port);
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
      const manifest = await api.getEditorPlaybackManifest(projectId, sessionId);
      if (!isCurrentRefresh()) return;
      const next = new VideoBoxEditorAdapter(manifest).viewModel;
      if (next.projectId !== projectId || next.sessionId !== sessionId) {
        resultMessage = "최신 편집 내용을 확인하지 못했어요. 새로고침한 뒤 다시 시도해 주세요.";
      } else {
        setState({ key: requestKey, view: next, error: null });
      }
    } catch {
      if (isCurrent()) {
        resultMessage = "최신 편집 내용을 불러오지 못했어요. 새로고침한 뒤 다시 시도해 주세요.";
      }
    } finally {
      if (isCurrent()) {
        mutationInFlight.current = false;
        setMutation({ isSaving: false, message: resultMessage });
      }
    }
  };
  return <EditorWorkbench
    isSavingTimeline={mutation.isSaving}
    onPreviewRefresh={refreshPreview}
    onReorderNarration={(input) => commitTimelineMutation((port) => port.reorderNarration(input))}
    onTrimNarration={(input) => commitTimelineMutation((port) => port.setNarrationBounds(input))}
    timelineMutationMessage={mutation.message}
    view={state.view}
  />;
}
