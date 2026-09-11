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

  // 2026-09-11 리뷰로 확인된 결함 둘 (task-1-report.md 리뷰 코멘트).
  // 추출한 규칙이 `OutputsPage.tsx`가 실제로 하던 것과 달랐다 -- 옛 규칙을
  // 그대로 옮기지 못하면 두 화면이 다시 다른 파일을 "완성본"이라 부른다.
  describe("리뷰로 확인된 결함 -- OutputsPage와 규칙이 갈라져 있었다", () => {
    it("이 세션의 타임라인 작업을 못 찾아도(옛 기록 등) 완성본이 있으면 그걸 준다 (낙오 방지 폴백)", async () => {
      // `OutputsPage.tsx:482`는 timelineJob이 없으면 `input_ref` 필터 없이
      // 전체 final_render 중 최신을 그대로 쓴다. jobs 목록에 이 세션의
      // timeline_id를 가리키는 timeline_build 기록이 아예 없는 상황(예:
      // 오래된 세션, 목록이 아직 다 안 쌓인 상황)을 재현한다.
      const orphanFinalJob: JobRecord = {
        job_id: "final-orphan", project_id: "project-a", job_type: "final_render", status: "succeeded",
        input_ref: "some-untracked-timeline-job", output_ref: "final-orphan", error_message: null,
        started_at: "2026-09-11T00:02:00Z", finished_at: "2026-09-11T00:02:05Z",
      };
      vi.spyOn(api, "getFinalRender").mockResolvedValue({
        job_id: "final-orphan", status: "succeeded", render: {
          export_id: "final-orphan", timeline_id: "timeline-a", export_type: "final_render", file_uri: "local://orphan.mp4",
          status: "succeeded", is_current: true, source_session_id: "session-a", source_session_revision: 3,
        },
      } as FinalRenderJob);

      // jobs에는 timeline_build 기록이 없다 -- selectTimelineJob이 null을 준다.
      const result = await resolveMasterFinalRender("project-a", [orphanFinalJob], session);

      expect(result).toEqual({ kind: "ready", jobId: "final-orphan" });
    });

    it("완성본의 timeline_id가 지금 세션과 다르면 세션 id·리비전이 맞아도 낡았다고 본다", async () => {
      // `OutputsPage.tsx:756`은 `source_session_id`/`source_session_revision`
      // 말고 `timeline_id` 일치도 함께 본다. 지금 세션 값이 재사용돼 id·리비전은
      // 우연히 같아도 timeline_id가 다르면(다른 타임라인의 낡은 기록) 낡은 것이다.
      const jobs = [timelineJob, masterJob];
      vi.spyOn(api, "getFinalRender").mockResolvedValue({
        job_id: "final-master", status: "succeeded", render: {
          export_id: "final-master", timeline_id: "timeline-OLD", // 지금 세션은 "timeline-a"
          export_type: "final_render", file_uri: "local://master.mp4",
          status: "succeeded", is_current: true, source_session_id: "session-a", source_session_revision: 3,
        },
      } as FinalRenderJob);

      const result = await resolveMasterFinalRender("project-a", jobs, session);

      expect(result).toEqual({ kind: "stale", jobId: "final-master" });
    });

    it("완성본이 다른 프로젝트 세션을 가리키면(project_id 불일치) 낡았다고 본다", async () => {
      // `OutputsPage.tsx:755`는 `currentSession.project_id === projectId`도 확인한다.
      const jobs = [timelineJob, masterJob];
      vi.spyOn(api, "getFinalRender").mockResolvedValue({
        job_id: "final-master", status: "succeeded", render: {
          export_id: "final-master", timeline_id: "timeline-a", export_type: "final_render", file_uri: "local://master.mp4",
          status: "succeeded", is_current: true, source_session_id: "session-a", source_session_revision: 3,
        },
      } as FinalRenderJob);
      const otherProjectSession: EditingSession = { ...session, project_id: "project-OTHER" };

      const result = await resolveMasterFinalRender("project-a", jobs, otherProjectSession);

      expect(result).toEqual({ kind: "stale", jobId: "final-master" });
    });
  });
});
