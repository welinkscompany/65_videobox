import { useEffect, useState } from "react";
import { api, type MediaAnalysis } from "../../api";

const statusCopy: Record<string, string> = {
  queued: "분석을 기다리고 있어요",
  running: "미디어를 살펴보고 있어요",
  succeeded: "준비가 끝났어요",
  needs_review: "확인이 필요해요",
  failed: "분석을 마치지 못했어요",
  blocked: "분석을 마치지 못했어요",
  cancelled: "분석을 멈췄어요",
};

export function MediaAnalysisPanel({ projectId, onSelectAsset }: { projectId: string; onSelectAsset?: (assetId: string) => void }) {
  const [items, setItems] = useState<MediaAnalysis[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [tagText, setTagText] = useState<Record<string, string>>({});
  const [preview, setPreview] = useState<{ assetId: string; durationSec?: number } | null>(null);
  const load = () => api.listMediaAnalysis(projectId).then((response) => setItems(response.items)).catch(() => setError("미디어를 불러오지 못했어요. 새로고침해 주세요."));
  const refresh = () => { setError(null); setPreview(null); return load(); };
  useEffect(() => { void load(); }, [projectId]);
  const action = async (fn: () => Promise<unknown>) => { setError(null); try { await fn(); await load(); } catch { setPreview(null); setError("지금은 이 작업을 마칠 수 없어요. 다시 시도하거나 직접 선택해 주세요."); } };
  return <section className="panel" aria-labelledby="media-analysis-heading">
    <div className="panel-header"><div><p className="section-kicker">로컬 미디어</p><h2 id="media-analysis-heading">미디어 분석</h2></div><button className="action-button subtle" type="button" onClick={() => void refresh()}>새로고침</button></div>
    {error ? <p className="error-banner">{error}</p> : null}
    {items.length === 0 ? <p className="empty-state">확인할 미디어가 없어요.</p> : items.map((item, index) => <article className="confirmation-card" key={item.analysis_id}>
      <strong>미디어 {index + 1}</strong><p>{statusCopy[item.status] ?? "미디어를 확인하고 있어요"} · {item.progress_percent}%</p>
      {item.error_message ? <p className="error-banner">분석을 마치지 못했어요. 다시 시도하거나 직접 선택해 주세요.</p> : null}
      {(item.status === "succeeded" || item.status === "needs_review") ? <button className="action-button subtle" type="button" onClick={() => void action(async () => { const response = await api.mediaAnalysisPreview(projectId, item.asset_id); const raw = response.preview as { duration_sec?: unknown } | null; setPreview({ assetId: item.asset_id, durationSec: typeof raw?.duration_sec === "number" ? raw.duration_sec : undefined }); onSelectAsset?.(item.asset_id); })}>미리보기</button> : <p className="meta-copy">아직 미리보기를 준비하고 있어요.</p>}
      {preview?.assetId === item.asset_id ? <p className="meta-copy">{preview.durationSec === undefined ? "미리보기가 준비됐어요" : `미리보기 · ${preview.durationSec}초`}</p> : null}
      {(item.status === "queued" || item.status === "running") ? <button className="action-button subtle" type="button" onClick={() => void action(() => api.cancelMediaAnalysis(projectId, item.analysis_id))}>취소</button> : null}
      {(item.status === "failed" || item.status === "blocked") ? <button className="action-button subtle" type="button" onClick={() => void action(() => api.retryMediaAnalysis(projectId, item.analysis_id))}>다시 분석하기</button> : null}
      {item.status === "needs_review" ? <form onSubmit={(event) => { event.preventDefault(); const tags = (tagText[item.analysis_id] || "").split(",").map((tag) => tag.trim()).filter(Boolean); void action(() => api.reviewMediaAnalysis(projectId, item.analysis_id, { place: tags })); }}><label>수동 태그<input aria-label={`미디어 ${index + 1} 수동 태그`} value={tagText[item.analysis_id] || ""} onChange={(event) => setTagText({ ...tagText, [item.analysis_id]: event.target.value })} /></label><button className="action-button" type="submit">태그 승인</button></form> : null}
    </article>)}
  </section>;
}
