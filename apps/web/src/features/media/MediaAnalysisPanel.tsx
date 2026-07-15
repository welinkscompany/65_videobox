import { useEffect, useState } from "react";
import { api, type MediaAnalysis } from "../../api";

export function MediaAnalysisPanel({ projectId, onSelectAsset }: { projectId: string; onSelectAsset?: (assetId: string) => void }) {
  const [items, setItems] = useState<MediaAnalysis[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [tagText, setTagText] = useState<Record<string, string>>({});
  const [preview, setPreview] = useState<{ assetId: string; durationSec?: number } | null>(null);
  const load = () => api.listMediaAnalysis(projectId).then((response) => setItems(response.items)).catch((reason) => setError(reason instanceof Error ? reason.message : "분석 목록을 불러오지 못했습니다"));
  const refresh = () => { setError(null); setPreview(null); return load(); };
  useEffect(() => { void load(); }, [projectId]);
  const action = async (fn: () => Promise<unknown>) => { setError(null); try { await fn(); await load(); } catch (reason) { setPreview(null); setError(reason instanceof Error ? reason.message : "분석 작업을 처리하지 못했습니다"); } };
  return <section className="panel" aria-labelledby="media-analysis-heading">
    <div className="panel-header"><div><p className="section-kicker">로컬 미디어</p><h2 id="media-analysis-heading">미디어 분석</h2></div><button className="action-button subtle" type="button" onClick={() => void refresh()}>새로고침</button></div>
    {error ? <p className="error-banner">{error}</p> : null}
    {items.length === 0 ? <p className="empty-state">분석 대기 항목 없음</p> : items.map((item) => <article className="confirmation-card" key={item.analysis_id}>
      <strong>{item.asset_id}</strong><p>{item.status} · {item.progress_percent}%{item.queue_position === null ? "" : ` · 대기 순서 ${item.queue_position}`}</p>
      {item.error_message ? <p className="error-banner">{item.error_message}</p> : null}
      {(item.status === "succeeded" || item.status === "needs_review") ? <button className="action-button subtle" type="button" onClick={() => void action(async () => { const response = await api.mediaAnalysisPreview(projectId, item.asset_id); const raw = response.preview as { duration_sec?: unknown } | null; setPreview({ assetId: item.asset_id, durationSec: typeof raw?.duration_sec === "number" ? raw.duration_sec : undefined }); onSelectAsset?.(item.asset_id); })}>미리보기</button> : <p className="meta-copy">분석 미리보기 사용 불가</p>}
      {preview?.assetId === item.asset_id ? <p className="meta-copy">{preview.durationSec === undefined ? "분석 미리보기 준비됨" : `분석 미리보기 · ${preview.durationSec}초`}</p> : null}
      {(item.status === "queued" || item.status === "running") ? <button className="action-button subtle" type="button" onClick={() => void action(() => api.cancelMediaAnalysis(projectId, item.analysis_id))}>취소</button> : null}
      {(item.status === "failed" || item.status === "blocked") ? <button className="action-button subtle" type="button" onClick={() => void action(() => api.retryMediaAnalysis(projectId, item.analysis_id))}>재시도</button> : null}
      {item.status === "needs_review" ? <form onSubmit={(event) => { event.preventDefault(); const tags = (tagText[item.analysis_id] || "").split(",").map((tag) => tag.trim()).filter(Boolean); void action(() => api.reviewMediaAnalysis(projectId, item.analysis_id, { place: tags })); }}><label>수동 태그<input aria-label={`${item.asset_id} 수동 태그`} value={tagText[item.analysis_id] || ""} onChange={(event) => setTagText({ ...tagText, [item.analysis_id]: event.target.value })} /></label><button className="action-button" type="submit">태그 승인</button></form> : null}
    </article>)}
  </section>;
}
