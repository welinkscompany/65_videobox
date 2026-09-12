/**
 * 숏폼 **첫 화면 제목 띠**를 화면에서 읽고 끄고 켜는 한 자리.
 *
 * 제목은 유진이 숏폼을 고를 때 같이 짠다(`short_form_scene_pick`의 짜기 호출
 * 하나). 화면이 하는 일은 **지금 걸린 것을 보여 주고 끄고 켜는 것**이다 --
 * 목록과 "지금 걸린 값"은 한 쌍이다(owner 지시 2026-09-06). 끌 때 문구를 지우지
 * 않는 이유가 그것이다: 지우면 다시 켤 때 되돌릴 것이 없다.
 *
 * 계산을 컴포넌트 안에 두지 않는 이유는 이 저장소가 여러 번 겪은 일이다 --
 * 같은 값 읽기가 두 자리에 살면 한쪽만 고쳐진다.
 */

import type { OutputVariant, OutputVariantPatch } from "../../../api";

export type ShortsTitleBand = Readonly<{
  lines: readonly string[];
  highlight: string | null;
  /** 문구는 있는데 띠만 껐다. */
  hidden: boolean;
}>;

/** 이 숏폼에 걸린 제목. 아직 없으면 `null` -- 지어내지 않는다. */
export function shortsTitleBand(variant: OutputVariant): ShortsTitleBand | null {
  const layout = variant.overrides?.layout;
  if (!layout || typeof layout !== "object") return null;
  const raw = (layout as { title_lines?: unknown }).title_lines;
  const lines = Array.isArray(raw)
    ? raw.map((line) => String(line).trim()).filter((line) => line.length > 0)
    : [];
  if (!lines.length) return null;
  const rawHighlight = (layout as { highlight?: unknown }).highlight;
  return {
    lines,
    highlight: typeof rawHighlight === "string" && rawHighlight.trim() ? rawHighlight.trim() : null,
    hidden: Boolean((layout as { hidden?: unknown }).hidden),
  };
}

/** 제목 띠를 끄거나 켜는 patch. **문구는 그대로 싣는다.**
 *
 *  `overrides`는 필드 통째로 갈아 끼우므로(`_merged_overrides`) 문구를 안 실으면
 *  끄는 순간 제목이 사라지고, 그러면 켜기가 빈 띠를 켠다. */
export function shortsTitleBandPatch(
  band: ShortsTitleBand,
  options: { readonly hidden: boolean },
): OutputVariantPatch {
  return {
    overrides: {
      layout: {
        title_lines: [...band.lines],
        highlight: band.highlight,
        hidden: options.hidden,
      },
    },
  };
}
