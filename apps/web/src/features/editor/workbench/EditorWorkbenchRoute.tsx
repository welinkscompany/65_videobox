import { useEffect, useState } from "react";

import { api } from "../../../api";
import { VideoBoxEditorAdapter, type EditorViewModel } from "../editorViewModel";
import { EditorWorkbench } from "./EditorWorkbench";

export function EditorWorkbenchRoute({ projectId, sessionId }: { projectId: string; sessionId: string | null }) {
  const requestKey = `${projectId}:${sessionId ?? "missing"}`;
  const [refreshToken, setRefreshToken] = useState(0);
  const [state, setState] = useState<Readonly<{ key: string; view: EditorViewModel | null; error: string | null }>>({ key: requestKey, view: null, error: sessionId ? null : "편집 세션을 찾을 수 없어요. 다시 열어 주세요." });
  useEffect(() => {
    if (!sessionId) { setState({ key: requestKey, view: null, error: "편집 세션을 찾을 수 없어요. 다시 열어 주세요." }); return; }
    let active = true;
    setState({ key: requestKey, view: null, error: null });
    void api.getEditorPlaybackManifest(projectId, sessionId).then((manifest) => {
      if (!active) return;
      const next = new VideoBoxEditorAdapter(manifest).viewModel;
      if (next.projectId !== projectId || next.sessionId !== sessionId) { setState({ key: requestKey, view: null, error: "편집 세션 정보가 일치하지 않아요. 다시 열어 주세요." }); return; }
      setState({ key: requestKey, view: next, error: null });
    }).catch(() => { if (active) setState({ key: requestKey, view: null, error: "재생 내용을 불러오지 못했어요. 새로고침 후 다시 확인해 주세요." }); });
    return () => { active = false; };
  }, [projectId, requestKey, refreshToken, sessionId]);
  useEffect(() => {
    const status = state.view?.playback.exactPreview.status;
    if (status !== "pending" && status !== "running") return;
    const poll = window.setTimeout(() => setRefreshToken((current) => current + 1), 1200);
    return () => window.clearTimeout(poll);
  }, [state.view?.playback.exactPreview.status, state.view?.playback.exactPreview.generationId]);
  if (state.key !== requestKey) return <main aria-live="polite"><p>편집 내용을 불러오는 중이에요.</p></main>;
  if (state.error) return <main aria-live="polite"><p>{state.error}</p></main>;
  if (!state.view) return <main aria-live="polite"><p>편집 내용을 불러오는 중이에요.</p></main>;
  const refreshPreview = async () => {
    if (!sessionId || !state.view) return;
    await api.startExactPreview(projectId, sessionId, { expected_revision: state.view.expectedRevision });
    setRefreshToken((current) => current + 1);
  };
  return <EditorWorkbench view={state.view} onPreviewRefresh={refreshPreview} />;
}
