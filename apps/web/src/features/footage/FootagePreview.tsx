import type { LibraryAsset } from "../../api";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { formatTime } from "./FootageSourceList";

type Props = { asset: LibraryAsset | null; currentTime: number; duration: number; frameStep: number; onTimeChange: (time: number) => void; onFrameStep: (delta: number) => void };

export function FootagePreview({ asset, currentTime, duration, frameStep, onTimeChange, onFrameStep }: Props) {
  const filename = asset ? String(asset.user_metadata?.filename ?? asset.library_asset_id) : "촬영본을 선택하세요";
  return <section className="vb-footage-pane vb-footage-preview" data-testid="footage-preview">
    <div className="vb-footage-pane__heading"><div><p className="vb-eyebrow">PREVIEW</p><h2>{filename}</h2></div><span>{formatTime(currentTime)} / {formatTime(duration)}</span></div>
    <div className="vb-footage-player">{asset ? <video controls preload="metadata" src={asset.preview_url ?? undefined} aria-label={`${filename} 미리보기`} /> : <p>선택한 촬영본의 미리보기가 여기에 표시돼요.</p>}</div>
    <div className="vb-footage-waveform" aria-label="오디오 파형" role="img">{Array.from({ length: 48 }, (_, index) => <i key={index} style={{ height: `${20 + ((index * 37) % 75)}%` }} />)}<b style={{ left: `${duration ? Math.min(100, currentTime / duration * 100) : 0}%` }} aria-hidden="true" /></div>
    <div className="vb-footage-transport"><Button type="button" variant="outline" onClick={() => onFrameStep(-1)} aria-label="1프레임 뒤로">−1f</Button><Button type="button" variant="outline" onClick={() => onFrameStep(1)} aria-label="1프레임 앞으로">+1f</Button><label>프레임 간격 <Input aria-label="프레임 간격" type="number" min="1" max="120" value={Math.round(1 / frameStep)} readOnly /> fps</label><output>{frameStep.toFixed(2)}초 이동</output></div>
    <Input className="vb-footage-scrubber" aria-label="재생 위치" type="range" min="0" max={duration || 1} step={frameStep} value={Math.min(currentTime, duration || 1)} onChange={(event) => onTimeChange(Number(event.target.value))} />
  </section>;
}
