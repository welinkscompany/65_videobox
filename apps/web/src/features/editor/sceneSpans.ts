import type { EditorViewModel } from "./editorViewModel";

/** 장면 구간 하나. 자막·영상·내레이션 어디서 읽었든 모양이 같다. */
export type SceneSpan = Readonly<{ segmentId: string; startSec: number; endSec: number }>;

type Caption = EditorViewModel["captions"][number];

/**
 * 자막이 **어느 장면의 것인지**. 자막의 `segmentId`는 대본 정렬용 계보(분할 전 낡은 id가 그대로
 * 남는다)이고 `owningSegmentId`가 지금 실제로 놓인 장면이다(2026-10-09 실기 점검: 742e1924는
 * 자막 15개 중 13개가 낡은 `…__split_2`를 달고 있어 무엇을 눌러도 장면 2가 골라졌다).
 * 장면을 가리키는 모든 자리는 이 함수만 거친다 -- `caption.segmentId`로 장면을 찾지 않는다.
 */
export function captionOwnerSegmentId(caption: Pick<Caption, "segmentId" | "owningSegmentId">): string {
  return caption.owningSegmentId ?? caption.segmentId;
}

function narrationClips(view: EditorViewModel): SceneSpan[] {
  return view.tracks
    .filter((track) => track.role === "narration")
    .flatMap((track) => track.clips.map((clip) => ({ segmentId: clip.segmentId, startSec: clip.startSec, endSec: clip.endSec })));
}

/** 자막을 장면(소유 id)별로 묶는다. 한 장면에 자막이 여럿이면 처음~끝을 한 구간으로 본다. */
function captionScenes(view: EditorViewModel): SceneSpan[] {
  const byOwner = new Map<string, { startSec: number; endSec: number }>();
  for (const caption of view.captions) {
    const owner = captionOwnerSegmentId(caption);
    const known = byOwner.get(owner);
    if (!known) byOwner.set(owner, { startSec: caption.startSec, endSec: caption.endSec });
    else byOwner.set(owner, { startSec: Math.min(known.startSec, caption.startSec), endSec: Math.max(known.endSec, caption.endSec) });
  }
  return Array.from(byOwner, ([segmentId, range]) => ({ segmentId, ...range }));
}

/** 자막이 없는 장면의 마지막 보루 -- 그 장면에 깔린 화면(영상) 클립. */
function visualClips(view: EditorViewModel): SceneSpan[] {
  return view.tracks
    .filter((track) => track.role === "broll")
    .flatMap((track) => track.clips.map((clip) => ({ segmentId: clip.segmentId, startSec: clip.startSec, endSec: clip.endSec })));
}

/**
 * 장면 구간 목록(고르기·잘라내기 도구의 단위). 내레이션 장면이 둘 이상이면 그것이 장면이다.
 * 내레이션이 통짜 하나이거나 없으면 자막이 의미 단위다(없는 장면은 영상 클립으로 채운다).
 */
export function sceneSpans(view: EditorViewModel): SceneSpan[] {
  const narration = narrationClips(view);
  if (narration.length > 1) return narration;
  const captions = captionScenes(view);
  if (!captions.length) return narration;
  const known = new Set(captions.map((scene) => scene.segmentId));
  return [...captions, ...visualClips(view).filter((clip) => !known.has(clip.segmentId))];
}

/**
 * 재생 시각으로 장면을 고를 때 쓰는 목록. `sceneSpans`에 더해, 누른 장면의 화면 클립이 자막과
 * 다른 시각에 놓여 있어도(예: 장면 1의 영상이 90초에 있음) 누름이 지켜지도록 영상 클립 구간도 싣는다.
 */
export function playbackSelectionSpans(view: EditorViewModel): SceneSpan[] {
  const spans = sceneSpans(view);
  if (narrationClips(view).length > 1 || !view.captions.length) return spans;
  return [...spans, ...visualClips(view)];
}

/** 장면 id 하나의 구간. 내레이션 -> 자막(소유 id) -> 영상 클립 순서로 찾는다. 반환 id는 **물은 id 그대로**다. */
export function sceneSpanBySegmentId(view: EditorViewModel, segmentId: string): SceneSpan | undefined {
  const found = narrationClips(view).find((clip) => clip.segmentId === segmentId)
    ?? captionScenes(view).find((scene) => scene.segmentId === segmentId)
    ?? visualClips(view).find((clip) => clip.segmentId === segmentId);
  return found ? { segmentId, startSec: found.startSec, endSec: found.endSec } : undefined;
}
