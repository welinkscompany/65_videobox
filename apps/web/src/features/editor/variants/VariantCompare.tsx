import { Button } from "../../../components/ui/button";
import type { VariantProjection } from "./variantProjection";

function pane(projection: VariantProjection, onSeek: (seconds: number) => void) {
  return <section className="vb-editor-variants__pane" aria-label={`${projection.label} 미리보기`}>
    <header><strong>{projection.label}</strong><span>{projection.aspectRatio}</span></header>
    <div className="vb-editor-variants__canvas" data-aspect-ratio={projection.aspectRatio}>
      <span>안전 영역: {projection.safeArea}</span>
      <span>크롭: {projection.crop}</span>
      <span>초점 {Math.round(projection.focalPoint.x * 100)}% · {Math.round(projection.focalPoint.y * 100)}%</span>
    </div>
    <output aria-label={`${projection.label} 재생 위치`}>재생 위치 {projection.playheadSec.toFixed(1)}초</output>
    <Button type="button" variant="ghost" onClick={() => onSeek(5)} aria-label="재생 위치 5.0초로 이동">5초로 이동</Button>
  </section>;
}

export function VariantCompare({
  master,
  variant,
  onSeek,
}: Readonly<{
  master: VariantProjection;
  variant: VariantProjection;
  onSeek: (seconds: number) => void;
}>) {
  return <section className="vb-editor-variants__compare" aria-label="가로·세로 비교">
    <div className="vb-editor-variants__audio-note">오디오는 마스터만 재생</div>
    {pane(master, onSeek)}
    {pane(variant, onSeek)}
  </section>;
}
