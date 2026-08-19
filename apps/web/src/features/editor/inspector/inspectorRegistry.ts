import type { EditorCaptionStyle, EditorControls, EditorViewModel } from "../editorViewModel";

type MediaKind = "broll" | "bgm" | "sfx";
type MediaField = "fadeInSec" | "fadeOutSec" | "inSec" | "outSec" | "speed" | "volume" | "ducking" | "preserveSourceAudio" | "gainDb";
type CaptionField = "style";
type ExplanationCardField = "title" | "body" | "text";
type ImageField = "assetId" | "text";
type TableField = "columns" | "rows" | "text";

export type InspectorTarget =
  | Readonly<{ id: string; kind: "media"; label: string; segmentId: string; mediaKind: MediaKind; fields: readonly MediaField[]; assetId: string; controls: EditorControls; clearOnly: boolean }>
  | Readonly<{ id: string; kind: "caption"; label: string; segmentId: string; fields: readonly CaptionField[]; style: EditorCaptionStyle }>
  | Readonly<{ id: string; kind: "overlay"; label: string; segmentId: string; overlayKind: "explanation-card"; fields: readonly ExplanationCardField[]; value: Readonly<{ title: string; body: string; text: string }> }>
  | Readonly<{ id: string; kind: "overlay"; label: string; segmentId: string; overlayKind: "image"; fields: readonly ImageField[]; value: Readonly<{ assetId: string; text: string }> }>
  | Readonly<{ id: string; kind: "overlay"; label: string; segmentId: string; overlayKind: "table"; fields: readonly TableField[]; value: Readonly<{ columns: string[]; rows: string[][]; text: string }> }>;

// 2026-08-19: `소리 크기`(gainDb)가 화면에 들어왔다. 예전에는 "입력 자리를 주면
// owner가 정하지 않은 값이 저장마다 실린다"고 뺐는데, 슬라이더는 저장된 값에서
// 시작하므로 손대지 않은 저장이 값을 옮기지 않는다. 렌더러는 처음부터 클립별
// gain_db를 반영하고 있었다(`ffmpeg_final_renderer`) -- 화면에 자리만 없었다.
const mediaFields = ["fadeInSec", "fadeOutSec", "gainDb"] as const;
// 배경 음악만 내레이션 밑으로 비켜설 수 있다. 렌더러가 사이드체인 압축을
// **bgm에만** 걸기 때문이다(`ffmpeg_final_renderer`) -- 효과음에 스위치를 주면
// 눌러도 아무 일이 없는 단추가 된다.
const bgmFields = ["fadeInSec", "fadeOutSec", "ducking", "gainDb"] as const;
// Task 24: B-roll carries no audio by default, so fades are meaningless for it.
// What the owner actually corrects is which slice of a long take gets used --
// the recommendation picks a scene window, this is where that is overridden.
// Phone B-roll is routinely too long and too loud, so the clip carries a
// source window, a rate, and its own loudness.
//
// 2026-08-18: 페이드가 다시 들어왔다. 위 문장은 **소리** 페이드 이야기였고,
// 여기 것은 **화면** 페이드다 -- 겹쳐 놓은 두 클립에서 위에 걸면 아래가 비쳐
// 장면이 부드럽게 바뀐다(디졸브). 렌더러가 알파를 태워 실제로 그렇게 그린다.
//
// 2026-08-18: `소리 크기` 옆에 **자체 소리를 살릴지**가 함께 있어야 한다. 렌더러는
// 그 스위치가 켜져 있을 때만 이 클립의 소리를 섞는데, 켜는 자리가 없어서 음량이
// 영영 아무 일도 하지 못했다. 순서도 소리 크기 바로 뒤에 둔다 -- 떨어뜨려 놓으면
// 둘이 한 벌이라는 게 보이지 않는다.
const brollFields = ["inSec", "outSec", "speed", "volume", "preserveSourceAudio", "fadeInSec", "fadeOutSec"] as const;
const mediaLabels = { broll: "B-roll", bgm: "배경 음악", sfx: "효과음" } as const;

function isMediaKind(role: EditorViewModel["tracks"][number]["role"]): role is MediaKind {
  return role === "broll" || role === "bgm" || role === "sfx";
}

function stringValue(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function stringList(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function stringRows(value: unknown): string[][] {
  return Array.isArray(value)
    ? value.filter(Array.isArray).map((row) => row.filter((item): item is string => typeof item === "string"))
    : [];
}

export function projectInspectorTargets({ view, selectedSegmentId }: Readonly<{ view: EditorViewModel; selectedSegmentId: string | null }>): readonly InspectorTarget[] {
  if (!selectedSegmentId) return [];

  const mediaTargets = view.tracks.flatMap((track) => {
    const mediaKind = track.role;
    if (!isMediaKind(mediaKind)) return [];
    return track.clips
      .filter((clip) => clip.segmentId === selectedSegmentId && clip.type === mediaKind && clip.assetId !== null)
      .map((clip) => ({
        id: `clip:${clip.clipId}`,
        kind: "media" as const,
        label: mediaLabels[mediaKind],
        segmentId: selectedSegmentId,
        mediaKind,
        fields: mediaKind === "broll" ? brollFields : mediaKind === "bgm" ? bgmFields : mediaFields,
        assetId: clip.assetId!,
        controls: clip.controls,
        clearOnly: false,
      }));
  });
  const captionTargets = view.captions
    .filter((caption) => caption.segmentId === selectedSegmentId)
    .map((caption) => ({
      id: `caption:${caption.captionId ?? caption.segmentId}`,
      kind: "caption" as const,
      label: "연결 자막",
      segmentId: selectedSegmentId,
      fields: ["style"] as const,
      style: caption.style,
    }));
  const overlayTargets = view.tracks
    .filter((track) => track.role === "overlay")
    .flatMap((track) => track.clips.filter((clip) => clip.segmentId === selectedSegmentId && clip.type === "overlay"))
    .flatMap((clip): readonly InspectorTarget[] => {
      const payload = clip.overlayPayload ?? {};
      if (clip.overlayType === "explanation_card") return [{
        id: `overlay:${clip.clipId}`, kind: "overlay", label: "설명 카드", segmentId: selectedSegmentId, overlayKind: "explanation-card", fields: ["title", "body", "text"],
        value: { title: stringValue(payload.title), body: stringValue(payload.body), text: stringValue(payload.text) },
      }];
      if (clip.overlayType === "image_overlay") return [{
        id: `overlay:${clip.clipId}`, kind: "overlay", label: "이미지", segmentId: selectedSegmentId, overlayKind: "image", fields: ["assetId", "text"],
        value: { assetId: clip.assetId ?? stringValue(payload.asset_id), text: stringValue(payload.text) },
      }];
      if (clip.overlayType === "table_overlay") return [{
        id: `overlay:${clip.clipId}`, kind: "overlay", label: "표", segmentId: selectedSegmentId, overlayKind: "table", fields: ["columns", "rows", "text"],
        value: { columns: stringList(payload.columns), rows: stringRows(payload.rows), text: stringValue(payload.text) },
      }];
      return [];
    });

  return [...mediaTargets, ...captionTargets, ...overlayTargets];
}
