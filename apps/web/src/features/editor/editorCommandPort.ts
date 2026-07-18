import { api, type BrollOverrideRequest, type CaptionStyleMutationRequest, type EditingSession, type ImageOverlayRequest, type MusicOverrideRequest, type TableOverlayRequest } from "../../api";
import type { EditorCaptionStyle, EditorControls } from "./editorViewModel";

type Context = Readonly<{ projectId: string; sessionId: string; expectedRevision: number }>;
type MediaKind = "broll" | "bgm" | "sfx";
type MediaCommand = Readonly<{ kind: MediaKind; segmentId: string; assetId: string; controls?: EditorControls }>;
type OverlayApply =
  | Readonly<{ kind: "explanation-card"; segmentId: string; title: string; body: string; text: string }>
  | Readonly<{ kind: "image"; segmentId: string; assetId: string; text: string }>
  | Readonly<{ kind: "table"; segmentId: string; columns: string[]; rows: string[][]; text: string }>;
type OverlayClear = Readonly<{ kind: OverlayApply["kind"]; segmentId: string }>;

export type EditorCommandApi = Pick<typeof api,
  "splitEditingSessionSegment" | "mergeEditingSessionSegments" | "updateEditingSessionSegmentBounds" | "reorderEditingSessionSegments" |
  "updateEditingSessionBroll" | "clearEditingSessionBrollOverride" | "updateEditingSessionMusicOverride" | "clearEditingSessionMusicOverride" |
  "updateEditingSessionSfxOverride" | "clearEditingSessionSfxOverride" | "updateEditingSessionExplanationCard" | "removeEditingSessionExplanationCard" |
  "updateEditingSessionImageOverlay" | "removeEditingSessionImageOverlay" | "updateEditingSessionTableOverlay" | "removeEditingSessionTableOverlay" |
  "updateEditingSessionCaption" | "updateEditingSessionCaptionStyle"
>;

export type EditorCommandPort = Readonly<{
  splitNarration(input: { segmentId: string; splitSec: number }): Promise<EditingSession>;
  mergeNarration(input: { leftSegmentId: string; rightSegmentId: string }): Promise<EditingSession>;
  setNarrationBounds(input: { segmentId: string; startSec: number; endSec: number }): Promise<EditingSession>;
  reorderNarration(input: { segmentIds: string[] }): Promise<EditingSession>;
  applyMedia(input: MediaCommand): Promise<EditingSession>;
  updateMediaControls(input: MediaCommand): Promise<EditingSession>;
  clearMedia(input: { kind: MediaKind; segmentId: string }): Promise<EditingSession>;
  applyOverlay(input: OverlayApply): Promise<EditingSession>;
  clearOverlay(input: OverlayClear): Promise<EditingSession>;
  setCaptionText(input: { segmentId: string; text: string }): Promise<EditingSession>;
  setCaptionStyle(input: { segmentIds: string[]; scope: CaptionStyleMutationRequest["scope"]; style: EditorCaptionStyle }): Promise<EditingSession>;
}>;

function mediaControls(value: EditorControls | undefined): BrollOverrideRequest["media_controls"] {
  if (!value) return undefined;
  return { volume: value.volume, crop: value.crop, speed: value.speed, fade_in_sec: value.fadeInSec, fade_out_sec: value.fadeOutSec };
}
function captionStyle(style: EditorCaptionStyle): CaptionStyleMutationRequest["style"] {
  return { font_family: style.fontFamily, font_size_px: style.fontSizePx, text_color: style.textColor, outline_color: style.outlineColor, outline_width_px: style.outlineWidthPx, background_color: style.backgroundColor, position_x_percent: style.positionXPercent, position_y_percent: style.positionYPercent, horizontal_align: style.horizontalAlign, safe_area_enabled: style.safeAreaEnabled, shadow_blur_px: style.shadowBlurPx };
}

export function createEditorCommandPort(context: Context, commandApi: EditorCommandApi = api): EditorCommandPort {
  const { projectId, sessionId, expectedRevision } = context;
  const revise = { expected_revision: expectedRevision };
  const applyMedia = (input: MediaCommand) => {
    const payload = { asset_id: input.assetId, media_controls: mediaControls(input.controls), ...revise };
    if (input.kind === "broll") return commandApi.updateEditingSessionBroll(projectId, sessionId, input.segmentId, payload);
    if (input.kind === "bgm") return commandApi.updateEditingSessionMusicOverride(projectId, sessionId, input.segmentId, payload as MusicOverrideRequest);
    return commandApi.updateEditingSessionSfxOverride(projectId, sessionId, input.segmentId, payload);
  };
  return {
    splitNarration: ({ segmentId, splitSec }) => commandApi.splitEditingSessionSegment(projectId, sessionId, segmentId, { split_sec: splitSec, ...revise }),
    mergeNarration: ({ leftSegmentId, rightSegmentId }) => commandApi.mergeEditingSessionSegments(projectId, sessionId, { left_segment_id: leftSegmentId, right_segment_id: rightSegmentId, ...revise }),
    setNarrationBounds: ({ segmentId, startSec, endSec }) => commandApi.updateEditingSessionSegmentBounds(projectId, sessionId, segmentId, { start_sec: startSec, end_sec: endSec, ...revise }),
    reorderNarration: ({ segmentIds }) => commandApi.reorderEditingSessionSegments(projectId, sessionId, { segment_ids: segmentIds, ...revise }),
    applyMedia,
    updateMediaControls: applyMedia,
    clearMedia: ({ kind, segmentId }) => kind === "broll" ? commandApi.clearEditingSessionBrollOverride(projectId, sessionId, segmentId, expectedRevision) : kind === "bgm" ? commandApi.clearEditingSessionMusicOverride(projectId, sessionId, segmentId, expectedRevision) : commandApi.clearEditingSessionSfxOverride(projectId, sessionId, segmentId, expectedRevision),
    applyOverlay: (input) => input.kind === "explanation-card" ? commandApi.updateEditingSessionExplanationCard(projectId, sessionId, input.segmentId, { title: input.title, body: input.body, text: input.text, ...revise }) : input.kind === "image" ? commandApi.updateEditingSessionImageOverlay(projectId, sessionId, input.segmentId, { asset_id: input.assetId, text: input.text, ...revise } as ImageOverlayRequest) : commandApi.updateEditingSessionTableOverlay(projectId, sessionId, input.segmentId, { columns: input.columns, rows: input.rows, text: input.text, ...revise } as TableOverlayRequest),
    clearOverlay: (input) => input.kind === "explanation-card" ? commandApi.removeEditingSessionExplanationCard(projectId, sessionId, input.segmentId, expectedRevision) : input.kind === "image" ? commandApi.removeEditingSessionImageOverlay(projectId, sessionId, input.segmentId, expectedRevision) : commandApi.removeEditingSessionTableOverlay(projectId, sessionId, input.segmentId, expectedRevision),
    setCaptionText: ({ segmentId, text }) => commandApi.updateEditingSessionCaption(projectId, sessionId, segmentId, { caption_text: text, ...revise }),
    setCaptionStyle: ({ segmentIds, scope, style }) => commandApi.updateEditingSessionCaptionStyle(projectId, sessionId, { segment_ids: segmentIds, scope, style: captionStyle(style), ...revise }),
  };
}
