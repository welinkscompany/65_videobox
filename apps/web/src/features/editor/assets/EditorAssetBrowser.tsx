import { useEffect, useState, type ReactNode } from "react";

import { Button } from "../../../components/ui/button";
import { Input } from "../../../components/ui/input";
import { assetPreferenceChoice, canonicalPreferenceTag, useDirectorPreferences } from "./directorPreferences";
import { filterEditorAssets, type EditorAssetCard, type EditorAssetKind, type EditorAssetOrientation } from "./editorAssetProjection";
import { writeAssetDrag } from "./assetDragPayload";
import { AddMediaFiles } from "../../media/AddMediaFiles";
import { VoiceMaterialPanel } from "../../media/VoiceMaterialPanel";
import { ImportFromFootageInbox } from "../../media/ImportFromFootageInbox";
import { LibraryPickerDialog } from "./LibraryPickerDialog";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "../../../components/ui/dialog";
import { DEFAULT_SCENE_TRANSITION_DURATION_SEC, SCENE_TRANSITION_CHOICES } from "../inspector/sceneTransitions";
import type { InspectorAction } from "../inspector/InspectorControls";

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
  /** 편집기 안에서 미디어를 더한 뒤 목록을 다시 읽게 한다. */
  onMediaAdded?: () => void | Promise<void>;
  /** 전환을 걸 대상. 캡컷처럼 왼쪽 `전환` 탭에서 고른다. */
  transitionTarget?: Readonly<{ segmentId: string; hasPrevious: boolean }> | null;
  onInspectorAction?: (action: InspectorAction) => void | Promise<void>;
  /** 대본·자막 편집(캡컷 `텍스트` 자리). 주지 않으면 그 탭도 만들지 않는다. */
  transcript?: ReactNode;
  /** 원본만 확인하는 자리. 미디어 탭 안에 둔다. */
  sourceCheck?: ReactNode;
  /** 최상위 탭을 여기서 대신 관리하는 부모가 있으면 준다(승인 2026-08-30
   *  버튼 단위 벤치마킹 2단계) -- 캡컷은 이 탭이 편집기 맨 위, 패널
   *  바깥에 늘 떠 있다. 주지 않으면 이 컴포넌트가 예전처럼 자기 상태로
   *  탭을 관리한다(단독 시험·다른 자리에서 재사용할 때를 위한 대비책). */
  pane?: LeftPane;
  onPaneChange?: (pane: LeftPane) => void;
  /** 부모가 이미 같은 탭을 최상위에 그리고 있으면 여기서 또 그리지 않는다
   *  (기본값 `true` — 안 주면 예전처럼 이 컴포넌트가 직접 그린다). */
  renderPaneTabs?: boolean;
}>;

/** 캡컷 왼쪽 패널은 `미디어 · 오디오 · 텍스트 · 스티커 · 효과 · 전환 · 필터`가
 *  **최상위 탭**이다(공식 매뉴얼, 2026-08-27 확인). 우리는 영상·음악·효과음·그림이
 *  한 줄에 섞여 있었고 **전환은 오른쪽 속성 패널 안**에 있었다 -- 6종을 다 만들어
 *  놓고도 캡컷을 아는 사람이 왼쪽에서 찾으면 없었다.
 *
 *  **가진 것만 탭으로 둔다.** 스티커·효과·필터는 우리에게 없으므로 탭도 만들지
 *  않는다 -- 없는 기능의 자리를 흉내 내면 배치가 거짓말을 한다(owner 결정 2026-08-27).
 *  텍스트는 자막이 대신하고 있어 이번 범위에서 뺐다. */
export type LeftPane = "media" | "audio" | "transcript" | "transition";

/** **한 번에 하나만 보여 준다(owner 지시 2026-08-27).**
 *  > "지금 사진 부분이 스크롤이 너무 길다고, 여길 뭔가 정리를 해야지"
 *
 *  실측: 왼쪽 도크는 보이는 높이 **137px**인데 내용이 **1,608px**이었다 --
 *  **11.7배 스크롤**. 미디어 아래에 `영상 구성 · 소스 확인 · 대본 · 자막`이 세로로
 *  더 쌓여 있었기 때문이다. 캡컷 왼쪽 패널은 고른 탭의 내용만 보여 준다. */
