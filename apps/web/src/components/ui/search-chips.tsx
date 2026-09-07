import * as React from "react"

import { cn } from "@/lib/utils"
import "./capcut-patterns.css"

/**
 * 검색 + 칩 한 줄 — 캡컷 `오디오`·`편집효과` 패널의 무늬.
 * (`docs/references/capcut/2026-09-04-panel-audio.png`)
 *
 * 캡컷에서 잰 것: 검색 입력 높이 34, 그 아래 알약 칩이 한 줄로 가로로 흐른다
 * (칩 높이 20~32, 여기서는 28). 칩은 서로 배타적인 고르기라 `aria-selected`로
 * 지금 고른 것을 알린다.
 */
export interface SearchChip {
  id: string
  label: string
}

export interface SearchChipsProps extends Omit<React.ComponentProps<"div">, "onChange"> {
  /** 검색칸에 지금 적힌 것. */
  value: string
  onValueChange: (value: string) => void
  placeholder?: string
  /** 검색칸에 붙일 이름. 화면에 라벨을 안 두므로 필요하다. */
  searchLabel?: string
  chips?: SearchChip[]
  /** 지금 고른 칩. 아무것도 안 골랐으면 안 넘기면 된다. */
  selectedChipId?: string | null
  onChipSelect?: (id: string) => void
  /** 검색칸 오른쪽에 붙일 것(캡컷의 정렬 단추 자리). */
  trailing?: React.ReactNode
}

export function SearchChips({
  value,
  onValueChange,
  placeholder = "찾을 말을 적으세요",
  searchLabel = "찾기",
  chips = [],
  selectedChipId = null,
  onChipSelect,
  trailing,
  className,
  ...props
}: SearchChipsProps) {
  return (
    <div
      data-slot="search-chips"
      className={cn("vb-search-chips", className)}
      {...props}
    >
      <div className="vb-search-chips__search">
        <input
          type="search"
          className="vb-search-chips__input"
          aria-label={searchLabel}
          placeholder={placeholder}
          value={value}
          onChange={(event) => onValueChange(event.target.value)}
        />
        {trailing}
      </div>
      {chips.length > 0 ? (
        <div
          role="listbox"
          aria-orientation="horizontal"
          aria-label={`${searchLabel} 갈래`}
          className="vb-search-chips__chips"
        >
          {chips.map((chip) => (
            <button
              key={chip.id}
              type="button"
              role="option"
              aria-selected={selectedChipId === chip.id}
              className="vb-search-chips__chip"
              onClick={() => onChipSelect?.(chip.id)}
            >
              {chip.label}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  )
}
