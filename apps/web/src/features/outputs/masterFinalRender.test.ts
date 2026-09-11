import { afterEach, describe, expect, it, vi } from "vitest";

import { api, type EditingSession, type FinalRenderJob, type JobRecord } from "../../api";
import { resolveMasterFinalRender } from "./masterFinalRender";

afterEach(() => { vi.restoreAllMocks(); });

/** 감사에서 확인된 결함 둘을 그대로 가른다 (task-1-brief.md).
 *  (a) 마스터 뒤에 가로·세로 변형본을 만들면 "마지막 것"이 변형본이 되어
 *      그걸 줬다 -- `input_ref` 필터가 없었다.
 *  (b) 편집을 고친 뒤 다시 만들지 않으면 옛 파일을 그대로 줬다 -- 낡음
 *      확인이 없었다. */
describe("마스터 완성본 고르기 -- 링크가 엉뚱한 파일을 주면 안 된다", () => {
  const session: EditingSession = {
    session_id: "session-a", project_id: "project-a", timeline_id: "timeline-a", session_revision: 3,
    segments: [], history: [],
  };
  const timelineJob: JobRecord = {
    job_id: "timeline-job-a", project_id: "project-a", job_type: "timeline_build", status: "succeeded",
    input_ref: null, output_ref: "timeline-a", error_message: null,
    started_at: "2026-09-11T00:00:00Z", finished_at: "2026-09-11T00:00:01Z",
  };
  const masterJob: JobRecord = {
    job_id: "final-master", project_id: "project-a", job_type: "final_render", status: "succeeded",
    input_ref: "timeline-job-a", output_ref: "final-master", error_message: null,
    started_at: "2026-09-11T00:01:00Z", finished_at: "2026-09-11T00:01:05Z",
  };

  it("마스터 뒤에 만든 세로 변형본을 무시하고 마스터를 고른다", async () => {
    // 변형본은 같은 job_type("final_render")이지만 input_ref가 다르고,
    // 시간상 마스터보다 나중에 끝났다 -- "마지막 것" 규칙이면 이걸 고른다.
    const portraitVariantJob: JobRecord = {
      job_id: "final-portrait", project_id: "project-a", job_type: "final_render", status: "succeeded",
      input_ref: "variant-timeline-job", output_ref: "final-portrait", error_message: null,
      started_at: "2026-09-11T00:05:00Z", finished_at: "2026-09-11T00:05:05Z",
    };
    const jobs = [timelineJob, masterJob, portraitVariantJob];
    const getFinalRender = vi.spyOn(api, "getFinalRender").mockResolvedValue({
      job_id: "final-master", status: "succeeded", render: {
        export_id: "final-master", timeline_id: "timeline-a", export_type: "final_render", file_uri: "local://master.mp4",
        status: "succeeded", is_current: true, source_session_id: "session-a", source_session_revision: 3,
      },
    } as FinalRenderJob);

    const result = await resolveMasterFinalRender("project-a", jobs, session);

    expect(result).toEqual({ kind: "ready", jobId: "final-master" });
    expect(getFinalRender).toHaveBeenCalledWith("project-a", "final-master");
  });

  it("완성본을 만든 뒤 편집을 또 고치고 다시 안 만들었으면 낡았다고 본다", async () => {
    const jobs = [timelineJob, masterJob];
    vi.spyOn(api, "getFinalRender").mockResolvedValue({
      job_id: "final-master", status: "succeeded", render: {
        export_id: "final-master", timeline_id: "timeline-a", export_type: "final_render", file_uri: "local://master.mp4",
        status: "succeeded", is_current: false, // 편집 후 무효화됨
        source_session_id: "session-a", source_session_revision: 2, // 렌더 당시 리비전(지금은 3)
      },
    } as FinalRenderJob);

    const result = await resolveMasterFinalRender("project-a", jobs, session);

    expect(result).toEqual({ kind: "stale", jobId: "final-master" });
  });

  it("완성본을 아직 만들지 않았으면 아무것도 고르지 않는다", async () => {
    const getFinalRender = vi.spyOn(api, "getFinalRender");

    const result = await resolveMasterFinalRender("project-a", [timelineJob], session);

    expect(result).toEqual({ kind: "none" });
    expect(getFinalRender).not.toHaveBeenCalled();
  });
});
