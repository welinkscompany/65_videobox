import * as React from "react"

import { cn } from "@/lib/utils"
import "./capcut-patterns.css"

/**
 * 슬라이더 + 숫자칸 + 단위 — 캡컷 속성 패널의 무늬.
 * (`docs/references/capcut/2026-09-04-properties-speed.png`)
 *
 * 캡컷에서 잰 것: `불투명도 ──●── 100 %`, `속도 ──●── 1 x`, `기간 19.9s`.
 * 라벨은 12px 설명 크기, 숫자칸은 14px 본문 크기이고 숫자칸 높이는 30이다.
 *
 * **키프레임 `◇` 단추 자리는 일부러 안 만들었다.** 임의 키프레임은 제품 범위
 * 밖이다(`CLAUDE.md` §2.1).
 */
export interface NumberFieldProps
  extends Omit<React.ComponentProps<"div">, "onChange" | "defaultValue"> {
  label: React.ReactNode
  value: number
  onValueChange: (value: number) => void
  min?: number
  max?: number
  step?: number
  /** `%`, `x`, `초` 같은 단위. 없으면 안 나온다. */
  unit?: string
  disabled?: boolean
}

export function NumberField({
  label,
  value,
  onValueChange,
  min = 0,
  max = 100,
  step = 1,
  unit,
  disabled = false,
  className,
  ...props
}: NumberFieldProps) {
  const reactId = React.useId()
  const inputId = `${reactId}-input`

  const commit = (raw: string) => {
    const parsed = Number(raw)
    // 빈칸이나 글자가 들어오면 값을 안 바꾼다 -- NaN이 그대로 흘러가면
    // 슬라이더가 통째로 안 그려진다.
    if (raw.trim() === "" || Number.isNaN(parsed)) return
    onValueChange(Math.min(max, Math.max(min, parsed)))
  }

  return (
    <div
      data-slot="number-field"
      className={cn("vb-number-field", className)}
      {...props}
    >
      <label className="vb-number-field__label" htmlFor={inputId}>
        {label}
      </label>
      <div className="vb-number-field__controls">
        <input
          type="range"
          className="vb-number-field__slider"
          aria-label={typeof label === "string" ? `${label} 슬라이더` : undefined}
          min={min}
          max={max}
          step={step}
          value={value}
          disabled={disabled}
          onChange={(event) => commit(event.target.value)}
        />
        <span className="vb-number-field__box">
          <input
            id={inputId}
            type="number"
            className="vb-number-field__input"
            min={min}
            max={max}
            step={step}
            value={value}
            disabled={disabled}
            onChange={(event) => commit(event.target.value)}
          />
          {unit ? (
            <span className="vb-number-field__unit" aria-hidden="true">
              {unit}
            </span>
          ) : null}
        </span>
      </div>
    </div>
  )
}
