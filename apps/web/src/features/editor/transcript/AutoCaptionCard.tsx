import { useEffect, useState } from "react";

import { api } from "../../../api";
import { Button } from "../../../components/ui/button";

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
  onApplied,
}: {
  projectId: string;
  sessionId: string;
  /** 지금 편집본 판. 다르면 서버가 막는다 -- 그게 두 사람이 같은 편집본을
   *  고칠 때 서로 덮어쓰지 않게 하는 방법이다. */
  expectedRevision: number;
  onApplied: () => void;
}) {
  const [narrationAssetId, setNarrationAssetId] = useState<string | null>(null);
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

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
      const job = await api.startTranscription(projectId, { narration_asset_id: narrationAssetId });
      await api.applyCaptionsFromTranscript(projectId, sessionId, {
        transcription_job_id: job.job_id,
        expected_revision: expectedRevision,
      });
      onApplied();
    } catch {
      // 이유를 코드로 던지지 않는다. 다시 눌러 볼 수 있다는 것까지 말한다.
      setMessage("받아쓰지 못했어요. 잠시 뒤 다시 눌러 주세요.");
    } finally {
      setBusy(false);
    }
  };

  if (!ready) return null;
  return (
    <section aria-label="자동 캡션" className="vb-auto-caption">
      <h3>자동 캡션</h3>
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
