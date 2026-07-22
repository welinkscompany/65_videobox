import type { EditorViewModel } from "../editorViewModel";

type AudioMediaKind = "bgm" | "sfx";
type AudioMediaField = "fadeInSec" | "fadeOutSec";
type BrollMediaField = "fit" | "loop" | "pad" | "trimStartSec";
type CaptionField = "text" | "style";
type ExplanationCardField = "title" | "body" | "text";
type ImageField = "assetId" | "text";
type TableField = "columns" | "rows" | "text";

export type InspectorTarget =
  | Readonly<{ id: string; kind: "media"; label: string; segmentId: string; mediaKind: "broll"; fields: readonly BrollMediaField[] }>
  | Readonly<{ id: string; kind: "media"; label: string; segmentId: string; mediaKind: AudioMediaKind; fields: readonly AudioMediaField[] }>
  | Readonly<{ id: string; kind: "caption"; label: string; segmentId: string; fields: readonly CaptionField[] }>
  | Readonly<{ id: string; kind: "overlay"; label: string; segmentId: string; overlayKind: "explanation-card"; fields: readonly ExplanationCardField[] }>
  | Readonly<{ id: string; kind: "overlay"; label: string; segmentId: string; overlayKind: "image"; fields: readonly ImageField[] }>
  | Readonly<{ id: string; kind: "overlay"; label: string; segmentId: string; overlayKind: "table"; fields: readonly TableField[] }>;

const audioMediaFields = ["fadeInSec", "fadeOutSec"] as const;
const brollMediaFields = ["fit", "loop", "pad", "trimStartSec"] as const;
const mediaLabels = { broll: "보조 영상", bgm: "배경 음악", sfx: "효과음" } as const;

function isMediaKind(role: EditorViewModel["tracks"][number]["role"]): role is "broll" | AudioMediaKind {
  return role === "broll" || role === "bgm" || role === "sfx";
}

export function projectInspectorTargets({ view, selectedSegmentId }: Readonly<{ view: EditorViewModel; selectedSegmentId: string | null }>): readonly InspectorTarget[] {
  if (!selectedSegmentId) return [];

  const mediaTargets = view.tracks.flatMap((track) => {
    const mediaKind = track.role;
    if (!isMediaKind(mediaKind)) return [];
    return track.clips
      .filter((clip) => clip.segmentId === selectedSegmentId && clip.type === mediaKind && clip.assetId !== null)
      .map((clip): InspectorTarget => mediaKind === "broll"
        ? { id: `clip:${clip.clipId}`, kind: "media", label: mediaLabels[mediaKind], segmentId: selectedSegmentId, mediaKind, fields: brollMediaFields }
        : { id: `clip:${clip.clipId}`, kind: "media", label: mediaLabels[mediaKind], segmentId: selectedSegmentId, mediaKind, fields: audioMediaFields });
  });
  const captionTargets = view.captions
    .filter((caption) => caption.segmentId === selectedSegmentId)
    .map((caption) => ({ id: `caption:${caption.captionId ?? caption.segmentId}`, kind: "caption" as const, label: "연결 자막", segmentId: selectedSegmentId, fields: ["text", "style"] as const }));
  const overlayTargets = view.tracks
    .filter((track) => track.role === "overlay")
    .flatMap((track) => track.clips.filter((clip) => clip.segmentId === selectedSegmentId && clip.type === "overlay"))
    .flatMap((clip): readonly InspectorTarget[] => {
      if (clip.overlayType === "explanation_card") return [{ id: `overlay:${clip.clipId}`, kind: "overlay", label: "설명 카드", segmentId: selectedSegmentId, overlayKind: "explanation-card", fields: ["title", "body", "text"] }];
      if (clip.overlayType === "image_overlay") return [{ id: `overlay:${clip.clipId}`, kind: "overlay", label: "이미지", segmentId: selectedSegmentId, overlayKind: "image", fields: ["assetId", "text"] }];
      if (clip.overlayType === "table_overlay") return [{ id: `overlay:${clip.clipId}`, kind: "overlay", label: "표", segmentId: selectedSegmentId, overlayKind: "table", fields: ["columns", "rows", "text"] }];
      return [];
    });

  return [...mediaTargets, ...captionTargets, ...overlayTargets];
}
