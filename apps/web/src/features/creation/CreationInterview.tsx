import { useEffect, useRef, useState } from "react";

import { api, type CreationBrief, type DraftReadiness, type NarrationOption } from "../../api";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Textarea } from "../../components/ui/textarea";
import { AssetPreviewPlayer, type PreviewCandidate } from "../director/AssetPreviewPlayer";
import { SceneImageStudio } from "../media/SceneImageStudio";
import { SourceVideoStart } from "./SourceVideoStart";
import { YujinScriptStart } from "./YujinScriptStart";
import { usePlaceholderConfirmation } from "./usePlaceholderConfirmation";
import { creationBriefStorageKey as briefStorageKey } from "./pastedScriptSummary";


const pendingKey = (projectId: string, source: "paste" | "upload" | "footage" | "yujin") => `videobox.creation-pending.${projectId}.${source}`;
const shortcutAnswers = ["모르겠어요", "추천해줘", "건너뛰기"] as const;
type PendingAnswer = { questionId: string; answer: string; expectedRevision: number };
type PendingCandidateRange = { assetId: string; startSec: number; endSec: number; expectedRevision: number };
type BrollCandidate = NonNullable<NonNullable<DraftReadiness["result"]>["broll_candidates"]>[number];

function isUsableBrollCandidate(candidate: BrollCandidate) {
  const { start_sec: startSec, end_sec: endSec } = candidate.target_range;
  const durationSec = candidate.media_duration_sec;
  return Number.isFinite(startSec) && Number.isFinite(endSec) && startSec >= 0 && endSec > startSec
    && (durationSec == null || (Number.isFinite(durationSec) && durationSec > 0 && endSec <= durationSec));
}

const summaryFieldLabels: Record<string, string> = {
  audience: "보여줄 사람",
  tone: "분위기",
  format: "올릴 곳",
  call_to_action: "시청자가 할 일",
  duration: "영상 길이",
  goal: "영상 목표",
};

function generateSummary(brief: CreationBrief) {
  const script = brief.script_text.trim();
  const answers = brief.questions
    .map((question) => ({ label: summaryFieldLabels[question.field] ?? question.prompt, answer: brief.answers[question.field]?.trim() }))
    .filter((item): item is { label: string; answer: string } => Boolean(item.answer));
  return [script ? `영상 내용: ${script}` : "", ...answers.map((item) => `${item.label}: ${item.answer}`)]
    .filter(Boolean)
    .join("\n");
}

/** `script-3` -> 3. 초안 준비가 붙이는 이름이라 형식이 이것 하나다.
 *  내부 id는 창작자가 읽는 자리에 나가지 않는다(§10.13). */
function sceneNumberOf(segmentId: string): number {
  const tail = segmentId.split("-").pop() ?? "";
  return /^\d+$/.test(tail) ? Number(tail) : 0;
}

/** 그 장면에서 무슨 말을 하는지는 이미 대본이 알고 있다. 빈 칸을 주면
 *  owner가 매번 처음부터 쓰게 된다. */
function sceneTextOf(readiness: DraftReadiness, segmentId: string): string {
  return readiness.result?.script_segments?.find((item) => item.segment_id === segmentId)?.text ?? "";
}

function gapDurationOf(gap: { target_range?: { start_sec: number; end_sec: number } }): number {
  const range = gap.target_range;
  if (!range) return 5;
  const seconds = range.end_sec - range.start_sec;
  return Number.isFinite(seconds) && seconds > 0 ? seconds : 5;
}

