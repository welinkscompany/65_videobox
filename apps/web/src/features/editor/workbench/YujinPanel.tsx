import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { Sparkles, XIcon } from "lucide-react";

import { Button } from "../../../components/ui/button";
import { Input } from "../../../components/ui/input";
import { Textarea } from "../../../components/ui/textarea";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "../../../components/ui/dialog";
import { YujinStarters } from "../../yujin/YujinStarters";
import type { RightDockCandidate, RightDockCompletionEntry, RightDockConversationScroll, RightDockEditingProposal, RightDockEditingProposalPreview, RightDockMemory, RightDockMessage, RightDockProposal, RightDockTransitionSuggestion, YujinRunState } from "./rightDockTypes";
import { YujinMemoryPanel } from "./YujinMemoryPanel";
import { sceneTransitionLabel } from "../inspector/sceneTransitions";

const staleProposalMessage = "편집본이 바뀌어서 이 추천은 그대로 적용할 수 없어요.";

const SCRIPT_MINIMUM_CHARACTERS = 30;
function looksLikeScript(draft: string): boolean {
  return draft.trim().length >= SCRIPT_MINIMUM_CHARACTERS;
}

const SCRIPT_BUTTON_TEXT = "이 답을 대본으로 쓰기";
function scriptButtonLabel(text: string): string {
  return `${SCRIPT_BUTTON_TEXT} — ${text.trim().slice(0, 20)}…`;
}

/** 후보를 **부르는 이름**. 코드는 사람이 고르는 근거가 못 된다 -- 2026-08-19에
 *  owner 화면의 후보 일곱 개가 전부 `P08-B-01 · 미디어`였고, 실제로는 서로 다른
 *  장면을 겨냥한 같은 자산이었다. 이름이 오면 이름을, 없으면 코드를 쓴다. */
function candidateAssetLabel(candidate: RightDockCandidate): string {
  return candidate.displayName?.trim() || candidate.visibleReferenceCode;
}

function candidateLabel(candidate: RightDockCandidate): string {
  const scene = candidate.targetSceneLabel?.trim();
  return scene ? `${scene} — ${candidateAssetLabel(candidate)}` : candidateAssetLabel(candidate);
}

function candidateTitle(candidate: RightDockCandidate): string {
  return `${candidateAssetLabel(candidate)} · ${mediaKindLabel(candidate.sourceMediaKind)}`;
}

const matchModeWords: Readonly<Record<string, string>> = {
  semantic: "뜻으로 찾음",
  word: "단어로만 찾음",
};

function matchModeLabel(mode: string | undefined): string | null {
  return mode ? matchModeWords[mode] ?? null : null;
}

function previewVerb(kind: RightDockCandidate["sourceMediaKind"]): string {
  return kind === "bgm" || kind === "sfx" ? "미리 듣기" : "미리 보기";
}

// `broll`/`broll_video`는 "B-roll"로 쓴다 -- `EditorWorkbench.tsx`의
// `auditionRoleLabel`과 `inspectorRegistry.ts`의 `mediaLabels`가 이미 같은
// 트랙을 그렇게 부르고, 실제 화면에도 그 글자가 뜬다("B-roll 1 항상 쓰기").
// 예전엔 여기만 "영상"이라 같은 대상이 패널마다 다른 이름으로 보였다.
function mediaKindLabel(kind: RightDockCandidate["sourceMediaKind"]) {
  return {
    raw_video: "원본 영상",
    broll: "B-roll",
    broll_video: "B-roll",
    image: "이미지",
    bgm: "배경 음악",
    sfx: "효과음",
    output_variant: "출력 변형",
  }[kind] ?? "미디어";
}

