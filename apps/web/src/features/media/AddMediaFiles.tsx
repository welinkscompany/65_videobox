import { useRef, useState } from "react";

import { api } from "../../api";
import { Input } from "../../components/ui/input";

/** 파일을 골라 **이 프로젝트의 미디어로** 들이는 한 조각.
 *
 *  올리는 일은 두 단계다 -- 라이브러리에 넣고(`ingestLibraryAssets`), 그 항목을
 *  이 프로젝트로 실체화한다(`materializeLibraryAsset`).
 *
 *  왜 만들었나: 2026-08-27에 재 보니 **편집기 안에는 미디어를 더할 길이 아예
 *  없었다.** 파일 입력도, 미디어 화면으로 나가는 링크조차 없었다. 쓰려면 위 띠에서
 *  미디어 단계를 눌러 화면을 떠나야 한다는 것을 스스로 알아내야 했다. 캡컷은
 *  미디어 탭 안에서 바로 가져온다.
 *  → `docs/decisions/2026-08-27-editor-centered-shell-direction.ko.md`
 *
 *  **지금 이 절차는 두 곳에 있다.** `MediaWorkspacePage`가 같은 두 단계를 자기
 *  action-token 모델 안에서 따로 돌린다. 합치지 않은 이유는 그 화면이 위 결정
 *  문서의 순서 2에서 **편집기 탭으로 접히며 없어질 예정**이라, 지금 합치면 곧
 *  버릴 것을 손보게 되기 때문이다. 감추지 않고 여기 적어 둔다 -- 그 화면이
 *  없어질 때 이 조각 하나만 남는지 반드시 확인하라. 그때까지 **업로드 절차를
 *  고치면 두 곳을 같이 고쳐야 한다.**
 */
export function AddMediaFiles({
  projectId,
  label = "미디어 파일 추가",
  onAdded,
}: {
  projectId: string;
  label?: string;
  onAdded?: () => void | Promise<void>;
}) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  // 화면이 사라진 뒤 상태를 건드리지 않도록, 마지막 요청만 말하게 한다.
  const requestId = useRef(0);

  async function addFiles(files: FileList) {
    if (files.length === 0 || busy) return;
    const id = requestId.current + 1;
    requestId.current = id;
    setBusy(true);
    setMessage(null);
    let succeeded = 0;
    let failed = 0;
    try {
      const batch = await api.ingestLibraryAssets(Array.from(files), "broll", `editor-${projectId}-${id}`);
      for (const item of batch.items) {
        if (!item.library_asset_id || (item.state !== "ready" && item.state !== "duplicate")) {
          failed += 1;
          continue;
        }
        try {
          await api.materializeLibraryAsset(item.library_asset_id, projectId);
          succeeded += 1;
        } catch {
          failed += 1;
        }
      }
    } catch {
      failed = files.length;
    }
    if (requestId.current !== id) return;
    setBusy(false);
    // 실패를 조용히 넘기지 않는다. 몇 개가 들어갔는지 그대로 말한다.
    setMessage(
      succeeded > 0 && failed === 0 ? `${succeeded}개를 더했어요.`
        : succeeded > 0 ? `${succeeded}개를 더했고 ${failed}개는 더하지 못했어요.`
          : "파일을 더하지 못했어요. 다시 시도해 주세요.",
    );
    if (succeeded > 0) await onAdded?.();
  }

  return (
    <div className="vb-add-media">
      <label htmlFor={`add-media-${projectId}`}>{label}</label>
      <Input
        id={`add-media-${projectId}`}
        type="file"
        accept="video/*,.mp4,.mov,.webm,.mkv"
        multiple
        disabled={busy}
        onChange={(event) => {
          const files = event.target.files;
          event.target.value = "";
          if (files && files.length > 0) void addFiles(files);
        }}
      />
      {busy ? <p role="status">파일을 더하고 있어요.</p> : null}
      {message ? <p role="status">{message}</p> : null}
    </div>
  );
}
