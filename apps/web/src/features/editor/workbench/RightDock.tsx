import { useEffect, useLayoutEffect, useRef, useState } from "react";

import { Button } from "../../../components/ui/button";
import { Input } from "../../../components/ui/input";
import { NativeSelect } from "../../../components/ui/native-select";
import { Textarea } from "../../../components/ui/textarea";
import { InspectorControls, type ApprovedTtsCandidate, type InspectorAction, type PartialRegenerationControls } from "../inspector/InspectorControls";
import type { InspectorTarget } from "../inspector/inspectorRegistry";
import { YujinStarters } from "../../yujin/YujinStarters";
import type { RightDockCandidate, RightDockConversationScroll, RightDockMemory, RightDockMessage, RightDockProposal, YujinRunState } from "./rightDockTypes";
import { YujinMemoryPanel } from "./YujinMemoryPanel";

export type { InspectorTarget } from "../inspector/inspectorRegistry";

const staleProposalMessage = "편집본이 바뀌어서 이 추천은 그대로 적용할 수 없어요.";

type SelectedSegment = Readonly<{
  segmentId: string;
  startSec: number;
  endSec: number;
  nextSegmentId: string | null;
  cutAction: string;
  draftApplied: boolean;
  ttsReplacement?: Readonly<{ candidateId: string; assetId: string }> | null;
}>;

export type RightDockProps = Readonly<{
  /** 저장된 자막 모양을 읽으려면 필요하다. 없으면 그 절만 빠진다. */
  projectId?: string;
  state?: "script_required" | "idle" | "analysis_running" | "proposal_ready" | "applying" | "blocked" | "error";
  draft: string;
  onDraftChange: (draft: string) => void;
  messages?: readonly RightDockMessage[];
  proposal?: RightDockProposal | null;
  runState?: YujinRunState;
  selectedCandidateIds?: readonly string[];
  onSelectedCandidateIdsChange?: (candidateIds: readonly string[]) => void;
  conversationScroll?: RightDockConversationScroll;
  memory?: RightDockMemory;
  onConversationScrollChange?: (scroll: RightDockConversationScroll) => void;
  selectedSegment?: SelectedSegment;
  inspectorTargets?: readonly InspectorTarget[];
  inspectorDisabled?: boolean;
  partialRegeneration?: PartialRegenerationControls;
  loadApprovedTtsCandidates?: (segmentId: string) => Promise<readonly ApprovedTtsCandidate[]>;
  ttsCandidateScopeKey?: string;
  onInspectorAction?: (action: InspectorAction) => void | Promise<void>;
  composerDisabled?: boolean;
  onSendMessage?: (draft: string) => void | Promise<void>;
  onApplyProposal?: (proposalId: string, candidateIds: readonly string[]) => void | Promise<void>;
  onRefreshProposal?: () => void | Promise<void>;
  onManualEdit?: () => void;
  /** 붙여 넣은 글을 대본으로 받는다. 확정은 사람이 한다. */
  onUseDraftAsScript?: (script: string) => void | Promise<void>;
  onPreviewCandidate?: (candidate: RightDockCandidate) => void;
  onStart?: () => void | Promise<void>;
  /** 추천 시작이 거절된 이유. 다시 누를 수 있는 상태로 함께 보인다. */
  startFailure?: string | null;
  onRetryMessage?: () => void | Promise<void>;
  onCancelRun?: () => void | Promise<void>;
  onRetryRun?: () => void | Promise<void>;
  retryAfterSeconds?: number | null;
}>;

/** 붙여 넣은 것이 **대본인지 요청인지** 가른다. 기준은 길이 하나다 --
 *  "B-roll 추천해 줘"는 요청이고, 문장 여럿이 이어지면 대본으로 본다. */
const SCRIPT_MINIMUM_CHARACTERS = 30;
function looksLikeScript(draft: string): boolean {
  return draft.trim().length >= SCRIPT_MINIMUM_CHARACTERS;
}

