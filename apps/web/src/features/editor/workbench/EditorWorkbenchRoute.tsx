import { useEffect, useState } from "react";

import { api } from "../../../api";
import { VideoBoxEditorAdapter, type EditorViewModel } from "../editorViewModel";
import { EditorWorkbench } from "./EditorWorkbench";

export function EditorWorkbenchRoute({ projectId, sessionId }: { projectId: string; sessionId: string | null }) {
  const [view, setView] = useState<EditorViewModel | null>(null);
  const [error, setError] = useState<string | null>(sessionId ? null : "편집 세션을 찾을 수 없어요. 다시 열어 주세요.");
  useEffect(() => {
    if (!sessionId) return;
    let active = true;
    void api.getEditorPlaybackManifest(projectId, sessionId).then((manifest) => {
      if (!active) return;
      const next = new VideoBoxEditorAdapter(manifest).viewModel;
      if (next.projectId !== projectId || next.sessionId !== sessionId) { setError("편집 세션 정보가 일치하지 않아요. 다시 열어 주세요."); return; }
      setView(next);
    }).catch(() => { if (active) setError("재생 내용을 불러오지 못했어요. 새로고침 후 다시 확인해 주세요."); });
    return () => { active = false; };
  }, [projectId, sessionId]);
  if (error) return <main aria-live="polite"><p>{error}</p></main>;
  if (!view) return <main aria-live="polite"><p>편집 내용을 불러오는 중이에요.</p></main>;
  return <EditorWorkbench view={view} />;
}
