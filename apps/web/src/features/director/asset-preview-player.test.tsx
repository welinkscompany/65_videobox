import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AssetPreviewPlayer } from "./AssetPreviewPlayer";

describe("AssetPreviewPlayer", () => {
  it("audio는 autoplay하지 않고 새 preview가 기존 audio를 중지한다", () => {
    const pause = vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => undefined);
    vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue(undefined);
    render(<AssetPreviewPlayer proposalId="p-1" candidates={[
      { candidateId: "m-01", referenceCode: "M-01", mediaType: "bgm", controls: {} },
      { candidateId: "m-02", referenceCode: "M-02", mediaType: "bgm", controls: {} },
    ]} previewUrl={(id) => `/preview/${id}`} />);
    expect(screen.getAllByTestId("director-audio-preview")[0]).not.toHaveAttribute("autoplay");
    fireEvent.click(screen.getByRole("button", { name: "M-02 미리듣기" }));
    expect(pause).toHaveBeenCalled();
  });

  it("video preview는 in 지점부터 재생한다", () => {
    vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue(undefined);
    const { container } = render(<AssetPreviewPlayer proposalId="p-1" candidates={[{ candidateId: "b-01", referenceCode: "B-01", mediaType: "broll", controls: { in_sec: 2, out_sec: 4 } }]} previewUrl={(id) => `/preview/${id}`} />);
    const video = container.querySelector("video") as HTMLVideoElement;
    fireEvent.click(screen.getByRole("button", { name: "B-01 미리보기" }));
    expect(video.currentTime).toBe(2);
  });

  it("narration audition solo/mute는 preview 전용 narration audio에만 반영하고 timeline gain을 변경하지 않는다", () => {
    const { container } = render(<AssetPreviewPlayer proposalId="p-1" candidates={[]} previewUrl={() => ""} narrationPreviewUrl="/assets/narration/content" />);
    const mute = screen.getByRole("button", { name: "나레이션 컨텍스트 음소거" }); const solo = screen.getByRole("button", { name: "나레이션 컨텍스트 solo" });
    const narration = container.querySelector('[data-testid="director-narration-context-preview"]') as HTMLAudioElement;
    expect(narration).toHaveAttribute("src", "/assets/narration/content");
    fireEvent.click(mute);
    expect(mute).toHaveAttribute("aria-pressed", "true"); expect(solo).toHaveAttribute("aria-pressed", "false");
    expect(narration.muted).toBe(true);
    fireEvent.click(solo);
    expect(solo).toHaveAttribute("aria-pressed", "true");
    expect(narration.volume).toBe(1);
    expect(screen.getByText(/타임라인 gain은 변경하지 않습니다/)).toBeVisible();
  });

  it("native media control의 play도 다른 preview를 pause하고 video in 지점으로 seek한다", () => {
    const pause = vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => undefined);
    const { container } = render(<AssetPreviewPlayer proposalId="p-1" candidates={[
      { candidateId: "m-01", referenceCode: "M-01", mediaType: "bgm", controls: {} },
      { candidateId: "b-01", referenceCode: "B-01", mediaType: "broll", controls: { in_sec: 3, out_sec: 5 } },
    ]} previewUrl={(id) => `/preview/${id}`} />);
    const video = container.querySelector("video") as HTMLVideoElement;
    fireEvent.play(video);
    expect(video.currentTime).toBe(3);
    expect(pause).toHaveBeenCalled();
  });

  it("candidate controls의 audition_gain_db를 preview volume에만 반영한다", () => {
    const { container } = render(<AssetPreviewPlayer proposalId="p-1" candidates={[{ candidateId: "m-01", referenceCode: "M-01", mediaType: "bgm", controls: { audition_gain_db: -18 } }]} previewUrl={(id) => `/preview/${id}`} />);
    const audio = container.querySelector("audio") as HTMLAudioElement;
    expect(audio.volume).toBeCloseTo(0.7);
    expect(screen.getByText(/타임라인 gain은 변경하지 않습니다/)).toBeVisible();
  });
});
