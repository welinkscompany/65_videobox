/** 붙여 넣은 대본에서 확정 화면에 채워 둘 **요약 한 줄**.
 *
 * 2026-08-19 owner: 대본을 이미 가진 사람에게 "요약을 한 줄 쓰세요"를 다시
 * 묻는 것은 군더더기다. 확정 자체는 사람이 누르는 게이트라 그대로 두되,
 * 빈칸 때문에 막히지는 않게 한다(요약이 없으면 확정이 400으로 거절된다).
 *
 * **지어내지 않는다.** 첫 문장은 창작자가 쓴 말 그대로이고, 확정 화면에서
 * 고쳐 쓸 수 있다.
 */
const MAX_SUMMARY_CHARACTERS = 80;

export function pastedScriptSummary(script: string): string {
  const opening = script
    .split(/\r?\n/)
    .map((line) => line.trim())
    .find((line) => line.length > 0);
  if (!opening) return "붙여넣은 대본";
  return opening.length <= MAX_SUMMARY_CHARACTERS
    ? opening
    : `${opening.slice(0, MAX_SUMMARY_CHARACTERS - 1)}…`;
}


/** 기획 화면이 브리프를 되찾는 자리.
 *
 * 2026-08-19: 편집기에서 대본을 붙여 넣어 브리프를 만들어 놓고 **이 키를 쓰지
 * 않아서**, 확정 화면이 빈 폼을 보여 줬다. 대본은 서버에 있는데 화면에서 만날
 * 길이 없었다. 키를 한 곳에 두어 두 벌이 되지 않게 한다.
 */
export function creationBriefStorageKey(projectId: string): string {
  return `videobox.creation-brief.${projectId}`;
}
