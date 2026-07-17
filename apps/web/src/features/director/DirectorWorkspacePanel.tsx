import { useEffect, useRef, useState } from "react";
import { api, type DirectorMessageExchange, type DirectorProposal } from "../../api";
import { DirectorWorkspace } from "./DirectorWorkspace";
import type { DirectorWorkspaceState } from "./directorTypes";

export function DirectorWorkspacePanel({ projectId, sessionId, sessionRevision, selectedSegment, onStateChange, applyEditingMutation }: { projectId: string; sessionId: string | null; sessionRevision: number; selectedSegment?: { segmentId: string; startSec: number; endSec: number; draftApplied: boolean }; onStateChange?: (state: DirectorWorkspaceState) => void; applyEditingMutation?: (action: () => Promise<unknown>) => Promise<unknown> }) {
  const [state, setState] = useState<DirectorWorkspaceState>(sessionId ? "analysis_running" : "script_required");
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [proposal, setProposal] = useState<DirectorProposal | null>(null);
  const stableMessageId = useRef<string | null>(null);
  useEffect(() => { onStateChange?.(state); }, [onStateChange, state]);
  useEffect(() => {
    let cancelled = false;
    if (!sessionId) { setState("script_required"); return () => { cancelled = true; }; }
    setState("analysis_running"); setConversationId(null); setProposal(null); stableMessageId.current = null;
    void api.reloadDirectorSession(projectId, sessionId).then(async (recovered) => {
      if (cancelled) return;
      if (recovered.conversation) setConversationId(recovered.conversation.conversation_id);
      if (recovered.proposal) { setProposal(recovered.proposal); setState("proposal_ready"); return; }
      // Recovery is deliberately read-only.  A reload must not manufacture a
      // conversation/proposal merely because the operator has not asked for
      // one yet; manual mode stays available from this neutral state.
      setState("idle");
    }).catch((error: unknown) => { if (!cancelled) setState(error instanceof SyntaxError || error instanceof TypeError ? "error" : "blocked"); });
    return () => { cancelled = true; };
  }, [projectId, sessionId]);
  const sendMessage = async (text: string) => {
    if (!conversationId || !sessionId) throw new Error("director_conversation_unavailable");
    stableMessageId.current ??= globalThis.crypto?.randomUUID?.() ?? `director-${Date.now()}`;
    const prepared = api.prepareDirectorMessage(projectId, conversationId, { session_id: sessionId, client_message_id: stableMessageId.current, text });
    const result = await prepared.send();
    if (result.kind === "exchange") {
      stableMessageId.current = null;
      const exchange: DirectorMessageExchange = result.exchange;
      const proposalId = exchange.assistant_message.proposal_id ?? (typeof exchange.action_intent?.proposal_preflight?.proposal_id === "string" ? exchange.action_intent.proposal_preflight.proposal_id : null);
      if (proposalId) setProposal(await api.getDirectorProposal(projectId, proposalId));
    }
    return result;
  };
  const apply = async (proposalId: string, payload: { candidate_ids: string[]; expected_revision: number }) => {
    const action = () => api.batchApplyDirectorProposal(projectId, proposalId, payload);
    const result = applyEditingMutation ? await applyEditingMutation(action) : await action();
    if (result == null) throw new Error("director_apply_failed");
    return result;
  };
  const start = async () => {
    if (!sessionId || proposal) return;
    setState("analysis_running");
    try {
      if (!conversationId) {
        const conversation = await api.createDirectorConversation(projectId, { session_id: sessionId });
        setConversationId(conversation.conversation_id);
      }
      const initialProposal = await api.createDirectorProposal(projectId, { session_id: sessionId });
      setProposal(initialProposal); setState("proposal_ready");
    } catch { setState("idle"); }
  };
  return <DirectorWorkspace state={state} projectId={projectId} sessionId={sessionId ?? ""} sessionRevision={sessionRevision} selectedSegment={selectedSegment} proposal={proposal} sendMessage={sendMessage} preflightProposal={(id) => api.preflightDirectorProposal(projectId, id)} refreshProposal={async (id) => setProposal(await api.refreshDirectorProposal(projectId, id))} updatePreferences={async (payload) => { await api.updateDirectorPreferences(projectId, payload); }} materializeCandidate={(proposalId, candidateId) => api.materializeDirectorCandidate(projectId, proposalId, candidateId)} applyProposal={(proposalId, payload) => api.applyDirectorProposal(projectId, proposalId, payload)} batchApplyProposal={apply} onManualMode={() => setState("idle")} onStart={start} />;
}
