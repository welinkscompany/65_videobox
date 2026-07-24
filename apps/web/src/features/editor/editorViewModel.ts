import type { EditorMediaControls, EditorPlaybackManifest } from "../../api";

export type EditorControls = Readonly<{
  volume?: number;
  crop?: string;
  speed?: number;
  gainDb?: number;
  fadeInSec?: number;
  fadeOutSec?: number;
  ducking?: boolean;
  fit?: "fit" | "crop";
  loop?: boolean;
  pad?: boolean;
  trimStartSec?: number;
  preserveSourceAudio?: boolean;
  inSec?: number;
  outSec?: number;
}>;
export type EditorCaptionStyle = Readonly<{
  fontFamily: string; fontSizePx: number; textColor: string; outlineColor: string; outlineWidthPx: number;
  backgroundColor: string; positionXPercent: number; positionYPercent: number; horizontalAlign: "left" | "center" | "right";
  safeAreaEnabled: boolean; shadowBlurPx: number;
}>;
export type EditorViewModel = Readonly<{
  projectId: string; sessionId: string; timelineId: string; timelineVersion: string; expectedRevision: number; timebase: "seconds";
  fps: Readonly<{ num: number; den: number }>;
  output: Readonly<{ width: number; height: number; sampleAspectRatio: string; rotation: number; durationSec: number }>;
  tracks: ReadonlyArray<Readonly<{ trackId: string; role: "narration" | "broll" | "bgm" | "sfx" | "overlay"; clips: ReadonlyArray<Readonly<{ clipId: string; segmentId: string; placementId?: string | null; type: "narration" | "broll" | "bgm" | "sfx" | "overlay"; assetId: string | null; assetUri: string | null; startSec: number; endSec: number; controls: EditorControls; expectedContentSha256?: string | null; mediaRevision?: string | null; overlayType?: "explanation_card" | "image_overlay" | "table_overlay" | null; overlayPayload?: Record<string, unknown> }>> }>>;
  captions: ReadonlyArray<Readonly<{ segmentId: string; captionId?: string; placementId?: string; text: string; startSec: number; endSec: number; style: EditorCaptionStyle }>>;
  gaps: ReadonlyArray<Readonly<{ gapId: string; segmentId: string; startSec: number; endSec: number; reason: string }>>;
  source: Readonly<{ status: "current" | "stale"; sourceSessionId?: string | null; sourceSessionRevision?: number | null }>;
  playback: Readonly<{ auditionUrls: Readonly<Record<string, string>>; exactPreview: Readonly<{ status: "current" | "succeeded" | "pending" | "running" | "failed" | "stale" | "unavailable"; url?: string | null; sourceSessionId?: string | null; sourceSessionRevision?: number | null; generationId?: string | null; timelineStartSec?: number | null; timelineEndSec?: number | null; artifactRevision?: number | null }> }>;
  local: Readonly<{ selectedSegmentId: string | null; seekSec: number }>;
}>;

function controls(value: EditorMediaControls): EditorControls {
  return {
    volume: value.volume,
    crop: value.crop,
    speed: value.speed,
    gainDb: value.gain_db,
    fadeInSec: value.fade_in_sec,
    fadeOutSec: value.fade_out_sec,
    ducking: value.ducking,
    fit: value.fit,
    loop: value.loop,
    pad: value.pad,
    trimStartSec: value.trim_start_sec,
    preserveSourceAudio: value.preserve_source_audio,
    inSec: value.in_sec,
    outSec: value.out_sec,
  };
}

export class VideoBoxEditorAdapter {
  private selectedSegmentId: string | null = null;
  private seekSec = 0;
  public constructor(private readonly manifest: EditorPlaybackManifest) {}

  select(segmentId: string | null): void { this.selectedSegmentId = segmentId; }
  seek(seconds: number): void { this.seekSec = seconds; }

  get viewModel(): EditorViewModel {
    const { manifest } = this;
    return {
      projectId: manifest.project_id, sessionId: manifest.session_id, timelineId: manifest.timeline_id, timelineVersion: manifest.timeline_version, expectedRevision: manifest.session_revision,
      timebase: manifest.timebase, fps: manifest.fps,
      output: { width: manifest.output.width, height: manifest.output.height, sampleAspectRatio: manifest.output.sample_aspect_ratio, rotation: manifest.output.rotation, durationSec: manifest.output.duration_sec },
      tracks: manifest.tracks.map((track) => ({ trackId: track.track_id, role: track.track_type, clips: track.clips.map((clip) => ({ clipId: clip.clip_id, segmentId: clip.segment_id, placementId: clip.placement_id, type: clip.clip_type, assetId: clip.asset_id, assetUri: clip.asset_uri, startSec: clip.start_sec, endSec: clip.end_sec, controls: controls(clip.media_controls), expectedContentSha256: clip.expected_content_sha256, mediaRevision: clip.media_revision, overlayType: clip.overlay_type, overlayPayload: clip.overlay_payload })) })),
      captions: manifest.captions.map((caption) => ({ segmentId: caption.segment_id, captionId: caption.caption_id, placementId: caption.placement_id, text: caption.text, startSec: caption.start_sec, endSec: caption.end_sec, style: { fontFamily: caption.style.font_family, fontSizePx: caption.style.font_size_px, textColor: caption.style.text_color, outlineColor: caption.style.outline_color, outlineWidthPx: caption.style.outline_width_px, backgroundColor: caption.style.background_color, positionXPercent: caption.style.position_x_percent, positionYPercent: caption.style.position_y_percent, horizontalAlign: caption.style.horizontal_align, safeAreaEnabled: caption.style.safe_area_enabled, shadowBlurPx: caption.style.shadow_blur_px } })),
      gaps: manifest.gap_slots.map((gap) => ({ gapId: gap.gap_id, segmentId: gap.segment_id, startSec: gap.start_sec, endSec: gap.end_sec, reason: gap.reason })),
      source: { status: manifest.source_status.status, sourceSessionId: manifest.source_status.source_session_id, sourceSessionRevision: manifest.source_status.source_session_revision },
      playback: { auditionUrls: manifest.audition.asset_urls, exactPreview: { status: manifest.exact_preview.status, url: manifest.exact_preview.url, sourceSessionId: manifest.exact_preview.source_session_id, sourceSessionRevision: manifest.exact_preview.source_session_revision, generationId: manifest.exact_preview.generation_id, timelineStartSec: manifest.exact_preview.timeline_start_sec, timelineEndSec: manifest.exact_preview.timeline_end_sec, artifactRevision: manifest.exact_preview.artifact_revision } },
      local: { selectedSegmentId: this.selectedSegmentId, seekSec: this.seekSec },
    };
  }
}
