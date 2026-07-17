import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AssetPreviewPlayer } from "./AssetPreviewPlayer";

describe("AssetPreviewPlayer", () => {
  it("미리보기 영역을 추천 미리보기로 안내한다", () => {
    render(<AssetPreviewPlayer proposalId="p-1" candidates={[]} previewUrl={() => ""} />);

    expect(screen.getByRole("region", { name: "추천 미리보기" })).toBeVisible();
    expect(screen.queryByRole("region", { name: "후보 미리보기" })).not.toBeInTheDocument();
  });

  it("audio는 autoplay하지 않고 새 preview가 기존 audio를 중지한다", () => {
    const pause = vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => undefined);
    vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue(undefined);
    render(<AssetPreviewPlayer proposalId="p-1" candidates={[
      { candidateId: "m-01", referenceCode: "P1-M-01", mediaType: "bgm", controls: {} },
      { candidateId: "m-02", referenceCode: "P1-M-02", mediaType: "bgm", controls: {} },
    ]} previewUrl={(id) => `/preview/${id}`} />);
    expect(screen.getAllByTestId("director-audio-preview")[0]).not.toHaveAttribute("autoplay");
    fireEvent.click(screen.getByRole("button", { name: "루미 추천 1의 배경음악 2번 미리듣기" }));
    expect(pause).toHaveBeenCalled();
  });

  it("video preview는 in 지점부터 재생한다", () => {
    vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue(undefined);
    const { container } = render(<AssetPreviewPlayer proposalId="p-1" candidates={[{ candidateId: "b-01", referenceCode: "B-01", mediaType: "broll", controls: { in_sec: 2, out_sec: 4 } }]} previewUrl={(id) => `/preview/${id}`} />);
    const video = container.querySelector("video") as HTMLVideoElement;
    fireEvent.click(screen.getByRole("button", { name: "루미 추천의 비롤 1번 미리보기" }));
    expect(video.currentTime).toBe(2);
  });

  it("나레이션 미리듣기 설정은 미리듣기 소리에만 반영하고 편집본 음량을 바꾸지 않는다", () => {
    const { container } = render(<AssetPreviewPlayer proposalId="p-1" candidates={[]} previewUrl={() => ""} narrationPreviewUrl="/assets/narration/content" />);
    const mute = screen.getByRole("button", { name: "나레이션 미리듣기 음소거" }); const solo = screen.getByRole("button", { name: "나레이션만 듣기" });
    const narration = container.querySelector('[data-testid="director-narration-context-preview"]') as HTMLAudioElement;
    expect(narration).toHaveAttribute("src", "/assets/narration/content");
    fireEvent.click(mute);
    expect(mute).toHaveAttribute("aria-pressed", "true"); expect(solo).toHaveAttribute("aria-pressed", "false");
    expect(narration.muted).toBe(true);
    fireEvent.click(solo);
    expect(solo).toHaveAttribute("aria-pressed", "true");
    expect(narration.volume).toBe(1);
    expect(screen.getByText("미리듣기 설정은 편집본의 음량을 바꾸지 않아요.")).toBeVisible();
    expect(screen.queryByText(/컨텍스트|solo|audition|타임라인 gain/)).not.toBeInTheDocument();
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

  it("후보별 미리듣기 음량은 미리듣기에만 반영한다", () => {
    const { container } = render(<AssetPreviewPlayer proposalId="p-1" candidates={[{ candidateId: "m-01", referenceCode: "M-01", mediaType: "bgm", controls: { audition_gain_db: -18 } }]} previewUrl={(id) => `/preview/${id}`} />);
    const audio = container.querySelector("audio") as HTMLAudioElement;
    expect(audio.volume).toBeCloseTo(0.7);
    expect(screen.getByText("미리듣기 설정은 편집본의 음량을 바꾸지 않아요.")).toBeVisible();
  });

  it("원시 후보 ID와 참조 코드 대신 친숙한 추천 이름으로 재생 상태와 버튼을 표시한다", () => {
    render(<AssetPreviewPlayer proposalId="p-1" candidates={[{ candidateId: "candidate_003", referenceCode: "P12-B-03", mediaType: "broll", controls: {} }]} previewUrl={(id) => `/preview/${id}`} />);

    const button = screen.getByRole("button", { name: "루미 추천 12의 비롤 3번 미리보기" });
    expect(button).toBeVisible();
    fireEvent.click(button);
    expect(screen.getByText("루미 추천 12의 비롤 3번 미리보기 중")).toBeVisible();
    expect(screen.queryByText(/candidate_003|P12-B-03/)).not.toBeInTheDocument();
  });
});
