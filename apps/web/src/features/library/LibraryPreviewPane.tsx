import { useEffect, useState } from "react";
import { api, type LibraryAsset, type LibraryMediaType, type LibraryUsage } from "../../api";
import { resolveProjectStage } from "../../app/routeManifest";

function filename(asset: LibraryAsset) { return String(asset.user_metadata?.filename ?? asset.asset_id ?? asset.library_asset_id); }

const KIND_LABELS: Record<string, string> = { broll: "영상", image: "그림", music: "음악", sfx: "효과음" };

/**
 * 종류를 잘못 갈랐을 때 옮겨 갈 수 있는 곳 (owner 결정 2026-09-07).
 *
 * 자산을 한 폴더에 넣으면 VideoBox가 내용을 보고 가른다. 음악과 효과음은
 * 길이로 가르므로 경계 근처에서 틀리고, 정지 화면은 영상과 헷갈린다.
 * 고치는 이 길이 그 결정의 조건이었다 -- 없으면 기능을 낼 수 없다.
 *
 * 갈래를 넘는 수정은 없다. 소리를 그림이라 부르면 미리보기가 빈 그림을 그린다.
 */
const KIND_SWAP: Partial<Record<string, LibraryMediaType>> = { music: "sfx", sfx: "music", broll: "image", image: "broll" };

export function LibraryPreviewPane({ asset, onChanged }: { asset: LibraryAsset | null; onChanged?: () => void }) {
  const [usage, setUsage] = useState<LibraryUsage | null>(null); const [busy, setBusy] = useState(false);
  // 되돌릴 수 없는 동작이라 한 번 더 확인한다 -- 프로젝트 영구 삭제와 같은
  // 2단계 패턴이다(`app/AppRouter.tsx`의 `deleteConfirm`). 고른 자산이
  // 바뀌면 이전 자산에서 눌러 둔 확인 상태가 다음 자산에 새지 않게 지운다.
  const [confirmPermanentDelete, setConfirmPermanentDelete] = useState(false);
  useEffect(() => { setConfirmPermanentDelete(false); }, [asset?.library_asset_id]);
  useEffect(() => { let active = true; setUsage(null); if (asset) void api.getLibraryAssetUsage(asset.library_asset_id).then((next) => { if (active) setUsage(next); }).catch(() => { if (active) setUsage({ library_asset_id: asset.library_asset_id, locations: [] }); }); return () => { active = false; }; }, [asset]);
  if (!asset) return <aside className="vb-library-preview" data-testid="library-preview" aria-label="미디어 미리보기"><p className="vb-library-empty-preview">미디어를 선택하면 미리볼 수 있어요.</p></aside>;
  // 종류마다 보는 방법이 다르다. 예전에는 "영상이 아니면 소리"였는데, 그림이
  // 생기면서 그 갈래로는 그림에 빈 소리 재생기가 떴다.
  const name = filename(asset); const assetId = asset.library_asset_id; const isPicture = asset.media_type === "image"; const isAudio = !isPicture && asset.media_type !== "broll"; const isVideo = asset.media_type === "broll"; const blocked = (usage?.locations.length ?? 0) > 0 || asset.origin === "builtin";
  async function trash() { if (blocked) return; setBusy(true); try { await api.trashLibraryAsset(assetId); onChanged?.(); } finally { setBusy(false); } }
  async function restore() { setBusy(true); try { await api.restoreLibraryAsset(assetId); onChanged?.(); } finally { setBusy(false); } }
  async function permanentlyDelete() { setBusy(true); try { await api.permanentDeleteLibraryAsset(assetId); onChanged?.(); } finally { setBusy(false); setConfirmPermanentDelete(false); } }
  const swapTo = asset.origin === "builtin" ? undefined : KIND_SWAP[asset.media_type];
  async function correctKind(next: LibraryMediaType) { setBusy(true); try { await api.correctLibraryAssetMediaType(assetId, next); onChanged?.(); } finally { setBusy(false); } }
  return <aside className="vb-library-preview" data-testid="library-preview" aria-label="미디어 미리보기"><div className="vb-library-preview__heading"><p className="vb-eyebrow">미리보기</p><h2>{name}</h2>{isVideo && asset.lifecycle !== "trashed" ? <a className="vb-action-link" href={`/footage?library_asset_id=${encodeURIComponent(asset.library_asset_id)}`}>구간 정리하기</a> : null}</div><div className="vb-library-preview__player" data-testid="library-preview-player">{asset.lifecycle === "trashed" ? <p>휴지통에 있는 미디어</p> : isPicture ? <img src={asset.preview_url ?? api.libraryAssetPreviewUrl(asset.library_asset_id)} alt={name} /> : isAudio ? <audio controls preload="metadata" src={asset.preview_url ?? api.libraryAssetPreviewUrl(asset.library_asset_id)} /> : <video controls preload="metadata" src={asset.preview_url ?? api.libraryAssetPreviewUrl(asset.library_asset_id)} />}</div><dl className="vb-library-metadata"><div><dt>종류</dt><dd>{KIND_LABELS[asset.media_type] ?? asset.media_type}</dd></div><div><dt>상태</dt><dd>{asset.lifecycle === "ready" ? "준비됨" : asset.lifecycle === "needs_attention" ? "확인 필요" : asset.lifecycle === "processing" ? "분석 중" : "휴지통"}</dd></div>{asset.machine_metadata?.description ? <div><dt>분석</dt><dd>{String(asset.machine_metadata.description)}</dd></div> : null}</dl>{swapTo && asset.lifecycle !== "trashed" ? <p className="vb-library-kind-fix-row"><button data-native-control="library-correct-media-type" type="button" className="vb-library-kind-fix" onClick={() => void correctKind(swapTo)} disabled={busy} aria-label={`${name}을(를) ${KIND_LABELS[swapTo]}으로 옮기기`}>{KIND_LABELS[swapTo]}으로 옮기기</button></p> : null}{usage && usage.locations.length > 0 ? <div className="vb-library-usage" role="status"><strong>사용 중인 위치</strong><ul>{usage.locations.map((location, index) => {
      const label = String(location.location.label ?? location.location.kind ?? "프로젝트");
      // 어느 프로젝트인지 알면 그 프로젝트의 자산 화면으로 바로 보낸다. 위치를
      // 알려주면서 갈 길은 안 주면 owner가 다시 찾아 헤맨다.
      return <li key={`${location.project_id ?? "project"}-${index}`}>{location.project_id
        ? <a className="vb-action-link" aria-label={`${label} 편집기에서 열기`} href={resolveProjectStage(location.project_id, "edit")}>{label}</a>
        : label}</li>;
    })}</ul></div> : null}<div className="vb-library-preview__actions">{asset.lifecycle === "trashed" ? <>
      <button data-native-control="library-restore" type="button" onClick={() => void restore()} disabled={busy} aria-label="복원">복원</button>
      {confirmPermanentDelete ? (
        <button data-native-control="library-permanent-delete-confirm" type="button" onClick={() => void permanentlyDelete()} disabled={busy} aria-label={`${name} 영구 삭제 · 한 번 더 확인할게요`}>영구 삭제 · 한 번 더 확인할게요</button>
      ) : (
        <button data-native-control="library-permanent-delete" type="button" onClick={() => setConfirmPermanentDelete(true)} disabled={busy} aria-label={`${name} 영구 삭제`}>영구 삭제</button>
      )}
    </> : <button data-native-control="library-trash" type="button" onClick={() => void trash()} disabled={busy || blocked} aria-label="휴지통으로 이동">휴지통으로 이동</button>}</div></aside>;
}
