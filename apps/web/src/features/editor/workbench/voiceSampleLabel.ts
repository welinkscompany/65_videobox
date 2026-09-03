import type { AssetResponse } from "../../../api";

/**
 * 편집 화면의 목소리 목록에 보일 이름.
 *
 * **창작자가 붙인 이름이 먼저다.** 설정 화면(`VoiceTtsSettings`)은 붙인 이름을
 * 보여 주는데 편집 화면만 파일 이름을 보여 주고 있었다 -- 같은 목소리가 두
 * 화면에서 다른 이름으로 보이면, 채널이 여럿일 때 어느 것을 고른 건지 알 수
 * 없다(2026-09-03 리뷰에서 잡음).
 *
 * 붙인 이름이 없으면 저장 위치 끝의 파일 이름을 쓰되, 알아보기 어려운 해시만
 * 남으면 번호를 붙인 사람 말로 부른다(§10.13 창작자 언어).
 */
export function voiceSampleLabel(asset: AssetResponse, index: number): string {
  const named = String((asset.metadata?.display_name as string | undefined) ?? "").trim();
  if (named) return named;
  const tail = decodeURIComponent(asset.storage_uri.split("/").pop() ?? "").replace(/\.[a-z0-9]+$/i, "");
  const readable = tail.replace(/^[0-9a-f]{16,}-/i, "").trim();
  return readable.length > 2 ? readable : `내 목소리 ${index + 1}`;
}
