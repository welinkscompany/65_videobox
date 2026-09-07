import { describe, expect, it, vi } from "vitest"
import { fireEvent, render, screen } from "@testing-library/react"

import { BrowseSection } from "./browse-section"

/** 캡컷 `전환`·`필터` 패널(`docs/references/capcut/2026-09-04-panel-transition.png`,
 *  `2026-09-04-panel-filter.png`)의 무늬. 구역마다 한 줄만 가로로 흐른다. */
describe("BrowseSection — 구역 제목 + 모두 보기 + 가로 격자", () => {
  it("구역 제목과 안의 것을 보여 준다", () => {
    render(
      <BrowseSection title="인기">
        <div>3D 넘기기</div>
        <div>큐브 면</div>
      </BrowseSection>,
    )
    expect(screen.getByRole("heading", { name: "인기" })).toBeInTheDocument()
    expect(screen.getByText("3D 넘기기")).toBeInTheDocument()
  })

  it("모두 보기를 누르면 알려 준다", () => {
    const onSeeAll = vi.fn()
    render(
      <BrowseSection title="기본형" onSeeAll={onSeeAll}>
        <div>큐브 면</div>
      </BrowseSection>,
    )
    fireEvent.click(screen.getByRole("button", { name: "모두 보기" }))
    expect(onSeeAll).toHaveBeenCalledTimes(1)
  })

  it("갈 곳이 없으면 모두 보기를 안 그린다", () => {
    render(
      <BrowseSection title="히트">
        <div>컷아웃 스캔</div>
      </BrowseSection>,
    )
    expect(screen.queryByRole("button", { name: "모두 보기" })).not.toBeInTheDocument()
  })

  it("세로로 쌓지 않고 가로로 흐른다", () => {
    const { container } = render(
      <BrowseSection title="인기">
        <div>3D 넘기기</div>
      </BrowseSection>,
    )
    // 이 무늬의 핵심이라 가로 격자 자리가 있는지를 지킨다. 세로로 쌓으면
    // 캡컷 무늬가 아니다 -- 지금 우리 패널이 딱 그렇게 돼 있다.
    expect(container.querySelector(".vb-browse-section__track")).not.toBeNull()
  })

  it("`▸`로 다음 것을 본다", () => {
    const { container } = render(
      <BrowseSection title="오버레이" scrollStep={200}>
        <div>윈터 스크린</div>
      </BrowseSection>,
    )
    const track = container.querySelector(".vb-browse-section__track") as HTMLDivElement
    const scrollBy = vi.fn()
    Object.defineProperty(track, "scrollBy", { configurable: true, value: scrollBy })
    fireEvent.click(screen.getByRole("button", { name: "다음 것 보기" }))
    expect(scrollBy).toHaveBeenCalledWith({ left: 200, behavior: "smooth" })
  })

  it("`scrollBy`가 없는 자리에서도 안 터진다", () => {
    // jsdom은 `scrollBy`를 안 구현한다. 여기서 터지면 이 부품을 쓰는 화면
    // 시험이 전부 같이 죽는다.
    render(
      <BrowseSection title="오버레이" scrollStep={120}>
        <div>먼지 러시</div>
      </BrowseSection>,
    )
    fireEvent.click(screen.getByRole("button", { name: "다음 것 보기" }))
    expect(screen.getByText("먼지 러시")).toBeInTheDocument()
  })

  it("`▸` 단추에 읽을 이름이 있다", () => {
    render(
      <BrowseSection title="인기">
        <div>3D 넘기기</div>
      </BrowseSection>,
    )
    const next = screen.getByRole("button", { name: "다음 것 보기" })
    next.focus()
    expect(next).toHaveFocus()
  })
})
