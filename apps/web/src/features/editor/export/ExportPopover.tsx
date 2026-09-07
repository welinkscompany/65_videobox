import { useEffect, useState } from "react";

import { api, type JobRecord } from "../../../api";
import { Button } from "../../../components/ui/button";

/** 캡컷 `내보내기` 팝오버 (계획 §7·§10 10단계).
 *
 *  지금까지는 `내보내기`를 누르면 완성본 화면이 **통째로** 팝업에 떴다 --
 *  카드 5장에 단추 15개다. 캡컷은 **목적지를 고르는 짧은 목록**을 먼저 주고,
 *  자세한 것은 한 겹 뒤에 둔다.
 *
 *  **가장 큰 빈칸은 `영상 내려받기`였다.** 완성본은 재생만 되고 파일로 받는
 *  링크가 없었다(오디오만 있었다) -- 만든 영상을 못 가져가는 것이다.
 *
 *  **유튜브는 목록에 없다.** 승인은 받았지만 아직 구현이 없다
 *  (`decisions/2026-08-30`: 없는 기능 버튼은 안 만든다). 눌러 보고 아무 일도
 *  안 일어나는 것이 목록에 없는 것보다 나쁘다.
 */
export function ExportPopover({
  projectId,
  onOpenDetails,
}: {
  projectId: string;
  /** 2단계 -- 완성본 만들기와 자세한 상태(기존 화면). */
  onOpenDetails: () => void;
}) {
  const [finalJobId, setFinalJobId] = useState<string | null>(null);
  const [subtitleJobId, setSubtitleJobId] = useState<string | null>(null);
  const [capcutReady, setCapcutReady] = useState(false);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let active = true;
    const latest = (jobs: readonly JobRecord[], jobType: string) => jobs
      .filter((job) => job.job_type === jobType && job.status === "succeeded")
      .slice(-1)[0] ?? null;
    void api.listJobs(projectId)
      .then((jobs) => {
        if (!active) return;
        setFinalJobId(latest(jobs, "final_render")?.job_id ?? null);
        setSubtitleJobId(latest(jobs, "subtitle_render")?.job_id ?? null);
        setCapcutReady(Boolean(latest(jobs, "capcut_draft_export")));
      })
      .catch(() => { /* 목록을 못 읽어도 2단계로는 갈 수 있어야 한다 */ })
      .finally(() => { if (active) setReady(true); });
    return () => { active = false; };
  }, [projectId]);

  if (!ready) return null;
  const base = `/api/projects/${encodeURIComponent(projectId)}`;
  return (
    <div className="vb-export-popover">
      <ul aria-label="내보낼 곳" className="vb-export-popover__list">
        <li>
          <strong>영상 내려받기</strong>
          {finalJobId ? (
            <a className="vb-action-link" download href={`${base}/final-renders/${encodeURIComponent(finalJobId)}/content`}>
              MP4 내려받기
            </a>
          ) : (
            // 준비를 떠넘기지 않는다 -- 무엇이 없어서 못 받는지 말한다.
            <p>완성본을 아직 만들지 않았어요. 아래에서 만들면 여기서 받을 수 있어요.</p>
          )}
        </li>
        <li>
          <strong>공유 링크</strong>
          <p>동료에게 보여 줄 링크를 만듭니다. 아래 자세한 자리에서 만들어요.</p>
        </li>
        <li>
          <strong>자막 파일</strong>
          {subtitleJobId ? (
            <a className="vb-action-link" download href={`${base}/subtitles/${encodeURIComponent(subtitleJobId)}/content`}>
              SRT 내려받기
            </a>
          ) : (
            <p>자막을 아직 만들지 않았어요.</p>
          )}
        </li>
        <li>
          <strong>CapCut 초안</strong>
          <p>{capcutReady ? "초안이 준비돼 있어요." : "초안을 아직 만들지 않았어요."}</p>
        </li>
      </ul>
      {/* 2단계. 캡컷도 `내보내기 설정`을 한 겹 뒤에 둔다. */}
      <Button onClick={onOpenDetails} type="button" variant="outline">완성본 만들기와 자세한 상태</Button>
    </div>
  );
}
