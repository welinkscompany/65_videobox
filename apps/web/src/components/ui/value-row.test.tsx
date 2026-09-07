import { describe, expect, it, vi } from "vitest"
import { fireEvent, render, screen } from "@testing-library/react"

import { ValueRow } from "./value-row"

/** 캡컷 속성 패널(`docs/references/capcut/2026-09-04-clip-selected-properties.png`)의
 *  `마스크 › 없음`, `색상 조정 › 기본,HSL,곡선` 무늬. */
describe("ValueRow — 이름·지금 값·`›`", () => {
  it("이름과 지금 값을 함께 보여 준다", () => {
    render(<ValueRow label="색보정" value="기본" />)
    expect(screen.getByText("색보정")).toBeInTheDocument()
    expect(screen.getByText("기본")).toBeInTheDocument()
  })

  it("하위 패널로 간다는 표시 `›`를 단다", () => {
    render(<ValueRow label="색보정" value="기본" />)
    expect(screen.getByRole("button", { name: /색보정/ })).toHaveTextContent("›")
  })

  it("값이 없으면 값 칸을 아예 안 그린다", () => {
    const { container } = render(<ValueRow label="색보정" />)
    expect(container.querySelector(".vb-value-row__value")).toBeNull()
  })

  it("누르면 하위 패널로 가는 신호를 준다", () => {
    const onClick = vi.fn()
    render(<ValueRow label="색보정" value="기본" onClick={onClick} />)
    fireEvent.click(screen.getByRole("button", { name: /색보정/ }))
    expect(onClick).toHaveBeenCalledTimes(1)
  })

  it("키보드로 닿고, 못 쓰는 행은 건너뛴다", () => {
    render(
      <>
        <ValueRow label="색보정" value="기본" disabled />
        <ValueRow label="속도" value="1x" />
      </>,
    )
    expect(screen.getByRole("button", { name: /색보정/ })).toBeDisabled()
    const usable = screen.getByRole("button", { name: /속도/ })
    usable.focus()
    expect(usable).toHaveFocus()
  })
})