/** 후보를 **부르는 이름**. 코드는 사람이 고르는 근거가 못 된다 -- 2026-08-19에
 *  owner 화면의 후보 일곱 개가 전부 `P08-B-01 · 미디어`였고, 실제로는 서로 다른
 *  장면을 겨냥한 같은 자산이었다. 이름이 오면 이름을, 없으면 코드를 쓴다.
 *
 *  **종류는 여기 넣지 않는다.** 접근 이름은 부르는 말이고, 종류는 카드가 `미디어`
 *  줄로 이미 말한다. 넣었더니 음성으로 부르는 이름이 통째로 바뀌었다. */
function candidateAssetLabel(candidate: RightDockCandidate): string {
  return candidate.displayName?.trim() || candidate.visibleReferenceCode;
}

/** 부르는 이름에 **장면이 먼저 온다.** 같은 자산을 여러 장면에 추천하는 일이
 *  흔해서(빈 구간을 한 자산으로 메우는 경우가 그렇다) 자산 이름만으로는 열세
 *  개가 전부 같은 이름이 된다. 장면을 모르면 예전처럼 자산 이름만 쓴다. */
function candidateLabel(candidate: RightDockCandidate): string {
  const scene = candidate.targetSceneLabel?.trim();
  return scene ? `${scene} — ${candidateAssetLabel(candidate)}` : candidateAssetLabel(candidate);
}

/** 카드에 보이는 글자. 이름 옆에 종류를 붙여 한눈에 구분되게 한다. */
function candidateTitle(candidate: RightDockCandidate): string {
  return `${candidateAssetLabel(candidate)} · ${mediaKindLabel(candidate.sourceMediaKind)}`;
}

