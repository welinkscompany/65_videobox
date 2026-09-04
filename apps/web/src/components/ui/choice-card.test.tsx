import { describe, expect, it, vi } from "vitest"
import { fireEvent, render, screen } from "@testing-library/react"

import { ChoiceCard } from "./choice-card"

/** 캡컷 `캡션` 패널(`docs/references/capcut/2026-09-04-panel-caption.png`)의 무늬.
 *  카드 셋이 나란히 있고 누르면 **그 카드 안에서** 설정이 열린다. */
describe("ChoiceCard — 카드 안에서 펼쳐진다", () => {
  it("접혀 있을 때 안의 것이 안 보인다", () => {
    render(
      <ChoiceCard title="자동 캡션" description="동영상에서 말을 알아듣습니다.">
        <button type="button">만들기</button>
      </ChoiceCard>,
    )
    expect(screen.getByText("자동 캡션")).toBeInTheDocument()
    expect(screen.getByText("동영상에서 말을 알아듣습니다.")).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "만들기" })).not.toBeInTheDocument()
  })

  it("누르면 그 카드 안에서 열린다", () => {
    render(
      <ChoiceCard title="자동 캡션">
        <button type="button">만들기</button>
      </ChoiceCard>,
    )
    fireEvent.click(screen.getByRole("button", { name: /자동 캡션/ }))
    const opened = screen.getByRole("button", { name: "만들기" })
    // 펼쳐진 것이 카드 **밖**이 아니라 카드 안에 있어야 한다.
    expect(opened.closest("[data-slot='choice-card']")).not.toBeNull()
  })

  it("aria-expanded가 상태를 그대로 알린다", () => {
    render(<ChoiceCard title="수동 캡션">내용</ChoiceCard>)
    const trigger = screen.getByRole("button", { name: /수동 캡션/ })
    expect(trigger).toHaveAttribute("aria-expanded", "false")
    fireEvent.click(trigger)
    expect(trigger).toHaveAttribute("aria-expanded", "true")
    fireEvent.click(trigger)
    expect(trigger).toHaveAttribute("aria-expanded", "false")
  })

  it("펼친 자리를 aria-controls로 가리킨다", () => {
    render(
      <ChoiceCard title="캡션 파일 올리기" defaultExpanded>
        내용
      </ChoiceCard>,
    )
    const trigger = screen.getByRole("button", { name: /캡션 파일 올리기/ })
    const bodyId = trigger.getAttribute("aria-controls")
    expect(bodyId).toBeTruthy()
    expect(document.getElementById(bodyId as string)).toHaveTextContent("내용")
  })

  it("밖에서 열림 상태를 정하면 그 말을 듣는다", () => {
    const onExpandedChange = vi.fn()
    render(
      <ChoiceCard title="자동 캡션" expanded={false} onExpandedChange={onExpandedChange}>
        <button type="button">만들기</button>
      </ChoiceCard>,
    )
    fireEvent.click(screen.getByRole("button", { name: /자동 캡션/ }))
    expect(onExpandedChange).toHaveBeenCalledWith(true)
    // 밖에서 false로 못박아 뒀으니 스스로 열지 않는다.
    expect(screen.queryByRole("button", { name: "만들기" })).not.toBeInTheDocument()
  })

  it("키보드로 카드에 닿는다", () => {
    render(<ChoiceCard title="자동 캡션">내용</ChoiceCard>)
    const trigger = screen.getByRole("button", { name: /자동 캡션/ })
    // 진짜 `<button>`이라야 탭 순서에 저절로 들어간다.
    expect(trigger.tagName).toBe("BUTTON")
    expect(trigger).not.toHaveAttribute("tabindex", "-1")
    trigger.focus()
    expect(trigger).toHaveFocus()
  })
})
