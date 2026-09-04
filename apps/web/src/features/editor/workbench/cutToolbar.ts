import type { EditorControls } from "../editorViewModel";
import type { InspectorAction } from "../inspector/InspectorControls";

/** 캡컷처럼 **타임라인 위에 컷 도구를 둔다.**
 *
 * 2026-08-17에 세어 보니 편집기 툴바에는 `실행 취소·다시 실행·소재·유진과
 * 편집 항목` 네 개뿐이었다. **영상 편집기인데 편집하는 단추가 하나도 없었다.**
 * 나누기·붙이기는 구현돼 있었지만 `선택 구간 편집`이라는 이름 뒤에 있어서
 * 컷편집을 찾는 사람은 영영 만나지 못했다.
 *
 * 여기서는 **무엇을 눌러야 하는지만** 정한다. 실제 변경은 이미 있는
 * `InspectorAction` 경로가 한다 -- 같은 편집이 두 경로를 갖지 않게.
 */
export type CutClip = Readonly<{
  segmentId: string;
  startSec: number;
  endSec: number;
  cutAction?: string;
}>;

export type CutTool = Readonly<{
  enabled: boolean;
  label: string;
  action: InspectorAction | null;
  /** 잠겨 있을 때 **왜** 잠겼는지. 이유 없이 회색인 단추는 고장으로 보인다. */
  hint: string;
}>;

/** 한 장면에 붙어 있는 재료. `save-media`가 다루는 단위와 같다. */
export type SceneMedia = Readonly<{
  segmentId: string;
  mediaKind: "broll" | "bgm" | "sfx";
  assetId: string;
  controls: EditorControls;
}>;

export type CutToolbarState = Readonly<{
  split: CutTool;
  join: CutTool;
  drop: CutTool;
  /** 캡컷의 `복제`에 해당한다 -- 아래 주석 참고. */
  copyToNext: CutTool;
}>;

const disabled = (label: string, hint: string): CutTool => ({ enabled: false, label, action: null, hint });

/** 아직 아무것도 계산되기 전의 상태. 키 처리기가 첫 렌더 전에 참조할 수 있다. */
export const EMPTY_CUT_TOOLS: CutToolbarState = {
  split: disabled("분할", ""),
  join: disabled("앞과 붙이기", ""),
  drop: disabled("빼기", ""),
  copyToNext: disabled("다음 장면에도", ""),
};

export function cutToolbarState({
  clips,
  selectedSegmentId,
  playheadSec,
  media = [],
}: {
  clips: readonly CutClip[];
  selectedSegmentId: string | null;
  playheadSec: number;
  media?: readonly SceneMedia[];
}): CutToolbarState {
  const ordered = [...clips].sort((left, right) => left.startSec - right.startSec);
  const index = ordered.findIndex((clip) => clip.segmentId === selectedSegmentId);
  const selected = index >= 0 ? ordered[index] : null;
  if (!selected) {
    const pickFirst = "아래 타임라인에서 장면을 먼저 고르세요.";
    return {
      split: disabled("분할", pickFirst),
      join: disabled("앞과 붙이기", pickFirst),
      drop: disabled("빼기", pickFirst),
      copyToNext: disabled("다음 장면에도", pickFirst),
    };
  }

  // 재생 위치가 선택한 장면 안에 있어야 무엇을 나누는지 알 수 있고, 경계에서
  // 나누면 길이 0짜리 장면이 생긴다.
  const splittable = playheadSec > selected.startSec && playheadSec < selected.endSec;
  const previous = index > 0 ? ordered[index - 1] : null;
  // **캡컷의 `복제`는 우리 모델에 그대로 없다.** 배치는 장면에서 파생되고 따로 만드는
  // 길이 없다(`timeline_placements.apply_placement_changes`는 있는 것만 옮긴다).
  // 같은 화면을 한 번 더 쓰는 실제 방법은 그 재료를 다음 장면에도 적용하는 것이고,
  // 그건 이미 있는 명령이다. 여기서는 그 길을 한 번에 만들 뿐 새 명령을 만들지 않는다.
  const next = index >= 0 && index + 1 < ordered.length ? ordered[index + 1] : null;
  const carried = media.find((item) => item.segmentId === selected.segmentId);

  return {
    split: splittable
      ? { enabled: true, label: "분할", hint: "재생 위치에서 두 장면으로 나눕니다. (Ctrl+B)", action: { kind: "split-narration", segmentId: selected.segmentId, splitSec: playheadSec } }
      : disabled("분할", "재생 위치를 고른 장면 안으로 옮기세요. 그 자리에서 나눕니다."),
    join: previous
      ? { enabled: true, label: "앞과 붙이기", hint: "앞 장면과 하나로 합칩니다.", action: { kind: "merge-narration", leftSegmentId: previous.segmentId, rightSegmentId: selected.segmentId } }
      : disabled("앞과 붙이기", "첫 장면 앞에는 붙일 것이 없습니다."),
    // 뺀 장면은 타임라인에서 사라져 다시 고를 수 없다(실제 앱에서 확인).
    // 그래서 이 단추는 되돌리지 못한다 -- 되돌리기는 `실행 취소`가, 다시 넣기는
    // 인스펙터의 `유지`가 맡는다. 여기서 되돌림을 흉내 내면 누를 수 없는 단추가 된다.
    drop: {
      enabled: true,
      label: "빼기",
      hint: "고른 장면을 영상에서 뺍니다. (Delete) 되돌리려면 실행 취소를 누르세요.",
      action: { kind: "set-cut-action", segmentId: selected.segmentId, cutAction: "remove" },
    },
    copyToNext: !carried
      ? disabled("다음 장면에도", "이 장면에 옮길 재료가 없습니다. 왼쪽에서 먼저 골라 적용하세요.")
      : !next
      ? disabled("다음 장면에도", "마지막 장면 뒤에는 붙일 곳이 없습니다.")
      : {
          enabled: true,
          label: "다음 장면에도",
          hint: "이 장면의 재료를 다음 장면에도 그대로 씁니다.",
          action: { kind: "save-media", mediaKind: carried.mediaKind, segmentId: next.segmentId, assetId: carried.assetId, controls: carried.controls },
        },
  };
}
