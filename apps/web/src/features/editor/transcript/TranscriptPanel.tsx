import { useEffect, useMemo, useState, type KeyboardEvent, type ReactNode } from "react";

import { Button } from "../../../components/ui/button";
import { Textarea } from "../../../components/ui/textarea";
import { resolvePlaybackSelection } from "./playbackNavigation";
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
  onDeleteSegment,
  isSaving = false,
  frameSec = 1 / 30,
  autoCaption,
}: Readonly<{
  entries: readonly TranscriptEntry[];
  playbackSec: number;
  selectedSegmentId: string | null;
  onSelectSegment: (segmentId: string) => void;
  onSeek: (seconds: number) => void;
  onSaveCaption?: (input: { segmentId: string; text: string }) => void;
  /** 브루·캡컷의 "텍스트로 편집": 대본 칸을 **완전히** 비우면 그 장면을
   *  타임라인에서 뺀다(owner 승인 2026-09-18). 이 판은 무엇을 부를지만 알고
   *  실제 삭제는 위층이 이미 가진 "빼기" 경로(`set-cut-action`/`remove`)로
   *  간다 -- 같은 편집이 두 경로를 갖지 않게 한다. */
  onDeleteSegment?: (segmentId: string) => void | Promise<void>;
  isSaving?: boolean;
  /** 한 프레임(초). 작업대와 같은 장면 고르기 규칙(`resolvePlaybackSelection`)에 쓴다. */
  frameSec?: number;
  /** 캡컷 `자동 캡션` 카드. 프로젝트·세션을 아는 위층이 만들어 넘긴다 --
   *  이 판은 캡션 목록만 알면 되고 프로젝트 배관은 몰라도 된다. */
  autoCaption?: ReactNode;
}>) {
  // 작업대(오른쪽 편집 항목)와 **같은 규칙**으로 현재 장면을 고른다 -- 경계에서 두 판이 서로 다른 장면을 가리키지 않게.
  const activeSegmentId = resolvePlaybackSelection(entries, playbackSec, { pinnedSegmentId: selectedSegmentId, frameSec });
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
  // 완전히 빈 문자열로 만들었을 때만 삭제로 읽는다 -- 단어 몇 개만 지우는
  // 것은 이 기능의 범위가 아니라 기존 캡션 수정이 처리한다(과제 지시 3번,
  // 헷갈리지 않게 확실히 구분하라는 요구). 여러 세그먼트에 걸친 삭제는
  // 1단계 범위 밖이라 이 판은 지금 고른 세그먼트 하나만 다룬다.
  const handleDraftChange = (value: string) => {
    if (isSaving) return;
    setDraft(value);
    if (value.trim() === "" && selectedEntry && onDeleteSegment) {
      void onDeleteSegment(selectedEntry.segmentId);
    }
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
        {visibleEntries.map((entry) => <li key={`${entry.segmentId}:${entry.startSec}`}>
          <Button aria-current={entry.segmentId === activeSegmentId ? "true" : undefined} aria-label={`${entry.text} 캡션 선택`} disabled={isSaving} onClick={() => select(entry)} type="button">
            {entry.text} · {seconds(entry.startSec)}–{seconds(entry.endSec)}
          </Button>
        </li>)}
      </ol> : <p>아직 캡션이 없어요.</p>}
      {autoCaption}
      {/* 시간을 여기서 못 고치는 이유를 한 줄로 말한다. 예전에는 이 안내가
          아래에 붙은 요약 절(`CaptionLane`)에 있었는데, 그 절은 바로 위 목록이
          이미 보여 주는 것을 한 벌 더 쌓고 있었다 -- 안내만 남기고 걷어냈다. */}
      <p>캡션 시간은 내레이션 구간을 따라가요.</p>
      {selectedEntry ? <>
        <label htmlFor="vb-transcript-caption">캡션 텍스트</label>
        <Textarea aria-label={`${selectedEntry.segmentId} 캡션 텍스트`} disabled={isSaving} id="vb-transcript-caption" onChange={(event) => handleDraftChange(event.target.value)} onKeyDown={handleEditorKeyDown} value={draft} />
        {/* 완전히 비운 상태는 "캡션 저장"이 아니라 위 onChange의 삭제 경로가
            이미 처리했다(또는 처리하는 중이다) -- 빈 문자열로 저장을 눌러
            빈 캡션을 만드는 혼동을 막는다. */}
        <Button disabled={isSaving || !onSaveCaption || draft === selectedEntry.text || draft.trim() === ""} title={isSaving ? "저장하고 있어요. 잠시 뒤에 눌러 주세요." : !onSaveCaption ? "여기서는 캡션을 저장할 수 없어요." : draft.trim() === "" ? "캡션이 비어 있어요. 글자를 적어 주세요." : draft === selectedEntry.text ? "고친 곳이 아직 없어요. 글자를 고치면 저장할 수 있어요." : undefined} onClick={() => onSaveCaption?.({ segmentId: selectedEntry.segmentId, text: draft })} type="button">캡션 저장</Button>
      </> : null}
    </section>
  </>;
}
