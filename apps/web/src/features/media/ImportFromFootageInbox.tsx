import { useEffect, useState } from "react";

import { api, type FootageSequence, type MediaInboxAsset } from "../../api";
import { Button } from "../../components/ui/button";
import "./importFromFootageInbox.css";

function fileSizeLabel(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return "크기 확인 중";
  const mb = bytes / (1024 * 1024);
  return mb >= 1 ? `${mb.toFixed(1)}MB` : `${Math.max(1, Math.round(bytes / 1024))}KB`;
}

/** 이 묶음 안 항목들이 가리키는 원본 라이브러리 자산 id를 모은다.
 *  묶음은 원본 여러 개를 섞어 만들 수 있어(`sources` 배열) 항목별로 어느
 *  원본인지 따로 찾아야 한다. 같은 원본에서 자른 항목이 여럿이면 원본은
 *  한 번만 들여온다 -- `materializeLibraryAsset`은 항목(장면 구간) 단위가
 *  아니라 라이브러리 자산 단위로 동작한다. */
function librarySourceAssetIds(sequence: FootageSequence): string[] {
  const ids = new Set<string>();
  for (const item of sequence.items) {
    const sourceId = item.source_id ?? sequence.source_id;
    const source = sequence.sources?.find((candidate) => candidate.source_id === sourceId);
    if (source?.library_asset_id) ids.add(source.library_asset_id);
  }
  return [...ids];
}

/** 따로 모아 둔 **촬영본**에서 골라 이 프로젝트로 가져온다.
 *
 *  탭 둘: **가져올 영상**(아직 라이브러리에 안 들여온 원본, `listMediaInboxAssets`)과
 *  **이미 정리한 묶음**(`/footage`에서 장면을 나눠 승인해 둔 가상 묶음,
 *  `listApprovedFootageSequences`). 뒤의 것은 목록만 보여 준다 -- `/footage`의
 *  나누기·타임라인·프레임 이동 UI는 여기 옮기지 않는다. 묶음을 고르면 그 안
 *  항목들이 가리키는 원본을 `materializeLibraryAsset`으로 들인다(개별 항목을
 *  고를 때 쓰는 것과 같은 경로).
 *  → `docs/superpowers/specs/2026-08-27-library-footage-projects-redesign-plan.ko.md` §2.3, §2.4
 */
