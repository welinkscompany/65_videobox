import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

import { api } from "../../../api";
import { ExportPopover } from "./ExportPopover";

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

/** 캡컷 `내보내기` 팝오버 (계획 §7·§10 10단계).
 *
 *  지금은 `내보내기`를 누르면 완성본 화면이 **통째로** 팝업에 뜬다 -- 카드 5장에
 *  단추 15개다. 캡컷은 **목적지를 고르는 짧은 목록**을 먼저 준다.
 *
 *  **가장 큰 빈칸은 `영상 내려받기`였다.** 완성본은 재생만 되고 파일로 받는
 *  링크가 없었다(오디오만 있었다) -- 만든 영상을 못 가져가는 것이다.
 *
 *  **유튜브는 넣지 않는다.** 승인은 받았지만 아직 구현이 없다 --
 *  `decisions/2026-08-30`: 없는 기능 버튼은 안 만든다. 눌러 보고 아무 일도
 *  안 일어나는 것이 목록에 없는 것보다 나쁘다.
 *
 *  **2026-09-11 감사로 확인된 결함 둘 (task-1-brief.md):**
 *  기존 규칙은 `job_type === "final_render" && status === "succeeded"` 중
 *  배열의 "마지막 것"이었다. (1) 가로·세로 변형본도 같은 job_type이라
 *  나중에 만들면 그게 마지막이 된다. (2) 편집을 고친 뒤 다시 안 만들었어도
 *  옛 파일을 그대로 줬다. 아래 두 시험이 그 둘을 가른다.
 */
const session = {
  session_id: "session-a", project_id: "project-a", timeline_id: "timeline-a", session_revision: 3,
  segments: [], history: [],
};
const timelineJob = {
  job_id: "timeline-job-a", project_id: "project-a", job_type: "timeline_build", status: "succeeded",
  input_ref: null, output_ref: "timeline-a", error_message: null,
  started_at: "2026-09-11T00:00:00Z", finished_at: "2026-09-11T00:00:01Z",
};
const masterFinalJob = {
  job_id: "final-master", project_id: "project-a", job_type: "final_render", status: "succeeded",
  input_ref: "timeline-job-a", output_ref: "final-master", error_message: null,
  started_at: "2026-09-11T00:01:00Z", finished_at: "2026-09-11T00:01:05Z",
};
const currentMasterRender = {
  job_id: "final-master", status: "succeeded", render: {
    export_id: "final-master", timeline_id: "timeline-a", export_type: "final_render", file_uri: "local://master.mp4",
    status: "succeeded", is_current: true, source_session_id: "session-a", source_session_revision: 3,
  },
};

function stubSelectionApi({ jobs, finalRender }: { jobs: unknown[]; finalRender?: unknown }) {
  vi.spyOn(api, "getLatestEditingSession").mockResolvedValue(session as never);
  vi.spyOn(api, "listJobs").mockResolvedValue(jobs as never);
  if (finalRender !== undefined) {
    vi.spyOn(api, "getFinalRender").mockResolvedValue(finalRender as never);
  }
}

describe("내보내기 팝오버", () => {
  it("목적지를 먼저 보여 준다 -- 완성본 화면을 통째로 열지 않는다", async () => {
    stubSelectionApi({ jobs: [timelineJob, masterFinalJob], finalRender: currentMasterRender });

    render(<ExportPopover projectId="project-a" onOpenDetails={vi.fn()} />);

    const list = await screen.findByRole("list", { name: "내보낼 곳" });
    expect(list).toBeInTheDocument();
    for (const label of ["영상 내려받기", "공유 링크", "자막 파일", "CapCut 초안"]) {
      expect(screen.getByText(label)).toBeVisible();
    }
    // 없는 기능은 목록에 두지 않는다.
    expect(screen.queryByText("유튜브")).toBeNull();
  });

  it("완성본이 있으면 영상을 파일로 받게 해 준다", async () => {
    stubSelectionApi({ jobs: [timelineJob, masterFinalJob], finalRender: currentMasterRender });

    render(<ExportPopover projectId="project-a" onOpenDetails={vi.fn()} />);

    const link = await screen.findByRole("link", { name: "MP4 내려받기" });
    expect(link).toHaveAttribute("download");
    expect(link.getAttribute("href")).toContain("/final-renders/final-master/content");
  });

  it("마스터 완성본 뒤에 만든 세로 변형본이 있어도 마스터를 준다 (input_ref 필터)", async () => {
    // 변형본은 같은 job_type("final_render")이지만 input_ref가 다른 타임라인
    // 작업을 가리키고, 시간상 마스터보다 나중에 끝났다 -- "마지막 것" 규칙이면
    // 이 변형본을 내려받기 링크로 준다.
    const portraitVariantJob = {
      job_id: "final-portrait", project_id: "project-a", job_type: "final_render", status: "succeeded",
      input_ref: "variant-timeline-job", output_ref: "final-portrait", error_message: null,
      started_at: "2026-09-11T00:05:00Z", finished_at: "2026-09-11T00:05:05Z",
    };
    stubSelectionApi({
      jobs: [timelineJob, masterFinalJob, portraitVariantJob],
      finalRender: currentMasterRender,
    });

    render(<ExportPopover projectId="project-a" onOpenDetails={vi.fn()} />);

    const link = await screen.findByRole("link", { name: "MP4 내려받기" });
    expect(link.getAttribute("href")).toContain("/final-renders/final-master/content");
    expect(link.getAttribute("href")).not.toContain("final-portrait");
  });

  it("편집을 고친 뒤 다시 안 만들었으면 낡았다고 말하고 링크를 감춘다", async () => {
    stubSelectionApi({
      jobs: [timelineJob, masterFinalJob],
      finalRender: {
        job_id: "final-master", status: "succeeded", render: {
          export_id: "final-master", timeline_id: "timeline-a", export_type: "final_render", file_uri: "local://master.mp4",
          status: "succeeded", is_current: false,
          source_session_id: "session-a", source_session_revision: 2, // 지금 세션은 3(위 session)
        },
      },
    });

    render(<ExportPopover projectId="project-a" onOpenDetails={vi.fn()} />);

    expect(await screen.findByText(/완성본이 최신 편집본과 달라요/)).toBeVisible();
    expect(screen.queryByRole("link", { name: "MP4 내려받기" })).toBeNull();
  });

  it("완성본이 아직 없으면 왜 못 받는지 그 자리에서 말한다", async () => {
    stubSelectionApi({ jobs: [] });

    render(<ExportPopover projectId="project-a" onOpenDetails={vi.fn()} />);

    expect(await screen.findByText(/완성본을 아직 만들지 않았어요/)).toBeVisible();
    expect(screen.queryByRole("link", { name: "MP4 내려받기" })).toBeNull();
  });

  it("자세한 것은 2단계로 넘긴다", async () => {
    stubSelectionApi({ jobs: [timelineJob, masterFinalJob], finalRender: currentMasterRender });
    const onOpenDetails = vi.fn();

    render(<ExportPopover projectId="project-a" onOpenDetails={onOpenDetails} />);
    fireEvent.click(await screen.findByRole("button", { name: "완성본 만들기와 자세한 상태" }));

    await waitFor(() => expect(onOpenDetails).toHaveBeenCalled());
  });
});
