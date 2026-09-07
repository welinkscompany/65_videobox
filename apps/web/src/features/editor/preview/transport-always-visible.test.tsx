import { afterEach, describe, expect, it, vi } from "vitest"
import { cleanup, render, screen } from "@testing-library/react"

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

/** owner(2026-09-04): "타임라인에서 스페이스바를 누르면 멈춰야 되는데, 그것도 안되고"
 *
 *  재 보니 **기능은 원래 있었다** -- `preview-stage.tsx`가 `window`에 전역으로
 *  듣는다. 문제는 재생할 미디어가 없을 때 `if (!mediaRef.current) return`으로
 *  조용히 빠지고, **재생줄이 화면에서 통째로 사라진다**는 것이었다. 그래서
 *  창작자에게는 "눌러도 아무 일이 없다"로 보인다 -- 왜인지 알 방법이 없다.
 *
 *  캡컷은 재생 단추가 타임라인 도구줄에 늘 있다. 실시간 타임라인 재생을 새로
 *  만드는 것은 큰 일이라 이번 범위가 아니고, **여기서는 재생줄이 사라지지 않고
 *  이유를 말하게** 한다. 눌리지 않는 단추라도 있는 편이 없는 것보다 낫다 --
 *  없으면 고장인지 내 잘못인지 모른다. */
describe("재생줄은 사라지지 않는다", () => {
  it("재생할 것이 없어도 재생 단추가 남아 있고, 눌리지 않는다고 알려 준다", () => {
    render(<PreviewStage {...base} exactPreview={{ status: "unavailable" }} />)

    const play = screen.getByRole("button", { name: "재생 또는 일시정지" })
    expect(play).toBeInTheDocument()
    expect(play).toBeDisabled()
  })

  it("왜 못 누르는지 말한다", () => {
    render(<PreviewStage {...base} exactPreview={{ status: "unavailable" }} />)
    expect(screen.getByText(/아직 재생할 영상이 없어요/)).toBeInTheDocument()
  })
})
