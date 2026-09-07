import { afterEach, describe, expect, it, vi } from "vitest"
import { cleanup, fireEvent, render, screen } from "@testing-library/react"

import { RightDock } from "./RightDock"

afterEach(() => { cleanup(); vi.restoreAllMocks() })

const segment = {
  segmentId: "scene-1",
  startSec: 0,
  endSec: 8,
  ripplePlaybackRate: 1,
} as never

/** owner 지시(2026-09-04): "속도는 캡컷이랑 동일하게 맞춰."
 *  기록: `decisions/2026-09-04-capcut-shell-with-my-assets.ko.md` §1
 *
 *  캡컷 `속도` 속성은 `속도 [ ]x`와 `기간 [ ]s`를 나란히 두고 **연동**한다.
 *  우리는 `장면 길이`라는 다른 이름에 단추 셋(`기본`·`1.5배`·`2배`)뿐이라
 *  1.25배를 쓸 방법이 없었다.
 *
 *  엔진은 처음부터 0.25~4를 감당했다(`_atempo_chain`) -- 화면과 검증만 좁혀
 *  놨던 것이라, 여기서 넓히는 것은 새 기능이 아니라 막아 뒀던 것을 여는 일이다. */
describe("속도 칸은 캡컷과 같다", () => {
  it("이름이 `속도`다", () => {
    render(<RightDock selectedSegment={segment} onSetSegmentRippleSpeed={vi.fn()} />)
    // 묶음은 `속도 조정`이고 입력칸이 `속도`다 -- 둘 다 `속도`면 화면 읽개가
    // 같은 이름을 두 번 부르고, 시험에서도 어느 쪽인지 가릴 수 없다.
    expect(screen.getByRole("group", { name: "속도 조정" })).toBeInTheDocument()
    expect(screen.getByRole("spinbutton", { name: "속도" })).toBeInTheDocument()
    expect(screen.queryByText("장면 길이")).not.toBeInTheDocument()
  })

  it("임의 배속을 숫자로 넣는다", async () => {
    const onSet = vi.fn()
    render(<RightDock selectedSegment={segment} onSetSegmentRippleSpeed={onSet} />)

    const speed = screen.getByLabelText("속도")
    fireEvent.change(speed, { target: { value: "1.25" } })
    fireEvent.blur(speed)

    expect(onSet).toHaveBeenCalledWith({ segmentId: "scene-1", rate: 1.25 })
  })

  it("기간이 배속을 따라 바뀐다", () => {
    // 8초 장면을 2배속으로 보면 4초다. 캡컷은 이 둘을 나란히 보여 준다.
    render(<RightDock selectedSegment={segment} onSetSegmentRippleSpeed={vi.fn()} />)
    const speed = screen.getByLabelText("속도")
    fireEvent.change(speed, { target: { value: "2" } })

    expect(screen.getByLabelText("기간")).toHaveValue(4)
  })

  it("렌더가 못 내는 값은 보내지 않는다", () => {
    // 엔진도 거부하지만, 화면이 먼저 막아야 창작자가 실패를 안 본다.
    const onSet = vi.fn()
    render(<RightDock selectedSegment={segment} onSetSegmentRippleSpeed={onSet} />)
    const speed = screen.getByLabelText("속도")

    fireEvent.change(speed, { target: { value: "9" } })
    fireEvent.blur(speed)

    expect(onSet).not.toHaveBeenCalled()
  })
})
