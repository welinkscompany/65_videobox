import { useEffect, useState } from "react";

import { api } from "../../api";
import { Button } from "../../components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "../../components/ui/dialog";
import { Input } from "../../components/ui/input";
import { extractTitleSuggestions } from "./titleSuggestions";

/** 유진에게 보내는 부탁. 한 줄에 하나씩 달라고 해야 골라낼 수 있다 --
 *  줄글로 오면 어디까지가 제목인지 아무도 모른다. */
const TITLE_REQUEST = "이 영상에 어울리는 제목을 다섯 개만 추천해 줘. 한 줄에 하나씩, 번호를 붙여서 제목만 적어 줘.";

const NO_DRAFT = "편집을 한 번 열고 나면 유진이 이 영상을 보고 제목을 추천할 수 있어요. 그전에는 직접 적어 주세요.";
const ASK_FAILED = "유진이 지금 제목을 추천하지 못했어요. 직접 적거나 잠시 뒤 다시 눌러 주세요.";
const NOTHING_TO_PICK = "유진이 고를 만한 제목을 주지 않았어요. 직접 적어 주세요.";

async function askYujinForTitles(projectId: string): Promise<readonly string[]> {
  // 화면이 쓰는 로컬 경로 그대로다. 유진에게 말을 걸려면 붙일 편집 기록이
  // 하나 있어야 하므로, 없으면 물어보기 전에 그 사실을 돌려준다.
  const session = await api.getLatestEditingSession(projectId);
  const sessionId = session?.session_id;
  if (!sessionId) return [];
  const conversation = await api.createDirectorConversation(projectId, { session_id: sessionId });
  const result = await api.sendDirectorMessage(projectId, conversation.conversation_id, {
    session_id: sessionId,
    client_message_id: crypto.randomUUID(),
    text: TITLE_REQUEST,
  });
  if (result.kind !== "exchange") throw new Error("still_answering");
  return extractTitleSuggestions(result.exchange.assistant_message.text ?? "");
}

/** 영상 제목을 바꾸는 자리.
 *
 * 유진에게 추천을 받을 수는 있지만 **고르는 것도 저장하는 것도 사람이 누른다** --
 * 승인된 사람 게이트가 `제목 추천 -> [사람: 선택]`이라
 * (`docs/decisions/2026-08-16-autonomous-creator-loop-scope-expansion.ko.md`),
 * 추천을 누르면 입력칸이 채워질 뿐 저장은 한 번 더 눌러야 일어난다.
 */
export function ProjectTitleDialog({ projectId, currentName, open, onOpenChange, onRename }: {
  projectId: string;
  currentName: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onRename: (projectId: string, name: string) => void | Promise<void>;
}) {
  const [title, setTitle] = useState(currentName);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [asking, setAsking] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [suggestions, setSuggestions] = useState<readonly string[]>([]);

  // 열 때마다 지금 제목에서 다시 시작한다. 지난번에 적다 만 글자가 남아 있으면
  // owner는 그것이 현재 제목인 줄 안다.
  useEffect(() => {
    if (!open) return;
    setTitle(currentName);
    setError(null);
    setNotice(null);
    setSuggestions([]);
    setSaving(false);
    setAsking(false);
  }, [open, currentName]);

  const save = async () => {
    const next = title.trim();
    if (!next) {
      setError("제목을 입력해 주세요.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await onRename(projectId, next);
      onOpenChange(false);
    } catch {
      setError("제목을 바꾸지 못했어요. 잠시 뒤 다시 눌러 주세요.");
    } finally {
      setSaving(false);
    }
  };

  const ask = async () => {
    setAsking(true);
    setNotice(null);
    setSuggestions([]);
    try {
      const found = await askYujinForTitles(projectId);
      if (!found.length) {
        // 편집 기록이 없어서 못 물은 것과, 물었는데 고를 것이 없는 것은
        // owner가 할 행동이 다르다. 뭉뚱그리지 않는다.
        const session = await api.getLatestEditingSession(projectId).catch(() => null);
        setNotice(session?.session_id ? NOTHING_TO_PICK : NO_DRAFT);
        return;
      }
      setSuggestions(found);
    } catch {
      setNotice(ASK_FAILED);
    } finally {
      setAsking(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="vb-dialog-content">
        <DialogHeader>
          <DialogTitle>영상 제목 바꾸기</DialogTitle>
          <DialogDescription>이 영상을 부를 이름이에요. 언제든 다시 바꿀 수 있어요.</DialogDescription>
        </DialogHeader>
        <label className="grid gap-2 text-sm" htmlFor="vb-project-title">새 제목</label>
        <Input
          id="vb-project-title"
          value={title}
          disabled={saving}
          autoFocus
          onChange={(event) => setTitle(event.target.value)}
          onKeyDown={(event) => { if (event.key === "Enter") void save(); }}
        />
        <div className="vb-project-title-suggest">
          <Button type="button" variant="outline" disabled={asking || saving} onClick={() => void ask()}>
            {asking ? "유진에게 물어보는 중" : "유진에게 제목 추천받기"}
          </Button>
          {notice ? <p role="status">{notice}</p> : null}
          {suggestions.length ? <>
            <p>마음에 드는 제목을 고르면 위 칸에 채워져요. 저장은 직접 눌러 주세요.</p>
            <div className="vb-project-title-suggest__list">
              {suggestions.map((suggestion) => (
                <Button key={suggestion} type="button" variant="ghost" disabled={saving} onClick={() => { setTitle(suggestion); setError(null); }}>
                  {suggestion}
                </Button>
              ))}
            </div>
          </> : null}
        </div>
        {error ? <p role="alert">{error}</p> : null}
        <DialogFooter>
          <Button type="button" variant="outline" disabled={saving} onClick={() => onOpenChange(false)}>취소</Button>
          <Button type="button" disabled={saving} onClick={() => void save()}>{saving ? "저장하는 중" : "저장"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
