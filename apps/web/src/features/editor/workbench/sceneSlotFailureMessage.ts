import { ApiRequestError } from "../../../api";

/**
 * 뺀 장면을 되살리려는데 옆 장면이 그 자리를 쓰고 있을 때(`segment_restore_overlaps_neighbour`)
 * 창작자가 **무엇을 하면 되는지** 말해 준다. 아니면 `null`.
 *
 * 서버 사유 코드는 화면에 그대로 내보내지 않는다(§10.13). 다시 눌러도 안 되는 경우라
 * "저장하지 못했어요"만 뜨면 눌러 보다 포기한다.
 */
export function sceneSlotFailureMessage(error: unknown): string | null {
  const detail = typeof error === "string" ? error : error instanceof ApiRequestError ? (error.detail ?? "") : "";
  if (detail.includes("segment_restore_overlaps_neighbour")) {
    return "옆 장면이 이 자리를 쓰고 있어요. 옆 장면을 줄이거나 되돌리기를 눌러 주세요.";
  }
  return null;
}
