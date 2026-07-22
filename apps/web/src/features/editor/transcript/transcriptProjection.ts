import type { TimedSegment } from "./playbackNavigation";

export type TranscriptCaption = TimedSegment & Readonly<{ text: string }>;
export type TranscriptEntry = TranscriptCaption;

export function projectTranscriptEntries(input: Readonly<{ narration: readonly TimedSegment[]; captions: readonly TranscriptCaption[] }>): TranscriptEntry[] {
  const narration = new Map(input.narration.filter((item) => item.endSec > item.startSec).map((item) => [item.segmentId, item]));
  return input.captions
    .filter((caption) => narration.has(caption.segmentId) && caption.endSec > caption.startSec)
    .map((caption) => ({ ...caption, startSec: narration.get(caption.segmentId)!.startSec, endSec: narration.get(caption.segmentId)!.endSec }))
    .sort((left, right) => left.startSec - right.startSec || left.segmentId.localeCompare(right.segmentId));
}

export function visibleTranscriptWindow(entries: readonly TranscriptEntry[], activeIndex: number, maxRows: number): TranscriptEntry[] {
  if (!Number.isSafeInteger(maxRows) || maxRows < 1) throw new RangeError("maxRows must be a positive safe integer");
  const index = Math.max(0, Math.min(entries.length - 1, activeIndex));
  const start = Math.max(0, Math.min(index - Math.floor(maxRows / 2), Math.max(0, entries.length - maxRows)));
  return entries.slice(start, start + maxRows);
}
