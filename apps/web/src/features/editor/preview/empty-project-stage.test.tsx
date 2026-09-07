import { describe, expect, it } from "vitest"
import { cleanup, render, screen } from "@testing-library/react"
import { afterEach } from "vitest"

import { PreviewStage } from "./preview-stage"

afterEach(() => cleanup())

const base = {
  expectedRevision: 1,
  captions: [],
  sources: [],
  playbackSec: 0,
  fps: { num: 30, den: 1 },
  durationSec: 5,
} as const

/** owner가 제일 먼저 막힌 자리다(2026-09-04):
 *  > "가장 큰 문제는 처음에 영상 제작을 할때 뭘 어떤걸 눌러야할지도 모르겠고"
 *
 *  갓 만든 프로젝트를 열면 첫 화면이 **"미리보기를 만들지 못했어요"를 두 번**
 *  말했다(실측). 백엔드가 빈 타임라인의 미리보기를 `failed`로 표시하기 때문인데,
 *  **빈 프로젝트를 그리는 데 실패한 게 아니라 그릴 것이 아직 없는 것**이다.
 *  첫인상이 오류 화면이면 "내가 뭘 잘못했나"부터 생각하게 된다.
 *
 *  여기서 지키는 것은 **아직 아무것도 없을 때는 실패라고 말하지 않고 다음에
 *  할 일을 알려 준다**이다. 캡컷도 빈 프로젝트에는 오류가 아니라 올리기 안내를 둔다. */
describe("갓 만든 프로젝트는 실패라고 말하지 않는다", () => {
  it("아직 아무것도 안 넣었으면 다음에 할 일을 알려 준다", () => {
    render(<PreviewStage {...base} projectIsEmpty exactPreview={{ status: "failed" }} />)

    expect(screen.queryByText(/만들지 못했어요/)).toBeNull()
    expect(screen.getByText(/미디어/)).toBeInTheDocument()
  })

  it("내용이 있는데 진짜로 실패했으면 그대로 실패라고 말한다", () => {
    // 빈 프로젝트 안내가 진짜 실패까지 덮으면 창작자가 고장을 모른다.
    render(<PreviewStage {...base} projectIsEmpty={false} exactPreview={{ status: "failed" }} />)

    // 빈 자리 안내와 아래 상태 줄 두 곳이 같이 말한다 -- 실패는 눈에 띄어야 한다.
    expect(screen.getAllByText(/만들지 못했어요/).length).toBeGreaterThan(0)
  })
})
