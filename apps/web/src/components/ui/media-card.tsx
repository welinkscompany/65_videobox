import * as React from "react"

import { cn } from "@/lib/utils"
import "./capcut-patterns.css"

/**
 * 버튼 없는 카드 — 캡컷 `최근 프로젝트`의 무늬.
 * (`docs/references/capcut/2026-09-04-recent-projects.png`)
 *
 * 캡컷에서 잰 것: 썸네일(16:9) 왼쪽 아래에 길이 배지가 **겹쳐** 있고, 그 아래
 * 제목 14px, 메타 12px 한 줄(`welinkscompany · 10분 전`)이 전부다.
 * **카드 안에 단추가 하나도 없다** — 카드 자체를 누르면 열린다.
 */
export interface MediaCardProps
  extends Omit<React.ComponentProps<"button">, "title"> {
  title: React.ReactNode
  /** 제목 아래 한 줄. 만든 사람·시각 같은 것. */
  meta?: React.ReactNode
  thumbnailUrl?: string
  /** 썸네일 대신 넣을 것(아직 그림이 없을 때의 자리). */
  thumbnailFallback?: React.ReactNode
  /** 썸네일 위에 겹치는 길이 배지. `00:20` 같은 것. */
  duration?: React.ReactNode
}

export function MediaCard({
  title,
  meta,
  thumbnailUrl,
  thumbnailFallback,
  duration,
  className,
  ...props
}: MediaCardProps) {
  return (
    <button
      type="button"
      data-slot="media-card"
      className={cn("vb-media-card", className)}
      {...props}
    >
      <span className="vb-media-card__thumb">
        {thumbnailUrl ? (
          <img className="vb-media-card__image" src={thumbnailUrl} alt="" />
        ) : (
          thumbnailFallback
        )}
        {duration ? (
          <span className="vb-media-card__duration">{duration}</span>
        ) : null}
      </span>
      <span className="vb-media-card__title">{title}</span>
      {meta ? <span className="vb-media-card__meta">{meta}</span> : null}
    </button>
  )
}
