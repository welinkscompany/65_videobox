import { useRef, useState } from "react";

import { api, type RetakeCandidate, type SourceVoiceStart } from "../../api";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Textarea } from "../../components/ui/textarea";

/** 서버가 붙여 보낸 이유를 owner가 **할 수 있는 일**로 옮긴다.
 *  `SourceVideoStart.tsx`의 같은 자리와 같은 이유다 -- 무엇을 바꿔야 하는지를 말한다. */
const messageByDetail: Record<string, string> = {
  source_voice_has_no_speech: "이 녹음에는 말소리가 없어요. 마이크가 켜져 있는지 확인하고 다시 녹음해 주세요.",
  source_voice_upload_invalid: "받아쓸 수 없는 형식이에요. 다시 녹음해 주세요.",
  source_voice_upload_too_large: "녹음이 너무 길어요. 조금 더 짧게 나눠서 다시 녹음해 주세요.",
};
const TOO_LONG = "녹음이 길어서 받아쓰기를 제 시간에 마치지 못했어요. 조금 더 짧게 나눠서 다시 녹음해 주세요.";
const TOO_BIG = "녹음이 너무 커요. 조금 더 짧게 나눠서 다시 녹음해 주세요.";
const UNKNOWN = "녹음에서 대본을 만들지 못했어요. 잠시 뒤 다시 눌러 주세요.";

function messageFor(error: unknown): string {
  const detail = (error as { detail?: string | null })?.detail ?? null;
  if (detail && messageByDetail[detail]) return messageByDetail[detail];
  const status = (error as { status?: number })?.status;
  if (status === 504 || status === 408) return TOO_LONG;
  if (status === 413) return TOO_BIG;
  return UNKNOWN;
}

const reasonLabel: Record<RetakeCandidate["reason"], string> = {
  low_confidence: "발음이 흐릿하게 들렸어요",
  retry_cue: "다시 말하겠다고 하신 것 같아요",
  retry_cue_precursor: "이 뒤에 다시 말씀하신 것 같아요",
};

/** 컷 편집으로 뺄 구간을 뺀 나머지를 시간 순으로 이어 붙인다. 문자열
 *  치환이 아니라 구간 단위로 다시 짓는다 -- 같은 문장이 두 번 나올 때
 *  엉뚱한 곳이 지워지는 걸 막는다(백엔드가 구간별 원문을 그래서 함께 준다). */
function rebuildScript(segments: SourceVoiceStart["segments"], excluded: ReadonlySet<number>): string {
  return segments
    .filter((segment) => !excluded.has(segment.segment_index))
    .map((segment) => segment.text)
    .join(" ")
    .trim();
}

/** 목소리만 녹음해서 시작하는 길(owner 요청 2026-08-29).
 *
 *  "녹음이 끝나면 잘못 발음하는 거 컷 편집으로 날리고 바로 자동 자막 만들고."
 *  받아쓰기는 이미 영상에도 그대로 도니(`SourceVideoStart.tsx`), 여기서는
 *  마이크로 직접 녹음한 소리를 같은 길로 태운다. 다른 점은 받아쓴 뒤 **다시
 *  들어볼 구간 후보**를 보여주고, 뺄지 남길지 owner가 하나씩 고른다는 것이다
 *  -- 조용히 지우지 않는다(§10.13, 사람 게이트).
 *
 *  녹음한 소리는 버려지지 않고 프로젝트의 내레이션 자산으로 남는다 --
 *  나중에 그대로 골라 쓸 수 있다. */
