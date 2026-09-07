import { useRef, useState } from "react";

import { api } from "../../api";
import { Button } from "../../components/ui/button";

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
 *  **이 절차가 두 곳에 있던 문제는 2026-09-01에 닫혔다.** `MediaWorkspacePage`
 *  (독립 "미디어" 단계 화면)가 같은 두 단계를 자기 action-token 모델 안에서
 *  따로 돌리고 있었는데, 그 화면이 위 결정 문서의 순서 2대로 편집기 탭으로
 *  접히며 없어졌다 -- 이제 이 조각 하나만 남았다.
 */
export function AddMediaFiles({
  projectId,
  label = "파일 추가",
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
  const inputRef = useRef<HTMLInputElement | null>(null);

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
      {/* **입력칸을 감추고 단추로 연다.** 좁은 도크(265px)에서 네이티브 파일칸은
          `파일 선택 | 선택된 파일 없음`까지 그려서 한 줄을 통째로 먹었다. 재 보니
          도크 402px 중 조작부가 282px(70%)였고 첫 미디어 카드는 335px 아래에서야
          시작했다 -- 미디어를 보러 연 칸인데 미디어가 안 보였다.
          이 저장소가 이미 쓰는 방식이다(`AssetIngestDropzone`). */}
      <input
        ref={inputRef}
        data-native-control="editor-media-file-input"
        aria-label={label}
        type="file"
        accept="video/*,.mp4,.mov,.webm,.mkv"
        multiple
        hidden
        onChange={(event) => {
          const files = event.target.files;
          event.target.value = "";
          if (files && files.length > 0) void addFiles(files);
        }}
      />
      <Button type="button" variant="outline" disabled={busy} onClick={() => inputRef.current?.click()}>
        {busy ? "더하는 중" : label}
      </Button>
      {message ? <p role="status">{message}</p> : null}
    </div>
  );
}
