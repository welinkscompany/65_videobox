import { useState } from "react";

import { Button } from "../../../components/ui/button";
import { Input } from "../../../components/ui/input";
import { assetPreferenceChoice, canonicalPreferenceTag, useDirectorPreferences } from "./directorPreferences";
import { filterEditorAssets, type EditorAssetCard, type EditorAssetKind, type EditorAssetOrientation } from "./editorAssetProjection";
import { writeAssetDrag } from "./assetDragPayload";

type EditorAssetTarget = Readonly<{
  segmentId: string;
  startSec: number;
  endSec: number;
}>;

export type EditorAssetPreviewState = Readonly<{ status: "preparing" | "failed" }>;

type Props = Readonly<{
  cards: readonly EditorAssetCard[];
  target: EditorAssetTarget | null;
  isSaving: boolean;
  onPreview: (card: EditorAssetCard) => void;
  onApply: (card: EditorAssetCard, segmentId: string) => void;
  previewStates?: Readonly<Record<string, EditorAssetPreviewState>>;
  onRefreshExactPreview?: () => void;
  /** 있으면 "항상 쓰기 / 쓰지 않기"를 저장한다. 없으면 그 절만 빠진다. */
  projectId?: string;
}>;

const filters: readonly Readonly<{ type: "all" | EditorAssetKind; label: string }>[] = [
  { type: "all", label: "전체" },
  { type: "broll", label: "영상" },
  { type: "bgm", label: "음악" },
  { type: "sfx", label: "효과음" },
];

const orientationFilters: readonly { value: "all" | EditorAssetOrientation; label: string }[] = [
  { value: "all", label: "모든 방향" },
  { value: "가로", label: "가로" },
  { value: "세로", label: "세로" },
];

function targetLabel(target: EditorAssetTarget | null): string {
  return target
    ? `적용 구간: ${target.startSec.toFixed(2)}–${target.endSec.toFixed(2)}초`
    : "적용할 내레이션 구간을 먼저 선택하세요.";
}

