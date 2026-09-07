import { ApiRequestError } from "../../../api";

/**
 * 더빙이 실패했을 때 **무엇을 하면 되는지**를 창작자 말로 돌려준다.
 * 더빙 실패가 아니면 `null`.
 *
 * 왜 따로 두나: 편집 실패는 전부 "변경 내용을 저장하지 못했어요"로 묶여 있었다.
 * 다른 편집에는 그게 맞다 -- 다시 누르면 되니까. 그런데 더빙이 실패하는 두 가지
 * 흔한 이유는 **다시 눌러도 안 된다.** 목소리 서비스가 안 떠 있거나, 읽힐
 * 목소리가 없거나다. 둘 다 창작자가 할 일이 따로 있는데 그 말을 안 해 주면
 * 눌러 보다 포기한다.
 *
 * 서버가 준 사유를 그대로 화면에 쓰지 않는다 -- 그건 영어 기술 문구다(§10.13).
 * 여기서 **무엇을 하면 되는지**로 옮긴다.
 */
export function voiceFailureMessage(error: unknown): string | null {
  // **문자열도 받는다.** 더빙이 비동기가 된 뒤로 실패 사유는 `ApiRequestError`가
  // 아니라 작업 상태의 `error_detail` 문자열로 온다. 문자열을 안 받으면 그 사유가
  // 여기를 안 거치고 **영어 원문 그대로 화면에 나간다**(2026-09-03 리뷰에서 잡음).
  const detail = typeof error === "string" ? error : error instanceof ApiRequestError ? (error.detail ?? "") : "";
  if (!detail) return null;
  if (detail.includes("Voice bridge is not answering")) {
    return "목소리를 만드는 프로그램이 꺼져 있어요. 이 컴퓨터에서 목소리 프로그램을 켠 뒤 다시 시도해 주세요.";
  }
  if (detail.includes("Voice sample not found") || detail.includes("Voice cloning needs")) {
    return "읽어 줄 목소리가 아직 없어요. 자료실의 내 목소리에서 유튜브 영상 주소로 목소리를 먼저 가져와 주세요.";
  }
  if (detail.includes("TTS synthesis is not configured")) {
    return "목소리 만들기가 꺼져 있어요. 설정에서 켠 뒤 다시 시도해 주세요.";
  }
  return null;
}
