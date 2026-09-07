import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

import { api } from "../../../api";
import { ExportPopover } from "./ExportPopover";

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

const finalJob = {
  job_id: "final-1", project_id: "project-a", job_type: "final_render", status: "succeeded",
  input_ref: "timeline-1", output_ref: "final-1", error_message: null, started_at: null, finished_at: null,
};

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
 */
describe("내보내기 팝오버", () => {
  it("목적지를 먼저 보여 준다 -- 완성본 화면을 통째로 열지 않는다", async () => {
    vi.spyOn(api, "listJobs").mockResolvedValue([finalJob] as never);

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
    vi.spyOn(api, "listJobs").mockResolvedValue([finalJob] as never);

    render(<ExportPopover projectId="project-a" onOpenDetails={vi.fn()} />);

    const link = await screen.findByRole("link", { name: "MP4 내려받기" });
    expect(link).toHaveAttribute("download");
    expect(link.getAttribute("href")).toContain("/final-renders/final-1/content");
  });

  it("완성본이 아직 없으면 왜 못 받는지 그 자리에서 말한다", async () => {
    vi.spyOn(api, "listJobs").mockResolvedValue([] as never);

    render(<ExportPopover projectId="project-a" onOpenDetails={vi.fn()} />);

    expect(await screen.findByText(/완성본을 아직 만들지 않았어요/)).toBeVisible();
    expect(screen.queryByRole("link", { name: "MP4 내려받기" })).toBeNull();
  });

  it("자세한 것은 2단계로 넘긴다", async () => {
    vi.spyOn(api, "listJobs").mockResolvedValue([finalJob] as never);
    const onOpenDetails = vi.fn();

    render(<ExportPopover projectId="project-a" onOpenDetails={onOpenDetails} />);
    fireEvent.click(await screen.findByRole("button", { name: "완성본 만들기와 자세한 상태" }));

    await waitFor(() => expect(onOpenDetails).toHaveBeenCalled());
  });
});
