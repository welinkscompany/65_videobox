import type { OutputVariant, OutputVariantPatch } from "../../../api";
import { Button } from "../../../components/ui/button";

function variantLabel(kind: OutputVariant["kind"]): string {
  return kind === "horizontal" ? "가로" : kind === "vertical_highlight" ? "세로 하이라이트" : "세로";
}

export function VariantServerControls({
  variant,
  onMaterialize,
  onPatch,
  onCreateHighlight,
  masterSegmentIds = [],
  busy = false,
}: Readonly<{
  variant: OutputVariant;
  onMaterialize: (variant: OutputVariant) => void | Promise<void>;
  onPatch: (variant: OutputVariant, patch: OutputVariantPatch) => void | Promise<void>;
  onCreateHighlight?: () => void | Promise<void>;
  masterSegmentIds?: readonly string[];
  busy?: boolean;
}>) {
  const label = variantLabel(variant.kind);
  const hasConflicts = variant.conflicts.length > 0;
  return <section className="vb-editor-variants__server-controls" aria-label={`${label} 서버 변형 제어`}>
    <div className="vb-editor-variants__server-line">
      <strong>서버 변형 버전 {variant.variant_revision}</strong>
      <span>마스터 버전 {variant.source_session_revision}</span>
      {hasConflicts ? <span role="status">서버 충돌 {variant.conflicts.length}건</span> : <span>서버 연결됨</span>}
    </div>
    {hasConflicts ? <p className="vb-editor-variants__server-warning">마스터 변경을 확인해야 적용할 수 있어요.</p> : null}
    <div className="vb-editor-variants__server-actions">
      <Button type="button" variant="outline" disabled={busy || hasConflicts} onClick={() => void onMaterialize(variant)}>{label} 변형 준비</Button>
      <Button type="button" variant="outline" disabled={busy} onClick={() => void onPatch(variant, { overrides: { crop: { mode: "creator_adjusted" } } })}>크롭 저장</Button>
      <Button type="button" variant="outline" disabled={busy} onClick={() => void onPatch(variant, { overrides: { caption: { layout: "creator_adjusted" } } })}>캡션 저장</Button>
      <Button type="button" disabled={busy} onClick={() => void onPatch(variant, { lock_fields: ["crop", "caption"] })}>크롭·캡션 잠금</Button>
      {/* **이 단추가 실제로 하는 일은 "선택을 다시 고르는 것"이 아니라 "전체
          장면으로 되돌리는 것"이다** -- `selected_segment_ids`에 마스터 전체를
          넣는다. 자동 하이라이트(owner 결정 2026-08-28, `highlight_scoring.py`)가
          고른 결과가 마음에 안 들 때 쓰는 리셋 단추이지, 순서를 저장하는 단추가
          아니다. 이름이 실제 동작과 달라 헷갈렸던 것을 여기서 바로잡는다. */}
      {variant.kind === "vertical_highlight"
        ? <Button type="button" variant="outline" disabled={busy || !masterSegmentIds.length} onClick={() => void onPatch(variant, { selected_segment_ids: [...masterSegmentIds] })}>전체 장면으로 되돌리기</Button>
        : onCreateHighlight ? <Button type="button" variant="outline" disabled={busy} onClick={() => void onCreateHighlight()}>하이라이트 변형 만들기</Button> : null}
    </div>
  </section>;
}
