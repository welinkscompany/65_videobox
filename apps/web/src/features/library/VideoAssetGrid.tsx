import type { LibraryAsset } from "../../api";
import { assetDurationLabel as duration } from "./assetDurationLabel";

function filename(asset: LibraryAsset) { return String(asset.user_metadata?.filename ?? asset.asset_id ?? asset.library_asset_id); }

export function VideoAssetGrid({ assets, selectedId, onSelect }: { assets: LibraryAsset[]; selectedId?: string | null; onSelect: (asset: LibraryAsset) => void }) {
  return <div className="vb-library-video-grid" data-testid="library-video-grid">{assets.map((item) => <article key={item.library_asset_id} data-testid="library-asset-card" data-selected={selectedId === item.library_asset_id} className="vb-library-video-card" tabIndex={0} aria-label={filename(item)} onClick={() => onSelect(item)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); onSelect(item); } }}><div className="vb-library-video-card__thumb">{item.thumbnail_url ? <img src={item.thumbnail_url} alt="" loading="lazy" /> : <span aria-hidden="true">영상</span>}<span className="vb-library-video-card__duration">{duration(item)}</span></div><div className="vb-library-video-card__body"><strong title={filename(item)}>{filename(item)}</strong><span>{item.lifecycle === "needs_attention" ? "확인 필요" : item.lifecycle === "processing" ? "분석 중" : item.lifecycle === "trashed" ? "휴지통" : "준비됨"}</span>{item.lifecycle !== "trashed" ? <a className="vb-action-link" href={`/footage?library_asset_id=${encodeURIComponent(item.library_asset_id)}`} onClick={(event) => event.stopPropagation()}>구간 정리하기</a> : null}</div></article>)}</div>;
}
