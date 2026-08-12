import type { LibraryAsset } from "../../api";

function filename(asset: LibraryAsset) { return String(asset.user_metadata?.filename ?? asset.asset_id ?? asset.library_asset_id); }
function duration(asset: LibraryAsset) { const value = asset.duration_seconds ?? asset.technical_metadata?.duration_seconds; return typeof value === "number" ? `${Math.round(value)}초` : "길이 확인 중"; }

export function VideoAssetGrid({ assets, selectedId, onSelect }: { assets: LibraryAsset[]; selectedId?: string | null; onSelect: (asset: LibraryAsset) => void }) {
  return <div className="vb-library-video-grid" data-testid="library-video-grid">{assets.map((item) => <article key={item.library_asset_id} data-testid="library-asset-card" data-selected={selectedId === item.library_asset_id} className="vb-library-video-card" tabIndex={0} aria-label={filename(item)} onClick={() => onSelect(item)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); onSelect(item); } }}><div className="vb-library-video-card__thumb">{item.thumbnail_url ? <img src={item.thumbnail_url} alt="" loading="lazy" /> : <span aria-hidden="true">영상</span>}<span className="vb-library-video-card__duration">{duration(item)}</span></div><div className="vb-library-video-card__body"><strong title={filename(item)}>{filename(item)}</strong><span>{item.lifecycle === "needs_attention" ? "확인 필요" : item.lifecycle === "processing" ? "분석 중" : item.lifecycle === "trashed" ? "휴지통" : "준비됨"}</span></div></article>)}</div>;
}
