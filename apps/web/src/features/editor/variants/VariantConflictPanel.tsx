import { Button } from "../../../components/ui/button";
import type { VariantConflict } from "./variantProjection";

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
      <strong>{conflict.field}</strong><p>{conflict.reason}</p>
      <div><Button type="button" variant="outline" onClick={() => onKeep(conflict.field)}>직접 조정 유지</Button><Button type="button" onClick={() => onRebase(conflict.field)}>마스터 기준 다시 맞추기</Button></div>
    </article>)}
  </section>;
}
