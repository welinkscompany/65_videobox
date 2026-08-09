import { useEffect, useState } from "react";

import { api, type DirectorConversationSummary } from "../../api";
import { Button } from "../../components/ui/button";

/** 쌓인 유진 대화를 정리한다.
 *
 * 대화는 쌓이기만 하고 지울 방법이 없었다 -- 점검 시점에 28건이었다. 매일
 * 쓰면 늘어나기만 하는 목록은 결국 owner가 자기 기록을 못 찾게 만든다.
 */
export function ConversationCleanup({ projectId }: { projectId: string }) {
  const [conversations, setConversations] = useState<readonly DirectorConversationSummary[]>([]);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setReady(false);
    void api.listDirectorConversations(projectId)
      .then((result) => { if (active) setConversations(result.conversations); })
      .catch(() => { /* 대화를 못 읽어도 설정 화면 전체를 막지 않는다 */ })
      .finally(() => { if (active) setReady(true); });
    return () => { active = false; };
  }, [projectId]);

  const remove = async (conversationId: string) => {
    // 지워진 것처럼 먼저 보여 주고, 실패하면 되돌린다. 지운 척 남겨 두면
    // owner는 목록이 왜 그대로인지 알 수 없다.
    const previous = conversations;
    setError(null);
    setConversations((current) => current.filter((item) => item.conversation_id !== conversationId));
    try {
      await api.deleteDirectorConversation(projectId, conversationId);
    } catch {
      setConversations(previous);
      setError("대화를 지우지 못했어요. 잠시 뒤 다시 눌러 주세요.");
    }
  };

  if (!ready) return null;
  return (
    <section className="vb-conversation-cleanup" aria-labelledby="conversation-cleanup-heading">
      <h2 id="conversation-cleanup-heading">유진과 나눈 대화</h2>
      <p>더 이상 볼 일 없는 대화는 지울 수 있어요.</p>
      {error ? <p role="status">{error}</p> : null}
      {conversations.length ? conversations.map((item) => (
        <article key={item.conversation_id} aria-label={`${formatDay(item.updated_at)} 대화`}>
          <p>
            <strong>{formatDay(item.updated_at)}</strong>
            {" · "}
            {item.message_count > 0 ? `주고받은 말 ${item.message_count}개` : "아직 주고받은 말이 없어요"}
          </p>
          <Button type="button" variant="outline" onClick={() => void remove(item.conversation_id)}>
            이 대화 지우기
          </Button>
        </article>
      )) : <p>아직 나눈 대화가 없어요.</p>}
    </section>
  );
}

function formatDay(value: string): string {
  // 내부 시각 문자열은 owner에게 뜻이 없다.
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "날짜 모름";
  return `${parsed.getFullYear()}년 ${parsed.getMonth() + 1}월 ${parsed.getDate()}일`;
}
