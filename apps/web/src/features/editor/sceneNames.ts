import type { EditorViewModel } from "./editorViewModel";

/** 장면 번호는 **타임라인 순서**를 따른다. 검토 화면과 미리 듣기 이름이 이미
 *  그렇게 세고 있어서, 여기서 다르게 세면 같은 장면이 화면마다 다른 번호로
 *  불린다. 규칙이 두 벌이 되지 않도록 세는 자리를 하나로 둔다. */
export function sceneNumbersBySegmentId(view: EditorViewModel): ReadonlyMap<string, number> {
  const numbers = new Map<string, number>();
  view.tracks
    .flatMap((track) => track.clips)
    .slice()
    .sort((left, right) => left.startSec - right.startSec)
    .forEach((clip) => {
      if (clip.segmentId && !numbers.has(clip.segmentId)) numbers.set(clip.segmentId, numbers.size + 1);
    });
  return numbers;
}

/** 자막의 첫머리. 카드 한 줄에 들어가야 하므로 첫 문장만, 그것도 짧게 자른다.
 *  자막 전체를 실으면 카드가 자막 낭독기가 된다. */
const CAPTION_HEAD_MAX = 20;
export function captionHead(text: string): string {
  // 대본을 번호 목록으로 붙여 넣으면 자막이 `1. 걷는 리듬…`이 된다. 목록 번호를
  // 떼지 않으면 첫 문장이 `1`이 되고, 카드에 `4번째 장면 · 1`이 남는다.
  const cleaned = text.trim().replace(/^\d+[.)]\s*/, "");
  const first = (cleaned.split(/[.!?。！？\n]/)[0] ?? "").trim();
  // 한 글자짜리 조각은 장면 이름이 못 된다. 그럴 땐 아무 말도 하지 않고
  // 시작 시각으로 떨어진다.
  if (first.length < 2) return "";
  return first.length > CAPTION_HEAD_MAX ? `${first.slice(0, CAPTION_HEAD_MAX)}…` : first;
}

/** 장면을 **사람이 아는 말로** 부르는 이름. 내부 id(`segment_draft_444d28d0c7`)는
 *  창작자가 읽는 자리에 절대 나가지 않는다(§10.13).
 *
 *  자막이 있으면 그 첫머리가 가장 알아보기 쉽다 -- 창작자가 직접 쓴 말이기
 *  때문이다. 자막이 아직 없으면 타임라인 클립과 같은 방식으로 시작 시각을 쓴다. */
export function sceneLabelsBySegmentId(view: EditorViewModel): ReadonlyMap<string, string> {
  const numbers = sceneNumbersBySegmentId(view);
  const startBySegmentId = new Map<string, number>();
  for (const clip of view.tracks.flatMap((track) => track.clips)) {
    if (!clip.segmentId) continue;
    const known = startBySegmentId.get(clip.segmentId);
    if (known === undefined || clip.startSec < known) startBySegmentId.set(clip.segmentId, clip.startSec);
  }
  const captionBySegmentId = new Map<string, string>();
  for (const caption of view.captions) {
    const head = captionHead(caption.text);
    if (head && !captionBySegmentId.has(caption.segmentId)) captionBySegmentId.set(caption.segmentId, head);
  }
  const labels = new Map<string, string>();
  for (const [segmentId, number] of numbers) {
    const caption = captionBySegmentId.get(segmentId);
    const startSec = startBySegmentId.get(segmentId) ?? 0;
    labels.set(segmentId, `${number}번째 장면 · ${caption ?? `${Math.round(startSec)}초부터`}`);
  }
  return labels;
}
