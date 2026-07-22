import { type FocusEvent, type KeyboardEvent, type RefObject, useEffect, useLayoutEffect, useRef, useState } from "react";

import { toExactPreviewState, type ExactPreviewInput } from "./exact-preview-state";
import { PreviewCoordinator, type AuditionMedia, type PreviewMode, type TimelineRange } from "./preview-coordinator";
import { isAllowedLocalUrl } from "../../../lib/network-guard";

export type AuditionSource = AuditionMedia & Readonly<{ label: string }>;
export type PreviewCaption = Readonly<{ text: string; startSec: number; endSec: number }>;
type MediaNode = HTMLVideoElement | HTMLAudioElement;

export function PreviewStage({ expectedRevision, exactPreview, captions = [], sources, onRefresh, playbackSec, onPlaybackTimeChange }: {
  expectedRevision: number;
  exactPreview: ExactPreviewInput;
  captions?: readonly PreviewCaption[];
  sources: readonly AuditionSource[];
  onRefresh?: () => void | Promise<void>;
  playbackSec?: number;
  onPlaybackTimeChange?: (seconds: number) => void;
}) {
  const exact = toExactPreviewState(exactPreview, expectedRevision);
  const localSources = sources.filter((source) => isAllowedLocalUrl(source.url));
  const coordinatorRef = useRef(new PreviewCoordinator());
  const mediaRef = useRef<MediaNode>(null);
  const [mode, setMode] = useState<PreviewMode>(() => exact.kind === "current" ? coordinatorRef.current.showExact({ id: exactMediaId(exact), url: exact.url, timelineRange: exact.timelineRange }) : coordinatorRef.current.state);
  const [timelineTime, setTimelineTime] = useState(() => exact.kind === "current" ? exact.timelineRange.startSec : 0);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshError, setRefreshError] = useState<string | null>(null);

  const stopActiveMedia = () => {
    const media = mediaRef.current;
    if (media) {
      try { media.pause(); } catch { /* native playback may already be detached */ }
      try { media.currentTime = 0; } catch { /* media can be released by a browser during teardown */ }
    }
  };
  const showExact = () => {
    if (exact.kind !== "current") return;
    stopActiveMedia();
    setMode(coordinatorRef.current.showExact({ id: exactMediaId(exact), url: exact.url, timelineRange: exact.timelineRange }));
    setTimelineTime(exact.timelineRange.startSec);
  };
  const showAudition = (source: AuditionSource) => {
    stopActiveMedia();
    setMode(coordinatorRef.current.showAudition(source));
    setTimelineTime(source.timelineRange.startSec);
  };

  useEffect(() => {
    if (exact.kind !== "current") {
      stopActiveMedia();
      setMode(coordinatorRef.current.stop());
      return;
    }
    if (mode.kind !== "audition" && (mode.kind !== "exact" || mode.media.url !== exact.url)) showExact();
    // Deliberately keep a user-selected audition active while the manifest refreshes unchanged.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [exact.kind, exact.kind === "current" ? exact.url : null, expectedRevision]);
  useLayoutEffect(() => {
    const stopForScroll = () => stopActiveMedia();
    window.addEventListener("scroll", stopForScroll, { passive: true });
    return () => { window.removeEventListener("scroll", stopForScroll); stopActiveMedia(); };
  }, []);
  useEffect(() => {
    if (!Number.isFinite(playbackSec) || mode.kind === "idle") return;
    const timelineSeconds = Math.min(mode.media.timelineRange.endSec, Math.max(mode.media.timelineRange.startSec, playbackSec!));
    setTimelineTime(timelineSeconds);
    if (timelineSeconds !== playbackSec) onPlaybackTimeChange?.(timelineSeconds);
    const media = mediaRef.current;
    const mediaSeconds = timelineSeconds - mode.media.timelineRange.startSec;
    if (media && Math.abs(media.currentTime - mediaSeconds) > 0.001) {
      try { media.currentTime = mediaSeconds; } catch { /* the browser can reject a not-yet-seekable media element */ }
    }
  }, [mode, onPlaybackTimeChange, playbackSec]);

  const currentMedia = mode.kind === "idle" ? null : mode.media;
  const mediaLabel = mode.kind === "audition" ? `${sourceLabel(localSources, mode.media.id)} 소스 미리보기` : "편집본 미리보기";
  const activeCaption = mode.kind === "exact" ? captions.find((caption) => timelineTime >= caption.startSec && timelineTime < caption.endSec) : null;
  const updateTimeline = (node: MediaNode) => {
    const nextSeconds = coordinatorRef.current.timelineTime(node.currentTime);
    setTimelineTime(nextSeconds);
    onPlaybackTimeChange?.(nextSeconds);
  };
  const togglePlayback = () => {
    const media = mediaRef.current;
    if (!media) return;
    if (media.paused) {
      const attempt = media.play();
      if (attempt && typeof attempt.catch === "function") void attempt.catch(() => undefined);
    } else stopActiveMedia();
  };
  const onStageKeyDown = (event: KeyboardEvent<HTMLElement>) => {
    if (event.key !== " " && event.key !== "Enter") return;
    if (event.target !== event.currentTarget) return;
    event.preventDefault();
    togglePlayback();
  };
  const onStageBlur = (event: FocusEvent<HTMLElement>) => {
    if (!event.currentTarget.contains(event.relatedTarget)) stopActiveMedia();
  };
  const refresh = async () => {
    if (!onRefresh || refreshing) return;
    setRefreshing(true);
    setRefreshError(null);
    try { await onRefresh(); } catch { setRefreshError("미리보기를 다시 요청하지 못했어요."); } finally { setRefreshing(false); }
  };

  return <section className="vb-preview-stage" aria-label="미리보기" tabIndex={0} onKeyDown={onStageKeyDown} onBlur={onStageBlur}>
    <header className="vb-preview-stage__header"><div><p className="vb-preview-stage__eyebrow">{mode.kind === "audition" ? "소스 미리보기" : "편집본 미리보기"}</p><h2>{mode.kind === "audition" ? "원본을 확인하는 중" : "현재 편집 결과"}</h2></div>{mode.kind === "audition" && exact.kind === "current" && <button type="button" onClick={showExact}>편집본으로 돌아가기</button>}</header>
    <div className="vb-preview-stage__media-shell" aria-busy={exact.kind === "pending" || exact.kind === "running"}>
      {currentMedia && (mode.kind === "audition" && mode.media.mediaKind === "audio"
        ? <audio ref={mediaRef as RefObject<HTMLAudioElement>} aria-label={mediaLabel} src={currentMedia.url} controls preload="metadata" onTimeUpdate={(event) => updateTimeline(event.currentTarget)} onSeeking={(event) => updateTimeline(event.currentTarget)} onSeeked={(event) => updateTimeline(event.currentTarget)} />
        : <video ref={mediaRef as RefObject<HTMLVideoElement>} aria-label={mediaLabel} src={currentMedia.url} controls preload="metadata" playsInline onTimeUpdate={(event) => updateTimeline(event.currentTarget)} onSeeking={(event) => updateTimeline(event.currentTarget)} onSeeked={(event) => updateTimeline(event.currentTarget)} />)}
      {!currentMedia && <div className="vb-preview-stage__empty"><strong>{exact.label}</strong><p>{exact.copy}</p><button type="button" onClick={() => void refresh()} disabled={!onRefresh || refreshing}>{refreshing ? "미리보기 요청 중" : "미리보기 새로 만들기"}</button>{refreshError && <p role="alert">{refreshError}</p>}</div>}
    </div>
    {currentMedia && <div className="vb-preview-stage__playback"><button type="button" onClick={togglePlayback} aria-label="재생 또는 일시정지">재생 / 일시정지</button><output aria-live="off">타임라인 {timelineTime.toFixed(1)}초</output></div>}
    {mode.kind === "exact" && <p className="vb-preview-stage__burned-caption">자막은 영상에 포함되어 재생됩니다.</p>}
    {mode.kind === "exact" && <p role="status" aria-label="현재 자막" aria-live="polite" aria-atomic="true" className="vb-preview-stage__caption-transcript vb-preview-stage__visually-hidden">{activeCaption ? `현재 자막: ${activeCaption.text}` : "현재 자막 없음"}</p>}
    <p role="status" aria-live="polite" className="vb-preview-stage__status">{mode.kind === "audition" ? `소스 미리보기 · 타임라인 ${timelineTime.toFixed(1)}초` : `${exact.copy} 타임라인 ${timelineTime.toFixed(1)}초`}</p>
    {localSources.length > 0 && <section aria-label="소스 미리보기 목록" className="vb-preview-stage__sources"><h3>소스 확인</h3><p>편집본에 적용하지 않고 원본만 확인합니다.</p><div>{localSources.map((source) => <button key={source.id} type="button" onClick={() => showAudition(source)} aria-label={`${source.label} 원본 열기`}>{source.label}</button>)}</div></section>}
  </section>;
}

function exactMediaId(exact: Extract<ReturnType<typeof toExactPreviewState>, { kind: "current" }>): string {
  return `exact:${exact.url}`;
}
function sourceLabel(sources: readonly AuditionSource[], id: string): string {
  return sources.find((source) => source.id === id)?.label ?? "선택한 소스";
}
