import { useEffect, useRef, useState } from "react";
import { api, type DirectorMessageExchange, type DirectorProposal } from "../../api";
import { DirectorWorkspace } from "./DirectorWorkspace";
import type { DirectorWorkspaceState } from "./directorTypes";

export function DirectorWorkspacePanel({ projectId, sessionId, sessionRevision, selectedSegment, onStateChange }: { projectId: string; sessionId: string | null; sessionRevision: number; selectedSegment?: { segmentId: string; startSec: number; endSec: number; draftApplied: boolean }; onStateChange?: (state: DirectorWorkspaceState) => void }) {
  const [state, setState] = useState<DirectorWorkspaceState>(sessionId ? "analysis_running" : "script_required");
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [proposal, setProposal] = useState<DirectorProposal | null>(null);
  const stableMessageId = useRef<string | null>(null);
  useEffect(() => { onStateChange?.(state); }, [onStateChange, state]);
  useEffect(() => {
    let cancelled = false;
    if (!sessionId) { setState("script_required"); return () => { cancelled = true; }; }
    setState("analysis_running"); setConversationId(null); setProposal(null); stableMessageId.current = null;
    void Promise.all([api.createDirectorConversation(projectId, { session_id: sessionId }), api.createDirectorProposal(projectId, { session_id: sessionId })]).then(([conversation, initialProposal]) => {
      if (cancelled) return; setConversationId(conversation.conversation_id); setProposal(initialProposal); setState("proposal_ready");
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
  return <DirectorWorkspace state={state} projectId={projectId} sessionId={sessionId ?? ""} sessionRevision={sessionRevision} selectedSegment={selectedSegment} proposal={proposal} sendMessage={sendMessage} preflightProposal={(id) => api.preflightDirectorProposal(projectId, id)} refreshProposal={async (id) => setProposal(await api.refreshDirectorProposal(projectId, id))} updatePreferences={async (payload) => { await api.updateDirectorPreferences(projectId, payload); }} materializeCandidate={(proposalId, candidateId) => api.materializeDirectorCandidate(projectId, proposalId, candidateId)} applyProposal={(proposalId, payload) => api.applyDirectorProposal(projectId, proposalId, payload)} batchApplyProposal={(proposalId, payload) => api.batchApplyDirectorProposal(projectId, proposalId, payload)} onManualMode={() => setState("idle")} />;
}
