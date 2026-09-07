import * as React from "react"

import { cn } from "@/lib/utils"
import "./capcut-patterns.css"

/**
 * 값 보이는 행 + `›` — 캡컷 속성 패널의 무늬.
 * (`docs/references/capcut/2026-09-04-clip-selected-properties.png`)
 *
 * 캡컷에서 잰 것: `마스크 › 없음`, `색상 조정 › 기본,HSL,곡선`처럼
 * 왼쪽에 이름, 오른쪽에 지금 값, 맨 끝에 `›`가 있고 누르면 하위 패널로 간다.
 * 값은 12px 설명 크기, 이름은 14px 본문 크기다.
 */
export interface ValueRowProps
  extends Omit<React.ComponentProps<"button">, "value"> {
  /** 왼쪽 이름. */
  label: React.ReactNode
  /** 오른쪽에 보이는 지금 값. */
  value?: React.ReactNode
  /** 이름 앞 아이콘(캡컷의 `없음` 앞 표시 자리). */
  icon?: React.ReactNode
}

export function ValueRow({
  label,
  value,
  icon,
  className,
  ...props
}: ValueRowProps) {
  return (
    <button
      type="button"
      data-slot="value-row"
      className={cn("vb-value-row", className)}
      {...props}
    >
      {icon ? (
        <span className="vb-value-row__icon" aria-hidden="true">
          {icon}
        </span>
      ) : null}
      <span className="vb-value-row__label">{label}</span>
      {value !== undefined && value !== null && value !== "" ? (
        <span className="vb-value-row__value">{value}</span>
      ) : null}
      <span className="vb-value-row__chevron" aria-hidden="true">
        {"›"}
      </span>
    </button>
  )
}
