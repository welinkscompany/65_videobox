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

  it("받아쓰고 그 말을 장면 캡션으로 넣는다", { timeout: 20000 }, async () => {
    // 받아쓰기는 **걸어 두고 물어서 받는다**(2026-09-08, §1-6) -- 더빙·자막
    // 번역과 같은 이유(Whisper 호출에 시간 제한이 없다).
    vi.spyOn(api, "listDraftNarrationOptions").mockResolvedValue([
      { asset_id: "asset-1", asset_type: "narration_audio" },
    ] as never);
    const start = vi.spyOn(api, "startTranscription").mockResolvedValue({ job_id: "job-1", status: "running", transcript_uri: null } as never);
    const poll = vi.spyOn(api, "getTranscriptionJob").mockResolvedValue({ job_id: "job-1", status: "succeeded", transcript_uri: "local://projects/x/transcripts/job-1" } as never);
    const apply = vi.spyOn(api, "applyCaptionsFromTranscript").mockResolvedValue({ session_revision: 4 } as never);
    const onApplied = vi.fn();

    render(<AutoCaptionCard {...props} onApplied={onApplied} />);
    fireEvent.click(await screen.findByRole("button", { name: "말 받아쓰기" }));

    await waitFor(() => expect(start).toHaveBeenCalledWith("project-a", { narration_asset_id: "asset-1" }));
    // 폴링 간격만큼(2초 + 여유) 실제로 기다려야 한다 -- 걸어 두고 물어서 받는 것이
    // 이 흐름의 요점이라 가짜 타이머로 건너뛰지 않는다.
    await waitFor(() => expect(poll).toHaveBeenCalledWith("project-a", "job-1"), { timeout: 10000 });
    await waitFor(() => expect(apply).toHaveBeenCalledWith("project-a", "session-1", {
      transcription_job_id: "job-1",
      expected_revision: 3,
    }), { timeout: 10000 });
    await waitFor(() => expect(onApplied).toHaveBeenCalled(), { timeout: 10000 });
  });

  it("실패하면 무엇이 안 됐는지 그 자리에서 말한다", { timeout: 20000 }, async () => {
    vi.spyOn(api, "listDraftNarrationOptions").mockResolvedValue([
      { asset_id: "asset-1", asset_type: "narration_audio" },
    ] as never);
    vi.spyOn(api, "startTranscription").mockRejectedValue(new Error("boom"));

    render(<AutoCaptionCard {...props} />);
    fireEvent.click(await screen.findByRole("button", { name: "말 받아쓰기" }));

    expect(await screen.findByText(/받아쓰지 못했어요/, {}, { timeout: 10000 })).toBeVisible();
  });

  it("받아쓰기 잡이 실패로 끝나면 그 자리에서 말한다", { timeout: 20000 }, async () => {
    vi.spyOn(api, "listDraftNarrationOptions").mockResolvedValue([
      { asset_id: "asset-1", asset_type: "narration_audio" },
    ] as never);
    vi.spyOn(api, "startTranscription").mockResolvedValue({ job_id: "job-1", status: "running", transcript_uri: null } as never);
    vi.spyOn(api, "getTranscriptionJob").mockResolvedValue({ job_id: "job-1", status: "failed", transcript_uri: null } as never);

    render(<AutoCaptionCard {...props} />);
    fireEvent.click(await screen.findByRole("button", { name: "말 받아쓰기" }));

    expect(await screen.findByText(/받아쓰지 못했어요/, {}, { timeout: 10000 })).toBeVisible();
  });

  /** **번역 자막을 보고 있으면 화면이 안 바뀐다**(2026-09-05 코드리뷰가 잡았다).
   *  받아쓴 말은 **원문**에 들어간다. 창작자가 영어 자막을 보고 있으면 원문이
   *  바뀌어도 화면에는 영어가 그대로라 "눌렀는데 아무 일도 안 일어났다"가 된다.
   *  막지는 않는다 -- 원문을 고치는 것은 맞는 동작이다. 대신 **먼저 말한다.** */
  it("번역을 보고 있으면 원문이 바뀐다는 것을 먼저 말한다", async () => {
    vi.spyOn(api, "listDraftNarrationOptions").mockResolvedValue([
      { asset_id: "asset-1", asset_type: "narration_audio" },
    ] as never);

    render(<AutoCaptionCard {...props} captionLanguage="en" />);

    expect(await screen.findByText(/원문에 들어가요/)).toBeVisible();
  });

  it("덮어쓴다는 것을 누르기 전에 말한다", async () => {
    vi.spyOn(api, "listDraftNarrationOptions").mockResolvedValue([
      { asset_id: "asset-1", asset_type: "narration_audio" },
    ] as never);

    render(<AutoCaptionCard {...props} />);

    expect(await screen.findByText(/말이 있는 장면의 캡션을 새로 씁니다/)).toBeVisible();
  });
});
