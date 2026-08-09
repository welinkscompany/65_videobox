import { useEffect, useLayoutEffect, useRef, useState } from "react";

import { Button } from "../../../components/ui/button";
import { Input } from "../../../components/ui/input";
import { NativeSelect } from "../../../components/ui/native-select";
import { Textarea } from "../../../components/ui/textarea";
import { InspectorControls, type ApprovedTtsCandidate, type InspectorAction, type PartialRegenerationControls } from "../inspector/InspectorControls";
import type { InspectorTarget } from "../inspector/inspectorRegistry";
import type { RightDockCandidate, RightDockConversationScroll, RightDockMemory, RightDockMessage, RightDockProposal, YujinRunState } from "./rightDockTypes";
import { YujinMemoryPanel } from "./YujinMemoryPanel";

export type { InspectorTarget } from "../inspector/inspectorRegistry";

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
  onManualEdit?: () => void;
  onPreviewCandidate?: (candidate: RightDockCandidate) => void;
  onStart?: () => void | Promise<void>;
  onRetryMessage?: () => void | Promise<void>;
  onCancelRun?: () => void | Promise<void>;
  onRetryRun?: () => void | Promise<void>;
  retryAfterSeconds?: number | null;
}>;

export function RightDock({
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
  onManualEdit,
  onPreviewCandidate,
  onStart,
  onRetryMessage,
  onCancelRun,
  onRetryRun,
  retryAfterSeconds = null,
}: RightDockProps) {
  const [inspectorOpen, setInspectorOpen] = useState(false);
  const [selectedInspectorTargetId, setSelectedInspectorTargetId] = useState<string | null>(null);
  const inspectorTargetIdentity = inspectorTargets.map((target) => target.id).join("|");
  const [retryRemaining, setRetryRemaining] = useState(0);
  const historyRef = useRef<HTMLDivElement>(null);

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
  const submit = () => { if (canSend) void onSendMessage?.(draft.trim()); };
  const runStatusAnnouncement = runState.kind === "complete"
    ? "유진 답변을 받았어요."
    : runState.kind === "unavailable"
    ? `${runState.message} 수동 편집을 계속할 수 있어요.`
    : null;
  const recommendationCandidates = proposal?.candidates.filter((candidate) => !candidate.readOnlyFinding) ?? [];
  const readOnlyFindings = proposal?.candidates.filter((candidate) => candidate.readOnlyFinding) ?? [];

  return <div className="vb-editor-right-dock">
    <section aria-label="유진" className="vb-editor-workbench__summary">
      <h2>유진</h2>
      {runStatusAnnouncement ? <p role="status" aria-live="polite" aria-atomic="true" aria-label="유진 대화 상태" className="sr-only">{runStatusAnnouncement}</p> : null}
      {runState.kind === "complete" && runState.syncWarning
        ? <p aria-label="대화 저장 상태" className="vb-editor-right-dock__sync-warning">{runState.syncWarning}</p>
        : null}
      {(runState.kind === "streaming" || runState.kind === "unavailable") && runState.cancelWarning
        ? <p role="status" className="vb-editor-right-dock__sync-warning">{runState.cancelWarning}</p>
        : null}
      {state === "blocked" || state === "error" || runState.kind === "unavailable" ? <div className="vb-editor-right-dock__fallback"><p>{runState.kind === "unavailable" ? runState.message : "유진의 답을 받지 못했어요."}</p>{onManualEdit ? <Button type="button" onClick={onManualEdit}>유진 없이 계속 편집</Button> : null}</div> : null}
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
        {messages.length ? messages.map((message) => <article key={message.id}><p><strong>{message.role === "user" ? "나" : "유진"}</strong> {message.text}</p></article>) : <p>유진 대화는 아직 시작하지 않았어요.</p>}
      </div>
      <label htmlFor="vb-eugene-request">유진에게 요청하기</label>
      <Textarea id="vb-eugene-request" disabled={composerDisabled} value={draft} onChange={(event) => onDraftChange(event.target.value)} placeholder="예: 이 구간에 어울리는 B-roll을 추천해 줘" />
      <Button type="button" disabled={!canSend} onClick={submit}>요청 보내기</Button>
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
              aria-label={`${candidate.visibleReferenceCode} 선택`}
              checked={activeCandidateIds.includes(candidate.candidateId)}
              disabled={!candidateIsActionable}
              onChange={() => {
                if (candidateIsActionable) onSelectedCandidateIdsChange?.([candidate.candidateId]);
              }}
            />{candidate.visibleReferenceCode} · {mediaKindLabel(candidate.sourceMediaKind)}</label>
            <p>{candidate.previewSummary}</p>
            <p>{`후보 상태: ${candidateDeclaresActionable ? "적용 가능" : "수동 적용"}`}</p>
            <dl>
              <dt>미디어</dt><dd>{mediaKindLabel(candidate.sourceMediaKind)}</dd>
              <dt>적용 설정</dt><dd>{controlSummary(candidate.supportedControls ?? {})}</dd>
            </dl>
            {candidateIsActionable && candidate.previewUrl && onPreviewCandidate ? <Button type="button" onClick={() => onPreviewCandidate(candidate)}>추천 미리 듣기</Button> : null}
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
          selectedSegment={selectedSegment ?? null}
          target={selectedInspectorTarget}
          ttsCandidateScopeKey={ttsCandidateScopeKey}
        /> : null}
      </div> : null}
    </section>
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

function mediaKindLabel(kind: RightDockCandidate["sourceMediaKind"]) {
  return {
    raw_video: "원본 영상",
    broll_video: "영상",
    image: "이미지",
    bgm: "배경 음악",
    sfx: "효과음",
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
