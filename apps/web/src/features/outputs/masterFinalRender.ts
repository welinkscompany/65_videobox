import { api, type EditingSession, type FinalRenderArtifact, type JobRecord } from "../../api";

/** "지금 편집본의 마스터 완성본"을 고르는 단 하나의 규칙.
 *
 *  왜 필요한가 -- 내려받는 링크가 엉뚱한 파일을 조용히 건네주는 사고가 있었다.
 *  이유는 둘이다.
 *
 *  1. `input_ref` 필터가 없었다 -- 가로·세로 변형본도 `job_type`이
 *     "final_render"라서, 마스터를 만든 뒤 변형본을 만들면 "마지막 것"이
 *     변형본이 되어 그걸 준다. `OutputsPage.tsx`의 `finalJobs` 판정
 *     (`job.input_ref === timelineJob.job_id`)이 이미 이 문제를 제대로
 *     풀고 있다 -- 그 규칙을 그대로 가져온다.
 *  2. 낡음 확인이 없었다 -- 완성본을 만든 뒤 편집을 또 고쳤는데 다시
 *     안 만들었으면 옛 파일 그대로 준다. `OutputsPage.tsx`의
 *     `currentFinal`/`staleFinal`이 쓰는 값(`is_current` +
 *     `source_session_id`/`source_session_revision`이 지금 세션과
 *     일치하는지)과 같은 값으로 잰다.
 *
 *  이 파일이 그 규칙의 유일한 정의다. `ExportPopover`와 확인·내보내기
 *  화면(Task 2)이 각자 규칙을 새로 짜면 두 화면이 서로 다른 파일을
 *  "완성본"이라 부르는 사고가 다시 난다 -- 그래서 여기 하나만 두고
 *  나눠 쓴다.
 */

function latestJobOfType(
  jobs: readonly JobRecord[],
  jobType: string,
  inputRef?: string | null,
): JobRecord | null {
  return jobs
    .filter((job) => job.job_type === jobType && (inputRef == null || job.input_ref === inputRef))
    .reduce<JobRecord | null>((latest, job) => {
      if (!latest) return job;
      const timestamp = job.finished_at ?? job.started_at ?? "";
      const latestTimestamp = latest.finished_at ?? latest.started_at ?? "";
      return timestamp > latestTimestamp ? job : latest;
    }, null);
}

/** 지금 세션이 가리키는 타임라인을 실제로 만들어 낸 작업. 완성본이 이
 *  작업의 결과물을 가리키는지(`input_ref`)로 마스터인지 변형본인지 가른다. */
export function selectTimelineJob(
  jobs: readonly JobRecord[],
  session: Pick<EditingSession, "timeline_id"> | null,
): JobRecord | null {
  if (!session) return null;
  return latestJobOfType(
    jobs.filter((job) => job.status === "succeeded" && job.output_ref === session.timeline_id),
    "timeline_build",
  );
}

/** 위 타임라인 작업의 결과물을 가리키는 `final_render` 중 가장 최근 것.
 *  가로·세로 변형본은 `input_ref`가 달라서 여기 걸리지 않는다. */
export function selectMasterFinalJob(
  jobs: readonly JobRecord[],
  timelineJobId: string | null,
): JobRecord | null {
  if (!timelineJobId) return null;
  return latestJobOfType(jobs, "final_render", timelineJobId);
}

/** `OutputsPage.tsx`의 `currentFinal`과 같은 값으로 낡음을 잰다. */
export function isMasterFinalRenderCurrent(
  render: FinalRenderArtifact | null | undefined,
  session: Pick<EditingSession, "session_id" | "session_revision"> | null,
): boolean {
  return Boolean(
    render?.is_current === true &&
    session != null &&
    render.source_session_id === session.session_id &&
    render.source_session_revision === session.session_revision,
  );
}

export type MasterFinalRenderSelection =
  | { kind: "ready"; jobId: string }
  | { kind: "stale"; jobId: string }
  | { kind: "none" };

/** 세 화면이 공유하는 진입점. `jobs`·`session`은 이미 읽어 온 값을 그대로
 *  넘기면 되고(중복 조회 안 함), 후보가 있을 때만 `getFinalRender`로
 *  낡음 판정에 쓸 값을 추가로 읽는다. */
export async function resolveMasterFinalRender(
  projectId: string,
  jobs: readonly JobRecord[],
  session: EditingSession | null,
): Promise<MasterFinalRenderSelection> {
  const timelineJob = selectTimelineJob(jobs, session);
  const finalJob = selectMasterFinalJob(jobs, timelineJob?.job_id ?? null);
  if (!finalJob) return { kind: "none" };
  const finalRender = await api.getFinalRender(projectId, finalJob.job_id);
  if (finalRender.status !== "succeeded" || !finalRender.render) return { kind: "none" };
  return isMasterFinalRenderCurrent(finalRender.render, session)
    ? { kind: "ready", jobId: finalJob.job_id }
    : { kind: "stale", jobId: finalJob.job_id };
}
