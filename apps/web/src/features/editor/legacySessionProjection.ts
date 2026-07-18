import type { EditingSession } from "../../api";
import type { EditorViewModel } from "./editorViewModel";

/**
 * A read-only bridge for the legacy shell. Pinned routes must derive these
 * values from the authoritative manifest rather than another restored session.
 */
export function projectLegacySession(view: EditorViewModel): EditingSession {
  const captions = new Map(view.captions.map((caption) => [caption.segmentId, caption]));
  const narration = view.tracks.find((track) => track.role === "narration")?.clips ?? [];
  const segmentIds = [...new Set([...narration.map((clip) => clip.segmentId), ...view.captions.map((caption) => caption.segmentId), ...view.gaps.map((gap) => gap.segmentId)])];
  return {
    project_id: view.projectId,
    session_id: view.sessionId,
    timeline_id: view.timelineId,
    session_revision: view.expectedRevision,
    history: [], undo_count: 0, redo_count: 0,
    segments: segmentIds.map((segmentId) => {
      const clip = narration.find((item) => item.segmentId === segmentId);
      const caption = captions.get(segmentId);
      const gap = view.gaps.find((item) => item.segmentId === segmentId);
      const mediaOverride = (role: "broll" | "bgm" | "sfx") => {
        const clip = view.tracks.find((track) => track.role === role)?.clips.find((item) => item.segmentId === segmentId);
        return clip?.assetId ? { asset_id: clip.assetId, media_controls: { volume: clip.controls.volume, crop: clip.controls.crop, speed: clip.controls.speed, fade_in_sec: clip.controls.fadeInSec, fade_out_sec: clip.controls.fadeOutSec } } : null;
      };
      const overlays = view.tracks.find((track) => track.role === "overlay")?.clips
        .filter((clip) => clip.segmentId === segmentId)
        .flatMap((clip) => clip.overlayType ? [{
          ...clip.overlayPayload,
          overlay_type: clip.overlayType,
          asset_id: clip.assetId,
          start_sec: clip.startSec,
          end_sec: clip.endSec,
          media_controls: {
            volume: clip.controls.volume,
            crop: clip.controls.crop,
            speed: clip.controls.speed,
            fade_in_sec: clip.controls.fadeInSec,
            fade_out_sec: clip.controls.fadeOutSec,
          },
        }] : []) ?? [];
      return {
        segment_id: segmentId,
        caption_text: caption?.text ?? "",
        start_sec: caption?.startSec ?? clip?.startSec ?? gap?.startSec ?? 0,
        end_sec: caption?.endSec ?? clip?.endSec ?? gap?.endSec ?? 0,
        cut_action: "keep",
        review_required: Boolean(gap),
        broll_override: mediaOverride("broll"),
        visual_overlays: overlays,
        music_override: mediaOverride("bgm"),
        sfx_override: mediaOverride("sfx"),
        tts_replacement: null,
      };
    }),
  };
}
