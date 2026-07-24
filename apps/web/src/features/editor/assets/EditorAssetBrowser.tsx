import { useState } from "react";

import { Button } from "../../../components/ui/button";
import { Input } from "../../../components/ui/input";
import { filterEditorAssets, type EditorAssetCard, type EditorAssetKind } from "./editorAssetProjection";

type EditorAssetTarget = Readonly<{
  segmentId: string;
  startSec: number;
  endSec: number;
}>;

type Props = Readonly<{
  cards: readonly EditorAssetCard[];
  target: EditorAssetTarget | null;
  isSaving: boolean;
  onPreview: (card: EditorAssetCard) => void;
  onApply: (card: EditorAssetCard, segmentId: string) => void;
}>;

const filters: readonly Readonly<{ type: "all" | EditorAssetKind; label: string }>[] = [
  { type: "all", label: "전체" },
  { type: "broll", label: "B-roll" },
  { type: "bgm", label: "BGM" },
  { type: "sfx", label: "SFX" },
];

function targetLabel(target: EditorAssetTarget | null): string {
  return target
    ? `적용 구간: ${target.startSec.toFixed(2)}–${target.endSec.toFixed(2)}초`
    : "적용할 나레이션 구간을 먼저 선택하세요.";
}

export function EditorAssetBrowser({ cards, target, isSaving, onPreview, onApply }: Props) {
  const [query, setQuery] = useState("");
  const [type, setType] = useState<"all" | EditorAssetKind>("all");
  const visibleCards = filterEditorAssets(cards, { type, query });

  return <section className="vb-editor-assets" aria-label="편집기 자산">
    <div className="vb-editor-assets__controls">
      <label className="vb-editor-assets__search-label">
        <span>자산 검색</span>
        <Input className="vb-editor-assets__search" type="search" aria-label="자산 검색" value={query} onChange={(event) => setQuery(event.target.value)} />
      </label>
      <div className="vb-editor-assets__filters" role="group" aria-label="자산 유형 필터">
        {filters.map((filter) => <Button key={filter.type} className="vb-editor-assets__filter" type="button" aria-pressed={type === filter.type} onClick={() => setType(filter.type)}>{filter.label} 필터</Button>)}
      </div>
    </div>
    <p className="vb-editor-assets__target" role="status">{targetLabel(target)}</p>
    <div className="vb-editor-assets__cards">
      {visibleCards.map((card) => {
        const applyDisabled = target === null || isSaving || !card.canApply;
        return <article key={card.id} className="vb-editor-assets__card">
          <h3 className="vb-editor-assets__title">{card.title}</h3>
          <p className="vb-editor-assets__summary">{card.label} · {card.durationLabel}</p>
          <p className="vb-editor-assets__detail">{card.status}</p>
          <p className="vb-editor-assets__detail">{card.audioPresence}</p>
          <p className="vb-editor-assets__detail">{card.license}</p>
          <p className="vb-editor-assets__reason">직접 선택한 자산</p>
          <p className="vb-editor-assets__card-target">{targetLabel(target)}</p>
          <div className="vb-editor-assets__actions">
            <Button type="button" aria-label={`${card.title} 원본 미리보기`} disabled={!card.previewUrl} onClick={() => onPreview(card)}>원본 미리보기</Button>
            <Button type="button" aria-label={`${card.title} 적용`} disabled={applyDisabled} onClick={() => target && onApply(card, target.segmentId)}>적용</Button>
          </div>
        </article>;
      })}
    </div>
    {visibleCards.length === 0 ? <p className="vb-editor-assets__empty">일치하는 자산이 없어요.</p> : null}
  </section>;
}