// 지금은 이유가 하나뿐이지만(`different_broll_asset`), 백엔드가 문장을
// 짓지 않고 코드만 보내는 이유가 여기 있다 -- 화면 문구는 creator-language
// 규정을 따라야 한다(`development-fast-path.ko.md` §10.13). 새 이유가
// 생기면 여기 한 줄만 늘면 된다.
function transitionSuggestionReasonLabel(reason: string): string {
  if (reason === "different_broll_asset") return "이 장면부터 다른 영상이 나와요";
  return "장면이 바뀌는 자리예요";
}

function controlSummary(controls: Readonly<Record<string, unknown>>) {
  const labels = Object.entries(controls).map(([name, value]) => {
    if (name === "fit") return value === "crop" ? "화면 채우기" : "화면 안에 맞추기";
    if (name === "volume") return `음량 ${value}`;
    if (name === "fade_in_sec") return `시작 전환 ${value}초`;
    if (name === "fade_out_sec") return `끝 전환 ${value}초`;
    if (name === "text") return "문구 변경";
    if (name === "style") return "캡션 모양 변경";
    if (name === "candidate_id") return "승인한 음성";
    if (name === "overlay_kind") return "오버레이 변경";
    return null;
  }).filter((value): value is string => value !== null);
  return labels.join(", ") || "기본 설정";
}

export type YujinPanelProps = Readonly<{
  /** 이 패널의 열림 상태는 오른쪽 도크와 완전히 독립이다(owner 지시
   *  2026-08-30: "우리 유진 대화창도 캡컷처럼 해도 되" -- 캡컷 EditPilot은
   *  속성 패널과 같은 도크의 탭이 아니라, 화면 구석에 떠 있는 버튼을 누르면
   *  따로 열리는 패널이다. `docs/reference/capcut-observed-2026-08-22.ko.md`
   *  §7 참고). 속성 도크가 닫혀 있어도 이 패널은 열 수 있다. */
  open: boolean;
  onOpenChange: (open: boolean) => void;
  state?: "script_required" | "idle" | "analysis_running" | "proposal_ready" | "applying" | "blocked" | "error";
  draft: string;
  onDraftChange: (draft: string) => void;
  messages?: readonly RightDockMessage[];
  completions?: readonly RightDockCompletionEntry[];
  proposal?: RightDockProposal | null;
  runState?: YujinRunState;
  selectedCandidateIds?: readonly string[];
  onSelectedCandidateIdsChange?: (candidateIds: readonly string[]) => void;
  onApplyProposal?: (proposalId: string, candidateIds: readonly string[]) => void | Promise<void>;
  onPreviewCandidate?: (candidate: RightDockCandidate) => void;
  conversationScroll?: RightDockConversationScroll;
  onConversationScrollChange?: (scroll: RightDockConversationScroll) => void;
  memory?: RightDockMemory;
  composerDisabled?: boolean;
  onSendMessage?: (draft: string) => void | Promise<void>;
  qualityFollowUps?: readonly string[];
  onCreateEditingProposal?: () => void | Promise<void>;
  editingProposal?: RightDockEditingProposal | null;
  editingProposalCreating?: boolean;
  onPreviewEditingProposal?: () => void | Promise<void>;
  onApplyEditingProposal?: () => void | Promise<void>;
  onRefreshProposal?: () => void | Promise<void>;
  onManualEdit?: () => void;
  /** 붙여 넣은 글을 대본으로 받는다. 확정은 사람이 한다. */
  onUseDraftAsScript?: (script: string) => void | Promise<void>;
  onStart?: () => void | Promise<void>;
  /** 추천 시작이 거절된 이유. 다시 누를 수 있는 상태로 함께 보인다. */
  startFailure?: string | null;
  onCancelRun?: () => void | Promise<void>;
  onRetryRun?: () => void | Promise<void>;
  /** 대화 시작 문구가 "이미 고른 장면이 있는지"에 따라 달라진다. */
  hasSelectedSegment?: boolean;
  /** 대화·자산 추천과 무관한 별도 경로다(`rightDockTypes.ts` 참고). */
  transitionSuggestions?: readonly RightDockTransitionSuggestion[];
  onApplyTransitionSuggestion?: (suggestion: RightDockTransitionSuggestion) => void | Promise<void>;
}>;

