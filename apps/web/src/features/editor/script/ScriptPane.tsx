import { useState } from "react";

import { api } from "../../../api";
import { Button } from "../../../components/ui/button";
import { Textarea } from "../../../components/ui/textarea";

/** 편집기 안 `대본` 자리 (계획 §10 5단계).
 *
 *  완성의 정의는 계획서가 정했다: **"새 프로젝트가 `이야기`를 안 거치고도
 *  대본을 넣을 수 있다"**.
 *
 *  **이 자리는 한 번 일부러 안 만들었다.** `EditorAssetBrowser` 주석이 그
 *  이유를 남겼다 -- "지금 탭만 만들면 대본을 붙여넣은 뒤 갈 곳이 없는 막다른
 *  자리가 된다". 그 경고를 지킨다: 저장까지 하되 **다음에 어디로 가는지**를
 *  같은 자리에서 알려 준다.
 *
 *  대본에서 영상이 만들어지는 길(질문·요약·초안)은 `이야기` 화면이 그대로
 *  맡는다. 여기서 그 흐름을 다시 만들지 않는다 -- 두 벌이 되면 반드시 어긋난다.
 */
export function ScriptPane({
  projectId,
  onOpenStory,
}: {
  projectId: string;
  /** `이야기` 화면으로 데려간다. 없으면 그 단추를 아예 만들지 않는다. */
  onOpenStory?: () => void;
}) {
  const [draft, setDraft] = useState("");
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const save = async () => {
    const text = draft.trim();
    if (!text) {
      setMessage("대본을 붙여넣어 주세요.");
      return;
    }
    setBusy(true);
    setMessage(null);
    try {
      await api.createCreationBrief(projectId, {
        script_filename: "붙여넣은-대본.txt",
        script_text: text,
        // 같은 대본을 두 번 눌러도 초안이 둘 생기지 않게 한다. 시각을 섞는 것은
        // 같은 세션에서 다른 대본을 넣을 수 있어야 하기 때문이다.
        idempotency_key: `editor-script-${projectId}-${text.length}-${Date.now()}`,
        capability_profile: { ai_execution: "disabled" },
      });
      setSaved(true);
    } catch {
      // **쓴 것을 지우지 않는다.** 저장에 실패했는데 글까지 사라지면 두 번 잃는다.
      setMessage("대본을 저장하지 못했어요. 잠시 뒤 다시 눌러 주세요.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section aria-label="대본" className="vb-script-pane">
      <h2>대본</h2>
      <p>여기에 붙여넣으면 이 프로젝트의 대본이 돼요. 장면으로 나누는 일은 `이야기`에서 이어서 해요.</p>
      <label className="sr-only" htmlFor="vb-editor-script">대본</label>
      <Textarea
        aria-label="대본"
        disabled={busy}
        id="vb-editor-script"
        onChange={(event) => setDraft(event.target.value)}
        value={draft}
      />
      {message ? <p role="status">{message}</p> : null}
      <Button disabled={busy} onClick={() => void save()} type="button">
        {busy ? "저장하는 중" : "대본 저장"}
      </Button>
      {/* 막다른 자리가 되지 않게 다음 걸음을 같은 자리에서 준다. */}
      {saved ? <>
        <p role="status">대본을 저장했어요.</p>
        {onOpenStory ? <Button onClick={onOpenStory} type="button" variant="outline">이야기 이어서 하기</Button> : null}
      </> : null}
    </section>
  );
}
