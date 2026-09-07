import type { CSSProperties } from "react";
import type { FootageProposal, FootageSegment } from "../../api";
import { Button } from "../../components/ui/button";
import { formatTime } from "./FootageSourceList";

type Props = { proposal: FootageProposal | null; playhead: number; onSelectSegment: (segment: FootageSegment, extend: boolean) => void; selectedSegmentId: string | null; selectedSegmentIds?: string[]; onSplit: () => void; onMerge: () => void; onExclude: () => void; onBoundary: (segment: FootageSegment, edge: "start" | "end", delta: number) => void };

export function SceneTimeline({ proposal, playhead, onSelectSegment, selectedSegmentId, selectedSegmentIds = [], onSplit, onMerge, onExclude, onBoundary }: Props) {
  return <section className="vb-footage-timeline" data-testid="scene-timeline" aria-label="장면 타임라인">
    <div className="vb-footage-timeline__heading"><div><p className="vb-eyebrow">나눈 결과</p><h2>장면 타임라인</h2></div><span>{proposal ? `${proposal.segments.length}개 장면` : "분석 전"}</span></div>
    {!proposal ? <p className="vb-footage-empty">분석을 시작하면 장면 경계가 표시돼요.</p> : <>
      <div className="vb-footage-track" style={{ "--playhead": `${proposal.segments.length ? Math.min(100, playhead / Math.max(...proposal.segments.map((s) => s.end_sec)) * 100) : 0}%` } as CSSProperties}>
        {proposal.segments.map((segment) => <Button type="button" data-multiline="true" variant="ghost" key={segment.segment_id} className="vb-footage-segment" aria-pressed={selectedSegmentIds.includes(segment.segment_id) || selectedSegmentId === segment.segment_id} onClick={(event) => onSelectSegment(segment, event.shiftKey)} style={{ flex: `${Math.max(.08, segment.end_sec - segment.start_sec)} 1 0` }}><strong>{String(segment.confirmed_fields.label ?? segment.machine_fields.label ?? "장면")}</strong><small>{formatTime(segment.start_sec)}–{formatTime(segment.end_sec)}</small></Button>)}
        <button data-native-control="footage-playhead" type="button" className="vb-footage-playhead" aria-label="현재 재생 위치" aria-valuemin={0} aria-valuemax={Math.max(...proposal.segments.map((s) => s.end_sec), 0)} aria-valuenow={playhead} tabIndex={0} />
      </div>
      <div className="vb-footage-timeline__actions"><Button type="button" variant="outline" onClick={() => onBoundary(proposal.segments.find((s) => s.segment_id === selectedSegmentId) ?? proposal.segments[0], "start", -1 / 30)} disabled={!selectedSegmentId}>앞 경계 −1f</Button><Button type="button" variant="outline" onClick={() => onBoundary(proposal.segments.find((s) => s.segment_id === selectedSegmentId) ?? proposal.segments[0], "end", 1 / 30)} disabled={!selectedSegmentId}>뒤 경계 +1f</Button><Button type="button" variant="outline" onClick={onSplit} disabled={!selectedSegmentId}>나누기</Button><Button type="button" variant="outline" onClick={onMerge} disabled={!selectedSegmentId}>합치기</Button><Button type="button" variant="outline" onClick={onExclude} disabled={!selectedSegmentId}>제외</Button></div>
    </>}
  </section>;
}