export const editorAssetPanes: readonly Readonly<{ pane: LeftPane; label: string }>[] = [
  { pane: "media", label: "미디어" },
  { pane: "audio", label: "오디오" },
  { pane: "transcript", label: "자막" },
  { pane: "transition", label: "전환" },
];

const paneKinds: Readonly<Record<"media" | "audio", readonly EditorAssetKind[]>> = {
  media: ["broll", "image"],
  audio: ["bgm", "sfx"],
};

const paneFilters: Readonly<Record<"media" | "audio", readonly Readonly<{ type: "all" | EditorAssetKind; label: string }>[]>> = {
  media: [
    { type: "all", label: "전체" },
    { type: "broll", label: "영상" },
    { type: "image", label: "그림" },
  ],
  audio: [
    { type: "all", label: "전체" },
    { type: "bgm", label: "음악" },
    { type: "sfx", label: "효과음" },
  ],
};

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

export function EditorAssetBrowser({ cards, target, isSaving, onPreview, onApply, onApplyOverlay, previewStates = {}, onRefreshExactPreview, projectId, onMediaAdded, transitionTarget, onInspectorAction, transcript, sourceCheck, pane: controlledPane, onPaneChange, renderPaneTabs = true }: Props) {
  const [query, setQuery] = useState("");
  const [type, setType] = useState<"all" | EditorAssetKind>("all");
  const [uncontrolledPane, setUncontrolledPane] = useState<LeftPane>("media");
  const pane = controlledPane ?? uncontrolledPane;
  const setPane = onPaneChange ?? setUncontrolledPane;
  const [orientation, setOrientation] = useState<"all" | EditorAssetOrientation>("all");
  // 탭이 먼저 갈라 놓고, 그 안에서 종류·검색·방향으로 좁힌다. 캡컷도 미디어 탭과
  // 오디오 탭이 서로 다른 목록이다.
  const paneCards = pane !== "media" && pane !== "audio" ? [] : cards.filter((card) => paneKinds[pane].includes(card.kind));
  const matchingCards = filterEditorAssets(paneCards, { type, query, orientation });
  // owner: "자산 내역에 스크롤이 엄청 길다니까."
  //
  // 카드 한 장에 썸네일·제목·설명·태그·단추가 다 들어간다. 맞는 것을 전부 그리면
  // 자산이 늘어나는 만큼 스크롤이 길어지고, 아래쪽 카드는 아무도 못 본다.
  // **찾는 것은 위의 검색과 필터가 하는 일이다** -- 목록은 한 화면에서 훑을 수 있는
  // 만큼만 보여 주고 나머지는 눌러서 편다.
  const [shown, setShown] = useState(FIRST_PAGE);
  const [narrationOpen, setNarrationOpen] = useState(false);
  const [footageOpen, setFootageOpen] = useState(false);
  const [libraryOpen, setLibraryOpen] = useState(false);
  const visibleCards = matchingCards.slice(0, shown);
  const hiddenCount = matchingCards.length - visibleCards.length;
  // 검색·필터를 바꾸면 다시 처음부터 본다. 안 그러면 조건을 좁혔는데도 앞서 펼친
  // 만큼 그대로 길게 남는다.
  useEffect(() => { setShown(FIRST_PAGE); }, [type, query, orientation, pane]);
  // 탭을 바꾸면 앞 탭에서 좁혀 둔 종류가 남으면 안 된다 -- `음악`을 고른 채
  // 미디어 탭으로 가면 아무것도 안 나온다.
  useEffect(() => { setType("all"); }, [pane]);
  const taste = useDirectorPreferences(projectId);
  const tasteReady = Boolean(projectId) && taste.ready;
  const excludedCreators = taste.preferences.exclude_creator;
  const excludedTags = taste.preferences.exclude_tag;

  return <section className="vb-editor-assets" aria-label="편집기 미디어">
    {/* 캡컷과 같은 자리의 최상위 탭. 가진 것만 둔다 -- 자세한 이유는 `LeftPane` 주석.
        승인 2026-08-30(버튼 단위 벤치마킹 2단계)로 이 탭은 이제 편집기 맨 위,
        패널 바깥에서도 그릴 수 있다(`renderPaneTabs={false}` + `pane`/`onPaneChange`
        제어) -- 그때는 여기서 중복해서 그리지 않는다. */}
    {renderPaneTabs ? <div className="vb-editor-assets__panes" role="tablist" aria-label="왼쪽 패널">
      {editorAssetPanes.filter((item) => item.pane !== "transcript" || transcript).map((item) => <Button key={item.pane} variant="ghost" className="vb-editor-assets__pane-tab" type="button" role="tab" aria-selected={pane === item.pane} onClick={() => setPane(item.pane)}>{item.label}</Button>)}
    </div> : null}
    {pane === "transition" ? <TransitionPane target={transitionTarget} disabled={isSaving} onInspectorAction={onInspectorAction} />
      : pane === "transcript" ? transcript : <>
    <div className="vb-editor-assets__controls">
      {/* **편집기를 떠나지 않고 미디어를 더한다(owner 승인 2026-08-27).**
          2026-08-27에 재 보니 편집기 안에는 미디어를 더할 길이 아예 없었다 --
          파일 입력도, 미디어 화면으로 나가는 링크조차 없었다. 쓰려면 위 띠에서
          미디어 단계를 눌러 화면을 떠나야 한다는 것을 스스로 알아내야 했다.
          올리는 절차는 미디어 화면과 **같은 조각**을 쓴다(두 벌로 적지 않는다). */}
      {projectId ? <div className="vb-editor-assets__add-row" role="group" aria-label="미디어 더하기">
        <AddMediaFiles projectId={projectId} onAdded={onMediaAdded} />
      {/* **내레이션은 팝업으로 연다(owner 승인 2026-08-27).**
          > "이걸 캡컷처럼 편집기 기반처럼 쉽게 확인하도록 팝업으로 만든다던지"

          내레이션도 영상·음악·효과음과 같은 미디어인데(`VoiceMaterialPanel` 주석)
          그 자리가 미디어 화면에만 있어서, 편집하다 목소리를 넣으려면 화면을
          떠나야 했다. 다만 이 도크는 220~400px이라 목소리 등록·후보 생성·청취
          승인까지 넣으면 답답하다. 그래서 도크에 밀어 넣지 않고 팝업으로 연다.
          패널은 **미디어 화면이 쓰는 것을 그대로** 쓴다. */}
        <Button type="button" variant="outline" className="vb-editor-assets__narration" onClick={() => setNarrationOpen(true)}>내레이션</Button>
        <Button type="button" variant="outline" className="vb-editor-assets__footage" onClick={() => setFootageOpen(true)}>촬영본</Button>
        {/* **라이브러리에서 가져오기(owner 승인, 재설계안 §1.3).**
            여러 프로젝트가 함께 쓰는 `/library`는 지금 편집 중인 프로젝트에
            속하지 않는다 -- 그래서 편집기 안으로 통째로 접지 않고, "고르기"
            슬라이스 하나만 팝업으로 연다. 팝업 내부는 `/library`가 쓰는
            `LibrarySidebar`·`LibraryResults`를 그대로 재사용한다
            (`LibraryPickerDialog.tsx` 주석 참고). */}
        <Button type="button" variant="outline" className="vb-editor-assets__library" onClick={() => setLibraryOpen(true)}>라이브러리에서 가져오기</Button>
        <LibraryPickerDialog open={libraryOpen} onOpenChange={setLibraryOpen} projectId={projectId} onImported={onMediaAdded} />
        <Dialog open={footageOpen} onOpenChange={setFootageOpen}>
          <DialogContent className="vb-dialog-content">
            <DialogHeader>
              <DialogTitle>촬영본 가져오기</DialogTitle>
              <DialogDescription>따로 모아 둔 영상에서 골라 이 프로젝트로 가져옵니다.</DialogDescription>
            </DialogHeader>
            <ImportFromFootageInbox projectId={projectId} onImported={onMediaAdded} />
          </DialogContent>
        </Dialog>
        <Dialog open={narrationOpen} onOpenChange={setNarrationOpen}>
          <DialogContent className="vb-dialog-content">
            <DialogHeader>
              <DialogTitle>내레이션</DialogTitle>
              <DialogDescription>내 목소리로 대본을 읽어 만들고, 들어 본 뒤 고릅니다.</DialogDescription>
            </DialogHeader>
            <VoiceMaterialPanel projectId={projectId} />
          </DialogContent>
        </Dialog>
      </div> : null}
      <label className="vb-editor-assets__search-label">
        <span>미디어 검색</span>
        {/* **빈 칸에 힌트를 넣는다**(2026-08-22, `capcut-observed` 기록 §5 "공통 생김새":
            캡컷은 모든 탭 검색창에 지금 뭘 찾을 수 있는지 안내 문구를 넣는다). 우리
            칸은 비어 있었다 -- 무엇을 검색할 수 있는지 눌러 보기 전엔 알 수 없었다. */}
        <Input className="vb-editor-assets__search" type="search" aria-label="미디어 검색" placeholder="영상 · 음악 · 효과음 · 그림 검색" value={query} onChange={(event) => setQuery(event.target.value)} />
      </label>
      {/* **캡컷처럼 탭 줄로 바꿨다(owner 지시 2026-08-22).**
          > "캡컷은 대부분 메뉴들을 탭으로 정리해서 깔끔하게 만들었어"

          앞서는 알약 여덟 개(`전체 필터`·`영상 필터`···`세로 필터`)가 한꺼번에 펼쳐져
          있었다. 캡컷 편집기는 `미디어·오디오·텍스트·스티커···`를 **탭 한 줄**로 두고
          고른 탭의 내용만 아래에 보여 준다.

          이름에서 `필터`를 뺐다 -- 캡컷 탭은 그냥 명사다. 화면 방향은 탭이 아니라
          **고른 탭 안에서 더 좁히는 것**이라 한 단 아래로 내렸다. */}
      <div className="vb-editor-assets__tabs" role="tablist" aria-label="미디어 종류">
        {paneFilters[pane === "audio" ? "audio" : "media"].map((filter) => <Button key={filter.type} variant="ghost" className="vb-editor-assets__tab" type="button" role="tab" aria-selected={type === filter.type} onClick={() => setType(filter.type)}>{filter.label}</Button>)}
      </div>
      <div className="vb-editor-assets__filters" role="group" aria-label="화면 방향">
        {orientationFilters.map((filter) => <Button key={filter.value} variant="ghost" className="vb-editor-assets__filter" type="button" aria-pressed={orientation === filter.value} onClick={() => setOrientation(filter.value)}>{filter.label}</Button>)}
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
        // **소리는 줄로, 보는 것은 격자로**(`capcut-observed` 기록 §5 오디오:
        // "오른쪽은 격자가 아니라 목록이다 -- 앨범 그림 + 곡명 + `아티스트 ·
        // 길이`"). 음악·효과음은 썸네일이 없어 카드로 그리면 글자만 든 빈
        // 상자가 되고, 효과음 100개를 한 화면에서 훑을 수가 없다. 카드를 새로
        // 만들지 않고 **같은 `article`을 가로로 눕힌다** -- 적용·미리듣기·취향
        // 단추가 전부 그대로 살아 있어야 하고, 두 벌을 유지하면 한쪽만 고치는
        // 사고가 난다.
        const isSound = card.kind === "bgm" || card.kind === "sfx";
        return <article key={card.id} className={`vb-editor-assets__card${isSound ? " vb-editor-assets__card--row" : ""}`}
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
          ) : isSound ? (
            // 캡컷 오디오 줄의 앨범 그림 자리. 우리 자산에는 그림이 없으므로
            // 파형 모양을 그려 **줄마다 눈에 걸리는 것**을 둔다(라이브러리
            // 화면의 `vb-library-waveform`과 같은 방식).
            <span className="vb-editor-assets__wave" aria-hidden="true">
              {Array.from({ length: 14 }, (_, index) => <i key={index} style={{ height: `${24 + ((index * 17) % 48)}%` }} />)}
            </span>
          ) : null}
          <h3 className="vb-editor-assets__title">{card.title}</h3>
          <p className="vb-editor-assets__summary">
            {card.label} · {card.durationLabel}
            {card.orientation ? <> · <span className="vb-editor-assets__orientation">{card.orientation}</span></> : null}
          </p>
          {/* 상태와 **출처 표기 여부**는 권리 정보라 줄로 눕혀도 감추지 않는다 --
              음악·효과음이 바로 그게 걸리는 자산이다. 다만 줄에서는 `라이선스:
              {긴 URL} · 출처 표기 불필요` 전체를 그리면 URL이 세 줄로 감겨
              줄이 카드보다 길어졌다(2026-08-23 실측 325px). 창작자에게 필요한
              것은 URL이 아니라 **표기가 필요한지**이므로, 줄에서는 짧은 쪽만
              보이고 URL을 포함한 전체 문구는 `title`로 남긴다. */}
          <p className="vb-editor-assets__detail vb-editor-assets__status">{card.status}</p>
          <p className="vb-editor-assets__detail vb-editor-assets__audio-presence">{card.audioPresence}</p>
          <p className="vb-editor-assets__detail vb-editor-assets__license">{card.license}</p>
          <p className="vb-editor-assets__detail vb-editor-assets__attribution" title={card.license}>
            {card.sourceMetadata.attributionRequired ? "출처 표기 필요" : "출처 표기 불필요"}
          </p>
          <p className="vb-editor-assets__reason">직접 선택한 미디어</p>
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
                    : "유진에게 이 미디어를 어떻게 다룰지 알려 줄 수 있어요."}
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
    {visibleCards.length === 0 ? <p className="vb-editor-assets__empty">일치하는 미디어가 없어요.</p> : null}
    {/* 원본만 확인하는 자리. 미디어를 다루는 탭 안에 두어야 찾을 수 있다. */}
    {pane === "media" ? sourceCheck : null}
    </>}
  </section>;
}

