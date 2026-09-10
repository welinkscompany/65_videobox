/**
 * 유진이 방금 무엇을 했는지 한 줄로.
 *
 * 말로 시킨 편집은 창작자가 `적용`을 누르지 않고 바로 반영된다(2026-09-01 결정).
 * **그래서 이 줄이 무엇이 바뀌었는지 알려 주는 유일한 자리다.** 모르는 명령이
 * 오면 `편집 항목을 바꿔요.`로 떨어지는데, 그건 아무것도 말해 주지 않는다 --
 * 명령을 늘릴 때마다 여기를 같이 늘려야 하는 이유다.
 *
 * 화면 안에 있던 것을 밖으로 꺼냈다. 편집기 화면 모듈은 무거워서 이 한 줄을
 * 시험하려면 화면을 통째로 띄워야 했고, 그래서 명령 열다섯 중 다섯이 아무
 * 시험 없이 기본 문구로 떨어지고 있었다.
 */

import type { YujinEditingProposal } from "../../../api";
import { photoMotionLabel } from "../inspector/photoMotions";
import { sceneFilterLabel } from "../inspector/sceneFilters";
import { sceneTransitionLabel } from "../inspector/sceneTransitions";
import {
  OVERLAY_HORIZONTAL_LABELS,
  OVERLAY_SIZE_LABELS,
  OVERLAY_VERTICAL_LABELS,
  SHAPE_OVERLAY_MOTION_LABELS,
} from "../inspector/inspectorRegistry";

type YujinEditingOperation = YujinEditingProposal["diff"]["operations"][number];

function label(table: Readonly<Record<string, string>>, value: unknown): string | null {
  return typeof value === "string" ? table[value] ?? null : null;
}

/** 사진 오버레이에서 고른 것만 이어 붙인다. 안 고른 것은 값이 없다. */
function imageOverlayDetail(operation: YujinEditingOperation): string {
  const parts = [
    label(OVERLAY_VERTICAL_LABELS, (operation as { vertical?: unknown }).vertical),
    label(OVERLAY_HORIZONTAL_LABELS, (operation as { horizontal?: unknown }).horizontal),
    label(OVERLAY_SIZE_LABELS, (operation as { size?: unknown }).size),
    label(SHAPE_OVERLAY_MOTION_LABELS, (operation as { motion?: unknown }).motion),
  ].filter((part): part is string => Boolean(part));
  return parts.length ? ` (${parts.join(" · ")})` : "";
}

export function yujinEditingOperationSummary(operation: YujinEditingOperation): string {
  if (operation.intent === "set_scene_speed" && typeof operation.rate === "number") return `${operation.rate}배로 속도를 바꿔요.`;
  if (operation.intent === "set_cut_action") return "장면 포함 여부를 바꿔요.";
  if (operation.intent === "set_caption_text") return "캡션을 고쳐요.";
  // 넣는 것과 빼는 것을 한 줄로 뭉치지 않는다(2026-09-01 실사용 확인:
  // "승인된 미디어 배치를 바꿔요"만 보고는 넣었는지 뺐는지 알 수 없었다).
  if (operation.intent === "apply_media" || operation.intent === "remove_media") {
    const what = operation.media_type === "bgm" ? "배경 음악" : operation.media_type === "sfx" ? "효과음" : "영상";
    return operation.intent === "apply_media" ? `골라 둔 ${what}을 넣어요.` : `넣어 둔 ${what}을 빼요.`;
  }
  if (operation.intent === "set_segment_bounds") return "장면 길이를 조정해요.";
  // 색감·전환·자리는 코드가 아니라 화면에 쓰는 이름으로 적는다(§10.13) --
  // 창작자에게 `vintage`나 `wipeleft`는 아무 뜻이 없다.
  if (operation.intent === "set_scene_look") {
    const looked = typeof operation.look === "string" ? sceneFilterLabel(operation.look) : null;
    return looked ? `색감을 ${looked} 바꿔요.` : "색감을 바꿔요.";
  }
  if (operation.intent === "set_photo_motion") {
    const moved = typeof operation.motion === "string" ? photoMotionLabel(operation.motion) : null;
    return moved ? `사진을 ${moved}로 바꿔요.` : "사진 움직임을 바꿔요.";
  }
  if (operation.intent === "set_caption_font") {
    return typeof operation.family === "string" ? `자막 글꼴을 ${operation.family}(으)로 바꿔요.` : "자막 글꼴을 바꿔요.";
  }
  if (operation.intent === "reorder_segments") return "장면 순서를 바꿔요.";
  if (operation.intent === "set_scene_transition") {
    const transition = (operation as { transition?: { type?: unknown } }).transition;
    const named = sceneTransitionLabel(typeof transition?.type === "string" ? transition.type : null);
    return `장면 넘기기를 ${named}(으)로 바꿔요.`;
  }
  // 사진인지 영상인지는 operation에 안 실린다(asset_id뿐) -- 그래서
  // "사진을"/"영상을"로 못 박지 않고 명사를 뺀다. 잘못 단정하면 바로 아래
  // 타임라인 바("오버레이 1 · 영상")와 다른 말을 하게 된다(최종 리뷰 발견).
  if (operation.intent === "set_image_overlay") return `골라 둔 것을 화면 위에 얹어요${imageOverlayDetail(operation)}.`;
  if (operation.intent === "remove_image_overlay") return "화면 위에 얹은 것을 빼요.";
  if (operation.intent === "set_picture_cleanup") return "화면을 다듬어요.";
  if (operation.intent === "set_sound_cleanup") return "소리를 다듬어요.";
  if (operation.intent === "set_scene_transform") return "화면 맞춤을 바꿔요.";
  return "편집 항목을 바꿔요.";
}
