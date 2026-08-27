import type { LibraryAsset } from "../../api";
import { Button } from "../../components/ui/button";

type Props = { assets: LibraryAsset[]; selectedIds: string[]; onSelect: (asset: LibraryAsset, extend: boolean) => void };

export function FootageSourceList({ assets, selectedIds, onSelect }: Props) {
  return <aside className="vb-footage-pane vb-footage-sources" data-testid="footage-source-list">
    <div className="vb-footage-pane__heading"><p className="vb-eyebrow">가져온 것</p><h2>촬영본</h2><span>{assets.length}개</span></div>
    {assets.length === 0 ? <p className="vb-footage-empty">준비된 촬영본이 없어요.</p> : <div className="vb-footage-source-scroll" data-bounded="true">
      {assets.map((asset) => {
        const filename = String(asset.user_metadata?.filename ?? asset.library_asset_id);
        const duration = asset.duration_seconds ?? Number(asset.technical_metadata?.duration_seconds ?? 0);
        return <div key={asset.library_asset_id} className="vb-footage-source-row">
          <Button type="button" variant="ghost" className="vb-footage-source" aria-pressed={selectedIds.includes(asset.library_asset_id)} onClick={(event) => onSelect(asset, event.shiftKey)}>
            <span className="vb-footage-source__thumb">{asset.thumbnail_url ? <img src={asset.thumbnail_url} alt="" /> : <span aria-hidden="true">▶</span>}</span>
            <span className="vb-footage-source__copy"><strong>{filename}</strong><small>{formatTime(duration)} · 원본 유지</small></span>
          </Button>
          <a className="vb-action-link" aria-label={`${filename} 라이브러리에서 보기`} href={`/library?library_asset_id=${encodeURIComponent(asset.library_asset_id)}`}>라이브러리에서 보기</a>
        </div>;
      })}
    </div>}
  </aside>;
}

export function formatTime(seconds: number) {
  const safe = Math.max(0, seconds || 0);
  const minutes = Math.floor(safe / 60);
  return `${minutes}:${(safe % 60).toFixed(1).padStart(4, "0")}`;
}
