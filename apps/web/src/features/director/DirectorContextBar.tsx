export function DirectorContextBar({ segmentId, timecode, placement, revision, draftApplied }: { segmentId?: string; timecode?: string; placement?: string; revision?: string; draftApplied?: boolean }) {
  return <p aria-label="디렉터 컨텍스트">{segmentId ?? "세그먼트 미선택"} · {timecode ?? "--:--"} · {placement ?? "배치 미선택"} · {revision ?? "제안 없음"}{draftApplied ? " · 초안 적용됨" : ""}</p>;
}
