import type { EditorCaptionStyle, EditorControls, EditorViewModel } from "../editorViewModel";

type MediaKind = "broll" | "bgm" | "sfx";
type MediaField = "fadeInSec" | "fadeOutSec";
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

const mediaFields = ["fadeInSec", "fadeOutSec"] as const;
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
        fields: mediaKind === "broll" ? [] : mediaFields,
        assetId: clip.assetId!,
        controls: clip.controls,
        clearOnly: mediaKind === "broll",
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
