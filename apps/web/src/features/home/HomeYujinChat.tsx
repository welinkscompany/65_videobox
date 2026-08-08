import { useEffect, useRef, useState } from "react";

import { api } from "../../api";
import { Button } from "../../components/ui/button";
import { Textarea } from "../../components/ui/textarea";

type Turn = { id: string; role: "user" | "assistant"; text: string };

const cannotAnswer = "유진이 지금 답하지 못했어요. 잠시 뒤 다시 보내 주세요.";

/** Yujin on the home screen, so a question does not require opening the editor.
 *
 * This uses the same local-first route the editor chats through
 * (`POST .../messages`), which is also the only route that reads the owner's
 * approved memories. A message needs an editing session to hang on, so a
 * project with no draft yet says so instead of failing on send.
 */
export function HomeYujinChat({ projectId }: { projectId: string }) {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [ready, setReady] = useState(false);
  const [draft, setDraft] = useState("");
  const [turns, setTurns] = useState<readonly Turn[]>([]);
  const [sending, setSending] = useState(false);
  const conversationId = useRef<string | null>(null);
  // Switching project while Yujin is still answering must not drop that answer
  // into the new project -- the owner would read it as advice about footage it
  // never saw. Every send captures the epoch it started in.
  const epoch = useRef(0);

  useEffect(() => {
    let active = true;
    epoch.current += 1;
    conversationId.current = null;
    setReady(false);
    setSessionId(null);
    setTurns([]);
    void api.getLatestEditingSession(projectId)
      .then((session) => {
        if (!active) return;
        setSessionId(session?.session_id ?? null);
        setReady(true);
      })
      .catch(() => { if (active) setReady(true); });
    return () => { active = false; };
  }, [projectId]);

  const send = async () => {
    const text = draft.trim();
    if (!text || !sessionId || sending) return;
    setSending(true);
    const startedIn = epoch.current;
    const isCurrent = () => epoch.current === startedIn;
    const clientMessageId = crypto.randomUUID();
    setTurns((current) => [...current, { id: `u:${clientMessageId}`, role: "user", text }]);
    setDraft("");
    try {
      if (!conversationId.current) {
        const conversation = await api.createDirectorConversation(projectId, { session_id: sessionId });
        if (!isCurrent()) return;
        conversationId.current = conversation.conversation_id;
      }
      const result = await api.sendDirectorMessage(projectId, conversationId.current, {
        session_id: sessionId,
        client_message_id: clientMessageId,
        text,
      });
      // A duplicate of the same message is still generating; say so rather
      // than pretending the answer is lost.
      const answer = result.kind === "in_progress"
        ? "먼저 보낸 요청에 답하는 중이에요. 잠시만 기다려 주세요."
        : (result.exchange.assistant_message.metadata as { status?: string } | null)
          ?.status === "blocked"
          ? cannotAnswer
          : result.exchange.assistant_message.text;
      if (!isCurrent()) return;
      setTurns((current) => [...current, {
        id: `a:${clientMessageId}`,
        role: "assistant",
        text: answer,
      }]);
    } catch {
      if (!isCurrent()) return;
      setTurns((current) => [...current, { id: `e:${clientMessageId}`, role: "assistant", text: cannotAnswer }]);
    } finally {
      if (isCurrent()) setSending(false);
    }
  };

  if (!ready) return null;
  return (
    <section className="vb-home-chat" aria-label="유진과 이야기하기">
      <h2>유진에게 물어보기</h2>
      {sessionId === null ? (
        <p>영상을 하나 만들면 유진과 이야기할 수 있어요.</p>
      ) : (
        <>
          <div className="vb-home-chat-history">
            {turns.length
              // Keyed by position: turns are only ever appended, and a client
              // id can repeat across a retry of the same message.
              ? turns.map((turn, index) => (
                <article key={`${index}:${turn.id}`}>
                  <p><strong>{turn.role === "user" ? "나" : "유진"}</strong> {turn.text}</p>
                </article>
              ))
              : <p>편집을 시작하기 전에 무엇이든 물어보세요.</p>}
          </div>
          <label htmlFor="vb-home-yujin">유진에게 물어보기</label>
          <Textarea
            id="vb-home-yujin"
            value={draft}
            disabled={sending}
            onChange={(event) => setDraft(event.target.value)}
            placeholder="예: 오늘 찍은 영상으로 뭘 만들면 좋을까?"
          />
          <Button type="button" disabled={sending} onClick={() => void send()}>
            {sending ? "답 기다리는 중" : "보내기"}
          </Button>
        </>
      )}
    </section>
  );
}
