import { useState } from "react";

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
  // **만들던 것이 있으면 시작하는 길을 되묻지 않는다(owner 지시 2026-08-27).**
  //
  // owner: "우리 메뉴가 너무 각각 페이지별로 따로 놀아."
  //
  // 2026-08-21에 "다음에 할 일로 보이는 것" 다섯을 세고 이 선택창을 만들었는데,
  // 2026-08-27에 다시 세니 **16~17개**로 늘어 있었다. 원인 하나가 여기다 --
  // 이미 만들던 영상이 있는 프로젝트에서도 `어떻게 시작할까요?`라고 물었다.
  // 이미 답이 나온 질문이고, 나머지 세 길은 전부 "처음부터 다시"라서 지금
  // 할 일과 경쟁한다.
  //
  // **접는 것이지 없애는 것이 아니다.** 감추면 거짓말이 된다 -- 만들던 것을
  // 버리고 새로 시작하고 싶을 수 있다. 그래서 한 번 더 누르면 그대로 나온다.
  const [showOtherPaths, setShowOtherPaths] = useState(false);
  const otherPathsVisible = !hasDraft || showOtherPaths;
  return (
    <section className="vb-start-chooser" aria-label={hasDraft ? "이어서 만들기" : "어떻게 시작할까요"}>
      <h1>{hasDraft ? "이어서 만들까요?" : "어떻게 시작할까요?"}</h1>
      <div className="vb-start-chooser__paths">
        {hasDraft ? (
          <Button type="button" className="vb-start-path" onClick={() => onStart("continue")}>
            <strong>만들던 영상 이어서</strong>
            <span>저장된 편집본 열기</span>
          </Button>
        ) : null}
        {otherPathsVisible ? (
          <>
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
          </>
        ) : null}
      </div>
      {hasDraft && !showOtherPaths ? (
        <Button
          type="button"
          variant="ghost"
          className="vb-start-chooser__more"
          aria-expanded={false}
          onClick={() => setShowOtherPaths(true)}
        >
          다르게 시작하기
        </Button>
      ) : null}
    </section>
  );
}
