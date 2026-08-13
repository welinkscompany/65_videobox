import { Button } from "../../../components/ui/button";
import type { VariantKind } from "./variantProjection";

const choices: readonly { kind: VariantKind | "side_by_side"; label: string }[] = [
  { kind: "master", label: "마스터" },
  { kind: "horizontal", label: "가로" },
  { kind: "vertical_full", label: "세로" },
  { kind: "side_by_side", label: "나란히" },
];

export function VariantSelector({
  selected,
  onSelect,
}: Readonly<{
  selected: VariantKind | "side_by_side";
  onSelect: (kind: VariantKind | "side_by_side") => void;
}>) {
  return <div className="vb-editor-variants__selector" role="tablist" aria-label="출력 변형 보기">
    {choices.map((choice) => <Button
      key={choice.kind}
      type="button"
      role="tab"
      aria-selected={selected === choice.kind}
      variant={selected === choice.kind ? "default" : "outline"}
      onClick={() => onSelect(choice.kind)}
    >{choice.label}</Button>)}
  </div>;
}
