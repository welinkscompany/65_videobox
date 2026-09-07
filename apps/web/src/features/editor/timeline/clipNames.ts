import { SHAPE_OVERLAY_LABELS } from "../inspector/inspectorRegistry";
import type { ShapeOverlayShape } from "../../../api";

/** 타임라인 막대에 이름을 짓는 자리.
 *
 *  예전에는 `자막 1`·`오버레이 2`처럼 **줄 이름과 번호**만 적었다. 편집본에 자막이
 *  다섯이면 다섯 개가 똑같이 생겼고, 어느 막대가 무슨 자막인지 알려면 하나씩
 *  눌러 봐야 했다. 캡컷은 막대에 그 자막 글자를 그대로 보여 준다.
 *
 *  **내용은 이미 클립이 들고 있었다** -- 자막의 `text`, 설명 카드의 `title`,
 *  도형의 `shape`. 화면이 그걸 한 번도 안 읽었을 뿐이다.
 */

/** 막대 위 한 줄에 들어갈 만큼. 길면 썸네일과 파형을 덮는다. */
const VISIBLE_LIMIT = 16

export type ClipContentInput = Readonly<{
  captionText?: string | null
  overlayType?: string | null
  overlayPayload?: Readonly<Record<string, unknown>> | null
}>

function firstWords(value: string): string {
  // 대본을 번호 목록으로 붙여 넣으면 자막이 `1. 걷는 리듬…`이 된다. 목록 번호를
  // 떼지 않으면 막대에 `1`만 남는다 -- `sceneNames`가 같은 이유로 같은 일을 한다.
  const cleaned = value.replace(/^\s*\d+[.)]\s*/, "").trim()
  if (!cleaned) return ""
  const sentence = cleaned.split(/(?<=[.!?])\s/)[0] ?? cleaned
  const trimmed = sentence.trim()
  return trimmed.length > VISIBLE_LIMIT ? `${trimmed.slice(0, VISIBLE_LIMIT)}…` : trimmed
}

function text(payload: Readonly<Record<string, unknown>> | null | undefined, key: string): string {
  const value = payload?.[key]
  return typeof value === "string" ? value.trim() : ""
}

/** 이 클립이 무엇인지 사람이 아는 말로. 알 수 없으면 `null` -- 지어내지 않는다. */
export function clipContentLabel(input: ClipContentInput): string | null {
  const caption = (input.captionText ?? "").trim()
  if (caption) return firstWords(caption) || null

  const kind = (input.overlayType ?? "").trim()
  if (!kind) return null
  if (kind === "shape_overlay") {
    const shape = text(input.overlayPayload, "shape") as ShapeOverlayShape
    return SHAPE_OVERLAY_LABELS[shape] ?? "도형"
  }
  if (kind === "explanation_card") {
    return firstWords(text(input.overlayPayload, "title") || text(input.overlayPayload, "text")) || "설명 카드"
  }
  if (kind === "table_overlay") {
    return firstWords(text(input.overlayPayload, "text")) || "표"
  }
  if (kind === "image_overlay") {
    return firstWords(text(input.overlayPayload, "text")) || "그림"
  }
  return null
}