function newIdempotencyKey() {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `creation-brief-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export function CreationInterview({ projectId }: { projectId: string }) {
  const [brief, setBrief] = useState<CreationBrief | null>(null);
  const [storedBriefId, setStoredBriefId] = useState<string | null>(() => window.localStorage.getItem(briefStorageKey(projectId)));
  const [scriptText, setScriptText] = useState("");
  const [scriptFile, setScriptFile] = useState<File | null>(null);
  const [isStarting, setIsStarting] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  // Task 33: the owner makes both long-form and shortform. Landscape is the
  // default (F-9 owner decision); this is the only place the choice is made,
  // because the draft bundle is what fixes the output size.
  const [vertical, setVertical] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [advanceRetry, setAdvanceRetry] = useState(false);
  const [retryAnswer, setRetryAnswer] = useState<PendingAnswer | null>(null);
  const [answerDraft, setAnswerDraft] = useState("");
  const [summaryText, setSummaryText] = useState("");
  const [readiness, setReadiness] = useState<DraftReadiness | null>(null);
  const [narrationOptions, setNarrationOptions] = useState<NarrationOption[]>([]);
  const [recording, setRecording] = useState(false);
  const [recordingFile, setRecordingFile] = useState<File | null>(null);
  const [candidateRanges, setCandidateRanges] = useState<Record<string, { start: string; end: string }>>({});
  const [rangeRetry, setRangeRetry] = useState<PendingCandidateRange | null>(null);
  const { confirmed: allowPlaceholder, setConfirmed: setAllowPlaceholder } = usePlaceholderConfirmation(readiness);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const recordingStreamRef = useRef<MediaStream | null>(null);
  const recordingDiscardRef = useRef(false);
  const answerInputRef = useRef<HTMLInputElement>(null);

  // The router reuses this component while switching projects. Clear every
  // project-owned draft field before the new project's request resolves so a
  // previous project's brief can never flash or be mutated under the new id.
  const [renderedProjectId, setRenderedProjectId] = useState(projectId);
  const projectSwitchPending = renderedProjectId !== projectId;
  useEffect(() => {
    if (!projectSwitchPending) return;
    setBrief(null);
    setStoredBriefId(window.localStorage.getItem(briefStorageKey(projectId)));
    setScriptText("");
    setScriptFile(null);
    setSummaryText("");
    setReadiness(null);
    setNarrationOptions([]);
    setVertical(false);
    setIsStarting(false);
    setIsSaving(false);
    setRecording(false);
    setRecordingFile(null);
    recordingDiscardRef.current = true;
    recorderRef.current?.state === "recording" && recorderRef.current.stop();
    recordingStreamRef.current?.getTracks().forEach((track) => track.stop());
    recorderRef.current = null;
    recordingStreamRef.current = null;
    setCandidateRanges({});
    setRangeRetry(null);
    setRetryAnswer(null);
    setAnswerDraft("");
    setError(null);
  }, [projectId, projectSwitchPending]);

  useEffect(() => {
    const briefId = window.localStorage.getItem(briefStorageKey(projectId));
    if (!briefId) {
      setRenderedProjectId(projectId);
      return;
    }
    let active = true;
    void api.getCreationBrief(projectId, briefId).then((loaded) => {
      if (active) {
        setRenderedProjectId(projectId);
        setStoredBriefId(loaded.brief_id);
        setBrief(loaded);
      }
    }).catch(() => {
      window.localStorage.removeItem(briefStorageKey(projectId));
      if (active) {
        setRenderedProjectId(projectId);
        setStoredBriefId(null);
      }
    });
    return () => { active = false; };
  }, [projectId]);

  // 후보를 못 읽었을 때 목록을 **비우지 않는다.** 방금 올린 영상은 이미 화면이
  // 알고 있는데, 실패했다고 지워 버리면 owner는 본편을 두고 무음을 고르게 된다.
  // 프로젝트가 바뀔 때는 위쪽 전환 처리가 따로 비운다.
  useEffect(() => { if (brief?.status === "approved") void api.listDraftNarrationOptions(projectId).then(setNarrationOptions).catch(() => undefined); }, [brief?.status, projectId]);
  useEffect(() => {
    if (brief?.status !== "approved") return;
    const params = new URLSearchParams(window.location.search);
    const candidate = params.get("readiness_id") || window.localStorage.getItem(`videobox.draft-readiness.${projectId}`);
    if (!candidate || !/^readiness_[A-Za-z0-9_-]+$/.test(candidate)) return;
    let active = true;
    void api.getDraftReadiness(projectId, candidate).then((run) => {
      if (!active) return;
      if (run.brief_id !== brief.brief_id) {
        window.localStorage.removeItem(`videobox.draft-readiness.${projectId}`);
        setReadiness(null);
        return;
      }
      window.localStorage.setItem(`videobox.draft-readiness.${projectId}`, run.readiness_id);
      setReadiness(run);
    }).catch(() => window.localStorage.removeItem(`videobox.draft-readiness.${projectId}`));
    return () => { active = false; };
  }, [brief?.status, projectId]);
  useEffect(() => () => { recordingDiscardRef.current = true; recorderRef.current?.state === "recording" && recorderRef.current.stop(); recordingStreamRef.current?.getTracks().forEach((track) => track.stop()); }, [projectId]);
  useEffect(() => {
    if (!readiness || !["asset_check", "planning"].includes(readiness.status)) return;
    const timer = window.setTimeout(() => {
      void advanceDraftReadiness(readiness);
    }, 50);
    return () => window.clearTimeout(timer);
  }, [readiness, projectId]);
  useEffect(() => {
    const candidates = readiness?.result?.broll_candidates;
    if (!candidates) return;
    setCandidateRanges(Object.fromEntries(candidates.filter(isUsableBrollCandidate).map((item) => [item.asset_id, { start: String(item.target_range.start_sec), end: String(item.target_range.end_sec) }] )));
  }, [readiness]);

  const currentQuestion = brief?.questions[brief.current_step] ?? null;
  const usableBrollCandidates = (readiness?.result?.broll_candidates ?? []).filter(isUsableBrollCandidate);
  const editableSummary = !currentQuestion && brief
    ? (summaryText || brief.summary?.trim() || generateSummary(brief))
    : summaryText;

  function continueDraft() {
    const targetId = currentQuestion ? "creation-answer" : brief ? "creation-summary" : "creation-script";
    document.getElementById(targetId)?.focus();
  }

  const resumeBanner = storedBriefId ? <section data-testid="creation-draft-resume" aria-label="저장된 초안">
    <p>작성 중인 기획 초안이 있어요. 이어서 작업하면 저장된 답변을 그대로 사용할 수 있습니다.</p>
    <Button type="button" variant="outline" onClick={continueDraft}>초안 이어서 하기</Button>
  </section> : null;

  function getPendingIdempotencyKey(source: "paste" | "upload" | "footage" | "yujin") {
    const key = pendingKey(projectId, source);
    const existing = window.localStorage.getItem(key);
    if (existing) return existing;
    const created = newIdempotencyKey();
    window.localStorage.setItem(key, created);
    return created;
  }

  useEffect(() => {
    if (!brief || currentQuestion) return;
    setSummaryText(brief.summary?.trim() || generateSummary(brief));
  }, [brief, currentQuestion]);

  useEffect(() => {
    if (!brief || !currentQuestion) return;
    setAnswerDraft(brief.answers[currentQuestion.field] ?? "");
  }, [brief, currentQuestion]);

  if (projectSwitchPending) {
    return <section className="vb-creation-interview" aria-live="polite"><p>새 프로젝트의 기획을 불러오는 중이에요.</p></section>;
  }

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

  /** 찍어 둔 영상에서 받아쓴 대본으로 기획을 연다.
   *
   *  `start()`와 다른 점은 하나뿐이다 -- 대본을 만들어 준 그 영상이 **곧 본편**이라
   *  내레이션 후보로도 바로 올려 둔다. 승인 뒤 서버에서 후보를 다시 읽지만, 그
   *  사이 화면에 "무음으로 초안 준비"만 보이면 owner가 그것을 눌러 자기 목소리를
   *  통째로 버리게 된다. */
  async function startFromFootage({ assetId, scriptText: heard }: { assetId: string; scriptText: string }) {
    const trimmed = heard.trim();
    if (!trimmed) return;
    setError(null);
    setIsStarting(true);
    try {
      const created = await api.createCreationBrief(projectId, {
        script_filename: "영상에서-받아쓴-대본.txt",
        script_text: trimmed,
        idempotency_key: getPendingIdempotencyKey("footage"),
        capability_profile: { ai_execution: "disabled" },
      });
      window.localStorage.setItem(briefStorageKey(projectId), created.brief_id);
      window.localStorage.removeItem(pendingKey(projectId, "footage"));
      setNarrationOptions((items) => items.some((item) => item.asset_id === assetId)
        ? items
        : [...items, { asset_id: assetId, asset_type: "raw_video" }]);
      setBrief(created);
    } catch {
      setError("받아쓴 대본으로 기획을 시작하지 못했습니다. 잠시 뒤 다시 눌러 주세요.");
    } finally {
      setIsStarting(false);
    }
  }

  /** 유진이 쓴 초안으로 기획을 연다.
   *
   *  `start()`와 다른 점은 대본이 어디서 왔는지 이름으로 남는 것뿐이다. **여기서
   *  받는 글은 이미 owner가 고치고 확인을 누른 글이다** -- 초안 그대로가 아니다.
   *  확정 게이트는 `YujinScriptStart` 안에 있다. */
  async function startFromYujinDraft({ scriptText: written }: { scriptText: string }) {
    const trimmed = written.trim();
    if (!trimmed) return;
    setError(null);
    setIsStarting(true);
    try {
      const created = await api.createCreationBrief(projectId, {
        script_filename: "유진이-쓴-대본.txt",
        script_text: trimmed,
        idempotency_key: getPendingIdempotencyKey("yujin"),
        capability_profile: { ai_execution: "disabled" },
      });
      window.localStorage.setItem(briefStorageKey(projectId), created.brief_id);
      window.localStorage.removeItem(pendingKey(projectId, "yujin"));
      setBrief(created);
    } catch {
      setError("유진이 쓴 대본으로 기획을 시작하지 못했습니다. 잠시 뒤 다시 눌러 주세요.");
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
      const nextQuestion = updated.questions[updated.current_step];
      setAnswerDraft(nextQuestion ? updated.answers[nextQuestion.field] ?? "" : "");
      setRetryAnswer(null);
      answerInputRef.current?.focus();
    } catch {
      setRetryAnswer(submission);
      setError("답변을 저장하지 못했습니다.");
    } finally {
      setIsSaving(false);
    }
  }

  async function goToPreviousQuestion() {
    if (!brief || brief.current_step <= 0) return;
    setError(null);
    setIsSaving(true);
    try {
      const updated = await api.previousCreationBriefQuestion(projectId, brief.brief_id, { expected_revision: brief.revision });
      setBrief(updated);
      const previousQuestion = updated.questions[updated.current_step];
      setAnswerDraft(previousQuestion ? updated.answers[previousQuestion.field] ?? "" : "");
      setRetryAnswer(null);
    } catch {
      setError("이전 질문으로 돌아가지 못했습니다. 다시 시도해 주세요.");
    } finally {
      setIsSaving(false);
    }
  }

  async function saveSummary() {
    const summary = summaryText.trim() || (brief ? generateSummary(brief) : "");
    if (!brief || !summary) {
      setError("기획 요약을 적어 주세요.");
      return;
    }
    setError(null);
    setIsSaving(true);
    try {
      setBrief(await api.updateCreationBriefSummary(projectId, brief.brief_id, { summary, expected_revision: brief.revision }));
    } catch {
      setError("기획 요약을 저장하지 못했습니다.");
    } finally {
      setIsSaving(false);
    }
  }

  async function approveSummary() {
    const summary = summaryText.trim() || (brief ? generateSummary(brief) : "");
    if (!brief || !summary) return;
    setError(null);
    setIsSaving(true);
    try {
      const saved = brief.summary?.trim() === summary
        ? brief
        : await api.updateCreationBriefSummary(projectId, brief.brief_id, { summary, expected_revision: brief.revision });
      setBrief(await api.approveCreationBrief(projectId, saved.brief_id, { expected_revision: saved.revision }));
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
      setStoredBriefId(null);
    } catch {
      setError("대본과 기획을 삭제하지 못했습니다. 다시 시도해 주세요.");
    } finally {
      setIsSaving(false);
    }
  }

  async function startDraft(narration_choice: { kind: "silent" | "existing" | "source_video"; asset_id?: string }) {
    if (!brief) return;
    setError(null); setIsSaving(true);
    try {
      const run = await api.startDraftReadiness(projectId, { brief_id: brief.brief_id, narration_choice, idempotency_key: `draft-${brief.brief_id}-${brief.revision}-${narration_choice.kind}-${narration_choice.asset_id ?? ""}`, expected_brief_revision: brief.revision });
      window.localStorage.setItem(`videobox.draft-readiness.${projectId}`, run.readiness_id); setReadiness(run);
    } catch { setError("초안을 준비하지 못했습니다. 다시 시도해 주세요."); }
    finally { setIsSaving(false); }
  }

  async function advanceDraftReadiness(run: DraftReadiness) {
    try {
      const next = run.status === "planning"
        ? await api.completeDraftReadiness(projectId, run.readiness_id, run.revision)
        : await api.retryDraftReadiness(projectId, run.readiness_id, run.revision);
      setAdvanceRetry(false); setReadiness(next);
    } catch {
      try {
        const current = await api.getDraftReadiness(projectId, run.readiness_id);
        setReadiness(current);
      } catch {
        // Preserve the last durable state when the recovery read is unavailable.
      }
      setAdvanceRetry(true);
      setError("초안 준비를 이어가지 못했습니다. 다시 시도해 주세요.");
    }
  }

  /** 그림을 만들었으면 준비를 다시 돌린다.
   *
   *  자산이 생긴 것과 그 장면이 채워진 것은 다른 일이다. 공백 목록은 저장된
   *  준비 결과라서, 다시 돌리기 전까지 화면은 아무것도 안 바뀐 것처럼 보인다. */
  async function replanAfterSceneImage() {
    if (!readiness) return;
    setError(null);
    setIsSaving(true);
    try {
      const planning = await api.retryDraftReadiness(projectId, readiness.readiness_id, readiness.revision);
      setReadiness(await api.completeDraftReadiness(projectId, planning.readiness_id, planning.revision));
    } catch {
      setError("초안을 다시 준비하지 못했습니다. 다시 준비를 눌러 주세요.");
    } finally {
      setIsSaving(false);
    }
  }

  async function runReadinessAction(action: () => Promise<DraftReadiness>, failureMessage: string) {
    setError(null);
    setIsSaving(true);
    try {
      setReadiness(await action());
    } catch {
      setError(failureMessage);
    } finally {
      setIsSaving(false);
    }
  }

  async function skipCandidate(assetId: string) {
    if (!readiness) return;
    await runReadinessAction(
      () => api.updateDraftReadinessCandidate(projectId, readiness.readiness_id, assetId, true, readiness.revision),
      "장면을 건너뛰지 못했습니다. 다시 시도해 주세요.",
    );
  }

  async function createDraftBundle(withPlaceholder = false) {
    if (!brief || !readiness || (readiness.status !== "ready" && (readiness.status !== "needs_assets" || !withPlaceholder || !allowPlaceholder))) return;
    setError(null); setIsSaving(true);
    try {
      const bundle = await api.createAtomicDraftBundle(projectId, { brief_id: brief.brief_id, readiness_id: readiness.readiness_id, expected_brief_revision: brief.revision, expected_readiness_revision: readiness.revision, idempotency_key: `draft-bundle-${readiness.readiness_id}-${readiness.revision}`, ...(withPlaceholder ? { allow_placeholder: true } : {}), ...(vertical ? { orientation: "vertical" as const } : {}) });
      window.location.assign(`/projects/${encodeURIComponent(projectId)}/editor?session_id=${encodeURIComponent(bundle.session_id)}`);
    } catch {
      setError("초안을 만들지 못했어요. 준비 상태를 확인한 뒤 다시 시도해 주세요.");
    } finally { setIsSaving(false); }
  }

  async function uploadNarration(file: File | null) { if (!file) return; setIsSaving(true); try { const asset = await api.uploadDraftNarration(projectId, file); setNarrationOptions((items) => [...items, { asset_id: asset.asset_id, asset_type: "narration_audio" }]); } catch { setError("소리 파일을 준비하지 못했습니다."); } finally { setIsSaving(false); } }

  async function saveCandidateRange(assetId: string, previous?: PendingCandidateRange) {
    if (!readiness) return;
    const candidate = readiness.result?.broll_candidates?.find((item) => item.asset_id === assetId);
    if (!candidate || !isUsableBrollCandidate(candidate)) {
      setError("이 장면은 사용할 수 있는 구간이 아니에요. 다른 장면을 골라 주세요.");
      return;
    }
    const values = candidateRanges[assetId];
    const startSec = previous?.startSec ?? Number(values?.start);
    const endSec = previous?.endSec ?? Number(values?.end);
    const submission = previous ?? { assetId, startSec, endSec, expectedRevision: readiness.revision };
    if (!Number.isFinite(startSec) || !Number.isFinite(endSec) || startSec < 0 || endSec <= startSec) {
      setError("끝 시간은 시작 시간보다 뒤로 정해 주세요.");
      return;
    }
    setError(null); setIsSaving(true);
    try {
      setReadiness(await api.updateDraftReadinessCandidateRange(projectId, readiness.readiness_id, submission.assetId, submission.startSec, submission.endSec, submission.expectedRevision));
      setRangeRetry(null);
    } catch {
      setRangeRetry(submission);
      setError("구간을 저장하지 못했습니다. 다시 시도해 주세요.");
    } finally { setIsSaving(false); }
  }

  async function startRecording() {
    setError(null);
    try {
      if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") throw new Error("unavailable");
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const chunks: Blob[] = []; const recorder = new MediaRecorder(stream);
      recorder.ondataavailable = (event) => { if (event.data.size) chunks.push(event.data); };
      recorder.onstop = () => { stream.getTracks().forEach((track) => track.stop()); recordingStreamRef.current = null; setRecording(false); if (recordingDiscardRef.current) return; const file = new File([new Blob(chunks, { type: recorder.mimeType || "audio/webm" })], "녹음한-내레이션.webm", { type: recorder.mimeType || "audio/webm" }); setRecordingFile(file); void uploadNarration(file); };
      recorderRef.current = recorder; recordingStreamRef.current = stream; recordingDiscardRef.current = false; recorder.start(); setRecording(true);
    } catch { recordingStreamRef.current?.getTracks().forEach((track) => track.stop()); recordingStreamRef.current = null; setError("마이크를 사용할 수 없습니다. 권한을 확인한 뒤 다시 시도해 주세요."); }
  }

  function stopRecording() { recordingDiscardRef.current = false; recorderRef.current?.stop(); }

  if (!brief) {
    return <section className="vb-creation-interview" aria-labelledby="creation-interview-heading">
      {resumeBanner}
      <p className="vb-eyebrow">새 영상 만들기</p>
      <h1 id="creation-interview-heading">유진과 영상 기획을 시작해요</h1>
      <p>대본을 붙여넣으면, 이미 적힌 내용은 건너뛰고 필요한 것만 함께 정리해 드릴게요.</p>
      <label htmlFor="creation-script">대본 붙여넣기</label>
      <Textarea id="creation-script" value={scriptText} onChange={(event) => { setScriptText(event.target.value); window.localStorage.removeItem(pendingKey(projectId, "paste")); }} placeholder="영상에서 전할 내용을 붙여넣어 주세요." rows={10} />
      <Button type="button" onClick={() => void start()} disabled={isStarting}>{isStarting ? "대본 준비 중" : "유진과 기획 시작"}</Button>
      <label htmlFor="creation-script-file">대본 파일 선택</label>
      <p id="creation-script-file-help">지원 형식: TXT · MD · SRT</p>
      <Input id="creation-script-file" type="file" accept=".txt,.md,.srt,text/plain,text/markdown,application/x-subrip" onChange={(event) => { setScriptFile(event.target.files?.[0] ?? null); window.localStorage.removeItem(pendingKey(projectId, "upload")); }} />
      <Button type="button" variant="outline" onClick={() => void startFromFile()} disabled={isStarting}>{isStarting ? "대본 준비 중" : "파일로 기획 시작"}</Button>
      {/* 대본이 없어도 시작할 수 있는 길. 영상에서 말을 받아써 대본을 만든다.
          첫 화면의 "찍어 둔 영상이 있어요"가 여기로 온다. */}
      <SourceVideoStart projectId={projectId} disabled={isStarting} onReady={(start) => void startFromFootage(start)} />
      {/* 대본도 영상도 없는 사람이 시작하는 길. 첫 화면의 "아직 아무것도 없어요"가
          여기로 온다. 주제만 받아 유진이 초안을 쓰고, owner가 고쳐 확인한다. */}
      <YujinScriptStart projectId={projectId} disabled={isStarting} onReady={(start) => void startFromYujinDraft(start)} />
      {error ? <p role="alert">{error}</p> : null}
    </section>;
  }

  if (!currentQuestion) {
    return <section className="vb-creation-interview" aria-labelledby="creation-summary-heading">
      {resumeBanner}
      <p className="vb-eyebrow">영상 기획</p>
      <h1 id="creation-summary-heading">{brief.status === "approved" ? "기획을 확인했어요" : "기획 요약을 확인해 주세요"}</h1>
      {brief.status === "approved" ? <><p>소리 고르기 · 초안 준비</p>
        {!readiness ? <><Button type="button" disabled={isSaving} onClick={() => void startDraft({ kind: "silent" })}>무음으로 초안 준비</Button>
          {narrationOptions.filter((item) => item.asset_type === "raw_video").map((item) => <Button key={item.asset_id} type="button" variant="outline" onClick={() => void startDraft({ kind: "source_video", asset_id: item.asset_id })}>영상 소리로 초안 준비</Button>)}
          {narrationOptions.filter((item) => item.asset_type === "narration_audio").map((item) => <Button key={item.asset_id} type="button" variant="outline" onClick={() => void startDraft({ kind: "existing", asset_id: item.asset_id })}>준비한 내레이션으로 초안 준비</Button>)}
          <label htmlFor="draft-narration-file">내레이션 파일 추가</label><Input id="draft-narration-file" type="file" accept="audio/*,.wav,.mp3,.m4a,.ogg,.webm" onChange={(event) => void uploadNarration(event.target.files?.[0] ?? null)} />
          <Button type="button" variant="outline" disabled={isSaving || recording} onClick={() => void startRecording()}>마이크로 녹음 시작</Button>{recording ? <Button type="button" onClick={stopRecording}>녹음 마치기</Button> : null}{recordingFile && error ? <Button type="button" variant="outline" onClick={() => void uploadNarration(recordingFile)}>녹음 다시 올리기</Button> : null}
        </> : <section aria-label="초안 준비 상태"><label><Input type="checkbox" checked={vertical} onChange={(event) => setVertical(event.target.checked)} />숏폼(세로)으로 만들기</label><h2>{readiness.status === "ready" ? "초안이 준비됐어요" : readiness.status === "needs_assets" ? "추가 미디어가 필요해요" : readiness.status === "cancelled" ? "초안 준비를 멈췄어요" : readiness.status === "failed" ? "초안을 준비하지 못했어요" : readiness.status === "asset_check" ? "미디어를 확인하고 있어요" : "초안을 준비하고 있어요"}</h2>{readiness.status === "ready" ? <Button type="button" disabled={isSaving} onClick={() => void createDraftBundle()}>초안 만들기</Button> : null}{readiness.status === "needs_assets" ? <><p role="note">누락된 장면은 빈 구간으로 남습니다. 이 초안은 내보낼 수 없어요.</p><label><Input type="checkbox" checked={allowPlaceholder} onChange={(event) => setAllowPlaceholder(event.target.checked)} />빈 구간을 남긴 채 편집용 초안을 만들겠습니다</label><Button type="button" variant="outline" disabled={isSaving || !allowPlaceholder} onClick={() => void createDraftBundle(true)}>빈 구간 포함 초안 만들기</Button></> : null}{advanceRetry ? <Button type="button" onClick={() => void advanceDraftReadiness(readiness)}>준비 계속하기</Button> : null}{readiness.result?.gap_slots?.map((gap) => <div key={gap.gap_slot_id}><p>{gap.reason} <a href={`/projects/${encodeURIComponent(projectId)}/media?return_to=${encodeURIComponent(`/projects/${projectId}/create?brief_id=${brief.brief_id}&readiness_id=${readiness.readiness_id}`)}`}>미디어 추가</a></p>{gap.segment_id ? <SceneImageStudio projectId={projectId} vertical={vertical} gap={{ gapSlotId: gap.gap_slot_id, segmentId: gap.segment_id, sceneNumber: sceneNumberOf(gap.segment_id), sceneText: sceneTextOf(readiness, gap.segment_id), durationSec: gapDurationOf(gap) }} onGenerated={() => void replanAfterSceneImage()} /> : null}</div>)}{usableBrollCandidates.length ? <><AssetPreviewPlayer proposalId={readiness.readiness_id} candidates={usableBrollCandidates.map((item): PreviewCandidate => ({ candidateId: item.asset_id, referenceCode: item.label, mediaType: "broll", controls: { in_sec: item.target_range.start_sec, out_sec: item.target_range.end_sec } }))} previewUrl={(assetId) => `/api/projects/${encodeURIComponent(projectId)}/assets/${encodeURIComponent(assetId)}/content`} />{usableBrollCandidates.map((item) => <div key={item.asset_id}><label htmlFor={`${item.asset_id}-start`}>{item.label} 시작</label><Input id={`${item.asset_id}-start`} type="number" min="0" step="0.1" value={candidateRanges[item.asset_id]?.start ?? String(item.target_range.start_sec)} onChange={(event) => setCandidateRanges((ranges) => ({ ...ranges, [item.asset_id]: { start: event.target.value, end: ranges[item.asset_id]?.end ?? String(item.target_range.end_sec) } }))} /><label htmlFor={`${item.asset_id}-end`}>{item.label} 끝</label><Input id={`${item.asset_id}-end`} type="number" min="0" step="0.1" value={candidateRanges[item.asset_id]?.end ?? String(item.target_range.end_sec)} onChange={(event) => setCandidateRanges((ranges) => ({ ...ranges, [item.asset_id]: { start: ranges[item.asset_id]?.start ?? String(item.target_range.end_sec), end: event.target.value } }))} /><Button type="button" variant="outline" disabled={isSaving} onClick={() => void saveCandidateRange(item.asset_id)}>구간 저장</Button><Button type="button" variant="ghost" disabled={isSaving} onClick={() => void skipCandidate(item.asset_id)}>{item.label} 건너뛰기</Button></div>)}</> : null}{rangeRetry ? <Button type="button" variant="outline" disabled={isSaving} onClick={() => void saveCandidateRange(rangeRetry.assetId, rangeRetry)}>구간 다시 저장</Button> : null}{["planning", "asset_check"].includes(readiness.status) ? <Button type="button" variant="ghost" disabled={isSaving} onClick={() => void runReadinessAction(() => api.cancelDraftReadiness(projectId, readiness.readiness_id, readiness.revision), "준비를 멈추지 못했습니다. 다시 시도해 주세요.")}>준비 멈추기</Button> : null}{["failed", "cancelled", "needs_assets"].includes(readiness.status) ? <Button type="button" variant="outline" disabled={isSaving} onClick={() => void runReadinessAction(() => api.retryDraftReadiness(projectId, readiness.readiness_id, readiness.revision), "다시 준비하지 못했습니다. 다시 시도해 주세요.")}>다시 준비</Button> : null}</section>}
      </> : <>
        <p>유진이 정리한 내용을 고친 뒤, 마음에 들면 승인해 주세요.</p>
        <label htmlFor="creation-summary">기획 요약</label>
        <Textarea id="creation-summary" value={editableSummary} onChange={(event) => setSummaryText(event.target.value)} rows={6} disabled={isSaving} />
        <Button type="button" variant="outline" disabled={isSaving} onClick={() => void saveSummary()}>요약 저장</Button>
        <Button type="button" disabled={isSaving || !editableSummary.trim()} onClick={() => void approveSummary()}>요약 승인</Button>
      </>}
      {error ? <p role="alert">{error}</p> : null}
      <Button type="button" variant="ghost" disabled={isSaving} onClick={() => void deleteBrief()}>대본과 기획 삭제</Button>
    </section>;
  }

  return <section className="vb-creation-interview" aria-labelledby="creation-question-heading">
    {resumeBanner}
    <p className="vb-eyebrow">유진 질문</p>
    <p aria-label="질문 진행">{brief.current_step + 1} / {brief.questions.length}</p>
    <h1 id="creation-question-heading">{currentQuestion.prompt}</h1>
    <label htmlFor="creation-answer">답변</label>
    <Input id="creation-answer" ref={answerInputRef} value={answerDraft} onChange={(event) => setAnswerDraft(event.target.value)} disabled={isSaving} />
    <Button type="button" disabled={isSaving} onClick={() => void submitAnswer(answerDraft)}>답변 저장</Button>
    <div aria-label="빠른 답변">{shortcutAnswers.map((answer) => <Button key={answer} type="button" variant="outline" disabled={isSaving} onClick={() => void submitAnswer(answer)}>{answer}</Button>)}</div>
    {brief.current_step > 0 ? <Button type="button" variant="outline" disabled={isSaving} onClick={() => void goToPreviousQuestion()}>이전 질문</Button> : null}
    <Button type="button" variant="ghost" disabled={isSaving} onClick={() => void bypassInterview()}>바로 요약 보기</Button>
    {error ? <div role="alert"><p>{error}</p><Button type="button" variant="outline" onClick={() => void submitAnswer(answerDraft, retryAnswer ?? undefined)}>다시 시도</Button></div> : null}
    <Button type="button" variant="ghost" disabled={isSaving} onClick={() => void deleteBrief()}>대본과 기획 삭제</Button>
  </section>;
}
