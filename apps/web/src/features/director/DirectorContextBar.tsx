export function DirectorContextBar({ segmentId, timecode, placement, revision, draftApplied }: { segmentId?: string; timecode?: string; placement?: string; revision?: string; draftApplied?: boolean }) {
  void segmentId;
  void placement;
  void revision;
  return <p aria-label="현재 선택 위치">선택한 장면 · {timecode ?? "시간 정보 없음"}{draftApplied ? " · 편집본에 적용됨" : ""}</p>;
}
