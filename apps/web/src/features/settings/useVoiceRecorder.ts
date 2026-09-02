import { useCallback, useEffect, useRef, useState } from "react";

/**
 * 마이크로 목소리를 녹음한다. 창작자 요청(2026-09-03):
 * "내가 다시 버튼을 눌러서 녹음해서 새로운 버전으로 만들수 있게."
 *
 * **길이를 화면에 보여 주는 것이 중요하다.** 목소리 복제는 참조가 짧으면
 * 안 닮는다. 몇 초를 읽었는지 안 보이면 창작자는 3초만 읽고 "안 닮네"라고
 * 결론 내린다 -- 짧아서 그런 것인데.
 */

/** 이보다 짧으면 복제가 잘 안 된다. 화면이 이 값을 기준으로 알려 준다. */
export const VOICE_MIN_SECONDS = 15;
/** 이보다 길 필요는 없다. 더 길면 기다림만 늘어난다. */
export const VOICE_ENOUGH_SECONDS = 60;

export type RecorderState = "idle" | "recording" | "denied" | "unsupported";

export function useVoiceRecorder() {
  const [state, setState] = useState<RecorderState>("idle");
  const [seconds, setSeconds] = useState(0);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<BlobPart[]>([]);
  const tickRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopTicking = useCallback(() => {
    if (tickRef.current !== null) {
      clearInterval(tickRef.current);
      tickRef.current = null;
    }
  }, []);

  // 화면을 떠나도 마이크를 놓는다. 안 놓으면 녹음 표시등이 계속 켜져 있다.
  useEffect(() => () => {
    stopTicking();
    recorderRef.current?.stream.getTracks().forEach((track) => track.stop());
  }, [stopTicking]);

  const start = useCallback(async () => {
    if (typeof MediaRecorder === "undefined" || !navigator.mediaDevices?.getUserMedia) {
      setState("unsupported");
      return;
    }
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      // 거절한 것과 마이크가 없는 것을 화면에서는 같게 다룬다 -- 창작자가
      // 할 일은 "브라우저에서 마이크를 허용해 주세요"로 같다.
      setState("denied");
      return;
    }
    chunksRef.current = [];
    const recorder = new MediaRecorder(stream);
    recorder.ondataavailable = (event) => {
      if (event.data.size > 0) chunksRef.current.push(event.data);
    };
    recorderRef.current = recorder;
    recorder.start();
    setSeconds(0);
    setState("recording");
    tickRef.current = setInterval(() => setSeconds((current) => current + 1), 1000);
  }, []);

  /** 녹음을 멈추고 파일을 돌려준다. 아무것도 안 녹음됐으면 `null`. */
  const stop = useCallback(async (): Promise<File | null> => {
    const recorder = recorderRef.current;
    stopTicking();
    setState("idle");
    if (!recorder || recorder.state === "inactive") return null;
    const finished = new Promise<void>((resolve) => {
      recorder.onstop = () => resolve();
    });
    recorder.stop();
    await finished;
    recorder.stream.getTracks().forEach((track) => track.stop());
    recorderRef.current = null;
    if (!chunksRef.current.length) return null;
    const blob = new Blob(chunksRef.current, { type: recorder.mimeType || "audio/webm" });
    chunksRef.current = [];
    // 확장자는 서버가 받는 목록에 있는 것으로 준다(`.webm`). 이름에 시각을
    // 넣어 두면 이름을 안 붙여도 어느 것이 나중 것인지 알 수 있다.
    const stamp = new Date().toISOString().slice(0, 16).replace(/[:T]/g, "-");
    return new File([blob], `내 목소리 ${stamp}.webm`, { type: blob.type });
  }, [stopTicking]);

  return { state, seconds, start, stop };
}

/** 녹음 길이를 창작자 말로. 짧으면 왜 더 읽어야 하는지까지 말한다. */
export function recordingHint(seconds: number): string {
  if (seconds < VOICE_MIN_SECONDS) {
    return `${seconds}초 — ${VOICE_MIN_SECONDS}초는 넘겨 주세요. 짧으면 목소리가 잘 안 닮아요.`;
  }
  if (seconds < VOICE_ENOUGH_SECONDS) return `${seconds}초 — 충분해요. 더 읽으면 더 좋아요.`;
  return `${seconds}초 — 넉넉해요. 이제 멈추셔도 됩니다.`;
}
