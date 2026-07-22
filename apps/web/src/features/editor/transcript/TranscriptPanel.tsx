import { useEffect, useMemo, useState, type KeyboardEvent } from "react";

import { CaptionLane } from "./CaptionLane";
import { activeSegmentIdAt } from "./playbackNavigation";
import { visibleTranscriptWindow, type TranscriptEntry } from "./transcriptProjection";

const MAX_MOUNTED_ROWS = 120;

function seconds(value: number): string { return `${value.toFixed(1)}초`; }

export function TranscriptPanel({
  entries,
  playbackSec,
  selectedSegmentId,
  onSelectSegment,
  onSeek,
  onSaveCaption,
  isSaving = false,
}: Readonly<{
  entries: readonly TranscriptEntry[];
  playbackSec: number;
  selectedSegmentId: string | null;
  onSelectSegment: (segmentId: string) => void;
  onSeek: (seconds: number) => void;
  onSaveCaption?: (input: { segmentId: string; text: string }) => void;
  isSaving?: boolean;
}>) {
  const activeSegmentId = activeSegmentIdAt(entries, playbackSec);
  const currentSegmentId = selectedSegmentId ?? activeSegmentId;
  const selectedEntry = entries.find((entry) => entry.segmentId === currentSegmentId) ?? null;
  const [draft, setDraft] = useState(selectedEntry?.text ?? "");
  useEffect(() => { setDraft(selectedEntry?.text ?? ""); }, [selectedEntry?.segmentId, selectedEntry?.text]);
  const activeIndex = Math.max(0, entries.findIndex((entry) => entry.segmentId === currentSegmentId));
  const visibleEntries = useMemo(() => visibleTranscriptWindow(entries, activeIndex, MAX_MOUNTED_ROWS), [activeIndex, entries]);
  const select = (entry: TranscriptEntry) => { onSelectSegment(entry.segmentId); onSeek(entry.startSec); };
  const selectRelative = (offset: number) => {
    const index = entries.findIndex((entry) => entry.segmentId === currentSegmentId);
    const next = entries[Math.max(0, Math.min(entries.length - 1, (index === -1 ? 0 : index) + offset))];
    if (next) select(next);
  };
  const handleEditorKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.nativeEvent.isComposing || (event as unknown as { isComposing?: boolean }).isComposing) return;
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      selectRelative(event.key === "ArrowDown" ? 1 : -1);
    }
  };
  return <>
    <section aria-label="대본" className="vb-editor-workbench__summary">
      <h2>대본</h2>
      {visibleEntries.length ? <ol>
        {visibleEntries.map((entry) => <li key={entry.segmentId}>
          <button aria-current={entry.segmentId === activeSegmentId ? "true" : undefined} aria-label={`${entry.text} 대본 선택`} onClick={() => select(entry)} type="button">
            {entry.text} · {seconds(entry.startSec)}–{seconds(entry.endSec)}
          </button>
        </li>)}
      </ol> : <p>연결된 대본이 없습니다.</p>}
      {selectedEntry ? <>
        <label htmlFor="vb-transcript-caption">자막 텍스트</label>
        <textarea aria-label={`${selectedEntry.segmentId} 자막 텍스트`} id="vb-transcript-caption" onChange={(event) => setDraft(event.target.value)} onKeyDown={handleEditorKeyDown} value={draft} />
        <button disabled={isSaving || !onSaveCaption || draft === selectedEntry.text} onClick={() => onSaveCaption?.({ segmentId: selectedEntry.segmentId, text: draft })} type="button">자막 저장</button>
      </> : null}
    </section>
    <CaptionLane entries={entries} selectedSegmentId={currentSegmentId} />
  </>;
}
