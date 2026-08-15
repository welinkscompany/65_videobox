import { useEffect, useRef } from "react";
import type { LibraryAsset } from "../../api";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { formatTime } from "./FootageSourceList";

type Range = { start_sec: number; end_sec: number };
type Props = { asset: LibraryAsset | null; previewUrl?: string | null; previewRanges?: Range[]; previewUnavailable?: boolean; currentTime: number; duration: number; frameStep: number; onTimeChange: (time: number) => void; onFrameStep: (delta: number) => void; onPreviewError?: () => void };

function sourceToPreviewTime(sourceTime: number, ranges: Range[]) { let offset = 0; for (const range of ranges) { if (sourceTime <= range.start_sec) return offset; if (sourceTime <= range.end_sec) return offset + sourceTime - range.start_sec; offset += range.end_sec - range.start_sec; } return offset; }
function previewToSourceTime(previewTime: number, ranges: Range[]) { let offset = 0; for (const range of ranges) { const length = range.end_sec - range.start_sec; if (previewTime <= offset + length) return range.start_sec + Math.max(0, previewTime - offset); offset += length; } return ranges.length ? ranges[ranges.length - 1].end_sec : previewTime; }

export function FootagePreview({ asset, previewUrl, previewRanges = [], previewUnavailable = false, currentTime, duration, frameStep, onTimeChange, onFrameStep, onPreviewError }: Props) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const filename = asset ? String(asset.user_metadata?.filename ?? asset.library_asset_id) : "촬영본을 선택하세요";
  useEffect(() => {
    const video = videoRef.current;
    const target = previewUrl && previewRanges.length ? sourceToPreviewTime(currentTime, previewRanges) : currentTime;
    if (video && Math.abs(video.currentTime - target) > frameStep) { try { video.currentTime = target; } catch { /* jsdom media elements expose a read-only clock */ } }
  }, [currentTime, frameStep, previewRanges, previewUrl]);
  return <section className="vb-footage-pane vb-footage-preview" data-testid="footage-preview">
    <div className="vb-footage-pane__heading"><div><p className="vb-eyebrow">PREVIEW</p><h2>{filename}</h2></div><span>{formatTime(currentTime)} / {formatTime(duration)}</span></div>
    <div className="vb-footage-player">{previewUnavailable ? <p role="alert">제안 미리보기를 재생할 수 없습니다. 다시 준비하세요.</p> : asset ? <video ref={videoRef} controls preload="metadata" src={previewUrl ?? asset.preview_url ?? undefined} aria-label={`${filename} 미리보기`} data-testid="footage-video" onError={onPreviewError} onTimeUpdate={(event) => onTimeChange(previewUrl && previewRanges.length ? previewToSourceTime(event.currentTarget.currentTime, previewRanges) : event.currentTarget.currentTime)} onSeeked={(event) => onTimeChange(previewUrl && previewRanges.length ? previewToSourceTime(event.currentTarget.currentTime, previewRanges) : event.currentTarget.currentTime)} /> : <p>선택한 촬영본의 미리보기가 여기에 표시돼요.</p>}</div>
    <div className="vb-footage-waveform" aria-label="오디오 파형" role="img">{Array.from({ length: 48 }, (_, index) => <i key={index} style={{ height: `${20 + ((index * 37) % 75)}%` }} />)}<b style={{ left: `${duration ? Math.min(100, currentTime / duration * 100) : 0}%` }} aria-hidden="true" /></div>
    <div className="vb-footage-transport"><Button type="button" variant="outline" onClick={() => onFrameStep(-1)} aria-label="1프레임 뒤로">−1f</Button><Button type="button" variant="outline" onClick={() => onFrameStep(1)} aria-label="1프레임 앞으로">+1f</Button><label>프레임 간격 <Input aria-label="프레임 간격" type="number" min="1" max="120" value={Math.round(1 / frameStep)} readOnly /> fps</label><output>{frameStep.toFixed(2)}초 이동</output></div>
    <Input className="vb-footage-scrubber" aria-label="재생 위치" type="range" min="0" max={duration || 1} step={frameStep} value={Math.min(currentTime, duration || 1)} onChange={(event) => onTimeChange(Number(event.target.value))} />
    <div className="vb-footage-sr-status" role="status" aria-label="재생 위치" aria-live="polite">재생 위치 {formatTime(currentTime)}</div>
  </section>;
}
