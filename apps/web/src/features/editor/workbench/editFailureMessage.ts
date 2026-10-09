import { ApiRequestError } from "../../../api";

/**
 * 저장이 거절된 이유를 창작자 말로. 모르는 이유는 `null`(그때만 옛 일반 문장).
 *
 * 서버 사유 코드는 화면에 그대로 내지 않는다(§10.13). "최신 내용을 확인한 뒤 다시 시도"는
 * 정말 다른 곳이 먼저 저장한 충돌(409)에서만 맞는 안내라 거기에만 쓴다 -- 다시 눌러도
 * 안 되는 거절에 그 문장을 붙이면 눌러 보다 포기한다.
 */
export function editFailureMessage(error: unknown): string | null {
  if (!(error instanceof ApiRequestError)) return null;
  if (error.status === 409) return "다른 변경이 먼저 저장됐어요. 최신 내용을 확인한 뒤 다시 시도해 주세요.";
  const detail = error.detail ?? "";
  if (!detail) return null;
  if (detail.includes("timeline_placement_out_of_range")) return "영상 길이 밖으로는 옮길 수 없어요.";
  if (detail.includes("timeline_placement_frame_span_invalid")) return "한 프레임보다 짧게는 자를 수 없어요.";
  if (detail.includes("timeline_placement_duplicate")) {
    return "같은 조각이 두 번 들어 있어서 저장할 수 없어요. 되돌리기를 누른 뒤 다시 해 주세요.";
  }
  if (detail.includes("timeline_placement_")) {
    return "이 자리는 지금 저장할 수 없어요. 되돌리기를 누른 뒤 다시 해 주세요.";
  }
  if (detail.includes("segment_restore_overlaps_neighbour")) {
    return "옆 장면이 이 자리를 쓰고 있어요. 옆 장면을 줄이거나 되돌리기를 눌러 주세요.";
  }
  if (detail.includes("segment_split_ripple_removed")) {
    return "당겨서 뺀 장면은 나눌 수 없어요. 먼저 되살린 뒤에 나눠 주세요.";
  }
  if (detail.includes("segment_ripple_playback_rate_below_minimum_duration")) {
    return "이 배속이면 장면이 너무 짧아져요. 배속을 낮춰 주세요.";
  }
  if (detail.includes("Split must leave at least")) return "나눈 양쪽이 각각 0.2초는 남아야 해요.";
  if (detail.includes("Segment duration must be at least")) return "장면은 0.2초보다 짧게 만들 수 없어요.";
  if (detail.includes("segment_source_expansion_outside_slice") || detail.includes("segment_media_expansion_outside_window")) {
    return "원본 영상 밖으로는 늘릴 수 없어요.";
  }
  return null;
}
