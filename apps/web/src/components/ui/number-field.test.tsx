import { describe, expect, it, vi } from "vitest"
import { fireEvent, render, screen } from "@testing-library/react"

import { NumberField } from "./number-field"

/** 캡컷 속성 패널(`docs/references/capcut/2026-09-04-properties-speed.png`)의
 *  `불투명도 ──●── 100 %`, `속도 ──●── 1 x` 무늬. */
describe("NumberField — 슬라이더 + 숫자칸 + 단위", () => {
  it("슬라이더와 숫자칸이 같은 값을 본다", () => {
    render(<NumberField label="불투명도" value={80} onValueChange={() => {}} unit="%" />)
    expect(screen.getByRole("slider")).toHaveValue("80")
    expect(screen.getByRole("spinbutton", { name: "불투명도" })).toHaveValue(80)
    expect(screen.getByText("%")).toBeInTheDocument()
  })

  it("슬라이더를 옮기면 값을 알려 준다", () => {
    const onValueChange = vi.fn()
    render(<NumberField label="불투명도" value={80} onValueChange={onValueChange} />)
    fireEvent.change(screen.getByRole("slider"), { target: { value: "40" } })
    expect(onValueChange).toHaveBeenCalledWith(40)
  })

  it("숫자칸에 적어도 값을 알려 준다", () => {
    const onValueChange = vi.fn()
    render(
      <NumberField label="속도" value={1} onValueChange={onValueChange} min={0} max={10} unit="x" />,
    )
    fireEvent.change(screen.getByRole("spinbutton", { name: "속도" }), { target: { value: "3" } })
    expect(onValueChange).toHaveBeenCalledWith(3)
  })

  it("범위를 넘겨 적으면 범위 안으로 붙잡는다", () => {
    const onValueChange = vi.fn()
    render(
      <NumberField label="불투명도" value={80} onValueChange={onValueChange} min={0} max={100} />,
    )
    const box = screen.getByRole("spinbutton", { name: "불투명도" })
    fireEvent.change(box, { target: { value: "250" } })
    expect(onValueChange).toHaveBeenCalledWith(100)
    fireEvent.change(box, { target: { value: "-30" } })
    expect(onValueChange).toHaveBeenCalledWith(0)
  })

  it("빈칸이 들어와도 값을 망가뜨리지 않는다", () => {
    const onValueChange = vi.fn()
    render(<NumberField label="불투명도" value={80} onValueChange={onValueChange} />)
    fireEvent.change(screen.getByRole("spinbutton", { name: "불투명도" }), {
      target: { value: "" },
    })
    expect(onValueChange).not.toHaveBeenCalled()
  })

  it("키프레임 자리는 만들지 않는다", () => {
    // 임의 키프레임은 제품 범위 밖이다(`CLAUDE.md` §2.1). 캡컷 화면에는
    // 숫자칸 오른쪽에 `◇`가 있지만 우리는 일부러 안 만든다.
    const { container } = render(
      <NumberField label="불투명도" value={80} onValueChange={() => {}} unit="%" />,
    )
    expect(container.textContent).not.toContain("◇")
    expect(container.querySelectorAll("button")).toHaveLength(0)
  })

  it("단위를 안 주면 단위 칸이 안 나온다", () => {
    const { container } = render(
      <NumberField label="기간" value={19.9} onValueChange={() => {}} />,
    )
    expect(container.querySelector(".vb-number-field__unit")).toBeNull()
  })

  it("키보드로 슬라이더와 숫자칸에 닿는다", () => {
    render(<NumberField label="불투명도" value={80} onValueChange={() => {}} unit="%" />)
    const slider = screen.getByRole("slider")
    slider.focus()
    expect(slider).toHaveFocus()
    const box = screen.getByRole("spinbutton", { name: "불투명도" })
    box.focus()
    expect(box).toHaveFocus()
  })
})
