import type { LibraryIngestItem } from "../../api";

export function IngestJobTable({ items, onRetry }: { items: LibraryIngestItem[]; onRetry?: (filename: string) => void }) {
  if (!items.length) return null;
  return <section className="vb-library-ingest-jobs" aria-label="등록 결과"><h2>등록 결과</h2>{items.some((item) => item.state === "needs_attention") ? <p role="alert">주의가 필요한 항목이 있어요. 성공한 자산은 그대로 등록됐습니다.</p> : null}<ul>{items.map((item, index) => <li key={`${item.filename ?? "file"}-${index}`}><span>{item.filename ?? "이름 없음"}</span><span>{item.state === "ready" ? "등록됨" : item.state === "duplicate" ? "이미 등록됨" : item.state === "needs_attention" ? <><span>확인 필요</span>{onRetry && item.filename ? <button type="button" onClick={() => onRetry(item.filename!)}>다시 시도</button> : null}</> : "분석 중"}</span></li>)}</ul></section>;
}
