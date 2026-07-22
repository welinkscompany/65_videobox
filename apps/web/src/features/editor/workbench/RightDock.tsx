import { useEffect, useState } from "react";

import type { DirectorProposal } from "../../../api";
import type { DirectorMessageExchange, DirectorWorkspaceState } from "../../director/directorTypes";

export type InspectorTarget = Readonly<{
  id: string;
  label: string;
  kind: "broll" | "bgm" | "sfx" | "caption" | "overlay";
}>;

type SelectedSegment = Readonly<{ segmentId: string; startSec: number; endSec: number; draftApplied: boolean }>;

export type RightDockProps = Readonly<{
  state?: DirectorWorkspaceState;
  draft: string;
  onDraftChange: (draft: string) => void;
  messages?: readonly DirectorMessageExchange[];
  proposal?: DirectorProposal | null;
  selectedSegment?: SelectedSegment;
  inspectorTargets?: readonly InspectorTarget[];
  composerDisabled?: boolean;
  onSendMessage?: (draft: string) => void | Promise<void>;
  onApplyProposal?: (proposalId: string, candidateIds: readonly string[]) => void | Promise<void>;
  onManualEdit?: () => void;
}>;

export function RightDock({
  state = "idle",
  draft,
  onDraftChange,
  messages = [],
  proposal = null,
  selectedSegment,
  inspectorTargets = [],
  composerDisabled = false,
  onSendMessage,
  onApplyProposal,
  onManualEdit,
}: RightDockProps) {
  const [inspectorOpen, setInspectorOpen] = useState(false);
  const [selectedCandidateIds, setSelectedCandidateIds] = useState<readonly string[]>(() => proposal?.candidates[0] ? [proposal.candidates[0].candidate_id] : []);
  const candidateIdentity = proposal?.candidates.map((candidate) => candidate.candidate_id).join("|") ?? "";

  useEffect(() => {
    setSelectedCandidateIds(proposal?.candidates[0] ? [proposal.candidates[0].candidate_id] : []);
  }, [proposal?.proposal_id, candidateIdentity]);

  const proposalIsReady = proposal?.status === "ready";
  const canSend = Boolean(!composerDisabled && onSendMessage && draft.trim());
  const submit = () => { if (canSend) void onSendMessage?.(draft.trim()); };

  return <div className="vb-editor-right-dock">
    <section aria-label="유진" className="vb-editor-workbench__summary">
      <h2>유진</h2>
      {state === "blocked" || state === "error" ? <div className="vb-editor-right-dock__fallback"><p>유진이 지금 추천을 만들 수 없어요. 직접 골라 계속 편집할 수 있어요.</p>{onManualEdit ? <button type="button" onClick={onManualEdit}>직접 편집하기</button> : null}</div> : null}
      <div role="log" aria-label="유진 대화" className="vb-editor-right-dock__history" tabIndex={0}>
        {messages.length ? messages.map((message) => <article key={message.assistant_message.message_id}><p><strong>나</strong> {message.user_message.text}</p><p><strong>유진</strong> {message.assistant_message.text}</p></article>) : <p>유진 대화는 아직 시작하지 않았어요.</p>}
      </div>
      <label htmlFor="vb-eugene-request">유진에게 요청하기</label>
      <textarea id="vb-eugene-request" disabled={composerDisabled} value={draft} onChange={(event) => onDraftChange(event.target.value)} placeholder="예: 이 구간에 어울리는 B-roll을 추천해 줘" />
      <button type="button" disabled={!canSend} onClick={submit}>요청 보내기</button>
    </section>

    <section aria-label="추천" className="vb-editor-workbench__summary">
      <h2>추천</h2>
      {proposal?.candidates.length ? <div role="radiogroup" aria-label="추천 후보">
        {proposal.candidates.map((candidate) => <label key={candidate.candidate_id}><input type="radio" name="vb-eugene-candidate" aria-label={`${candidate.visible_reference_code} 선택`} checked={selectedCandidateIds.includes(candidate.candidate_id)} onChange={() => setSelectedCandidateIds([candidate.candidate_id])} />{candidate.visible_reference_code} · {candidate.media_type}</label>)}
      </div> : <p>아직 추천이 없어요. 직접 편집을 계속하거나 유진에게 요청할 수 있어요.</p>}
      {proposal && proposalIsReady && onApplyProposal ? <button type="button" onClick={() => void onApplyProposal(proposal.proposal_id, selectedCandidateIds)}>선택한 추천 적용</button> : null}
    </section>

    <section className="vb-editor-workbench__summary">
      <button type="button" aria-expanded={inspectorOpen} onClick={() => setInspectorOpen((open) => !open)}>{inspectorOpen ? "Inspector 닫기" : "Inspector 열기"}</button>
      {inspectorOpen ? <div role="region" aria-label="Inspector" className="vb-editor-right-dock__inspector"><h2>Inspector</h2>{selectedSegment ? <p>선택 구간: {selectedSegment.segmentId} · {selectedSegment.startSec.toFixed(2)}–{selectedSegment.endSec.toFixed(2)}초</p> : <p>선택한 구간이 없어요.</p>}{inspectorTargets.length ? <ul>{inspectorTargets.map((target) => <li key={target.id}>{target.label} · {target.kind}</li>)}</ul> : <p>현재 편집 명령이 지원하는 항목만 표시됩니다.</p>}</div> : null}
    </section>
  </div>;
}
