import { useEffect, useRef, useState } from "react";

import { api } from "../../../api";
import { Button } from "../../../components/ui/button";
import { runTranscriptionWithProgress } from "./transcriptionProgress";

/** 캡컷 캡션 패널의 `자동 캡션` 카드 (계획 §4).
 *
 *  **부품은 다 있었고 잇는 자리만 없었다.** 받아쓰기(faster-whisper)는 시간
 *  구간별 텍스트를 주고 장면도 시간 구간을 갖는데, 그 둘을 잇는 코드가 없어
 *  받아쓰기 결과가 캡션이 되지 못했다 -- 제작 파이프라인의 다음 단계로만 흘렀다.
 *
 *  **누르기 전에 무엇이 바뀌는지 말한다.** 이 단추는 말이 있는 장면의 캡션을
 *  새로 쓴다. 손으로 써 둔 말이 사라질 수 있으므로 먼저 알린다(말이 없는 장면은
 *  엔진이 건드리지 않는다).
 */
export function AutoCaptionCard({
  projectId,
  sessionId,
  expectedRevision,
  captionLanguage = null,
  onApplied,
}: {
  projectId: string;
  sessionId: string;
  /** 지금 편집본 판. 다르면 서버가 막는다 -- 그게 두 사람이 같은 편집본을
   *  고칠 때 서로 덮어쓰지 않게 하는 방법이다. */
  expectedRevision: number;
  /** 지금 화면이 보여 주는 자막 언어. `null`이면 원문이다. */
  captionLanguage?: string | null;
  onApplied: () => void;
}) {
  const [narrationAssetId, setNarrationAssetId] = useState<string | null>(null);
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  // 받아쓰기가 비동기라(2026-09-08, §1-6) 몇 초가 아니라 몇 분 걸릴 수 있다 --
  // 그 사이 화면을 떠나면 죽은 컴포넌트에 상태를 쓰지 않게 막는다.
  const mounted = useRef(true);
  useEffect(() => () => { mounted.current = false; }, []);

  useEffect(() => {
    let active = true;
    void api.listDraftNarrationOptions(projectId)
      .then((options) => { if (active) setNarrationAssetId(options[0]?.asset_id ?? null); })
      .catch(() => { if (active) setNarrationAssetId(null); })
      .finally(() => { if (active) setReady(true); });
    return () => { active = false; };
  }, [projectId]);

  const run = async () => {
    if (!narrationAssetId || busy) return;
    setBusy(true);
    setMessage(null);
    try {
      // 받아쓰기는 **걸어 두고 물어서 받는다**(더빙·자막 번역과 같은 이유) --
      // Whisper 호출에 시간 제한이 없어 긴 내레이션은 한 요청에 못 끝낸다.
      const outcome = await runTranscriptionWithProgress({
        projectId,
        narrationAssetId,
        isStillRelevant: () => mounted.current,
      });
      if (!mounted.current) return;
      if (outcome.kind !== "succeeded") {
        setMessage(
          outcome.kind === "timed_out"
            ? "받아쓰기가 너무 오래 걸려서 기다리기를 멈췄어요. 잠시 뒤 다시 확인해 주세요."
            : "받아쓰지 못했어요. 잠시 뒤 다시 눌러 주세요.",
        );
        return;
      }
      await api.applyCaptionsFromTranscript(projectId, sessionId, {
        transcription_job_id: outcome.jobId,
        expected_revision: expectedRevision,
      });
      onApplied();
    } catch {
      // 이유를 코드로 던지지 않는다. 다시 눌러 볼 수 있다는 것까지 말한다.
      if (mounted.current) setMessage("받아쓰지 못했어요. 잠시 뒤 다시 눌러 주세요.");
    } finally {
      if (mounted.current) setBusy(false);
    }
  };

  if (!ready) return null;
  return (
    <section aria-label="자동 캡션" className="vb-auto-caption">
      <h3>자동 캡션</h3>
      {/* **번역을 보고 있으면 화면이 안 바뀐다.** 받아쓴 말은 원문에 들어가는데,
          창작자가 영어 자막을 보고 있으면 원문이 바뀌어도 눈앞은 그대로다 --
          "눌렀는데 아무 일도 안 일어났다"가 된다. 막지는 않고 먼저 말한다. */}
      {captionLanguage ? <p>지금 옮긴 자막을 보고 있어요. 받아쓴 말은 <b>원문에 들어가요</b> -- 화면은 그대로일 수 있어요.</p> : null}
      {narrationAssetId ? (
        <p>말이 있는 장면의 캡션을 새로 씁니다. 손으로 쓴 말은 그 장면에 말이 없을 때만 남아요.</p>
      ) : (
        <p>받아쓸 소리가 없어요. 내레이션을 먼저 넣어 주세요.</p>
      )}
      {message ? <p role="status">{message}</p> : null}
      <Button disabled={!narrationAssetId || busy} onClick={() => void run()} type="button" variant="outline">
        {busy ? "받아쓰는 중" : "말 받아쓰기"}
      </Button>
    </section>
  );
}
