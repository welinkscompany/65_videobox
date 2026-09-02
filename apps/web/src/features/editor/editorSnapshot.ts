import type { EditingSession, EditorPlaybackManifest, SceneTransition } from "../../api";
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
  /** 완성본에 실리는 자막 언어. `null`이면 원본(한국어). */
  captionLanguage: string | null;
  /** 이미 옮겨 둔 언어들. 하나라도 옮긴 장면이 있으면 그 언어가 들어온다. */
  translatedLanguages: readonly string[];
  segments: ReadonlyArray<Readonly<{
    segmentId: string;
    cutAction: string;
    bgm: EditorSessionMedia | null;
    sfx: EditorSessionMedia | null;
    /** 앞 장면에서 이 장면으로 넘어오는 방법. 안 골랐으면 null. */
    transitionIn: EditorSessionTransition | null;
    ripplePlaybackRate?: 1 | 1.5 | 2;
    ttsReplacement: EditorSessionTtsReplacement | null;
  }>>;
}>;

export type EditorSessionTransition = Readonly<{
  type: string;
  durationSec: number;
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

function transition(value: SceneTransition | null | undefined): EditorSessionTransition | null {
  const type = stringOrNull(value?.type);
  // `none`은 "전환 없음"이다. 값이 아예 없는 것과 화면에서 구별하지 않는다.
  if (!type || type === "none") return null;
  return {
    type,
    durationSec: typeof value?.duration_sec === "number" ? value.duration_sec : 0.5,
  };
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
      captionLanguage: editingSession.caption_language ?? null,
      // 장면마다 따로 셀 것이 아니라 **하나라도 있으면 고를 수 있는 언어**다.
      // 반쯤 번역된 상태에서도 고를 수 있어야 한다 -- 나머지 장면은 원문으로
      // 메워져 나가고, 다시 누르면 빠진 장면만 옮긴다.
      translatedLanguages: [...new Set(
        editingSession.segments.flatMap((segment) => Object.entries(segment.caption_translations ?? {})
          .filter(([, text]) => String(text ?? "").trim().length > 0)
          .map(([code]) => code)),
      )],
      segments: editingSession.segments.map((segment) => ({
        segmentId: segment.segment_id,
        cutAction: segment.cut_action,
        bgm: media(segment.music_override),
        sfx: media(segment.sfx_override),
        transitionIn: transition(segment.transition_in),
        ...(segment.ripple_playback_rate ? { ripplePlaybackRate: segment.ripple_playback_rate } : {}),
        ttsReplacement: ttsReplacement(segment.tts_replacement),
      })),
    },
  };
}
