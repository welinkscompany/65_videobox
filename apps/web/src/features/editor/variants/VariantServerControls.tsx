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
  onRemakeShortForm,
  onUnfoldShortForm,
  masterSegmentIds = [],
  busy = false,
}: Readonly<{
  variant: OutputVariant;
  onMaterialize: (variant: OutputVariant) => void | Promise<void>;
  onPatch: (variant: OutputVariant, patch: OutputVariantPatch) => void | Promise<void>;
  onCreateHighlight?: () => void | Promise<void>;
  /** 이미 있는 숏폼의 장면을 **다시 판단해** 갈아 끼운다. 숏폼은 한 편집본에
   *  하나뿐이라(유일 제약) 두 번 만들 수 없고, 지우는 문도 없다 -- 그래서
   *  `만들기` 단추는 한 번 쓰면 조용히 죽어 있었다. */
  onRemakeShortForm?: (variant: OutputVariant) => void | Promise<void>;
  /** 숏폼을 **따로 편집할 수 있는 편집본으로 펼친다.** 숏폼에는 장면별 편집을
   *  담을 자리가 없어서, 펼치지 않고 숏폼의 한 장면을 고치면 원본 영상의 그
   *  장면도 같이 바뀐다. */
  onUnfoldShortForm?: (variant: OutputVariant) => void | Promise<void>;
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
          넣는다. 자동 숏폼 고르기(owner 결정 2026-08-28, 2026-09-11부터는
          유진이 고른다 -- `short_form_scene_pick.py`)가
          고른 결과가 마음에 안 들 때 쓰는 리셋 단추이지, 순서를 저장하는 단추가
          아니다. 이름이 실제 동작과 달라 헷갈렸던 것을 여기서 바로잡는다. */}
      {variant.kind === "vertical_highlight"
        ? <>
          <Button type="button" variant="outline" disabled={busy || !masterSegmentIds.length} onClick={() => void onPatch(variant, { selected_segment_ids: [...masterSegmentIds] })}>전체 장면으로 되돌리기</Button>
          {/* 다시 만들기는 **새 숏폼을 만들지 않는다** -- 이 숏폼의 장면을 다시
              골라 갈아 끼운다. 지우는 문을 내지 않은 이유는 되돌릴 길이 없어지기
              때문이고, 되돌리기는 바로 위 단추(통째 목록 PATCH)가 지킨다. */}
          {onRemakeShortForm ? <Button type="button" variant="outline" disabled={busy} onClick={() => void onRemakeShortForm(variant)}>숏폼 다시 만들기</Button> : null}
          {/* **받아 보고 손보는 문.** 숏폼은 장면 목록과 화면 전체 설정만
              들 수 있어서, 펼치지 않고 숏폼의 한 장면을 고치면 원본 영상의
              그 장면도 같이 바뀐다. 펼치면 자막·확대·전환·효과음·되돌리기가
              전부 그 판에서 그대로 된다. 규칙은 아래 한 줄로 미리 말한다 --
              되돌릴 수 없는 일이라 누른 뒤에 알리면 늦다. */}
          {onUnfoldShortForm ? <Button type="button" variant="outline" disabled={busy} onClick={() => void onUnfoldShortForm(variant)}>숏폼을 편집본으로 펼치기</Button> : null}
        </>
        : onCreateHighlight ? <Button type="button" variant="outline" disabled={busy} onClick={() => void onCreateHighlight()}>하이라이트 변형 만들기</Button> : null}
    </div>
    {/* **규칙을 누르기 전에 말한다.** 펼치면 원본과의 줄이 끊기고 그건 되돌릴 수
        없다 -- 누른 뒤에 알리면 늦다. 문장은 서버(`UNFOLD_INDEPENDENCE_RULE`)와
        같은 말이어야 한다. */}
    {variant.kind === "vertical_highlight" && onUnfoldShortForm
      ? <p className="vb-editor-variants__server-note">펼치면 독립된 편집본이 되고, 그 뒤 원본을 고쳐도 따라오지 않아요.</p>
      : null}
  </section>;
}
