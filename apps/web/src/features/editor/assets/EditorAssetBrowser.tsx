import { useEffect, useState } from "react";

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
  /** 이미지 카드를 장면 위에 오버레이로 얹는다. 없으면 그 단추만 빠진다. */
  onApplyOverlay?: (card: EditorAssetCard, segmentId: string) => void;
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
  { type: "image", label: "그림" },
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

/** 한 번에 그리는 카드 수. 한 화면에서 훑을 수 있는 만큼이다. */
const FIRST_PAGE = 8;

export function EditorAssetBrowser({ cards, target, isSaving, onPreview, onApply, onApplyOverlay, previewStates = {}, onRefreshExactPreview, projectId }: Props) {
  const [query, setQuery] = useState("");
  const [type, setType] = useState<"all" | EditorAssetKind>("all");
  const [orientation, setOrientation] = useState<"all" | EditorAssetOrientation>("all");
  const matchingCards = filterEditorAssets(cards, { type, query, orientation });
  // owner: "자산 내역에 스크롤이 엄청 길다니까."
  //
  // 카드 한 장에 썸네일·제목·설명·태그·단추가 다 들어간다. 맞는 것을 전부 그리면
  // 자산이 늘어나는 만큼 스크롤이 길어지고, 아래쪽 카드는 아무도 못 본다.
  // **찾는 것은 위의 검색과 필터가 하는 일이다** -- 목록은 한 화면에서 훑을 수 있는
  // 만큼만 보여 주고 나머지는 눌러서 편다.
  const [shown, setShown] = useState(FIRST_PAGE);
  const visibleCards = matchingCards.slice(0, shown);
  const hiddenCount = matchingCards.length - visibleCards.length;
  // 검색·필터를 바꾸면 다시 처음부터 본다. 안 그러면 조건을 좁혔는데도 앞서 펼친
  // 만큼 그대로 길게 남는다.
  useEffect(() => { setShown(FIRST_PAGE); }, [type, query, orientation]);
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
            {/* 라이브러리 그림에는 `적용`이 없다. 그건 장면 영상을 갈아 끼우는
                길인데 그림으로는 할 수 없고, 단추만 두면 눌러 보고 나서야 안다.
                그림이 장면에 닿는 길은 아래 `화면에 얹기` 하나다. */}
            {card.kind === "image" ? null : <Button type="button" aria-label={`${card.title} 적용`} disabled={applyDisabled} onClick={() => target && onApply(card, target.segmentId)}>적용</Button>}
            {/* 이미지만: 장면을 바꾸는 `적용`(B-roll)과 달리, 장면 위에 얹는다.
                오버레이 endpoint와 렌더는 처음부터 있었는데 이미지를 고를 자리가
                없었다 -- 자산 목록이 그 선택기다. */}
            {onApplyOverlay && card.previewKind === "image" ? (
              <Button type="button" aria-label={`${card.title} 화면에 얹기`} disabled={applyDisabled} onClick={() => target && onApplyOverlay(card, target.segmentId)}>화면에 얹기</Button>
            ) : null}
          </div>
        </article>;
      })}
    </div>
    {hiddenCount > 0 ? (
      <Button type="button" variant="outline" className="vb-editor-assets__more" onClick={() => setShown((count) => count + FIRST_PAGE)}>
        {`${hiddenCount}개 더 보기`}
      </Button>
    ) : null}
    {visibleCards.length === 0 ? <p className="vb-editor-assets__empty">일치하는 자산이 없어요.</p> : null}
  </section>;
}
