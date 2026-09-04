import * as React from "react"

import { cn } from "@/lib/utils"
import "./capcut-patterns.css"

/**
 * 아코디언 카드 — 캡컷 `캡션` 패널의 무늬.
 * (`docs/references/capcut/2026-09-04-panel-caption.png`)
 *
 * 캡컷에서 잰 것: 카드 폭은 패널 전체, 아이콘·제목·한 줄 설명이 가운데
 * 정렬돼 있고, 누르면 **그 카드 안에서** 라벨+드롭다운+`생성` 단추가 열린다.
 * 다른 패널로 넘어가지 않는 것이 이 무늬의 핵심이다.
 *
 * 열림 상태는 넘겨줘도 되고(`expanded`) 안 넘겨주면 카드가 스스로 기억한다.
 */
export interface ChoiceCardProps extends Omit<React.ComponentProps<"section">, "onSelect" | "title"> {
  /** 카드 제목. 캡컷 기준 14px 본문 크기다. */
  title: React.ReactNode
  /** 제목 아래 한 줄 설명. 12px. */
  description?: React.ReactNode
  /** 제목 위 아이콘. */
  icon?: React.ReactNode
  /** 제목 옆 작은 표시(캡컷의 `무료` 배지 자리). */
  badge?: React.ReactNode
  /** 열림 상태를 밖에서 정할 때 쓴다. 안 주면 카드가 스스로 기억한다. */
  expanded?: boolean
  /** 안 넘겨줄 때의 첫 상태. */
  defaultExpanded?: boolean
  onExpandedChange?: (expanded: boolean) => void
  /** 펼쳤을 때 카드 안에 나오는 것. */
  children?: React.ReactNode
}

export function ChoiceCard({
  title,
  description,
  icon,
  badge,
  expanded,
  defaultExpanded = false,
  onExpandedChange,
  children,
  className,
  ...props
}: ChoiceCardProps) {
  const reactId = React.useId()
  const triggerId = `${reactId}-trigger`
  const bodyId = `${reactId}-body`

  const [uncontrolled, setUncontrolled] = React.useState(defaultExpanded)
  const isControlled = expanded !== undefined
  const isExpanded = isControlled ? expanded : uncontrolled

  const toggle = () => {
    const next = !isExpanded
    if (!isControlled) setUncontrolled(next)
    onExpandedChange?.(next)
  }

  return (
    <section
      data-slot="choice-card"
      data-expanded={isExpanded}
      className={cn("vb-choice-card", className)}
      {...props}
    >
      <button
        type="button"
        id={triggerId}
        className="vb-choice-card__trigger"
        aria-expanded={isExpanded}
        aria-controls={bodyId}
        onClick={toggle}
      >
        {icon ? (
          <span className="vb-choice-card__icon" aria-hidden="true">
            {icon}
          </span>
        ) : null}
        <span className="vb-choice-card__title">
          {title}
          {badge ? <span className="vb-choice-card__badge">{badge}</span> : null}
        </span>
        {description ? (
          <span className="vb-choice-card__description">{description}</span>
        ) : null}
      </button>
      <div
        id={bodyId}
        role="region"
        aria-labelledby={triggerId}
        className="vb-choice-card__body"
        hidden={!isExpanded}
      >
        {children}
      </div>
    </section>
  )
}