export function YujinPanel({
  open,
  onOpenChange,
  state = "idle",
  draft,
  onDraftChange,
  messages = [],
  completions = [],
  proposal = null,
  runState = { kind: "idle" },
  selectedCandidateIds,
  onSelectedCandidateIdsChange,
  onApplyProposal,
  onPreviewCandidate,
  conversationScroll = { key: "default", top: 0, pinnedToBottom: true },
  onConversationScrollChange,
  memory,
  composerDisabled = false,
  onSendMessage,
  qualityFollowUps = [],
  onCreateEditingProposal,
  editingProposal = null,
  editingProposalCreating = false,
  onPreviewEditingProposal,
  onApplyEditingProposal,
  onRefreshProposal,
  onManualEdit,
  onUseDraftAsScript,
  onStart,
  startFailure = null,
  onCancelRun,
  onRetryRun,
  hasSelectedSegment = false,
  transitionSuggestions = [],
  onApplyTransitionSuggestion,
}: YujinPanelProps) {
  const [editingProposalOpen, setEditingProposalOpen] = useState(false);
  const editingProposalPreview: RightDockEditingProposalPreview = editingProposal?.preview ?? { kind: "idle" };
  const historyRef = useRef<HTMLDivElement>(null);
  const composerContainerRef = useRef<HTMLDivElement>(null);
  const askedForRevision = useRef<number | null>(null);
  /** 한 번에 그리는 추천 카드 수. 왼쪽 자산 내역과 같은 기준이다. */
  const CANDIDATE_PAGE = 4;
  const [shownCandidates, setShownCandidates] = useState(CANDIDATE_PAGE);

  // 패널이 닫혀 있어도(펼치는 버튼만 보일 때도) 이 컴포넌트 자체는 늘
  // 마운트돼 있다 -- 그래야 대화 스크롤 위치 같은 자기 상태가 닫혔다
  // 열어도 그대로 남는다(아래 효과가 그 상태를 되살린다). **낡은 추천을
  // 다시 묻는 효과(밑에 따로 있음)는 그와 반대로 `open`을 확인해서
  // 닫혀 있는 동안은 돌지 않는다** -- 안 보는 화면 때문에 로컬 모델을
  // 돌릴 이유가 없다는 원래 RightDock의 계약을 그대로 지킨다.
  useLayoutEffect(() => {
    const history = historyRef.current;
    if (!history || !open) return;
    history.scrollTop = conversationScroll.pinnedToBottom
      ? history.scrollHeight
      : conversationScroll.top;
  }, [conversationScroll.key, conversationScroll.pinnedToBottom, conversationScroll.top, messages, open]);

  const proposalIsReady = proposal?.status === "ready";
  const proposalIsCurrent = proposalIsReady
    && proposal.baseSessionRevision === proposal.currentRevision;
  const proposalIsOutOfDate = Boolean(
    proposal && proposal.baseSessionRevision !== proposal.currentRevision,
  );
  // 패널이 알약 버튼으로 접혀 있어도 이 효과는 계속 돈다 -- 창작자가 다시
  // 열었을 때 이미 죽은 카드만 남아 있고 그걸 눈치채서 눌러야 하는 예전
  // 경험(`editor-workbench-route.test.tsx`의 "re-asks by itself" 테스트가
  // 이 계약을 고정한다)을 그대로 지킨다. `open`을 조건에 넣으면 효과가
  // 조용히 새는 대신 접힌 동안 낡은 채로 멈춰 있다가 다시 열 때만
  // 뒤늦게 물어보게 되는데, 이는 이미 테스트로 고정된 "도크가 보이면
  // 대신 물어본다" 계약을 어긴다(2026-08-31에 이 자리에 넣었다가
  // 되돌렸다 -- 효율 관점 리뷰 지적을 그대로 적용하면 기존 테스트가 깨졌다).
  useEffect(() => {
    if (!proposalIsOutOfDate || !onRefreshProposal) return;
    if (state === "analysis_running" || state === "applying") return;
    const revision = proposal?.currentRevision ?? null;
    if (revision === null || askedForRevision.current === revision) return;
    askedForRevision.current = revision;
    void onRefreshProposal();
  }, [onRefreshProposal, proposal?.currentRevision, proposalIsOutOfDate, state]);

  // 위 두 효과(훅) 다음, 나머지 파생 상태보다 앞에 둔다 -- 클릭 한 번으로
  // 얻는 알약 버튼일 뿐인 접힌 모습에는 후보·검사 결과 파생값이 전혀
  // 안 쓰이는데, 이 확인을 훅들보다 먼저 두면 Rules of Hooks를 어긴다.
  // 훅 호출 없이 순수 계산만 건너뛰는 것이라 여기가 안전한 가장 이른 자리다.
  if (!open) {
    return <Button type="button" className="vb-yujin-panel__toggle" onClick={() => onOpenChange(true)}>
      <Sparkles aria-hidden="true" /> 유진
    </Button>;
  }

  const activeCandidateIds = selectedCandidateIds
    ?? (proposal?.candidates[0] ? [proposal.candidates[0].candidateId] : []);
  // 빈 구간이 열두 개면 고르기·적용을 열두 번 반복해야 했다. `batch-apply`는
  // 처음부터 여러 개를 받아 **한 번의 편집**으로 쓰므로(되돌리기도 한 번),
  // 서버가 함께 받는 추천에서는 카드도 여러 개 고를 수 있어야 한다.
  const allowsMultipleSelection = proposal?.allowsMultipleSelection === true;
  const candidateIsChoosable = (candidate: RightDockCandidate) => (
    candidate.actionable
    && candidate.availability === "actionable"
    && candidate.reviewStatus === "approved"
  );
  const selectedCandidatesAreActionable = Boolean(
    proposalIsCurrent
    && activeCandidateIds.length >= 1
    && (allowsMultipleSelection || activeCandidateIds.length === 1)
    && activeCandidateIds.every((candidateId) => proposal?.candidates.some((candidate) => (
      candidate.candidateId === candidateId && candidateIsChoosable(candidate)
    ))),
  );
  // 같은 장면에 둘을 고르면 서버는 둘 다 그 장면에 쓰고 **나중 것이 이긴다** --
  // 조용히 하나가 사라진다. 장면당 하나로 묶어 그 일이 일어나지 않게 한다.
  const sceneKey = (candidate: RightDockCandidate) => candidate.targetSegmentId || candidate.candidateId;
  const chooseCandidate = (candidate: RightDockCandidate, chosen: boolean) => {
    if (!allowsMultipleSelection) {
      onSelectedCandidateIdsChange?.([candidate.candidateId]);
      return;
    }
    const dropped = new Set(
      (proposal?.candidates ?? [])
        .filter((other) => sceneKey(other) === sceneKey(candidate))
        .map((other) => other.candidateId),
    );
    const kept = activeCandidateIds.filter((candidateId) => !dropped.has(candidateId));
    const next = chosen ? [...kept, candidate.candidateId] : kept;
    // 카드 순서를 그대로 지킨다. 고른 순서로 보내면 적용 순서가 화면과 달라져
    // 무엇이 어디에 들어갔는지 되짚기 어렵다.
    const order = (proposal?.candidates ?? []).map((item) => item.candidateId);
    onSelectedCandidateIdsChange?.([...next].sort((left, right) => order.indexOf(left) - order.indexOf(right)));
  };
  const recommendationCandidates = proposal?.candidates.filter((candidate) => !candidate.readOnlyFinding) ?? [];
  const readOnlyFindings = proposal?.candidates.filter((candidate) => candidate.readOnlyFinding) ?? [];

  const canSend = Boolean(!composerDisabled && onSendMessage && draft.trim());
  const showConversationStarters = messages.length === 0
    && !proposal
    && state === "idle"
    && runState.kind === "idle";
  /** 권한 문장을 입력칸에 채우고 커서를 거기 둔다. **보내지는 않는다** --
   *  보낼지는 창작자가 정한다.
   *
   *  대화 스타터(대화 전)와 이어서 해볼 것(답변 뒤)이 같은 함수를 쓴다.
   *  둘은 화면에서 같은 알약 단추로 보이므로, 하나는 커서를 옮기고 다른 하나는
   *  안 옮기면 "왜 어떤 건 바로 쓸 수 있고 어떤 건 다시 눌러야 하지"가 된다. */
  const fillComposerWith = (starter: { label: string }) => {
    onDraftChange(starter.label);
    composerContainerRef.current?.querySelector<HTMLTextAreaElement>("textarea")?.focus();
  };
  const submit = () => { if (canSend) void onSendMessage?.(draft.trim()); };
  const runStatusAnnouncement = runState.kind === "complete"
    ? "유진 답변을 받았어요."
    : runState.kind === "unavailable"
    ? `${runState.message} 수동 편집을 계속할 수 있어요.`
    : null;

  return <section aria-label="유진" className="vb-yujin-panel">
    <header className="vb-yujin-panel__header">
      <h2>유진</h2>
      <Button type="button" variant="ghost" size="icon" aria-label="유진 닫기" onClick={() => onOpenChange(false)}><XIcon aria-hidden="true" /></Button>
    </header>
    {runStatusAnnouncement ? <p role="status" aria-live="polite" aria-atomic="true" aria-label="유진 대화 상태" className="sr-only">{runStatusAnnouncement}</p> : null}
    {runState.kind === "complete" && runState.syncWarning
      ? <p aria-label="대화 저장 상태" className="vb-editor-right-dock__sync-warning">{runState.syncWarning}</p>
      : null}
    {(runState.kind === "streaming" || runState.kind === "unavailable") && runState.cancelWarning
      ? <p role="status" className="vb-editor-right-dock__sync-warning">{runState.cancelWarning}</p>
      : null}
    {state === "blocked" || state === "error" || runState.kind === "unavailable" ? <div className="vb-editor-right-dock__fallback"><p>{runState.kind === "unavailable" ? runState.message : proposalIsOutOfDate ? staleProposalMessage : "유진의 답을 받지 못했어요."}</p>{proposal && onRefreshProposal ? <Button type="button" onClick={() => void onRefreshProposal()}>지금 편집본으로 다시 추천받기</Button> : null}{onManualEdit ? <Button type="button" onClick={onManualEdit}>유진 없이 계속 편집</Button> : null}</div> : null}
    {startFailure ? <p role="alert" className="vb-editor-right-dock__sync-warning">{startFailure}</p> : null}
    {state === "idle" && !proposal && onStart ? <Button type="button" onClick={() => void onStart()}>유진에게 추천받기</Button> : null}
    <div
      ref={historyRef}
      role="log"
      aria-label="유진 대화"
      aria-busy={runState.kind === "streaming"}
      className="vb-editor-right-dock__history"
      tabIndex={0}
      onScroll={(event) => {
        const history = event.currentTarget;
        onConversationScrollChange?.({
          key: conversationScroll.key,
          top: history.scrollTop,
          pinnedToBottom: history.scrollHeight - history.clientHeight - history.scrollTop <= 4,
        });
      }}
    >
      {messages.length
        ? messages.map((message) => <article key={message.id}>
          <p><strong>{message.role === "user" ? "나" : "유진"}</strong> {message.text}</p>
          {onUseDraftAsScript && message.role === "assistant" && looksLikeScript(message.text)
            ? <Button type="button" aria-label={scriptButtonLabel(message.text)} onClick={() => void onUseDraftAsScript(message.text)}>{SCRIPT_BUTTON_TEXT}</Button>
            : null}
        </article>)
        : null}
      {/* **답변이 끝나면 이어서 해볼 것 셋**(owner 2026-09-01: "유진이와 질문
          답변이 끝나면 꼬리질문도 3개 만들어서 제안해줘 -- 영상 퀄리티를 더
          좋게 만드는 방법으로"). 지금 편집본을 읽어서 만든 것이라 이미 해 둔
          것은 권하지 않고, 누르면 실제로 되는 것만 있다(`qualityFollowUps.ts`).
          누르면 입력칸에 채워진다 -- 대화 스타터·편집안 꼬리질문과 같은 방식이라
          "누르면 바로 실행되나?"를 새로 배울 필요가 없다. */}
      {qualityFollowUps.length > 0 && runState.kind !== "streaming"
        ? <div className="vb-yujin-panel__follow-ups" role="group" aria-label="이어서 해볼 것">
          <p>이어서 해볼 것</p>
          {qualityFollowUps.map((question) => (
            <Button key={question} type="button" variant="outline" disabled={composerDisabled} onClick={() => fillComposerWith({ label: question })}>{question}</Button>
          ))}
        </div>
        : null}
      {completions.length
        ? completions.map((completion) => <article key={completion.id} className="vb-editor-right-dock__completion" role="status" aria-label={`모든 작업 완료 ${completion.items.length}/${completion.items.length}`}>
          <p><strong>모든 작업 완료</strong> {completion.items.length}/{completion.items.length}</p>
          <ul>{completion.items.map((item, index) => <li key={`${completion.id}-${index}`}>{item.sceneLabel ? `${item.sceneLabel} · ` : ""}{item.label}</li>)}</ul>
        </article>)
        : null}
      {/* **추천 후보를 대화 로그 안에 섞는다**(owner 2026-08-30: "캡컷도
          화면공간이 필요해서 버튼들을 엄청 작게 만들었어. 그래서 나도
          캡컷을 벤치마킹하라고 한거잖아" -- 캡컷 EditPilot은 제안 카드를
          대화 안에 두지 별도 탭에 두지 않는다). 완성된 작업 목록과 같은
          자리(이 `history` 스크롤 안)에 둔다. */}
      {proposal ? <div aria-label="제안 편집본" className="vb-yujin-panel__proposal-meta">
        <p>{`제안 기준 편집본 ${proposal.baseSessionRevision}`}</p>
        <p>{`현재 편집본 ${proposal.currentRevision}`}</p>
        {matchModeLabel(proposal.matchMode) ? <p>{matchModeLabel(proposal.matchMode)}</p> : null}
        {proposalIsOutOfDate && state !== "blocked" && state !== "error" ? <>
          <p role="status">{staleProposalMessage}</p>
          {onRefreshProposal ? <Button type="button" disabled={state === "analysis_running" || state === "applying"} onClick={() => void onRefreshProposal()}>지금 편집본으로 다시 추천받기</Button> : null}
        </> : null}
      </div> : null}
      {recommendationCandidates.length && allowsMultipleSelection ? <div className="vb-editor-right-dock__bulk-pick">
        <Button type="button" onClick={() => {
          const bySceneFirst = new Map<string, string>();
          for (const candidate of recommendationCandidates) {
            if (!candidateIsChoosable(candidate)) continue;
            if (!bySceneFirst.has(sceneKey(candidate))) bySceneFirst.set(sceneKey(candidate), candidate.candidateId);
          }
          onSelectedCandidateIdsChange?.([...bySceneFirst.values()]);
        }}>장면마다 하나씩 모두 고르기</Button>
        <Button type="button" variant="outline" disabled={!activeCandidateIds.length} onClick={() => onSelectedCandidateIdsChange?.([])}>고른 추천 모두 끄기</Button>
      </div> : null}
      {recommendationCandidates.length ? <div role={allowsMultipleSelection ? "group" : "radiogroup"} aria-label="추천 후보" className="vb-yujin-panel__candidates">
        {recommendationCandidates.slice(0, shownCandidates).map((candidate) => {
          const candidateDeclaresActionable = candidate.actionable === undefined
            ? proposalIsReady
            : (
              candidate.actionable
              && candidate.availability === "actionable"
              && candidate.reviewStatus === "approved"
            );
          const candidateIsActionable = Boolean(
            proposalIsCurrent
            && candidateDeclaresActionable,
          );
          return <article key={candidate.candidateId} className="vb-yujin-panel__candidate">
            <label><Input
              type={allowsMultipleSelection ? "checkbox" : "radio"}
              name={allowsMultipleSelection ? undefined : "vb-eugene-candidate"}
              aria-label={`${candidateLabel(candidate)} 선택`}
              checked={activeCandidateIds.includes(candidate.candidateId)}
              disabled={!candidateIsActionable}
              onChange={(event) => {
                if (candidateIsActionable) chooseCandidate(candidate, event.target.checked);
              }}
            />{candidate.targetSceneLabel?.trim()
              ? <><strong className="vb-editor-right-dock__candidate-scene">{candidate.targetSceneLabel.trim()}</strong>{" "}<span>{candidateTitle(candidate)}</span></>
              : candidateTitle(candidate)}</label>
            <p>{candidate.previewSummary}</p>
            <p>{`후보 상태: ${candidateDeclaresActionable ? "적용 가능" : "수동 적용"}`}</p>
            <dl>
              <dt>미디어</dt><dd>{mediaKindLabel(candidate.sourceMediaKind)}</dd>
              <dt>적용 설정</dt><dd>{controlSummary(candidate.supportedControls ?? {})}</dd>
            </dl>
            {candidateIsActionable && candidate.previewUrl && onPreviewCandidate ? <Button type="button" aria-label={`${candidateLabel(candidate)} ${previewVerb(candidate.sourceMediaKind)}`} onClick={() => onPreviewCandidate(candidate)}>{previewVerb(candidate.sourceMediaKind)}</Button> : null}
          </article>;
        })}
        {recommendationCandidates.length > shownCandidates ? <Button type="button" variant="outline" onClick={() => setShownCandidates((count) => count + CANDIDATE_PAGE)}>{`추천 ${recommendationCandidates.length - shownCandidates}개 더 보기`}</Button> : null}
      </div> : (proposal ? <p>아직 추천이 없어요. 직접 편집을 계속하거나 유진에게 요청할 수 있어요.</p> : null)}
      {proposal && proposalIsReady && onApplyProposal ? <Button type="button" disabled={state === "applying" || !selectedCandidatesAreActionable} onClick={() => void onApplyProposal(proposal.proposalId, activeCandidateIds)}>{activeCandidateIds.length > 1 ? `고른 추천 ${activeCandidateIds.length}개 적용` : "선택한 추천 적용"}</Button> : null}
      {readOnlyFindings.length ? <section aria-label="검사 결과">
        <h2>검사 결과</h2>
        {readOnlyFindings.map((finding) => <article key={finding.candidateId}>
          {finding.supportedControls.check === "timeline_gaps"
            ? <p>{`빈 구간 ${String(finding.supportedControls.gap_count ?? 0)}개`}</p>
            : null}
        </article>)}
      </section> : null}
      {transitionSuggestions.length ? <section aria-label="장면 전환 추천" className="vb-yujin-panel__transition-suggestions">
        <h2>넘기기 추천</h2>
        {transitionSuggestions.map((suggestion) => <article key={suggestion.segmentId}>
          <p>{transitionSuggestionReasonLabel(suggestion.reason)}</p>
          <p>{sceneTransitionLabel(suggestion.type)}</p>
          {onApplyTransitionSuggestion ? (
            <Button type="button" disabled={state === "applying"} onClick={() => void onApplyTransitionSuggestion(suggestion)}>
              적용
            </Button>
          ) : null}
        </article>)}
      </section> : null}
      {!messages.length && !completions.length && !proposal
        ? <>
          <p>유진 대화는 아직 시작하지 않았어요.</p>
          {showConversationStarters ? <YujinStarters
            context={{ surface: "edit", selection: hasSelectedSegment ? "segment" : "none" }}
            disabled={composerDisabled}
            onSelect={fillComposerWith}
          /> : null}
        </>
        : null}
    </div>
    <label htmlFor="vb-eugene-request">유진에게 요청하기</label>
    <div ref={composerContainerRef}>
      <Textarea id="vb-eugene-request" disabled={composerDisabled} value={draft} onChange={(event) => onDraftChange(event.target.value)} placeholder="예: 이 구간에 어울리는 B-roll을 추천해 줘" />
    </div>
    <Button type="button" disabled={!canSend} onClick={submit}>요청 보내기</Button>
    {onCreateEditingProposal && messages.some((message) => message.role === "assistant")
      ? <Button type="button" disabled={editingProposalCreating || Boolean(editingProposal)} onClick={() => void onCreateEditingProposal()}>
        {editingProposalCreating ? "편집안 만드는 중" : "이 대화로 편집안 만들기"}
      </Button>
      : null}
    {editingProposal ? <><Button type="button" variant="outline" onClick={() => setEditingProposalOpen(true)}>편집안 보기</Button><p role="status">{editingProposal.summary}</p>
      <Dialog open={editingProposalOpen} onOpenChange={setEditingProposalOpen}>
        <DialogContent className="vb-dialog-content">
          <DialogHeader><DialogTitle>편집안</DialogTitle><DialogDescription>아직 적용되지 않았어요. 내용을 확인한 뒤 직접 적용해 주세요.</DialogDescription></DialogHeader>
          <p>{editingProposal.summary}</p>
          <ul aria-label="바뀌는 항목">{editingProposal.operationSummaries.map((summary, index) => <li key={`${index}:${summary}`}>{summary}</li>)}</ul>
          {editingProposal.followUpQuestions.length ? <div aria-label="이어서 물어보기">{editingProposal.followUpQuestions.map((question) => <Button key={question} type="button" variant="outline" onClick={() => onDraftChange(question)}>{question}</Button>)}</div> : null}
          {editingProposal.error ? <p role="alert">{editingProposal.error}</p> : null}
          {editingProposalPreview.kind === "working" ? <p role="status">{editingProposalPreview.message}</p> : null}
          {editingProposalPreview.kind === "unavailable" ? <p role="alert">{editingProposalPreview.message}</p> : null}
          {editingProposalPreview.kind === "ready"
            ? <video aria-label="편집안 미리보기" controls preload="metadata" src={editingProposalPreview.videoUrl} />
            : null}
          <DialogFooter>
            {onPreviewEditingProposal ? <Button type="button" variant="outline" disabled={editingProposal.isApplying || editingProposalPreview.kind === "working"} onClick={() => void onPreviewEditingProposal()}>이 구간 미리보기</Button> : null}
            {onApplyEditingProposal ? <Button type="button" disabled={editingProposal.isApplying} onClick={() => void onApplyEditingProposal()}>{editingProposal.isApplying ? "편집안 적용 중" : "이 편집안 적용"}</Button> : null}
          </DialogFooter>
        </DialogContent>
      </Dialog></> : null}
    {onUseDraftAsScript && looksLikeScript(draft)
      ? <Button type="button" onClick={() => void onUseDraftAsScript(draft)}>이 글을 대본으로 쓰기</Button>
      : null}
    {onCancelRun
      ? <Button type="button" onClick={() => void onCancelRun()}>답변 중단</Button>
      : null}
    {runState.kind === "unavailable" && runState.retryable && onRetryRun
      ? <Button type="button" onClick={() => void onRetryRun()}>같은 요청 다시 보내기</Button>
      : null}
    {memory ? <YujinMemoryPanel memory={memory} /> : null}
  </section>;
}
