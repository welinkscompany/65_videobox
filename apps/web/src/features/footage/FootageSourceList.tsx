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
          {/* `data-multiline`: 이 칸은 그림·파일이름·길이·`자료실에서 보기`가 여러 줄로
              들어가서 단추 기본 높이(32px)에 가두면 내용이 잘린다. 껍데기의 고정 높이를
              푸는 고리다(`product-shell.css`의 `[data-multiline="true"]`). */}
          <Button type="button" data-multiline="true" variant="ghost" className="vb-footage-source" aria-pressed={selectedIds.includes(asset.library_asset_id)} onClick={(event) => onSelect(asset, event.shiftKey)}>
            <span className="vb-footage-source__thumb">{asset.thumbnail_url ? <img src={asset.thumbnail_url} alt="" /> : <span aria-hidden="true">▶</span>}</span>
            <span className="vb-footage-source__copy"><strong>{filename}</strong><small>{formatTime(duration)} · 원본 유지</small></span>
          </Button>
          <a className="vb-action-link" aria-label={`${filename} 자료실에서 보기`} href={`/library?library_asset_id=${encodeURIComponent(asset.library_asset_id)}`}>자료실에서 보기</a>
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
