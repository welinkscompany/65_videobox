import { describe, expect, it, vi } from "vitest"
import { fireEvent, render, screen } from "@testing-library/react"

import { SearchChips } from "./search-chips"

/** 캡컷 `오디오` 패널(`docs/references/capcut/2026-09-04-panel-audio.png`)의 무늬.
 *  검색칸 아래 `background music`·`phonk`·`Happy` 칩이 한 줄로 흐른다. */
const CHIPS = [
  { id: "bgm", label: "배경 음악" },
  { id: "bright", label: "밝은" },
  { id: "calm", label: "잔잔한" },
]

describe("SearchChips — 검색 + 칩 한 줄", () => {
  it("적은 대로 밖에 알려 준다", () => {
    const onValueChange = vi.fn()
    render(<SearchChips value="" onValueChange={onValueChange} chips={CHIPS} />)
    fireEvent.change(screen.getByRole("searchbox", { name: "찾기" }), {
      target: { value: "잔잔한 배경" },
    })
    expect(onValueChange).toHaveBeenCalledWith("잔잔한 배경")
  })

  it("칩을 고르면 그 칩만 aria-selected가 참이다", () => {
    render(
      <SearchChips value="" onValueChange={() => {}} chips={CHIPS} selectedChipId="bright" />,
    )
    expect(screen.getByRole("option", { name: "밝은" })).toHaveAttribute("aria-selected", "true")
    expect(screen.getByRole("option", { name: "배경 음악" })).toHaveAttribute(
      "aria-selected",
      "false",
    )
  })

  it("칩을 누르면 어느 것인지 알려 준다", () => {
    const onChipSelect = vi.fn()
    render(
      <SearchChips value="" onValueChange={() => {}} chips={CHIPS} onChipSelect={onChipSelect} />,
    )
    fireEvent.click(screen.getByRole("option", { name: "잔잔한" }))
    expect(onChipSelect).toHaveBeenCalledWith("calm")
  })

  it("칩이 없으면 칩 줄을 아예 안 그린다", () => {
    render(<SearchChips value="" onValueChange={() => {}} />)
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument()
  })

  it("검색칸과 칩이 전부 키보드로 닿는다", () => {
    render(<SearchChips value="" onValueChange={() => {}} chips={CHIPS} />)
    const search = screen.getByRole("searchbox", { name: "찾기" })
    search.focus()
    expect(search).toHaveFocus()
    for (const chip of screen.getAllByRole("option")) {
      expect(chip.tagName).toBe("BUTTON")
      expect(chip).not.toHaveAttribute("tabindex", "-1")
    }
  })

  it("검색칸 오른쪽에 붙인 것을 그대로 보여 준다", () => {
    render(
      <SearchChips
        value=""
        onValueChange={() => {}}
        trailing={<button type="button">정렬</button>}
      />,
    )
    expect(screen.getByRole("button", { name: "정렬" })).toBeInTheDocument()
  })
})
