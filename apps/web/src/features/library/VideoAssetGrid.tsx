import type { LibraryAsset } from "../../api";
import { assetDurationLabel as duration } from "./assetDurationLabel";

function filename(asset: LibraryAsset) { return String(asset.user_metadata?.filename ?? asset.asset_id ?? asset.library_asset_id); }

/**
 * 썸네일로 보는 자산 — 영상과 그림이 같은 격자를 쓴다.
 *
 * 그림에는 길이도 구간도 없다. 영상 칸을 그대로 씌우면 화면은 `길이 정보 없음`
 * 과 `구간 정리하기`를 보여 주는데, 하나는 물어볼 것이 아니고 하나는 열어 봐야
 * 아무것도 없다.
 */
export function VideoAssetGrid({ assets, selectedId, onSelect }: { assets: LibraryAsset[]; selectedId?: string | null; onSelect: (asset: LibraryAsset) => void }) {
  return <div className="vb-library-video-grid" data-testid="library-video-grid">{assets.map((item) => {
    const isPicture = item.media_type === "image";
    return <article key={item.library_asset_id} data-testid="library-asset-card" data-selected={selectedId === item.library_asset_id} className="vb-library-video-card" tabIndex={0} aria-label={filename(item)} onClick={() => onSelect(item)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); onSelect(item); } }}><div className="vb-library-video-card__thumb">{item.thumbnail_url ? <img src={item.thumbnail_url} alt="" loading="lazy" /> : <span aria-hidden="true">{isPicture ? "그림" : "영상"}</span>}{isPicture ? null : <span className="vb-library-video-card__duration">{duration(item)}</span>}</div><div className="vb-library-video-card__body"><strong title={filename(item)}>{filename(item)}</strong><span>{item.lifecycle === "needs_attention" ? "확인 필요" : item.lifecycle === "processing" ? "분석 중" : item.lifecycle === "trashed" ? "휴지통" : "준비됨"}</span>{!isPicture && item.lifecycle !== "trashed" ? <a className="vb-action-link" aria-label={`${filename(item)} 구간 정리하기`} href={`/footage?library_asset_id=${encodeURIComponent(item.library_asset_id)}`} onClick={(event) => event.stopPropagation()} onKeyDown={(event) => event.stopPropagation()}>구간 정리하기</a> : null}</div></article>;
  })}</div>;
}
