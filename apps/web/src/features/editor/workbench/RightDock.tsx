import { useEffect, useState } from "react";

import { Button } from "../../../components/ui/button";
import { Input } from "../../../components/ui/input";
import { NativeSelect } from "../../../components/ui/native-select";
import { Textarea } from "../../../components/ui/textarea";
import { InspectorControls, type InspectorAction, type PartialRegenerationControls } from "../inspector/InspectorControls";
import type { InspectorTarget } from "../inspector/inspectorRegistry";
import type { RightDockCandidate, RightDockMessage, RightDockProposal } from "./rightDockTypes";

export type { InspectorTarget } from "../inspector/inspectorRegistry";

type SelectedSegment = Readonly<{
  segmentId: string;
  startSec: number;
  endSec: number;
  nextSegmentId: string | null;
  cutAction: string;
  draftApplied: boolean;
}>;

export type RightDockProps = Readonly<{
  state?: "script_required" | "idle" | "analysis_running" | "proposal_ready" | "applying" | "blocked" | "error";
  draft: string;
  onDraftChange: (draft: string) => void;
  messages?: readonly RightDockMessage[];
  proposal?: RightDockProposal | null;
  selectedSegment?: SelectedSegment;
  inspectorTargets?: readonly InspectorTarget[];
  inspectorDisabled?: boolean;
  partialRegeneration?: PartialRegenerationControls;
  onInspectorAction?: (action: InspectorAction) => void | Promise<void>;
  composerDisabled?: boolean;
  onSendMessage?: (draft: string) => void | Promise<void>;
  onApplyProposal?: (proposalId: string, candidateIds: readonly string[]) => void | Promise<void>;
  onManualEdit?: () => void;
  onPreviewCandidate?: (candidate: RightDockCandidate) => void;
  onStart?: () => void | Promise<void>;
  onRetryMessage?: () => void | Promise<void>;
  retryAfterSeconds?: number | null;
}>;

