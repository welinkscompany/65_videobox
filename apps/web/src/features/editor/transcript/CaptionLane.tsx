import type { TranscriptEntry } from "./transcriptProjection";

export function CaptionLane({ entries, selectedSegmentId }: Readonly<{ entries: readonly TranscriptEntry[]; selectedSegmentId: string | null }>) {
  const selectedEntry = entries.find((entry) => entry.segmentId === selectedSegmentId) ?? null;
  return <section aria-label="연결 자막" className="vb-editor-workbench__summary">
    <h2>자막</h2>
    <p>자막 시간은 연결된 내레이션 구간을 따릅니다.</p>
    <p>{entries.length}개 연결 자막</p>
    {selectedEntry ? <p aria-current="true">선택한 자막: {selectedEntry.text}</p> : null}
  </section>;
}
