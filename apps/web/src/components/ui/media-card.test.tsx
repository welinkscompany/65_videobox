import { describe, expect, it, vi } from "vitest"
import { fireEvent, render, screen } from "@testing-library/react"

import { MediaCard } from "./media-card"

/** 캡컷 `최근 프로젝트`(`docs/references/capcut/2026-09-04-recent-projects.png`)의
 *  무늬. 썸네일 + 겹친 길이 배지 + 제목 + 메타, 그리고 **단추가 없다**. */
describe("MediaCard — 버튼 없는 카드", () => {
  it("제목과 메타와 길이를 보여 준다", () => {
    render(<MediaCard title="202609041310" meta="루이스 · 10분 전" duration="00:20" />)
    expect(screen.getByText("202609041310")).toBeInTheDocument()
    expect(screen.getByText("루이스 · 10분 전")).toBeInTheDocument()
    expect(screen.getByText("00:20")).toBeInTheDocument()
  })

  it("길이 배지는 썸네일 위에 겹친다", () => {
    const { container } = render(<MediaCard title="내 영상" duration="00:20" />)
    const badge = container.querySelector(".vb-media-card__duration")
    expect(badge?.closest(".vb-media-card__thumb")).not.toBeNull()
  })

  it("카드 자체가 눌리는 자리다", () => {
    const onClick = vi.fn()
    render(<MediaCard title="내 영상" onClick={onClick} />)
    fireEvent.click(screen.getByRole("button", { name: /내 영상/ }))
    expect(onClick).toHaveBeenCalledTimes(1)
  })

  it("카드 안에 따로 누를 단추가 없다", () => {
    // 캡컷 카드에는 단추가 0개다. 우리 첫 화면은 카드마다 단추를 달아 놔서
    // 누를 것이 22개가 됐다(계획서 §8-3). 그 회귀를 여기서 막는다.
    const { container } = render(
      <MediaCard title="내 영상" meta="루이스 · 10분 전" duration="00:20" />,
    )
    expect(container.querySelectorAll("button")).toHaveLength(1)
  })

  it("썸네일 그림은 이름 읽기에서 빠진다", () => {
    // 카드 자체가 단추라 그림까지 읽히면 이름이 두 벌이 된다.
    render(<MediaCard title="내 영상" thumbnailUrl="/thumb.jpg" />)
    expect(screen.queryByRole("img")).toBeNull()
  })

  it("그림이 없으면 대신 넣은 것을 보여 준다", () => {
    render(<MediaCard title="내 영상" thumbnailFallback={<span>아직 미리보기가 없어요</span>} />)
    expect(screen.getByText("아직 미리보기가 없어요")).toBeInTheDocument()
  })

  it("키보드로 카드에 닿는다", () => {
    render(<MediaCard title="내 영상" />)
    const card = screen.getByRole("button", { name: /내 영상/ })
    expect(card.tagName).toBe("BUTTON")
    card.focus()
    expect(card).toHaveFocus()
  })
})
