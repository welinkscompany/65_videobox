import { useEffect, useMemo, useState, type KeyboardEvent, type ReactNode } from "react";

import { Button } from "../../../components/ui/button";
import { Textarea } from "../../../components/ui/textarea";
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
  autoCaption,
}: Readonly<{
  entries: readonly TranscriptEntry[];
  playbackSec: number;
  selectedSegmentId: string | null;
  onSelectSegment: (segmentId: string) => void;
  onSeek: (seconds: number) => void;
  onSaveCaption?: (input: { segmentId: string; text: string }) => void;
  isSaving?: boolean;
  /** 캡컷 `자동 캡션` 카드. 프로젝트·세션을 아는 위층이 만들어 넘긴다 --
   *  이 판은 캡션 목록만 알면 되고 프로젝트 배관은 몰라도 된다. */
  autoCaption?: ReactNode;
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
    <section aria-label="캡션" className="vb-editor-workbench__summary">
      <h2>캡션</h2>
      {visibleEntries.length ? <ol>
        {visibleEntries.map((entry) => <li key={entry.segmentId}>
          <Button aria-current={entry.segmentId === activeSegmentId ? "true" : undefined} aria-label={`${entry.text} 캡션 선택`} disabled={isSaving} onClick={() => select(entry)} type="button">
            {entry.text} · {seconds(entry.startSec)}–{seconds(entry.endSec)}
          </Button>
        </li>)}
      </ol> : <p>아직 캡션이 없어요.</p>}
      {autoCaption}
      {/* 시간을 여기서 못 고치는 이유를 한 줄로 말한다. 예전에는 이 안내가
          아래에 붙은 요약 절(`CaptionLane`)에 있었는데, 그 절은 바로 위 목록이
          이미 보여 주는 것을 한 벌 더 쌓고 있었다 -- 안내만 남기고 걷어냈다. */}
      <p>캡션 시간은 연결된 내레이션 구간을 따릅니다.</p>
      {selectedEntry ? <>
        <label htmlFor="vb-transcript-caption">캡션 텍스트</label>
        <Textarea aria-label={`${selectedEntry.segmentId} 캡션 텍스트`} disabled={isSaving} id="vb-transcript-caption" onChange={(event) => { if (!isSaving) setDraft(event.target.value); }} onKeyDown={handleEditorKeyDown} value={draft} />
        <Button disabled={isSaving || !onSaveCaption || draft === selectedEntry.text} onClick={() => onSaveCaption?.({ segmentId: selectedEntry.segmentId, text: draft })} type="button">캡션 저장</Button>
      </> : null}
    </section>
  </>;
}
