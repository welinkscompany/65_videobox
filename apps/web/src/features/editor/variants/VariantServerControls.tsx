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
      <strong>서버 변형 revision {variant.variant_revision}</strong>
      <span>마스터 revision {variant.source_session_revision}</span>
      {hasConflicts ? <span role="status">서버 충돌 {variant.conflicts.length}건</span> : <span>서버 연결됨</span>}
    </div>
    {hasConflicts ? <p className="vb-editor-variants__server-warning">마스터 변경을 확인해야 적용할 수 있어요.</p> : null}
    <div className="vb-editor-variants__server-actions">
      <Button type="button" variant="outline" disabled={busy || hasConflicts} onClick={() => void onMaterialize(variant)}>{label} 변형 준비</Button>
      <Button type="button" variant="outline" disabled={busy} onClick={() => void onPatch(variant, { overrides: { crop: { mode: "creator_adjusted" } } })}>크롭 저장</Button>
      <Button type="button" variant="outline" disabled={busy} onClick={() => void onPatch(variant, { overrides: { caption: { layout: "creator_adjusted" } } })}>자막 저장</Button>
      <Button type="button" disabled={busy} onClick={() => void onPatch(variant, { lock_fields: ["crop", "caption"] })}>크롭·자막 잠금</Button>
      {variant.kind === "vertical_highlight"
        ? <Button type="button" variant="outline" disabled={busy || !masterSegmentIds.length} onClick={() => void onPatch(variant, { selected_segment_ids: [...masterSegmentIds] })}>하이라이트 순서 저장</Button>
        : onCreateHighlight ? <Button type="button" variant="outline" disabled={busy} onClick={() => void onCreateHighlight()}>하이라이트 변형 만들기</Button> : null}
    </div>
  </section>;
}
