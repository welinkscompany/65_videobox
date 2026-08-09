import type { JobRecord } from "../api";

/** 화면이 실제로 쓰는 두 가지만 남긴다.
 *
 * 이 파일은 562줄에 export 39개였는데 화면이 부르는 것은 둘뿐이었다. 나머지
 * 37개는 어디서도 호출되지 않는 사장 코드였고, 그 안에 `TTS`, `세그먼트`,
 * `revision` 같은 개발 용어 라벨이 들어 있어서 문구 점검 때마다 살아 있는
 * 화면 문구처럼 보였다.
 */

function getLatestJobTimestamp(job: JobRecord) {
  return job.finished_at ?? job.started_at ?? "";
}

export function formatSeconds(startSec: number, endSec: number) {
  return `${startSec.toFixed(1)}s - ${endSec.toFixed(1)}s`;
}

export function findLatestSucceededJob(jobs: JobRecord[], jobType: string, inputRef?: string | null) {
  const candidates = jobs
    .filter(
      (job) =>
        job.job_type === jobType &&
        job.status === "succeeded" &&
        (inputRef == null || job.input_ref === inputRef),
    )
    .sort((left, right) =>
      getLatestJobTimestamp(right).localeCompare(getLatestJobTimestamp(left)),
    );
  return candidates.length > 0 ? candidates[0] : null;
}
