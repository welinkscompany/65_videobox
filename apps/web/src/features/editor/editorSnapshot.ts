import type { EditingSession, EditorPlaybackManifest } from "../../api";
import { VideoBoxEditorAdapter, type EditorControls, type EditorViewModel } from "./editorViewModel";

export type EditorSessionMedia = Readonly<{
  assetId: string;
  assetUri: string | null;
  expectedContentSha256: string | null;
  mediaRevision: string | null;
  controls: EditorControls;
}>;

export type EditorSessionTtsReplacement = Readonly<{
  candidateId: string;
  assetId: string;
}>;

export type EditorSessionSnapshot = Readonly<{
  projectId: string;
  sessionId: string;
  timelineId: string;
  expectedRevision: number;
  undoCount: number;
  redoCount: number;
  updatedAt: string | null;
  segments: ReadonlyArray<Readonly<{
    segmentId: string;
    cutAction: string;
    bgm: EditorSessionMedia | null;
    sfx: EditorSessionMedia | null;
    ttsReplacement: EditorSessionTtsReplacement | null;
  }>>;
}>;

export type EditorSnapshot = Readonly<{
  view: EditorViewModel;
  session: EditorSessionSnapshot;
}>;

function stringOrNull(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function media(value: Record<string, unknown> | null | undefined): EditorSessionMedia | null {
  if (!value) return null;
  const assetId = stringOrNull(value.asset_id);
  if (!assetId) return null;
  const rawControls = value.media_controls;
  const controls = rawControls && typeof rawControls === "object" && !Array.isArray(rawControls)
    ? rawControls as Record<string, unknown>
    : {};
  return {
    assetId,
    assetUri: stringOrNull(value.asset_uri),
    expectedContentSha256: stringOrNull(value.expected_content_sha256),
    mediaRevision: stringOrNull(value.media_revision),
    controls: {
      gainDb: typeof controls.gain_db === "number" ? controls.gain_db : undefined,
      fadeInSec: typeof controls.fade_in_sec === "number" ? controls.fade_in_sec : undefined,
      fadeOutSec: typeof controls.fade_out_sec === "number" ? controls.fade_out_sec : undefined,
      ducking: typeof controls.ducking === "boolean" ? controls.ducking : undefined,
    },
  };
}

function ttsReplacement(value: Record<string, unknown> | null | undefined): EditorSessionTtsReplacement | null {
  if (!value) return null;
  const candidateId = stringOrNull(value.recommendation_id);
  const assetId = stringOrNull(value.asset_id);
  return candidateId && assetId ? { candidateId, assetId } : null;
}

export function joinEditorSnapshot(
  manifest: EditorPlaybackManifest,
  editingSession: EditingSession,
): EditorSnapshot {
  const identitiesMatch = Boolean(
    manifest.project_id
    && manifest.session_id
    && manifest.timeline_id
    && editingSession.project_id
    && editingSession.session_id
    && editingSession.timeline_id
    && manifest.project_id === editingSession.project_id
    && manifest.session_id === editingSession.session_id
    && manifest.timeline_id === editingSession.timeline_id
    && manifest.session_revision === editingSession.session_revision,
  );
  if (!identitiesMatch) throw new Error("editor_snapshot_identity_mismatch");

  return {
    view: new VideoBoxEditorAdapter(manifest).viewModel,
    session: {
      projectId: editingSession.project_id,
      sessionId: editingSession.session_id,
      timelineId: editingSession.timeline_id,
      expectedRevision: editingSession.session_revision,
      undoCount: editingSession.undo_count ?? 0,
      redoCount: editingSession.redo_count ?? 0,
      updatedAt: editingSession.updated_at ?? null,
      segments: editingSession.segments.map((segment) => ({
        segmentId: segment.segment_id,
        cutAction: segment.cut_action,
        bgm: media(segment.music_override),
        sfx: media(segment.sfx_override),
        ttsReplacement: ttsReplacement(segment.tts_replacement),
      })),
    },
  };
}
