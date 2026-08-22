import { Button } from "../../components/ui/button";

/** 들어가는 길. **실제로 뚫려 있는 길만** 여기 올린다.
 *
 *  `continue` — 만들던 편집본으로. 초안이 있을 때만.
 *  `script`   — 대본 붙여넣기 / 파일 불러오기.
 *  `footage`  — 찍어 둔 영상에서 말을 받아써 대본을 만든다(2026-08-21에 뚫렸다).
 *  `draft`    — 주제만 알려 주면 유진이 대본 초안을 쓴다(2026-08-21에 뚫렸다).
 *
 *  **앞의 셋은 전부 이미 가진 것을 전제했다** — 만들던 편집본, 써 둔 대본, 찍어 둔
 *  영상. 아무것도 없는 사람은 들어갈 문이 없었고, 그래서 네 번째 자리를 비워 뒀다는
 *  주석이 여기 있었다. 그 길이 실제로 뚫렸으므로 이제는 감추는 쪽이 거짓말이다
 *  (`docs/decisions/2026-08-21-capcut-shell-layout.ko.md`). */
export type StartPath = "continue" | "script" | "footage" | "draft";

export function StartChooser({
  hasDraft,
  onStart,
}: {
  hasDraft: boolean;
  onStart: (path: StartPath) => void;
}) {
  return (
    <section className="vb-start-chooser" aria-label="어떻게 시작할까요">
      <h1>어떻게 시작할까요?</h1>
      <div className="vb-start-chooser__paths">
        {hasDraft ? (
          <Button type="button" className="vb-start-path" onClick={() => onStart("continue")}>
            <strong>만들던 영상 이어서</strong>
            <span>저장된 편집본 열기</span>
          </Button>
        ) : null}
        <Button
          type="button"
          variant={hasDraft ? "outline" : "default"}
          className="vb-start-path"
          onClick={() => onStart("script")}
        >
          <strong>대본이 있어요</strong>
          <span>붙여넣기 · 파일 불러오기</span>
        </Button>
        <Button
          type="button"
          variant="outline"
          className="vb-start-path"
          onClick={() => onStart("footage")}
        >
          <strong>찍어 둔 영상이 있어요</strong>
          <span>말 받아쓰기 → 대본</span>
        </Button>
        <Button
          type="button"
          variant="outline"
          className="vb-start-path"
          onClick={() => onStart("draft")}
        >
          <strong>아직 아무것도 없어요</strong>
          <span>주제 입력 → 유진이 대본 초안</span>
        </Button>
      </div>
    </section>
  );
}
