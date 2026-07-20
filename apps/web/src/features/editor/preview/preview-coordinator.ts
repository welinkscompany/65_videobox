export type TimelineRange = Readonly<{ startSec: number; endSec: number }>;
export type PreviewMedia = Readonly<{ id: string; url: string; timelineRange: TimelineRange }>;
export type AuditionMedia = PreviewMedia & Readonly<{ mediaKind: "video" | "audio" }>;
export type PreviewMode =
  | Readonly<{ kind: "idle"; activeMediaId: null }>
  | Readonly<{ kind: "exact"; activeMediaId: string; media: PreviewMedia }>
  | Readonly<{ kind: "audition"; activeMediaId: string; media: AuditionMedia }>;

/** The sole owner of the shared player identity. It never creates a second player. */
export class PreviewCoordinator {
  private current: PreviewMode = { kind: "idle", activeMediaId: null };

  get state(): PreviewMode { return this.current; }
  showExact(media: PreviewMedia): PreviewMode { this.current = { kind: "exact", activeMediaId: media.id, media }; return this.current; }
  showAudition(media: AuditionMedia): PreviewMode { this.current = { kind: "audition", activeMediaId: media.id, media }; return this.current; }
  stop(): PreviewMode { this.current = { kind: "idle", activeMediaId: null }; return this.current; }
  timelineTime(mediaTimeSec: number): number {
    if (this.current.kind === "idle") return 0;
    if (!Number.isFinite(mediaTimeSec)) return this.current.media.timelineRange.startSec;
    return Math.min(this.current.media.timelineRange.endSec, Math.max(this.current.media.timelineRange.startSec, this.current.media.timelineRange.startSec + Math.max(0, mediaTimeSec)));
  }
}