export function VoiceRecordStart({
  projectId,
  onReady,
  disabled = false,
}: {
  projectId: string;
  onReady: (start: { assetId: string; scriptText: string }) => void;
  disabled?: boolean;
}) {
  const [recording, setRecording] = useState(false);
  // 이미 녹음돼 있는 파일을 고르는 길. 마이크 녹음과 짝인 `SourceVideoStart.tsx`는
  // 처음부터 파일 선택만 있었는데, 여기는 마이크 녹음만 있고 **파일을 고르는
  // 자리가 없었다** -- `upload()`는 이미 어떤 File이든 받는데 부르는 자리가
  // 하나뿐이었다(owner 지적 2026-09-03: "내가 녹음 한 파일을 업로드하면").
  const [file, setFile] = useState<File | null>(null);
  const [isReading, setIsReading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [heard, setHeard] = useState<SourceVoiceStart | null>(null);
  const [excludedIndices, setExcludedIndices] = useState<Set<number>>(new Set());
  const [scriptText, setScriptText] = useState("");
  const recorderRef = useRef<MediaRecorder | null>(null);
  const recordingStreamRef = useRef<MediaStream | null>(null);

  async function upload(file: File) {
    setIsReading(true);
    setError(null);
    try {
      const start = await api.uploadSourceVoice(projectId, file);
      const initiallyExcluded = new Set(start.retake_candidates.map((candidate) => candidate.segment_index));
      setHeard(start);
      setExcludedIndices(initiallyExcluded);
      setScriptText(rebuildScript(start.segments, initiallyExcluded));
    } catch (caught) {
      setError(messageFor(caught));
    } finally {
      setIsReading(false);
    }
  }

  async function startRecording() {
    setError(null);
    try {
      if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") throw new Error("unavailable");
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const chunks: Blob[] = [];
      const recorder = new MediaRecorder(stream);
      recorder.ondataavailable = (event) => { if (event.data.size) chunks.push(event.data); };
      recorder.onstop = () => {
        stream.getTracks().forEach((track) => track.stop());
        recordingStreamRef.current = null;
        setRecording(false);
        const file = new File([new Blob(chunks, { type: recorder.mimeType || "audio/webm" })], "녹음한-목소리.webm", { type: recorder.mimeType || "audio/webm" });
        void upload(file);
      };
      recorderRef.current = recorder;
      recordingStreamRef.current = stream;
      recorder.start();
      setRecording(true);
    } catch {
      recordingStreamRef.current?.getTracks().forEach((track) => track.stop());
      recordingStreamRef.current = null;
      setError("마이크를 사용할 수 없어요. 권한을 확인한 뒤 다시 시도해 주세요.");
    }
  }

  function stopRecording() {
    recorderRef.current?.stop();
  }

  async function readFile() {
    if (isReading) return;
    if (!file) {
      setError("녹음 파일을 먼저 골라 주세요.");
      return;
    }
    setError(null);
    void upload(file);
  }

  function toggleExcluded(segmentIndex: number) {
    if (!heard) return;
    setExcludedIndices((current) => {
      const next = new Set(current);
      if (next.has(segmentIndex)) next.delete(segmentIndex); else next.add(segmentIndex);
      setScriptText(rebuildScript(heard.segments, next));
      return next;
    });
  }

  if (heard) {
    return (
      <section aria-label="녹음한 목소리 확인">
        <h2>이렇게 들었어요</h2>
        <p>잘못 들은 곳을 고친 뒤 기획을 시작해 주세요. 사람 이름과 숫자는 특히 자주 틀려요.</p>
        {heard.retake_candidates.length ? (
          <section aria-label="다시 들어볼 구간">
            <h3>다시 들어볼 구간</h3>
            <p>발음이 흐릿하거나 다시 말씀하신 것 같은 곳이에요. 뺄지 남길지 직접 골라 주세요 -- 기본은 빼는 쪽이에요.</p>
            <ul>
              {heard.retake_candidates.map((candidate) => (
                <li key={candidate.segment_index}>
                  <label>
                    <Input
                      type="checkbox"
                      checked={excludedIndices.has(candidate.segment_index)}
                      disabled={disabled}
                      onChange={() => toggleExcluded(candidate.segment_index)}
                    />
                    {reasonLabel[candidate.reason]} -- "{candidate.text}"
                  </label>
                </li>
              ))}
            </ul>
          </section>
        ) : null}
        <label htmlFor="source-voice-script">대본으로 쓸 글</label>
        <Textarea
          id="source-voice-script"
          rows={10}
          value={scriptText}
          onChange={(event) => setScriptText(event.target.value)}
          disabled={disabled}
        />
        <Button
          type="button"
          disabled={disabled || !scriptText.trim()}
          onClick={() => onReady({ assetId: heard.asset_id, scriptText: scriptText.trim() })}
        >
          이 대본으로 기획 시작
        </Button>
        <Button
          type="button"
          variant="ghost"
          disabled={disabled}
          onClick={() => { setHeard(null); setExcludedIndices(new Set()); setScriptText(""); }}
        >
          다시 녹음하기
        </Button>
      </section>
    );
  }

  return (
    <section aria-label="목소리 녹음으로 시작">
      <h2>목소리만 있어요</h2>
      <p>마이크로 바로 녹음하면 말을 받아써 대본을 만들어 드려요. 발음이 흐릿하거나 다시 말씀하신 곳도 찾아 드릴게요.</p>
      {recording ? (
        <Button type="button" disabled={disabled} onClick={stopRecording}>대본 녹음 마치기</Button>
      ) : (
        <Button type="button" disabled={disabled || isReading} onClick={() => void startRecording()}>
          {isReading ? "받아쓰는 중이에요" : "마이크로 대본 녹음 시작"}
        </Button>
      )}
      {recording ? <p role="status">녹음 중이에요. 다 말씀하셨으면 대본 녹음 마치기를 눌러 주세요.</p> : null}
      {/* 이미 녹음해 둔 파일이 있으면 마이크로 다시 읽을 필요가 없다. */}
      <p>이미 녹음해 둔 파일이 있으면 그대로 올려도 돼요.</p>
      <label htmlFor="source-voice-file">녹음 파일 선택</label>
      <p id="source-voice-file-help">WAV · MP3 · M4A · OGG · WEBM · 128MB 이하</p>
      <Input
        id="source-voice-file"
        type="file"
        accept="audio/*,.wav,.mp3,.m4a,.ogg,.webm"
        aria-describedby="source-voice-file-help"
        disabled={disabled || isReading || recording}
        onChange={(event) => { setFile(event.target.files?.[0] ?? null); setError(null); }}
      />
      <Button type="button" disabled={disabled || isReading || recording} onClick={() => void readFile()}>
        {isReading ? "받아쓰는 중이에요" : "파일에서 대본 만들기"}
      </Button>
      {isReading ? <p role="status">녹음 길이에 따라 몇 분 걸릴 수 있어요. 이 화면을 열어 둔 채 기다려 주세요.</p> : null}
      {error ? <p role="alert">{error}</p> : null}
    </section>
  );
}
