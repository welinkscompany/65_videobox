import { useEffect, useRef, useState } from "react";

import { api, type CreationBrief } from "../../api";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Textarea } from "../../components/ui/textarea";

const briefStorageKey = (projectId: string) => `videobox.creation-brief.${projectId}`;
const pendingKey = (projectId: string, source: "paste" | "upload") => `videobox.creation-pending.${projectId}.${source}`;
const shortcutAnswers = ["모르겠어요", "추천해줘", "건너뛰기"] as const;
type PendingAnswer = { questionId: string; answer: string; expectedRevision: number };

function newIdempotencyKey() {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `creation-brief-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export function CreationInterview({ projectId }: { projectId: string }) {
  const [brief, setBrief] = useState<CreationBrief | null>(null);
  const [scriptText, setScriptText] = useState("");
  const [scriptFile, setScriptFile] = useState<File | null>(null);
  const [isStarting, setIsStarting] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [retryAnswer, setRetryAnswer] = useState<PendingAnswer | null>(null);
  const [summaryText, setSummaryText] = useState("");
  const answerInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const briefId = window.localStorage.getItem(briefStorageKey(projectId));
    if (!briefId) return;
    let active = true;
    void api.getCreationBrief(projectId, briefId).then((loaded) => {
      if (active) setBrief(loaded);
    }).catch(() => {
      window.localStorage.removeItem(briefStorageKey(projectId));
    });
    return () => { active = false; };
  }, [projectId]);

  const currentQuestion = brief?.questions[brief.current_step] ?? null;

  function getPendingIdempotencyKey(source: "paste" | "upload") {
    const key = pendingKey(projectId, source);
    const existing = window.localStorage.getItem(key);
    if (existing) return existing;
    const created = newIdempotencyKey();
    window.localStorage.setItem(key, created);
    return created;
  }

  useEffect(() => {
    if (!brief || currentQuestion) return;
    setSummaryText(brief.summary ?? Object.values(brief.answers).filter(Boolean).join(" · "));
  }, [brief, currentQuestion]);

  async function start() {
    const trimmed = scriptText.trim();
    if (!trimmed) {
      setError("대본을 붙여넣어 주세요.");
      return;
    }
    setError(null);
    setIsStarting(true);
    try {
      const created = await api.createCreationBrief(projectId, {
        script_filename: "붙여넣은-대본.txt",
        script_text: trimmed,
        idempotency_key: getPendingIdempotencyKey("paste"),
        capability_profile: { ai_execution: "disabled" },
      });
      window.localStorage.setItem(briefStorageKey(projectId), created.brief_id);
      window.localStorage.removeItem(pendingKey(projectId, "paste"));
      setBrief(created);
    } catch {
      setError("대본을 저장하지 못했습니다. 내용을 확인한 뒤 다시 시도해 주세요.");
    } finally {
      setIsStarting(false);
    }
  }

  async function startFromFile() {
    if (!scriptFile) {
      setError("대본 파일을 선택해 주세요.");
      return;
    }
    setError(null);
    setIsStarting(true);
    try {
      const created = await api.uploadCreationBrief(projectId, scriptFile, {
        idempotency_key: getPendingIdempotencyKey("upload"),
        capability_profile: { ai_execution: "disabled" },
      });
      window.localStorage.setItem(briefStorageKey(projectId), created.brief_id);
      window.localStorage.removeItem(pendingKey(projectId, "upload"));
      setBrief(created);
    } catch {
      setError("대본 파일을 준비하지 못했습니다. 파일 형식과 내용을 확인해 주세요.");
    } finally {
      setIsStarting(false);
    }
  }

  async function submitAnswer(answer: string, previous?: PendingAnswer) {
    if (!brief || (!previous && (!currentQuestion || !answer.trim()))) return;
    const submission = previous ?? { questionId: currentQuestion!.question_id, answer: answer.trim(), expectedRevision: brief.revision };
    setError(null);
    setIsSaving(true);
    try {
      const updated = await api.answerCreationBriefQuestion(projectId, brief.brief_id, submission.questionId, { answer: submission.answer, expected_revision: submission.expectedRevision });
      setBrief(updated);
      setRetryAnswer(null);
      answerInputRef.current?.focus();
    } catch {
      setRetryAnswer(submission);
      setError("답변을 저장하지 못했습니다.");
    } finally {
      setIsSaving(false);
    }
  }

  async function saveSummary() {
    if (!brief || !summaryText.trim()) {
      setError("기획 요약을 적어 주세요.");
      return;
    }
    setError(null);
    setIsSaving(true);
    try {
      setBrief(await api.updateCreationBriefSummary(projectId, brief.brief_id, { summary: summaryText.trim(), expected_revision: brief.revision }));
    } catch {
      setError("기획 요약을 저장하지 못했습니다.");
    } finally {
      setIsSaving(false);
    }
  }

  async function approveSummary() {
    if (!brief || !summaryText.trim()) return;
    setError(null);
    setIsSaving(true);
    try {
      setBrief(await api.approveCreationBrief(projectId, brief.brief_id, { expected_revision: brief.revision }));
    } catch {
      setError("기획 요약을 확인하지 못했습니다. 다시 시도해 주세요.");
    } finally {
      setIsSaving(false);
    }
  }

  async function bypassInterview() {
    if (!brief) return;
    setError(null);
    setIsSaving(true);
    try {
      setBrief(await api.bypassCreationBriefInterview(projectId, brief.brief_id, { expected_revision: brief.revision }));
      setRetryAnswer(null);
    } catch {
      setError("질문을 건너뛰지 못했습니다. 다시 시도해 주세요.");
    } finally {
      setIsSaving(false);
    }
  }

  async function deleteBrief() {
    if (!brief || !window.confirm("대본과 기획 내용을 삭제할까요? 삭제하면 다시 불러올 수 없어요.")) return;
    setError(null);
    setIsSaving(true);
    try {
      await api.deleteCreationBrief(projectId, brief.brief_id);
      window.localStorage.removeItem(briefStorageKey(projectId));
      window.localStorage.removeItem(pendingKey(projectId, "paste"));
      window.localStorage.removeItem(pendingKey(projectId, "upload"));
      setScriptText("");
      setScriptFile(null);
      setSummaryText("");
      setRetryAnswer(null);
      setBrief(null);
    } catch {
      setError("대본과 기획을 삭제하지 못했습니다. 다시 시도해 주세요.");
    } finally {
      setIsSaving(false);
    }
  }

  if (!brief) {
    return <section className="vb-creation-interview" aria-labelledby="creation-interview-heading">
      <p className="vb-eyebrow">새 영상 만들기</p>
      <h1 id="creation-interview-heading">유진과 영상 기획을 시작해요</h1>
      <p>대본을 붙여넣으면, 이미 적힌 내용은 건너뛰고 필요한 것만 함께 정리해 드릴게요.</p>
      <label htmlFor="creation-script">대본 붙여넣기</label>
      <Textarea id="creation-script" value={scriptText} onChange={(event) => { setScriptText(event.target.value); window.localStorage.removeItem(pendingKey(projectId, "paste")); }} placeholder="영상에서 전할 내용을 붙여넣어 주세요." rows={10} />
      <Button type="button" onClick={() => void start()} disabled={isStarting}>{isStarting ? "대본 준비 중" : "유진과 기획 시작"}</Button>
      <label htmlFor="creation-script-file">대본 파일 선택</label>
      <Input id="creation-script-file" type="file" accept=".txt,.md,.srt,text/plain,text/markdown,application/x-subrip" onChange={(event) => { setScriptFile(event.target.files?.[0] ?? null); window.localStorage.removeItem(pendingKey(projectId, "upload")); }} />
      <Button type="button" variant="outline" onClick={() => void startFromFile()} disabled={isStarting}>{isStarting ? "대본 준비 중" : "파일로 기획 시작"}</Button>
      {error ? <p role="alert">{error}</p> : null}
    </section>;
  }

  if (!currentQuestion) {
    return <section className="vb-creation-interview" aria-labelledby="creation-summary-heading">
      <p className="vb-eyebrow">영상 기획</p>
      <h1 id="creation-summary-heading">{brief.status === "approved" ? "기획을 확인했어요" : "기획 요약을 확인해 주세요"}</h1>
      {brief.status === "approved" ? <p>다음 단계에서 영상 초안을 만들 수 있어요.</p> : <>
        <p>유진이 정리한 내용을 고친 뒤, 마음에 들면 승인해 주세요.</p>
        <label htmlFor="creation-summary">기획 요약</label>
        <Textarea id="creation-summary" value={summaryText} onChange={(event) => setSummaryText(event.target.value)} rows={6} disabled={isSaving} />
        <Button type="button" variant="outline" disabled={isSaving} onClick={() => void saveSummary()}>요약 저장</Button>
        <Button type="button" disabled={isSaving || !summaryText.trim()} onClick={() => void approveSummary()}>요약 승인</Button>
      </>}
      {error ? <p role="alert">{error}</p> : null}
      <Button type="button" variant="ghost" disabled={isSaving} onClick={() => void deleteBrief()}>대본과 기획 삭제</Button>
    </section>;
  }

  return <section className="vb-creation-interview" aria-labelledby="creation-question-heading">
    <p className="vb-eyebrow">유진 질문</p>
    <p aria-label="질문 진행">{brief.current_step + 1} / {brief.questions.length}</p>
    <h1 id="creation-question-heading">{currentQuestion.prompt}</h1>
    <label htmlFor="creation-answer">답변</label>
    <Input id="creation-answer" ref={answerInputRef} disabled={isSaving} />
    <Button type="button" disabled={isSaving} onClick={() => void submitAnswer(answerInputRef.current?.value ?? "")}>답변 저장</Button>
    <div aria-label="빠른 답변">{shortcutAnswers.map((answer) => <Button key={answer} type="button" variant="outline" disabled={isSaving} onClick={() => void submitAnswer(answer)}>{answer}</Button>)}</div>
    <Button type="button" variant="ghost" disabled={isSaving} onClick={() => void bypassInterview()}>바로 요약 보기</Button>
    {error ? <div role="alert"><p>{error}</p><Button type="button" variant="outline" onClick={() => void submitAnswer(answerInputRef.current?.value ?? "", retryAnswer ?? undefined)}>다시 시도</Button></div> : null}
    <Button type="button" variant="ghost" disabled={isSaving} onClick={() => void deleteBrief()}>대본과 기획 삭제</Button>
  </section>;
}
