import { useEffect, useState } from "react";

import { api, type MediaInboxAsset } from "../../api";
import { Button } from "../../components/ui/button";

function fileSizeLabel(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return "크기 확인 중";
  const mb = bytes / (1024 * 1024);
  return mb >= 1 ? `${mb.toFixed(1)}MB` : `${Math.max(1, Math.round(bytes / 1024))}KB`;
}

/** 따로 모아 둔 **촬영본**에서 골라 이 프로젝트로 가져온다.
 *
 *  미디어 화면의 `가져오기` 탭에는 길이 둘이었다 -- 새 파일 올리기와 촬영본에서
 *  고르기. 앞의 것은 편집기 도크에 바로 붙였고(`AddMediaFiles`), 뒤의 것은 목록을
 *  보여 줘야 해서 팝업 안에서 쓴다.
 *  → `docs/decisions/2026-08-27-editor-centered-shell-direction.ko.md`
 */
export function ImportFromFootageInbox({
  projectId,
  onImported,
}: {
  projectId: string;
  onImported?: () => void | Promise<void>;
}) {
  const [items, setItems] = useState<readonly MediaInboxAsset[] | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    let active = true;
    setItems(null);
    setLoadFailed(false);
    void api.listMediaInboxAssets()
      .then((next) => { if (active) setItems(next); })
      .catch(() => { if (active) setLoadFailed(true); });
    return () => { active = false; };
  }, [reloadToken]);

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

  if (loadFailed) {
    return <div className="vb-inbox-import">
      <p role="alert">모아 둔 영상을 불러오지 못했어요.</p>
      <Button type="button" variant="outline" onClick={() => setReloadToken((value) => value + 1)}>다시 불러오기</Button>
    </div>;
  }
  if (items === null) return <p role="status">모아 둔 영상을 불러오고 있어요.</p>;
  if (items.length === 0) return <p>아직 따로 모아 둔 영상이 없어요.</p>;

  return <div className="vb-inbox-import">
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
  </div>;
}