/** 앞 장면에서 이 장면으로 넘어오는 방법을 고른다.
 *
 *  **기능을 새로 만들지 않았다.** 6종과 저장 명령(`set-transition`)은 오른쪽 속성
 *  패널이 이미 갖고 있었다. 캡컷은 이것을 **왼쪽 패널 탭**에 두므로 자리만 옮겼다
 *  (owner 결정 2026-08-27 "있는 것만 자리 맞추기"). 오른쪽 속성 패널의 것은 그대로
 *  둔다 -- 거기서 길이까지 조절하는 사람이 있고, 없애는 것은 별도 결정이다. */
function TransitionPane({
  target,
  disabled,
  onInspectorAction,
}: {
  target?: Readonly<{ segmentId: string; hasPrevious: boolean }> | null;
  disabled: boolean;
  onInspectorAction?: (action: InspectorAction) => void | Promise<void>;
}) {
  if (!target) return <p className="vb-editor-assets__empty">장면을 먼저 고르면 넘어오는 방법을 고를 수 있어요.</p>;
  if (!target.hasPrevious) return <p className="vb-editor-assets__empty">첫 장면에는 넘어올 앞 장면이 없어요.</p>;
  const apply = (value: string | null) => onInspectorAction?.({
    kind: "set-transition",
    segmentId: target.segmentId,
    transition: value === null ? null : { type: value, durationSec: DEFAULT_SCENE_TRANSITION_DURATION_SEC },
  });
  return <div className="vb-editor-assets__transitions">
    <p className="vb-editor-assets__detail">고른 장면으로 넘어올 때의 모습입니다.</p>
    <Button type="button" variant="outline" disabled={disabled || !onInspectorAction} onClick={() => void apply(null)}>바로 넘기기 적용</Button>
    {SCENE_TRANSITION_CHOICES.map((choice) => (
      <Button key={choice.value} type="button" variant="outline" disabled={disabled || !onInspectorAction} onClick={() => void apply(choice.value)}>
        {`${choice.label} 적용`}
      </Button>
    ))}
  </div>;
}
