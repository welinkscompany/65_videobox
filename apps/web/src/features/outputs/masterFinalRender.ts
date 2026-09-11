import { api, type EditingSession, type FinalRenderArtifact, type JobRecord } from "../../api";
import { selectCurrentTimelineJob } from "../review/timeline-review-state";

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
 *  작업의 결과물을 가리키는지(`input_ref`)로 마스터인지 변형본인지 가른다.
 *
 *  **2026-09-11 리뷰로 확인된 결함(final-fix-report.md 발견 1)** -- 여기서
 *  독자적인 규칙(`finished_at ?? started_at` 한 값 비교)을 새로 짰었는데,
 *  `OutputsPage.tsx`가 합쳐진 화면(`ReviewAndOutputPage`)에서 실제로 쓰는
 *  값은 `timeline-review-state.ts`의 `selectCurrentTimelineJob`이 고른
 *  것(`shared.job`)이었다. 둘은 `finished_at`이 비어 있는 `succeeded` 기록
 *  앞에서 서로 다른 것을 고를 수 있다 -- 뒤엣것은 `project_id` 일치도 보고
 *  동점이면 `[finished_at, started_at, job_id]` 세 단으로 결정론적으로
 *  가르지만, 앞엣것은 그 검사와 세 번째 단(job_id)이 없었다.
 *
 *  둘 중 `selectCurrentTimelineJob`을 골랐다 -- 원래 규칙의 출처이자(실제
 *  화면이 이미 그 값으로 돌아가고 있었다), 더 엄격한 상위집합(project_id
 *  검사 + 결정론적 동점 처리)이기 때문이다. 그래서 새로 짜지 않고 그대로
 *  위임한다 -- `ExportPopover`와 `OutputsPage`(단독으로 쓰일 때의 폴백
 *  경로)가 다시 갈라지지 않는다. */
export function selectTimelineJob(
  jobs: readonly JobRecord[],
  session: Pick<EditingSession, "timeline_id" | "project_id"> | null,
): JobRecord | null {
  if (!session) return null;
  return selectCurrentTimelineJob(session, jobs);
}

/** 위 타임라인 작업의 결과물을 가리키는 `final_render` 중 가장 최근 것.
 *  가로·세로 변형본은 `input_ref`가 달라서 여기 걸리지 않는다.
 *
 *  `timelineJobId`가 없을 때(이 세션의 타임라인 작업을 목록에서 못 찾은
 *  경우) `null`을 주면 안 된다 -- `OutputsPage.tsx:482`가 같은 상황에서
 *  `input_ref` 필터 없이 전체 `final_render` 중 최신으로 폴백한다. 여기서
 *  `null`을 주면 두 화면이 갈라진다: 화면은 완성본을 보여 주는데 내보내기
 *  팝오버는 "아직 안 만들었다"고 말하는 사고(2026-09-11 리뷰 확인). */
export function selectMasterFinalJob(
  jobs: readonly JobRecord[],
  timelineJobId: string | null,
): JobRecord | null {
  if (!timelineJobId) return latestJobOfType(jobs, "final_render");
  return latestJobOfType(jobs, "final_render", timelineJobId);
}

/** 자막판 `selectMasterFinalJob` -- `job_type`만 다르고 나머지(입력 참조
 *  필터, 못 찾았을 때의 폴백)는 완전히 같은 규칙이다(final-fix-report.md
 *  발견 2). `ExportPopover`가 예전엔 `input_ref` 필터도 없이 "마지막
 *  succeeded 자막 job"을 그대로 썼다 -- 완성본에서 이미 고친 결함을
 *  자막에서는 그대로 갖고 있었다. */
export function selectMasterSubtitleJob(
  jobs: readonly JobRecord[],
  timelineJobId: string | null,
): JobRecord | null {
  if (!timelineJobId) return latestJobOfType(jobs, "subtitle_render");
  return latestJobOfType(jobs, "subtitle_render", timelineJobId);
}