export function ImportFromFootageInbox({
  projectId,
  onImported,
}: {
  projectId: string;
  onImported?: () => void | Promise<void>;
}) {
  const [tab, setTab] = useState<"inbox" | "sequences">("inbox");

  const [items, setItems] = useState<readonly MediaInboxAsset[] | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [reloadToken, setReloadToken] = useState(0);

  const [sequences, setSequences] = useState<readonly FootageSequence[] | null>(null);
  const [sequenceBusy, setSequenceBusy] = useState<string | null>(null);
  const [sequenceMessage, setSequenceMessage] = useState<string | null>(null);
  const [sequenceLoadFailed, setSequenceLoadFailed] = useState(false);
  const [sequenceReloadToken, setSequenceReloadToken] = useState(0);

  useEffect(() => {
    let active = true;
    setItems(null);
    setLoadFailed(false);
    void api.listMediaInboxAssets()
      .then((next) => { if (active) setItems(next); })
      .catch(() => { if (active) setLoadFailed(true); });
    return () => { active = false; };
  }, [reloadToken]);

  useEffect(() => {
    let active = true;
    setSequences(null);
    setSequenceLoadFailed(false);
    void api.listApprovedFootageSequences()
      .then((result) => { if (active) setSequences(result.sequences); })
      .catch(() => { if (active) setSequenceLoadFailed(true); });
    return () => { active = false; };
  }, [sequenceReloadToken]);

  async function importOne(filename: string) {
    if (busy) return;
    setBusy(filename);
    setMessage(null);
    try {
      await api.importMediaInboxAsset(projectId, filename);
      setMessage(`「${filename}」을 가져왔어요.`);
      await onImported?.();
    } catch {
      // 실패를 조용히 넘기지 않는다. 무엇이 안 됐는지 이름을 그대로 말한다.
      setMessage(`「${filename}」을 가져오지 못했어요. 다시 시도해 주세요.`);
    } finally {
      setBusy(null);
    }
  }

  async function importSequence(sequence: FootageSequence) {
    if (sequenceBusy) return;
    setSequenceBusy(sequence.sequence_id);
    setSequenceMessage(null);
    try {
      const assetIds = librarySourceAssetIds(sequence);
      if (assetIds.length === 0) throw new Error("footage_sequence_missing_library_asset");
      for (const assetId of assetIds) {
        await api.materializeLibraryAsset(assetId, projectId);
      }
      setSequenceMessage(`「${sequence.name}」을 가져왔어요.`);
      await onImported?.();
    } catch {
      setSequenceMessage(`「${sequence.name}」을 가져오지 못했어요. 다시 시도해 주세요.`);
    } finally {
      setSequenceBusy(null);
    }
  }

  return <div className="vb-inbox-import">
    <div className="vb-inbox-import__tabs" role="tablist" aria-label="촬영본 가져오기 방식">
      <Button type="button" variant="ghost" className="vb-inbox-import__tab" role="tab" aria-selected={tab === "inbox"} onClick={() => setTab("inbox")}>가져올 영상</Button>
      <Button type="button" variant="ghost" className="vb-inbox-import__tab" role="tab" aria-selected={tab === "sequences"} onClick={() => setTab("sequences")}>이미 정리한 묶음</Button>
    </div>

    {tab === "inbox" ? (
      loadFailed ? <div className="vb-inbox-import__state">
        <p role="alert">모아 둔 영상을 불러오지 못했어요.</p>
        <Button type="button" variant="outline" onClick={() => setReloadToken((value) => value + 1)}>다시 불러오기</Button>
      </div>
      : items === null ? <p role="status">모아 둔 영상을 불러오고 있어요.</p>
      : items.length === 0 ? <p>아직 따로 모아 둔 영상이 없어요.</p>
      : <div className="vb-inbox-import__list-wrap">
        <ul className="vb-inbox-import__list">
          {items.map((item) => (
            <li key={item.filename}>
              <span>{item.filename}</span>
              <span>{fileSizeLabel(item.size_bytes)}</span>
              <Button
                type="button"
                variant="outline"
                aria-label={`${item.filename} 가져오기`}
                disabled={busy !== null}
                onClick={() => void importOne(item.filename)}
              >
                가져오기
              </Button>
            </li>
          ))}
        </ul>
        {message ? <p role="status">{message}</p> : null}
      </div>
    ) : (
      sequenceLoadFailed ? <div className="vb-inbox-import__state">
        <p role="alert">정리한 묶음을 불러오지 못했어요.</p>
        <Button type="button" variant="outline" onClick={() => setSequenceReloadToken((value) => value + 1)}>다시 불러오기</Button>
      </div>
      : sequences === null ? <p role="status">정리한 묶음을 불러오고 있어요.</p>
      : sequences.length === 0 ? <p>아직 승인해 둔 묶음이 없어요.</p>
      : <div className="vb-inbox-import__list-wrap">
        <ul className="vb-inbox-import__list vb-inbox-import__sequence-list">
          {sequences.map((sequence) => (
            <li key={sequence.sequence_id}>
              <span>{sequence.name}</span>
              <span>{sequence.items.length}개 장면</span>
              <Button
                type="button"
                variant="outline"
                aria-label={`${sequence.name} 가져오기`}
                disabled={sequenceBusy !== null}
                onClick={() => void importSequence(sequence)}
              >
                가져오기
              </Button>
            </li>
          ))}
        </ul>
        {sequenceMessage ? <p role="status">{sequenceMessage}</p> : null}
      </div>
    )}
  </div>;
}