export function RightDock({
  state = "idle",
  draft,
  onDraftChange,
  messages = [],
  proposal = null,
  selectedSegment,
  inspectorTargets = [],
  inspectorDisabled = false,
  partialRegeneration,
  onInspectorAction,
  composerDisabled = false,
  onSendMessage,
  onApplyProposal,
  onManualEdit,
  onPreviewCandidate,
  onStart,
  onRetryMessage,
  retryAfterSeconds = null,
}: RightDockProps) {
  const [inspectorOpen, setInspectorOpen] = useState(false);
  const [selectedInspectorTargetId, setSelectedInspectorTargetId] = useState<string | null>(null);
  const [selectedCandidateIds, setSelectedCandidateIds] = useState<readonly string[]>(() => proposal?.candidates[0] ? [proposal.candidates[0].candidateId] : []);
  const candidateIdentity = proposal?.candidates.map((candidate) => candidate.candidateId).join("|") ?? "";
  const inspectorTargetIdentity = inspectorTargets.map((target) => target.id).join("|");
  const [retryRemaining, setRetryRemaining] = useState(0);

  useEffect(() => {
    setSelectedCandidateIds(proposal?.candidates[0] ? [proposal.candidates[0].candidateId] : []);
  }, [proposal?.proposalId, candidateIdentity]);
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

  const proposalIsReady = proposal?.status === "ready";
  const selectedInspectorTarget = inspectorTargets.find((target) => target.id === selectedInspectorTargetId) ?? null;
  const canSend = Boolean(!composerDisabled && onSendMessage && draft.trim());
  const submit = () => { if (canSend) void onSendMessage?.(draft.trim()); };

  return <div className="vb-editor-right-dock">
    <section aria-label="유진" className="vb-editor-workbench__summary">
      <h2>유진</h2>
      {state === "blocked" || state === "error" ? <div className="vb-editor-right-dock__fallback"><p>유진이 지금 추천을 만들 수 없어요. 직접 골라 계속 편집할 수 있어요.</p>{onManualEdit ? <Button type="button" onClick={onManualEdit}>직접 편집하기</Button> : null}</div> : null}
      {state === "idle" && !proposal && onStart ? <Button type="button" onClick={() => void onStart()}>유진에게 추천받기</Button> : null}
      <div role="log" aria-label="유진 대화" className="vb-editor-right-dock__history" tabIndex={0}>
        {messages.length ? messages.map((message) => <article key={message.id}><p><strong>나</strong> {message.userText}</p><p><strong>유진</strong> {message.assistantText}</p></article>) : <p>유진 대화는 아직 시작하지 않았어요.</p>}
      </div>
      <label htmlFor="vb-eugene-request">유진에게 요청하기</label>
      <Textarea id="vb-eugene-request" disabled={composerDisabled} value={draft} onChange={(event) => onDraftChange(event.target.value)} placeholder="예: 이 구간에 어울리는 B-roll을 추천해 줘" />
      <Button type="button" disabled={!canSend} onClick={submit}>요청 보내기</Button>
      {onRetryMessage ? <Button type="button" disabled={retryRemaining > 0} onClick={() => void onRetryMessage()}>{retryRemaining > 0 ? `같은 요청 다시 보내기 (${retryRemaining}초)` : "같은 요청 다시 보내기"}</Button> : null}
    </section>

    <section aria-label="추천" className="vb-editor-workbench__summary">
      <h2>추천</h2>
      {proposal?.candidates.length ? <div role="radiogroup" aria-label="추천 후보">
        {proposal.candidates.map((candidate) => <label key={candidate.candidateId}><Input type="radio" name="vb-eugene-candidate" aria-label={`${candidate.visibleReferenceCode} 선택`} checked={selectedCandidateIds.includes(candidate.candidateId)} onChange={() => setSelectedCandidateIds([candidate.candidateId])} />{candidate.visibleReferenceCode} · {candidate.mediaType}{candidate.previewUrl && onPreviewCandidate ? <Button type="button" onClick={() => onPreviewCandidate(candidate)}>추천 미리 듣기</Button> : null}</label>)}
      </div> : <p>아직 추천이 없어요. 직접 편집을 계속하거나 유진에게 요청할 수 있어요.</p>}
      {proposal && proposalIsReady && onApplyProposal ? <Button type="button" disabled={state === "applying"} onClick={() => void onApplyProposal(proposal.proposalId, selectedCandidateIds)}>선택한 추천 적용</Button> : null}
    </section>

    <section className="vb-editor-workbench__summary">
      <Button type="button" aria-expanded={inspectorOpen} onClick={() => setInspectorOpen((open) => !open)}>{inspectorOpen ? "편집 항목 닫기" : "편집 항목 열기"}</Button>
      {inspectorOpen ? <div role="region" aria-label="편집 항목" className="vb-editor-right-dock__inspector">
        <h2>편집 항목</h2>
        {selectedSegment ? <p>{selectedSegment.startSec.toFixed(2)}–{selectedSegment.endSec.toFixed(2)}초 구간</p> : <p>선택한 구간이 없어요.</p>}
        {inspectorTargets.length > 1 ? <label>편집 대상<NativeSelect aria-label="편집 대상" value={selectedInspectorTargetId ?? ""} onChange={(event) => setSelectedInspectorTargetId(event.target.value)}>{inspectorTargets.map((target) => <option key={target.id} value={target.id}>{target.label}</option>)}</NativeSelect></label> : null}
        {!inspectorTargets.length ? <p>현재 편집 명령이 지원하는 항목만 표시됩니다.</p> : null}
        {onInspectorAction ? <InspectorControls
          disabled={inspectorDisabled}
          onAction={onInspectorAction}
          partialRegeneration={partialRegeneration}
          selectedSegment={selectedSegment ?? null}
          target={selectedInspectorTarget}
        /> : null}
      </div> : null}
    </section>
  </div>;
}
