import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

import { api } from "../../api";
import { NarrationAudioSection } from "./NarrationAudioSection";

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe("narration audio section", () => {
  it("lets the owner hear the narration the project is carrying", async () => {
    // 목록만 보여 주면 파일이 있다는 것만 안다. 그 안이 무음인지는 들어 봐야 안다 —
    // 2026-08-16에 완전 무음 완성본이 그렇게 나갔다.
    vi.spyOn(api, "listNarrationAudio").mockResolvedValue([{ asset_id: "narration_1" }] as never);

    const { container } = render(<NarrationAudioSection projectId="project_a" />);

    expect(await screen.findByLabelText("narration_1 내레이션")).toBeVisible();
    expect(container.querySelector("audio")).toHaveAttribute(
      "src",
      api.assetContentUrl("project_a", "narration_1"),
    );
  });

  it("says where narration can come from when there is none", async () => {
    vi.spyOn(api, "listNarrationAudio").mockResolvedValue([] as never);

    render(<NarrationAudioSection projectId="project_a" />);

    expect(await screen.findByText(
      "아직 내레이션이 없어요. 녹음한 파일을 넣거나, 아래에서 내 목소리로 만들 수 있어요.",
    )).toBeVisible();
  });

  it("shows the newly added narration instead of only claiming it worked", async () => {
    vi.spyOn(api, "listNarrationAudio")
      .mockResolvedValueOnce([] as never)
      .mockResolvedValue([{ asset_id: "narration_new" }] as never);
    const upload = vi.spyOn(api, "uploadNarrationAudio").mockResolvedValue({ asset_id: "narration_new" } as never);

    render(<NarrationAudioSection projectId="project_a" />);
    await screen.findByLabelText("내레이션 파일 넣기");
    const file = new File([new Uint8Array([1, 2, 3])], "narration.wav", { type: "audio/wav" });
    fireEvent.change(screen.getByLabelText("내레이션 파일 넣기"), { target: { files: [file] } });

    await waitFor(() => expect(upload).toHaveBeenCalledWith("project_a", file));
    expect(await screen.findByLabelText("narration_new 내레이션")).toBeVisible();
  });

  it("points at the likely cause when the file is refused", async () => {
    // 빈 파일은 서버가 막는다. 그 이유를 화면이 말해 주지 않으면 같은 파일을 다시 넣는다.
    vi.spyOn(api, "listNarrationAudio").mockResolvedValue([] as never);
    vi.spyOn(api, "uploadNarrationAudio").mockRejectedValue(new Error("empty"));

    render(<NarrationAudioSection projectId="project_a" />);
    await screen.findByLabelText("내레이션 파일 넣기");
    fireEvent.change(screen.getByLabelText("내레이션 파일 넣기"), {
      target: { files: [new File([], "empty.wav", { type: "audio/wav" })] },
    });

    expect(await screen.findByText(
      "내레이션을 넣지 못했어요. 소리가 들어 있는 오디오 파일인지 확인해 주세요.",
    )).toBeVisible();
  });

  it("drops the previous project's narration when the project changes", async () => {
    vi.spyOn(api, "listNarrationAudio").mockImplementation(async (projectId: string) =>
      (projectId === "project_a" ? [{ asset_id: "narration_a" }] : []) as never);

    const view = render(<NarrationAudioSection projectId="project_a" />);
    expect(await screen.findByLabelText("narration_a 내레이션")).toBeVisible();
    view.rerender(<NarrationAudioSection projectId="project_b" />);

    await waitFor(() => expect(screen.queryByLabelText("narration_a 내레이션")).not.toBeInTheDocument());
  });
});
