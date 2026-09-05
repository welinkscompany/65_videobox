import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

import { api } from "../../../api";
import { AutoCaptionCard } from "./AutoCaptionCard";

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

/** 캡컷 캡션 패널의 `자동 캡션` 카드 (계획 §4).
 *
 *  **부품은 다 있었고 잇는 자리만 없었다.** 받아쓰기(faster-whisper)는 시간
 *  구간별 텍스트를 주고 장면도 시간 구간을 갖는데, 그 둘을 잇는 코드가 없어서
 *  받아쓰기 결과가 캡션이 되지 못했다. 백엔드를 먼저 잇고(엔진 →
 *  `captions-from-transcript`) 여기서 부른다.
 *
 *  **누르기 전에 무엇이 바뀌는지 말한다.** 이 단추는 장면 캡션을 통째로 덮으므로,
 *  손으로 써 둔 말이 있으면 그 사실을 먼저 알린다.
 */
describe("자동 캡션", () => {
  const props = { projectId: "project-a", sessionId: "session-1", expectedRevision: 3, onApplied: vi.fn() };

  it("받아쓸 소리가 없으면 그렇게 말하고 단추를 잠근다", async () => {
    vi.spyOn(api, "listDraftNarrationOptions").mockResolvedValue([]);

    render(<AutoCaptionCard {...props} />);

    expect(await screen.findByText(/받아쓸 소리가 없어요/)).toBeVisible();
    expect(screen.getByRole("button", { name: "말 받아쓰기" })).toBeDisabled();
  });

  it("받아쓰고 그 말을 장면 캡션으로 넣는다", async () => {
    vi.spyOn(api, "listDraftNarrationOptions").mockResolvedValue([
      { asset_id: "asset-1", asset_type: "narration_audio" },
    ] as never);
    const start = vi.spyOn(api, "startTranscription").mockResolvedValue({ job_id: "job-1", status: "succeeded" } as never);
    const apply = vi.spyOn(api, "applyCaptionsFromTranscript").mockResolvedValue({ session_revision: 4 } as never);
    const onApplied = vi.fn();

    render(<AutoCaptionCard {...props} onApplied={onApplied} />);
    fireEvent.click(await screen.findByRole("button", { name: "말 받아쓰기" }));

    await waitFor(() => expect(start).toHaveBeenCalledWith("project-a", { narration_asset_id: "asset-1" }));
    await waitFor(() => expect(apply).toHaveBeenCalledWith("project-a", "session-1", {
      transcription_job_id: "job-1",
      expected_revision: 3,
    }));
    await waitFor(() => expect(onApplied).toHaveBeenCalled());
  });

  it("실패하면 무엇이 안 됐는지 그 자리에서 말한다", async () => {
    vi.spyOn(api, "listDraftNarrationOptions").mockResolvedValue([
      { asset_id: "asset-1", asset_type: "narration_audio" },
    ] as never);
    vi.spyOn(api, "startTranscription").mockRejectedValue(new Error("boom"));

    render(<AutoCaptionCard {...props} />);
    fireEvent.click(await screen.findByRole("button", { name: "말 받아쓰기" }));

    expect(await screen.findByText(/받아쓰지 못했어요/)).toBeVisible();
  });

  it("덮어쓴다는 것을 누르기 전에 말한다", async () => {
    vi.spyOn(api, "listDraftNarrationOptions").mockResolvedValue([
      { asset_id: "asset-1", asset_type: "narration_audio" },
    ] as never);

    render(<AutoCaptionCard {...props} />);

    expect(await screen.findByText(/말이 있는 장면의 캡션을 새로 씁니다/)).toBeVisible();
  });
});
