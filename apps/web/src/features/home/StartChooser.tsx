import { Button } from "../../components/ui/button";

/** 들어가는 길. **실제로 뚫려 있는 길만** 여기 올린다.
 *
 *  `continue` — 만들던 편집본으로. 초안이 있을 때만.
 *  `script`   — 대본 붙여넣기 / 파일 불러오기.
 *
 *  아직 없는 길(영상 올려서 자막까지, 유진이 대본 쓰기)은 **일부러 빼 두었다.**
 *  없는 기능의 자리를 흉내 내면 배치가 거짓말을 하고, 익숙해서 쉬운 게 아니라
 *  익숙해서 더 헷갈리게 된다(`docs/decisions/2026-08-21-capcut-shell-layout.ko.md`). */
export type StartPath = "continue" | "script";

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
            <span>저장해 둔 편집본을 그대로 엽니다.</span>
          </Button>
        ) : null}
        <Button
          type="button"
          variant={hasDraft ? "outline" : "default"}
          className="vb-start-path"
          onClick={() => onStart("script")}
        >
          <strong>대본이 있어요</strong>
          <span>붙여넣거나 파일로 불러옵니다.</span>
        </Button>
      </div>
    </section>
  );
}
