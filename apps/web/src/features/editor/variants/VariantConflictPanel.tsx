import { Button } from "../../../components/ui/button";
import type { VariantConflict } from "./variantProjection";

// task-3-brief.md: 여기서 `conflict.field`/`conflict.reason`을 그대로
// 찍었었다(예: `crop`, `master_changed_while_locked`) -- `VariantOutputCard`의
// `사유: {item.error_code}`와 같은 병이다. 백엔드 사유는 닫힌 Literal 두
// 값뿐이라(`output_variants.py:77`) 표가 작다. `OutputsPage.tsx`의 실패 사유
// 표(`outputFailureMessages.ts`)와는 다른 어휘라 나눠 쓰지 않는다 -- 그
// 표는 렌더 실패 코드, 이 표는 세로 변형 충돌 필드·사유다. 두 번째로
// 만들지 말라는 지시는 "같은 어휘를 또 만들지 말라"는 뜻이지, 다른 어휘까지
// 하나로 합치라는 뜻이 아니다.
const VARIANT_CONFLICT_FIELD_LABELS: Record<string, string> = {
  crop: "자르기(크롭)",
  focal: "초점",
  caption: "자막 배치",
  safe_area: "안전 영역",
  audio: "소리",
  story: "스토리",
  segment_order: "장면 순서",
};

const VARIANT_CONFLICT_REASON_MESSAGES: Record<string, string> = {
  master_changed_while_locked: "마스터가 바뀌었는데 이 항목은 고정돼 있어요. 고정을 풀고 마스터 기준으로 맞추거나, 지금 상태를 유지하세요.",
  master_changed_while_overridden: "마스터가 바뀌었는데 이 항목은 직접 손본 상태예요. 직접 조정을 유지하거나 마스터 기준으로 다시 맞추세요.",
};

/** 표에 없는 항목·사유가 와도 코드를 그대로 보여주지 않는다 -- 아는 것은
 *  구체적으로, 모르는 것은 "무언가 달라졌다"까지만 말한다(`outputFailureMessages.ts`가
 *  이미 쓰는 방식과 같은 방침). */
function conflictFieldLabel(field: string): string {
  return VARIANT_CONFLICT_FIELD_LABELS[field] ?? "이 설정";
}

function conflictReasonMessage(reason: string): string {
  return VARIANT_CONFLICT_REASON_MESSAGES[reason] ?? "마스터가 그 사이에 바뀌었어요. 어느 쪽을 따를지 골라 주세요.";
}

export function VariantConflictPanel({
  conflicts,
  onKeep,
  onRebase,
}: Readonly<{
  conflicts: readonly VariantConflict[];
  onKeep: (field: string) => void;
  onRebase: (field: string) => void;
}>) {
  if (!conflicts.length) return null;
  return <section className="vb-editor-variants__conflicts" aria-label="세로 변형 충돌">
    <h3>세로 편집과 마스터가 달라요</h3>
    {conflicts.map((conflict) => <article key={conflict.field}>
      <strong>{conflictFieldLabel(conflict.field)}</strong><p>{conflictReasonMessage(conflict.reason)}</p>
      <div><Button type="button" variant="outline" onClick={() => onKeep(conflict.field)}>직접 조정 유지</Button><Button type="button" onClick={() => onRebase(conflict.field)}>마스터 기준 다시 맞추기</Button></div>
    </article>)}
  </section>;
}
