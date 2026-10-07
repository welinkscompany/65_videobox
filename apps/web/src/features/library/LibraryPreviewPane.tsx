import { useEffect, useState } from "react";
import { api, type LibraryAsset, type LibraryAssetRights, type LibraryMediaType, type LibraryUsage, type LibraryUsageLocation } from "../../api";
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

/**
 * 누가 만들었고 써도 되는가 (AK W1215-4, 2026-09-28). 기본은 모름이고, 모르는 자료를
 * 쓴 완성본은 업로드 승인 요청에서 막힌다 -- 여기가 그것을 푸는 자리다.
 */
const RIGHTS_LABELS: Record<LibraryAssetRights, string> = {
  unknown: "아직 몰라요 · 수익 채널에 못 올려요",
  own_footage: "직접 촬영",
  ai_generated: "AI로 만듦",
  third_party_licensed: "남의 자료 · 사용 허락 있음",
};
const RIGHTS_CHOICES: LibraryAssetRights[] = ["own_footage", "ai_generated", "third_party_licensed"];

type UsageRow = { key: string; label: string; projectId: string | null };

/**
 * 서버는 위치에 `label` 없이 `project_id`만 준다(2026-10-01 실측). 이름표가 없으면
 * 프로젝트 이름을 붙이고, 한 프로젝트에 여러 번 쓰였어도 한 줄로 묶는다. 목록에
 * 없는 프로젝트는 지워진 것이라 열 길이 없다 -- 한 줄로 모아 개수만 알린다.
 */
export function usageRows(locations: LibraryUsageLocation[], names: Map<string, string> | null): UsageRow[] {
  const rows: UsageRow[] = [];
  const seen = new Set<string>();
  let removed = 0;
  locations.forEach((location, index) => {
    const explicit = location.location.label ?? location.location.kind;
    const projectId = location.project_id ?? null;
    if (explicit == null && projectId) {
      if (seen.has(projectId)) return;
      seen.add(projectId);
      const name = names?.get(projectId);
      if (names && !name) { removed += 1; return; }
      rows.push({ key: projectId, label: name ?? "프로젝트", projectId });
      return;
    }
    rows.push({ key: `${projectId ?? "project"}-${index}`, label: String(explicit ?? "프로젝트"), projectId });
  });
  if (removed > 0) rows.push({ key: "removed", label: removed === 1 ? "지운 프로젝트" : `지운 프로젝트 ${removed}개`, projectId: null });
  return rows;
}