export function RightDock({
  projectId,
  state = "idle",
  draft,
  onDraftChange,
  messages = [],
  proposal = null,
  runState = { kind: "idle" },
  selectedCandidateIds,
  onSelectedCandidateIdsChange,
  conversationScroll = { key: "default", top: 0, pinnedToBottom: true },
  memory,
  onConversationScrollChange,
  selectedSegment,
  inspectorTargets = [],
  inspectorDisabled = false,
  partialRegeneration,
  loadApprovedTtsCandidates,
  ttsCandidateScopeKey,
  onInspectorAction,
  composerDisabled = false,
  onSendMessage,
  onApplyProposal,
  onRefreshProposal,
  onManualEdit,
  onUseDraftAsScript,
  onPreviewCandidate,
  onStart,
  startFailure = null,
  onRetryMessage,
  onCancelRun,
  onRetryRun,
  retryAfterSeconds = null,
}: RightDockProps) {
  // 캡컷은 클립을 누르면 속성이 이미 거기 있다. 접힌 채로 두었더니 `유진과 편집
  // 항목` → `편집 항목 열기` → `편집 대상`까지 네 겹을 지나야 속도·소리에 닿았다.
  // 접는 것은 여전히 되지만 기본은 펴 둔다.
  const [inspectorOpen, setInspectorOpen] = useState(true);
  const [selectedInspectorTargetId, setSelectedInspectorTargetId] = useState<string | null>(null);
  const inspectorTargetIdentity = inspectorTargets.map((target) => target.id).join("|");
  const [retryRemaining, setRetryRemaining] = useState(0);
  const historyRef = useRef<HTMLDivElement>(null);
  const composerContainerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setSelectedInspectorTargetId((current) => inspectorTargets.some((target) => target.id === current)
      ? current
      : inspectorTargets[0]?.id ?? null);
  }, [inspectorTargetIdentity, inspectorTargets]);
  useEffect(() => {
    setRetryRemaining(Math.max(0, retryAfterSeconds ?? 0));
  }, [retryAfterSeconds]);
  useEffect(() => {
    if (retryRemaining <= 0) return;
    const timer = window.setTimeout(() => setRetryRemaining((seconds) => Math.max(0, seconds - 1)), 1000);
    return () => window.clearTimeout(timer);
  }, [retryRemaining]);
  useLayoutEffect(() => {
    const history = historyRef.current;
    if (!history) return;
    history.scrollTop = conversationScroll.pinnedToBottom
      ? history.scrollHeight
      : conversationScroll.top;
  }, [conversationScroll.key, conversationScroll.pinnedToBottom, conversationScroll.top, messages]);

  const proposalIsReady = proposal?.status === "ready";
  const proposalIsCurrent = proposalIsReady
    && proposal.baseSessionRevision === proposal.currentRevision;
  // 편집본이 앞서 나가면 이 추천은 적용할 수 없다. 그 사실을 말하지 않으면
  // 적용 단추가 이유 없이 꺼져 있는 것처럼만 보인다.
  // **보고 있을 때는 대신 물어본다.** 편집본이 바뀌면 추천이 무효가 되는 것은
  // 백엔드가 여러 겹으로 지키는 계약이라 그대로 둔다. 문제는 그다음이었다 --
  // 죽은 카드와 단추만 남고, 창작자가 그걸 눈치채고 눌러야 대화가 이어졌다.
  //
  // 이 도크가 그려졌다는 것은 창작자가 지금 그것을 보고 있다는 뜻이다. 닫혀 있으면
  // 아무 일도 하지 않는다 -- 다시 묻는 것은 로컬 모델을 한 번 돌리는 일이라,
  // 안 보는 화면 때문에 시간을 쓸 이유가 없다.
  //
  // 같은 편집본에서는 한 번만 묻는다. 두 번 물으면 답은 같고 시간만 쓴다.
  const askedForRevision = useRef<number | null>(null);
  const proposalIsOutOfDate = Boolean(
    proposal && proposal.baseSessionRevision !== proposal.currentRevision,
  );
  const activeCandidateIds = selectedCandidateIds
    ?? (proposal?.candidates[0] ? [proposal.candidates[0].candidateId] : []);
  const selectedCandidatesAreActionable = Boolean(
    proposalIsCurrent
    && activeCandidateIds.length === 1
    && proposal?.candidates.some((candidate) => (
      candidate.candidateId === activeCandidateIds[0]
      && candidate.actionable
      && candidate.availability === "actionable"
      && candidate.reviewStatus === "approved"
    )),
  );
  const selectedInspectorTarget = inspectorTargets.find((target) => target.id === selectedInspectorTargetId) ?? null;
  const canSend = Boolean(!composerDisabled && onSendMessage && draft.trim());
  const showConversationStarters = messages.length === 0
    && !proposal
    && state === "idle"
    && runState.kind === "idle";
  const chooseConversationStarter = (starter: { label: string }) => {
    onDraftChange(starter.label);
    composerContainerRef.current?.querySelector<HTMLTextAreaElement>("textarea")?.focus();
  };
  const submit = () => { if (canSend) void onSendMessage?.(draft.trim()); };
  const runStatusAnnouncement = runState.kind === "complete"
    ? "유진 답변을 받았어요."
    : runState.kind === "unavailable"
    ? `${runState.message} 수동 편집을 계속할 수 있어요.`
    : null;
  useEffect(() => {
    if (!proposalIsOutOfDate || !onRefreshProposal) return;
    if (state === "analysis_running" || state === "applying") return;
    const revision = proposal?.currentRevision ?? null;
    if (revision === null || askedForRevision.current === revision) return;
    askedForRevision.current = revision;
    void onRefreshProposal();
  }, [onRefreshProposal, proposal?.currentRevision, proposalIsOutOfDate, state]);

  const recommendationCandidates = proposal?.candidates.filter((candidate) => !candidate.readOnlyFinding) ?? [];
  const readOnlyFindings = proposal?.candidates.filter((candidate) => candidate.readOnlyFinding) ?? [];

  // **선택한 것의 속성이 맨 앞에 온다.** 유진 대화를 지나 스크롤해야 나오면
  // 있어도 못 찾는다 -- 2026-08-17에 컷 도구가 정확히 그랬다.
  return <div className="vb-editor-right-dock">
    <section className="vb-editor-workbench__summary">
      <Button type="button" aria-expanded={inspectorOpen} onClick={() => setInspectorOpen((open) => !open)}>{inspectorOpen ? "편집 항목 닫기" : "편집 항목 열기"}</Button>
      {inspectorOpen ? <div role="region" aria-label="편집 항목" className="vb-editor-right-dock__inspector">
        <h2>편집 항목</h2>
        {selectedSegment ? <p>{selectedSegment.startSec.toFixed(2)}–{selectedSegment.endSec.toFixed(2)}초 구간</p> : <p>선택한 구간이 없어요.</p>}
        {inspectorTargets.length > 1 ? <label>편집 대상<NativeSelect aria-label="편집 대상" value={selectedInspectorTargetId ?? ""} onChange={(event) => setSelectedInspectorTargetId(event.target.value)}>{inspectorTargets.map((target) => <option key={target.id} value={target.id}>{target.label}</option>)}</NativeSelect></label> : null}
        {!inspectorTargets.length ? <p>현재 편집 명령이 지원하는 항목만 표시됩니다.</p> : null}
        {onInspectorAction ? <InspectorControls
          disabled={inspectorDisabled}
          loadApprovedTtsCandidates={loadApprovedTtsCandidates}
          onAction={onInspectorAction}
          partialRegeneration={partialRegeneration}
          projectId={projectId}
          selectedSegment={selectedSegment ?? null}
          target={selectedInspectorTarget}
          ttsCandidateScopeKey={ttsCandidateScopeKey}
        /> : null}
      </div> : null}
    </section>
    <section aria-label="유진" className="vb-editor-workbench__summary">
      <h2>유진</h2>
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
          ? messages.map((message) => <article key={message.id}><p><strong>{message.role === "user" ? "나" : "유진"}</strong> {message.text}</p></article>)
          : <>
            <p>유진 대화는 아직 시작하지 않았어요.</p>
            {showConversationStarters ? <YujinStarters
              // The original fixed starters were available before a segment
              // was selected; keep that entry point while the registry grows
              // context-aware alternatives.
              context={{ surface: "edit", selection: selectedSegment ? "segment" : "none" }}
              disabled={composerDisabled}
              onSelect={chooseConversationStarter}
            /> : null}
          </>}
      </div>
      <label htmlFor="vb-eugene-request">유진에게 요청하기</label>
      <div ref={composerContainerRef}>
        <Textarea id="vb-eugene-request" disabled={composerDisabled} value={draft} onChange={(event) => onDraftChange(event.target.value)} placeholder="예: 이 구간에 어울리는 B-roll을 추천해 줘" />
      </div>
      <Button type="button" disabled={!canSend} onClick={submit}>요청 보내기</Button>
      {/* 긴 글을 붙여 넣었으면 그것을 대본으로 받는 길을 준다(owner 2026-08-19).
          예전에는 대본이 `/plan`의 문답형 인터뷰로만 들어와서, 이미 써 둔 대본을
          가진 사람은 질문에 답해 가며 다시 만들어야 했다.
          짧은 한 줄에는 띄우지 않는다 -- 그건 요청이지 대본이 아니다. */}
      {onUseDraftAsScript && looksLikeScript(draft)
        ? <Button type="button" onClick={() => void onUseDraftAsScript(draft)}>이 글을 대본으로 쓰기</Button>
        : null}
      {onCancelRun
        ? <Button type="button" onClick={() => void onCancelRun()}>답변 중단</Button>
        : null}
      {runState.kind === "unavailable" && runState.retryable && onRetryRun
        ? <Button type="button" onClick={() => void onRetryRun()}>같은 요청 다시 보내기</Button>
        : null}

    </section>

    <section aria-label="추천" className="vb-editor-workbench__summary">
      <h2>추천</h2>
      {proposal ? <div aria-label="제안 편집본">
        <p>{`제안 기준 편집본 ${proposal.baseSessionRevision}`}</p>
        <p>{`현재 편집본 ${proposal.currentRevision}`}</p>
        {matchModeLabel(proposal.matchMode) ? <p>{matchModeLabel(proposal.matchMode)}</p> : null}
        {proposalIsOutOfDate && state !== "blocked" && state !== "error" ? <>
          <p role="status">{staleProposalMessage}</p>
          {onRefreshProposal ? <Button type="button" disabled={state === "analysis_running" || state === "applying"} onClick={() => void onRefreshProposal()}>지금 편집본으로 다시 추천받기</Button> : null}
        </> : null}
      </div> : null}
      {recommendationCandidates.length ? <div role="radiogroup" aria-label="추천 후보">
        {recommendationCandidates.map((candidate) => {
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
          return <article key={candidate.candidateId}>
            <label><Input
              type="radio"
              name="vb-eugene-candidate"
              aria-label={`${candidateLabel(candidate)} 선택`}
              checked={activeCandidateIds.includes(candidate.candidateId)}
              disabled={!candidateIsActionable}
              onChange={() => {
                if (candidateIsActionable) onSelectedCandidateIdsChange?.([candidate.candidateId]);
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
      </div> : <p>아직 추천이 없어요. 직접 편집을 계속하거나 유진에게 요청할 수 있어요.</p>}
      {proposal && proposalIsReady && onApplyProposal ? <Button type="button" disabled={state === "applying" || !selectedCandidatesAreActionable} onClick={() => void onApplyProposal(proposal.proposalId, activeCandidateIds)}>선택한 추천 적용</Button> : null}
    </section>

    {memory ? <YujinMemoryPanel memory={memory} /> : null}

    {readOnlyFindings.length ? <section aria-label="검사 결과" className="vb-editor-workbench__summary">
      <h2>검사 결과</h2>
      {readOnlyFindings.map((finding) => <article key={finding.candidateId}>
        {finding.supportedControls.check === "timeline_gaps"
          ? <p>{`빈 구간 ${String(finding.supportedControls.gap_count ?? 0)}개`}</p>
          : null}
      </article>)}
    </section> : null}

  </div>;
}


// 백엔드가 내는 값은 `semantic` / `word` 원값이다. 모르는 값이면 아무 말도
// 하지 않는다 -- 지어내는 것보다 침묵이 낫다.
const matchModeWords: Readonly<Record<string, string>> = {
  semantic: "뜻으로 찾음",
  word: "단어로만 찾음",
};

function matchModeLabel(mode: string | undefined): string | null {
  return mode ? matchModeWords[mode] ?? null : null;
}

// 소리만 있는 추천은 듣는 것이고 영상·이미지는 보는 것이다. 하나로 뭉뚱그리면
// owner는 영상 추천에 "미리 듣기"라고 적힌 단추를 누르게 된다.
function previewVerb(kind: RightDockCandidate["sourceMediaKind"]): string {
  return kind === "bgm" || kind === "sfx" ? "미리 듣기" : "미리 보기";
}

function mediaKindLabel(kind: RightDockCandidate["sourceMediaKind"]) {
  return {
    raw_video: "원본 영상",
    broll_video: "영상",
    image: "이미지",
    bgm: "배경 음악",
    sfx: "효과음",
    output_variant: "출력 변형",
  }[kind] ?? "미디어";
}

function controlSummary(controls: Readonly<Record<string, unknown>>) {
  const labels = Object.entries(controls).map(([name, value]) => {
    if (name === "fit") return value === "crop" ? "화면 채우기" : "화면 안에 맞추기";
    if (name === "volume") return `음량 ${value}`;
    if (name === "fade_in_sec") return `시작 전환 ${value}초`;
    if (name === "fade_out_sec") return `끝 전환 ${value}초`;
    if (name === "text") return "문구 변경";
    if (name === "style") return "자막 모양 변경";
    if (name === "candidate_id") return "승인한 음성";
    if (name === "overlay_kind") return "오버레이 변경";
    return null;
  }).filter((value): value is string => value !== null);
  return labels.join(", ") || "기본 설정";
}
