import * as React from "react"

import { cn } from "@/lib/utils"
import "./capcut-patterns.css"

/**
 * 구역 제목 + `모두 보기` + 가로 스크롤 격자 — 캡컷 `전환`·`필터`·`오디오`
 * 패널이 전부 이 무늬다.
 * (`docs/references/capcut/2026-09-04-panel-transition.png`,
 *  `2026-09-04-panel-filter.png`)
 *
 * 캡컷에서 잰 것: `인기`/`기본형`/`히트`/`오버레이`처럼 구역 제목(14px)이
 * 왼쪽, `모두 보기`(12px)가 오른쪽에 있고, 그 아래 한 줄만 가로로 흐른다.
 * **세로로 쌓지 않는 것이 핵심이다** — 더 보려면 오른쪽 `▸`를 누른다.
 */
export interface BrowseSectionProps
  extends Omit<React.ComponentProps<"section">, "title"> {
  /** 구역 제목. */
  title: React.ReactNode
  /** `모두 보기`를 눌렀을 때. 안 주면 그 글자가 안 나온다. */
  onSeeAll?: () => void
  seeAllLabel?: string
  /** 오른쪽 `▸` 한 번에 넘길 픽셀. */
  scrollStep?: number
  /** 격자에 들어갈 것들. */
  children?: React.ReactNode
}

export function BrowseSection({
  title,
  onSeeAll,
  seeAllLabel = "모두 보기",
  scrollStep = 240,
  children,
  className,
  ...props
}: BrowseSectionProps) {
  const trackRef = React.useRef<HTMLDivElement | null>(null)

  const scrollNext = () => {
    const track = trackRef.current
    if (!track) return
    // jsdom은 `scrollBy`를 안 구현한다. 시험에서 이 단추를 눌러도 터지지
    // 않도록 있는지 보고 부른다.
    if (typeof track.scrollBy === "function") {
      track.scrollBy({ left: scrollStep, behavior: "smooth" })
    } else {
      track.scrollLeft += scrollStep
    }
  }

  return (
    <section
      data-slot="browse-section"
      className={cn("vb-browse-section", className)}
      {...props}
    >
      <div className="vb-browse-section__header">
        <h3 className="vb-browse-section__title">{title}</h3>
        {onSeeAll ? (
          <button
            type="button"
            className="vb-browse-section__see-all"
            onClick={onSeeAll}
          >
            {seeAllLabel}
          </button>
        ) : null}
      </div>
      <div className="vb-browse-section__viewport">
        <div ref={trackRef} className="vb-browse-section__track">
          {children}
        </div>
        <button
          type="button"
          className="vb-browse-section__next"
          aria-label="다음 것 보기"
          onClick={scrollNext}
        >
          <span aria-hidden="true">{"▸"}</span>
        </button>
      </div>
    </section>
  )
}
