import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { Sparkles, XIcon } from "lucide-react";

import { Button } from "../../../components/ui/button";
import { Textarea } from "../../../components/ui/textarea";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "../../../components/ui/dialog";
import { YujinStarters } from "../../yujin/YujinStarters";
import type { RightDockCompletionEntry, RightDockConversationScroll, RightDockEditingProposal, RightDockEditingProposalPreview, RightDockMemory, RightDockMessage, RightDockProposal, YujinRunState } from "./rightDockTypes";
import { YujinMemoryPanel } from "./YujinMemoryPanel";

const staleProposalMessage = "편집본이 바뀌어서 이 추천은 그대로 적용할 수 없어요.";

const SCRIPT_MINIMUM_CHARACTERS = 30;
function looksLikeScript(draft: string): boolean {
  return draft.trim().length >= SCRIPT_MINIMUM_CHARACTERS;
}

const SCRIPT_BUTTON_TEXT = "이 답을 대본으로 쓰기";
function scriptButtonLabel(text: string): string {
  return `${SCRIPT_BUTTON_TEXT} — ${text.trim().slice(0, 20)}…`;
}

export type YujinPanelProps = Readonly<{
  /** 이 패널의 열림 상태는 오른쪽 도크와 완전히 독립이다(owner 지시
   *  2026-08-30: "우리 유진 대화창도 캡컷처럼 해도 되" -- 캡컷 EditPilot은
   *  속성 패널과 같은 도크의 탭이 아니라, 화면 구석에 떠 있는 버튼을 누르면
   *  따로 열리는 패널이다. `docs/reference/capcut-observed-2026-08-22.ko.md`
   *  §7 참고). 속성/추천 도크가 닫혀 있어도 이 패널은 열 수 있다. */
  open: boolean;
  onOpenChange: (open: boolean) => void;
  state?: "script_required" | "idle" | "analysis_running" | "proposal_ready" | "applying" | "blocked" | "error";
  draft: string;
  onDraftChange: (draft: string) => void;
  messages?: readonly RightDockMessage[];
  completions?: readonly RightDockCompletionEntry[];
  proposal?: RightDockProposal | null;
  runState?: YujinRunState;
  conversationScroll?: RightDockConversationScroll;
  onConversationScrollChange?: (scroll: RightDockConversationScroll) => void;
  memory?: RightDockMemory;
  composerDisabled?: boolean;
  onSendMessage?: (draft: string) => void | Promise<void>;
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
  conversationScroll = { key: "default", top: 0, pinnedToBottom: true },
  onConversationScrollChange,
  memory,
  composerDisabled = false,
  onSendMessage,
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
}: YujinPanelProps) {
  const [editingProposalOpen, setEditingProposalOpen] = useState(false);
  const editingProposalPreview: RightDockEditingProposalPreview = editingProposal?.preview ?? { kind: "idle" };
  const historyRef = useRef<HTMLDivElement>(null);
  const composerContainerRef = useRef<HTMLDivElement>(null);
  const askedForRevision = useRef<number | null>(null);

  // 패널이 닫혀 있어도(펼치는 버튼만 보일 때도) 이 컴포넌트 자체는 늘
  // 마운트돼 있다 -- 아래 "낡은 추천이면 다시 묻는다" 효과가 패널을 열지
  // 않은 채로도 계속 돌아야 하기 때문이다(예전에는 오른쪽 도크가 열려
  // 있어야만 돌았다. 이제는 도크와 무관하므로 여기서 직접 돈다).
  useLayoutEffect(() => {
    const history = historyRef.current;
    if (!history || !open) return;
    history.scrollTop = conversationScroll.pinnedToBottom
      ? history.scrollHeight
      : conversationScroll.top;
  }, [conversationScroll.key, conversationScroll.pinnedToBottom, conversationScroll.top, messages, open]);

  const proposalIsOutOfDate = Boolean(
    proposal && proposal.baseSessionRevision !== proposal.currentRevision,
  );
  useEffect(() => {
    if (!proposalIsOutOfDate || !onRefreshProposal) return;
    if (state === "analysis_running" || state === "applying") return;
    const revision = proposal?.currentRevision ?? null;
    if (revision === null || askedForRevision.current === revision) return;
    askedForRevision.current = revision;
    void onRefreshProposal();
  }, [onRefreshProposal, proposal?.currentRevision, proposalIsOutOfDate, state]);

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

  if (!open) {
    return <Button type="button" className="vb-yujin-panel__toggle" onClick={() => onOpenChange(true)}>
      <Sparkles aria-hidden="true" /> 유진
    </Button>;
  }

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
      {completions.length
        ? completions.map((completion) => <article key={completion.id} className="vb-editor-right-dock__completion" role="status" aria-label={`모든 작업 완료 ${completion.items.length}/${completion.items.length}`}>
          <p><strong>모든 작업 완료</strong> {completion.items.length}/{completion.items.length}</p>
          <ul>{completion.items.map((item, index) => <li key={`${completion.id}-${index}`}>{item.sceneLabel ? `${item.sceneLabel} · ` : ""}{item.label}</li>)}</ul>
        </article>)
        : null}
      {!messages.length && !completions.length
        ? <>
          <p>유진 대화는 아직 시작하지 않았어요.</p>
          {showConversationStarters ? <YujinStarters
            context={{ surface: "edit", selection: hasSelectedSegment ? "segment" : "none" }}
            disabled={composerDisabled}
            onSelect={chooseConversationStarter}
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