/** "지금 편집본의 것인가"를 재는 값의 모양은 완성본과 자막이 같다 --
 *  `is_current`, `timeline_id`, `source_session_id`, `source_session_revision`.
 *  자막 쪽 타입(`SubtitleArtifact`)만 `project_id`를 산출물 자체에 따로
 *  갖고 있어서, 있으면 그것도 확인하고(완성본 쪽 `FinalRenderArtifact`는
 *  그 필드가 없어 건너뛴다) 세션의 `project_id`는 항상 확인한다.
 *
 *  `OutputsPage.tsx`의 `currentFinal`/`currentSubtitle`과 같은 값으로
 *  낡음을 잰다(`OutputsPage.tsx:754-758`, `:737-743`) -- 처음 추출할 때
 *  `project_id`·`timeline_id` 일치를 빠뜨렸었다(2026-09-11 리뷰 확인).
 *  세션 값이 재사용돼 id·리비전만 우연히 같은 낡은 기록을 "최신"이라
 *  잘못 판단할 수 있었다. */
type FreshnessCheckArtifact = Readonly<{
  is_current?: boolean;
  timeline_id: string;
  source_session_id?: string | null;
  source_session_revision?: number | null;
  project_id?: string;
}>;

export function isArtifactCurrent(
  artifact: FreshnessCheckArtifact | null | undefined,
  session: Pick<EditingSession, "project_id" | "session_id" | "session_revision" | "timeline_id"> | null,
  projectId: string,
): boolean {
  return Boolean(
    artifact?.is_current === true &&
    session != null &&
    session.project_id === projectId &&
    (artifact.project_id == null || artifact.project_id === projectId) &&
    artifact.timeline_id === session.timeline_id &&
    artifact.source_session_id === session.session_id &&
    artifact.source_session_revision === session.session_revision,
  );
}

/** 옛 이름을 그대로 남긴다 -- `OutputsPage.tsx`가 세 자리에서 이 이름으로
 *  부른다. 판정 자체는 `isArtifactCurrent`로 옮겼다(자막과 나눠 쓰기 위해). */
export function isMasterFinalRenderCurrent(
  render: FinalRenderArtifact | null | undefined,
  session: Pick<EditingSession, "project_id" | "session_id" | "session_revision" | "timeline_id"> | null,
  projectId: string,
): boolean {
  return isArtifactCurrent(render, session, projectId);
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
  return isMasterFinalRenderCurrent(finalRender.render, session, projectId)
    ? { kind: "ready", jobId: finalJob.job_id }
    : { kind: "stale", jobId: finalJob.job_id };
}

export type MasterSubtitleSelection =
  | { kind: "ready"; jobId: string }
  | { kind: "stale"; jobId: string }
  | { kind: "none" };

/** 자막판 `resolveMasterFinalRender`(final-fix-report.md 발견 2).
 *
 *  `ExportPopover.tsx`가 예전엔 자막을 `job_type === "subtitle_render"`
 *  중 배열의 "마지막 것"으로 골랐다 -- `input_ref` 필터도, 낡음 확인도
 *  없었다. 완성본에서 이미 고친 바로 그 결함이었다. 여기서 새로 짜지 않고
 *  `selectTimelineJob`·`selectMasterSubtitleJob`·`isArtifactCurrent`를
 *  그대로 나눠 쓴다. */
export async function resolveMasterSubtitle(
  projectId: string,
  jobs: readonly JobRecord[],
  session: EditingSession | null,
): Promise<MasterSubtitleSelection> {
  const timelineJob = selectTimelineJob(jobs, session);
  const subtitleJobRecord = selectMasterSubtitleJob(jobs, timelineJob?.job_id ?? null);
  if (!subtitleJobRecord) return { kind: "none" };
  const subtitleJob = await api.getSubtitle(projectId, subtitleJobRecord.job_id);
  if (subtitleJob.status !== "succeeded" || !subtitleJob.subtitle) return { kind: "none" };
  return isArtifactCurrent(subtitleJob.subtitle, session, projectId)
    ? { kind: "ready", jobId: subtitleJobRecord.job_id }
    : { kind: "stale", jobId: subtitleJobRecord.job_id };
}