export function EditorAssetBrowser({ cards, target, isSaving, onPreview, onApply, previewStates = {}, onRefreshExactPreview, projectId }: Props) {
  const [query, setQuery] = useState("");
  const [type, setType] = useState<"all" | EditorAssetKind>("all");
  const [orientation, setOrientation] = useState<"all" | EditorAssetOrientation>("all");
  const visibleCards = filterEditorAssets(cards, { type, query, orientation });
  const taste = useDirectorPreferences(projectId);
  const tasteReady = Boolean(projectId) && taste.ready;
  const excludedCreators = taste.preferences.exclude_creator;
  const excludedTags = taste.preferences.exclude_tag;

  return <section className="vb-editor-assets" aria-label="편집기 자산">
    <div className="vb-editor-assets__controls">
      <label className="vb-editor-assets__search-label">
        <span>자산 검색</span>
        <Input className="vb-editor-assets__search" type="search" aria-label="자산 검색" value={query} onChange={(event) => setQuery(event.target.value)} />
      </label>
      <div className="vb-editor-assets__filters" role="group" aria-label="자산 유형 필터">
        {filters.map((filter) => <Button key={filter.type} variant="ghost" className="vb-editor-assets__filter" type="button" aria-pressed={type === filter.type} onClick={() => setType(filter.type)}>{filter.label} 필터</Button>)}
      </div>
      <div className="vb-editor-assets__filters" role="group" aria-label="화면 방향 필터">
        {orientationFilters.map((filter) => <Button key={filter.value} variant="ghost" className="vb-editor-assets__filter" type="button" aria-pressed={orientation === filter.value} onClick={() => setOrientation(filter.value)}>{filter.label} 필터</Button>)}
      </div>
    </div>
    <p className="vb-editor-assets__target" role="status">{targetLabel(target)}</p>
    {taste.error ? <p className="vb-editor-assets__detail" role="status">{taste.error}</p> : null}
    {tasteReady && (excludedCreators.length || excludedTags.length) ? (
      <div className="vb-editor-assets__taste" role="group" aria-label="유진이 빼 둔 것">
        <p className="vb-editor-assets__detail">유진이 추천에서 빼 두고 있는 것</p>
        {excludedCreators.map((creator) => (
          <Button
            key={`creator:${creator}`}
            className="vb-editor-assets__filter"
            type="button"
            variant="outline"
            disabled={taste.isSaving}
            aria-label={`${creator} 만든이 다시 쓰기`}
            onClick={() => void taste.setListMember("exclude_creator", creator, false)}
          >
            {`만든이 ${creator} · 다시 쓰기`}
          </Button>
        ))}
        {excludedTags.map((tag) => (
          <Button
            key={`tag:${tag}`}
            className="vb-editor-assets__filter"
            type="button"
            variant="outline"
            disabled={taste.isSaving}
            aria-label={`${tag} 분위기 다시 쓰기`}
            onClick={() => void taste.setListMember("exclude_tag", tag, false)}
          >
            {`분위기 ${tag} · 다시 쓰기`}
          </Button>
        ))}
      </div>
    ) : null}
    <div className="vb-editor-assets__cards">
      {visibleCards.map((card) => {
        const applyDisabled = target === null || isSaving || !card.canApply;
        const previewState = previewStates[card.id];
        const choice = assetPreferenceChoice(taste.preferences, card.assetId);
        const creator = card.sourceMetadata.creator.trim();
        // 캡컷처럼 끌어다 놓을 수 있게 한다. `적용` 단추는 그대로 둔다 --
        // 끌기가 안 되는 환경(키보드만 쓰는 경우 포함)에서도 길이 있어야 한다.
        return <article key={card.id} className="vb-editor-assets__card"
          draggable
          onDragStart={(event) => writeAssetDrag(event.dataTransfer, card.id)}
          title="타임라인의 장면 위로 끌어다 놓을 수 있어요">
          {card.thumbnailUrl ? (
            <img
              className="vb-editor-assets__thumb"
              src={card.thumbnailUrl}
              alt={`${card.title} 미리 이미지`}
              loading="lazy"
            />
          ) : null}
          <h3 className="vb-editor-assets__title">{card.title}</h3>
          <p className="vb-editor-assets__summary">
            {card.label} · {card.durationLabel}
            {card.orientation ? <> · <span className="vb-editor-assets__orientation">{card.orientation}</span></> : null}
          </p>
          <p className="vb-editor-assets__detail">{card.status}</p>
          <p className="vb-editor-assets__detail">{card.audioPresence}</p>
          <p className="vb-editor-assets__detail">{card.license}</p>
          <p className="vb-editor-assets__reason">직접 선택한 자산</p>
          {previewState?.status === "preparing" ? <p role="status">원본 미리보기를 준비하고 있어요</p> : null}
          {previewState?.status === "failed" ? <p role="alert">원본 미리보기를 준비하지 못했어요. 편집과 적용은 계속할 수 있어요.</p> : null}
          <p className="vb-editor-assets__card-target">{targetLabel(target)}</p>
          {tasteReady ? (
            <div className="vb-editor-assets__taste" role="group" aria-label={`${card.title} 추천 취향`}>
              <p className="vb-editor-assets__detail">
                {choice === "always"
                  ? "유진이 먼저 고려해요."
                  : choice === "never"
                    ? "유진이 추천에서 빼요."
                    : "유진에게 이 자산을 어떻게 다룰지 알려 줄 수 있어요."}
              </p>
              <Button
                className="vb-editor-assets__filter"
                type="button"
                variant="outline"
                disabled={taste.isSaving}
                aria-pressed={choice === "always"}
                aria-label={`${card.title} 항상 쓰기`}
                onClick={() => void taste.setAssetChoice(card.assetId, choice === "always" ? "none" : "always")}
              >
                항상 쓰기
              </Button>
              <Button
                className="vb-editor-assets__filter"
                type="button"
                variant="outline"
                disabled={taste.isSaving}
                aria-pressed={choice === "never"}
                aria-label={`${card.title} 쓰지 않기`}
                onClick={() => void taste.setAssetChoice(card.assetId, choice === "never" ? "none" : "never")}
              >
                쓰지 않기
              </Button>
              {creator ? (
                <Button
                  className="vb-editor-assets__filter"
                  type="button"
                  variant="outline"
                  disabled={taste.isSaving}
                  aria-pressed={excludedCreators.includes(creator)}
                  aria-label={`${card.title}의 만든이 ${creator} 빼기`}
                  onClick={() => void taste.setListMember(
                    "exclude_creator",
                    creator,
                    !excludedCreators.includes(creator),
                  )}
                >
                  {`만든이 ${creator} 빼기`}
                </Button>
              ) : null}
              {card.sourceMetadata.tags.map((tag) => {
                const stored = canonicalPreferenceTag(tag);
                if (!stored) return null;
                return (
                  <Button
                    key={`${card.id}:${stored}`}
                    className="vb-editor-assets__filter"
                    type="button"
                    variant="outline"
                    disabled={taste.isSaving}
                    aria-pressed={excludedTags.includes(stored)}
                    aria-label={`${card.title}의 분위기 ${tag} 빼기`}
                    onClick={() => void taste.setListMember(
                      "exclude_tag",
                      stored,
                      !excludedTags.includes(stored),
                    )}
                  >
                    {`분위기 ${tag} 빼기`}
                  </Button>
                );
              })}
            </div>
          ) : null}
          <div className="vb-editor-assets__actions">
            <Button type="button" aria-label={`${card.title} ${previewState?.status === "failed" ? "다시 준비" : "원본 미리보기"}`} disabled={!card.previewUrl || previewState?.status === "preparing"} onClick={() => onPreview(card)}>{previewState?.status === "failed" ? "다시 준비" : "원본 미리보기"}</Button>
            {previewState?.status === "failed" && onRefreshExactPreview ? <Button type="button" variant="outline" onClick={onRefreshExactPreview}>정확한 미리보기 새로고침</Button> : null}
            <Button type="button" aria-label={`${card.title} 적용`} disabled={applyDisabled} onClick={() => target && onApply(card, target.segmentId)}>적용</Button>
          </div>
        </article>;
      })}
    </div>
    {visibleCards.length === 0 ? <p className="vb-editor-assets__empty">일치하는 자산이 없어요.</p> : null}
  </section>;
}