export function LibraryPreviewPane({ asset, onChanged, onToggleFavorite }: { asset: LibraryAsset | null; onChanged?: () => void; onToggleFavorite?: (asset: LibraryAsset) => void }) {
  const [usage, setUsage] = useState<LibraryUsage | null>(null); const [busy, setBusy] = useState(false);
  const [projectNames, setProjectNames] = useState<Map<string, string> | null>(null);
  useEffect(() => { let active = true; void api.listProjects(true).then((projects) => { if (active) setProjectNames(new Map(projects.map((project) => [project.project_id, project.name]))); }).catch(() => undefined); return () => { active = false; }; }, []);
  // 되돌릴 수 없는 동작이라 한 번 더 확인한다 -- 프로젝트 영구 삭제와 같은
  // 2단계 패턴이다(`app/AppRouter.tsx`의 `deleteConfirm`). 고른 자산이
  // 바뀌면 이전 자산에서 눌러 둔 확인 상태가 다음 자산에 새지 않게 지운다.
  const [confirmPermanentDelete, setConfirmPermanentDelete] = useState(false);
  const [rightsDraft, setRightsDraft] = useState<LibraryAssetRights>("unknown");
  const [licenseNoteDraft, setLicenseNoteDraft] = useState("");
  // 이름 바꾸기(2026-10-02, 점검 후속 A4). 고른 자산이 바뀌면 열어 둔 편집을 닫는다.
  const [renaming, setRenaming] = useState(false);
  const [nameDraft, setNameDraft] = useState("");
  const [renameError, setRenameError] = useState<string | null>(null);
  useEffect(() => { setRenaming(false); setRenameError(null); }, [asset?.library_asset_id]);
  useEffect(() => { setConfirmPermanentDelete(false); }, [asset?.library_asset_id]);
  useEffect(() => { setRightsDraft(asset?.rights_source ?? "unknown"); setLicenseNoteDraft(asset?.rights_license_note ?? ""); }, [asset?.library_asset_id, asset?.rights_source, asset?.rights_license_note]);
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
  const needsLicenseNote = rightsDraft === "third_party_licensed";
  const canSaveRights = rightsDraft !== "unknown" && (!needsLicenseNote || licenseNoteDraft.trim().length > 0);
  async function saveRights() { if (!canSaveRights) return; setBusy(true); try { await api.updateLibraryAssetRights(assetId, rightsDraft, needsLicenseNote ? licenseNoteDraft.trim() : null); onChanged?.(); } finally { setBusy(false); } }
  const rightsEditable = asset.origin !== "builtin" && asset.lifecycle !== "trashed";
  const renameEditable = asset.origin !== "builtin" && asset.lifecycle !== "trashed";
  const trimmedDraft = nameDraft.trim();
  // 서버(RenameLibraryAssetRequest)와 같은 규칙: 앞뒤 공백을 뗀 뒤 1~255자, / \ 와 제어 문자 불가, . 와 .. 불가.
  const nameHint = /[\\/]/.test(trimmedDraft) ? "이름에 / 나 \\ 는 쓸 수 없어요."
    : trimmedDraft === "." || trimmedDraft === ".." ? "이름을 . 이나 .. 로만 할 수는 없어요."
    // eslint-disable-next-line no-control-regex
    : /[\u0000-\u001f\u007f]/.test(trimmedDraft) ? "이름에 탭 같은 보이지 않는 글자는 쓸 수 없어요."
    : nameDraft.length > 255 ? "이름은 255자까지만 쓸 수 있어요." : null;
  const nameDraftInvalid = nameHint !== null;
  const canSaveName = trimmedDraft.length > 0 && !nameDraftInvalid && trimmedDraft !== name;
  function startRename() { setNameDraft(name); setRenameError(null); setRenaming(true); }
  async function saveName() {
    if (!canSaveName) return;
    setBusy(true); setRenameError(null);
    try { await api.renameLibraryAsset(assetId, trimmedDraft); setRenaming(false); onChanged?.(); }
    catch { setRenameError("이름을 바꾸지 못했어요. 다시 해 주세요."); }
    finally { setBusy(false); }
  }
  return <aside className="vb-library-preview" data-testid="library-preview" aria-label="미디어 미리보기"><div className="vb-library-preview__heading"><p className="vb-eyebrow">미리보기</p>{renaming ? <div className="vb-library-rename-row"><input data-native-control="library-rename-input" aria-label="새 이름" value={nameDraft} autoFocus onChange={(event) => setNameDraft(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") { event.preventDefault(); void saveName(); } else if (event.key === "Escape") { event.preventDefault(); setRenaming(false); } }} disabled={busy} aria-invalid={nameDraftInvalid} /><button data-native-control="library-rename-save" type="button" onClick={() => void saveName()} disabled={busy || !canSaveName}>이름 저장</button><button data-native-control="library-rename-cancel" type="button" onClick={() => setRenaming(false)} disabled={busy}>취소</button>{nameHint ? <p role="alert">{nameHint}</p> : null}{renameError ? <p role="alert">{renameError}</p> : null}</div> : <h2>{name}</h2>}{renameEditable && !renaming ? <button data-native-control="library-rename" type="button" className="vb-library-kind-fix" onClick={startRename} aria-label={`${name} 이름 바꾸기`}>이름 바꾸기</button> : null}{isVideo && asset.lifecycle !== "trashed" ? <a className="vb-action-link" href={`/footage?library_asset_id=${encodeURIComponent(asset.library_asset_id)}`}>구간 정리하기</a> : null}</div><div className="vb-library-preview__player" data-testid="library-preview-player">{asset.lifecycle === "trashed" ? <p>휴지통에 있는 미디어</p> : isPicture ? <img src={asset.preview_url ?? api.libraryAssetPreviewUrl(asset.library_asset_id)} alt={name} /> : isAudio ? <audio controls preload="metadata" src={asset.preview_url ?? api.libraryAssetPreviewUrl(asset.library_asset_id)} /> : <video controls preload="metadata" src={asset.preview_url ?? api.libraryAssetPreviewUrl(asset.library_asset_id)} />}</div><dl className="vb-library-metadata"><div><dt>종류</dt><dd>{KIND_LABELS[asset.media_type] ?? asset.media_type}</dd></div><div><dt>상태</dt><dd>{asset.lifecycle === "ready" ? "준비됨" : asset.lifecycle === "needs_attention" ? "확인 필요" : asset.lifecycle === "processing" ? "분석 중" : "휴지통"}</dd></div>{asset.machine_metadata?.description ? <div><dt>분석</dt><dd>{String(asset.machine_metadata.description)}</dd></div> : null}{asset.origin !== "builtin" ? <div><dt>출처</dt><dd>{RIGHTS_LABELS[asset.rights_source ?? "unknown"]}</dd></div> : null}</dl>{rightsEditable ? <div className="vb-library-rights-row"><label htmlFor={`library-rights-${assetId}`}>출처</label><select data-native-control="library-rights-source" id={`library-rights-${assetId}`} value={rightsDraft} onChange={(event) => setRightsDraft(event.target.value as LibraryAssetRights)} disabled={busy}><option value="unknown" disabled>고르세요</option>{RIGHTS_CHOICES.map((choice) => <option key={choice} value={choice}>{RIGHTS_LABELS[choice]}</option>)}</select>{needsLicenseNote ? <><label htmlFor={`library-license-${assetId}`}>사용 허락 내용</label><input data-native-control="library-rights-license-note" id={`library-license-${assetId}`} value={licenseNoteDraft} placeholder="예: Pexels 라이선스, 2026-09-28 확인" onChange={(event) => setLicenseNoteDraft(event.target.value)} disabled={busy} /></> : null}<button data-native-control="library-rights-save" type="button" onClick={() => void saveRights()} disabled={busy || !canSaveRights}>출처 저장</button></div> : null}{swapTo && asset.lifecycle !== "trashed" ? <p className="vb-library-kind-fix-row"><button data-native-control="library-correct-media-type" type="button" className="vb-library-kind-fix" onClick={() => void correctKind(swapTo)} disabled={busy} aria-label={`${name}을(를) ${KIND_LABELS[swapTo]}으로 옮기기`}>{KIND_LABELS[swapTo]}으로 옮기기</button></p> : null}{usage && usage.locations.length > 0 ? <div className="vb-library-usage" role="status"><strong>사용 중인 위치</strong><ul>{usageRows(usage.locations, projectNames).map((row) =>
      // 어느 프로젝트인지 알면 그 프로젝트의 자산 화면으로 바로 보낸다. 위치를
      // 알려주면서 갈 길은 안 주면 owner가 다시 찾아 헤맨다.
      <li key={row.key}>{row.projectId
        ? <a className="vb-action-link" aria-label={`${row.label} 편집기에서 열기`} href={resolveProjectStage(row.projectId, "edit")}>{row.label}</a>
        : row.label}</li>)}</ul></div> : null}<div className="vb-library-preview__actions">{onToggleFavorite && asset.origin !== "builtin" && asset.lifecycle !== "trashed" ? <button data-native-control="library-favorite" type="button" aria-pressed={Boolean(asset.user_metadata?.favorite)} onClick={() => onToggleFavorite(asset)}>{asset.user_metadata?.favorite ? "★ 즐겨찾기 해제" : "☆ 즐겨찾기"}</button> : null}{asset.lifecycle === "trashed" ? <>
      <button data-native-control="library-restore" type="button" onClick={() => void restore()} disabled={busy} aria-label="복원">복원</button>
      {confirmPermanentDelete ? (
        <button data-native-control="library-permanent-delete-confirm" type="button" onClick={() => void permanentlyDelete()} disabled={busy} aria-label={`${name} 영구 삭제 확정`}>영구 삭제 확정</button>
      ) : (
        <button data-native-control="library-permanent-delete" type="button" onClick={() => setConfirmPermanentDelete(true)} disabled={busy} aria-label={`${name} 영구 삭제`}>영구 삭제</button>
      )}
    </> : <button data-native-control="library-trash" type="button" onClick={() => void trash()} disabled={busy || blocked} aria-label="휴지통으로 이동">휴지통으로 이동</button>}</div></aside>;
}
