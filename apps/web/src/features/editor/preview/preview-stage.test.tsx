import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { PreviewStage } from "./preview-stage";

beforeEach(() => { vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => undefined); });
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

const current = { expectedRevision: 4, exactPreview: { status: "succeeded" as const, url: "/api/exact.mp4", artifactRevision: 4, timelineStartSec: 0, timelineEndSec: 12 }, captions: [{ text: "첫 번째 안내 자막", startSec: 0, endSec: 3 }, { text: "두 번째 안내 자막", startSec: 3, endSec: 8 }], sources: [{ id: "clip-a", label: "B-roll A", url: "/api/assets/a/content", mediaKind: "video" as const, timelineRange: { startSec: 3, endSec: 8 } }] };

describe("PreviewStage", () => {
  it("mounts a single exact video with burned-caption guidance and no duplicate visual caption", () => {
    const { container } = render(<PreviewStage {...current} />);
    expect(screen.getByLabelText("편집본 미리보기")).toHaveAttribute("src", "/api/exact.mp4");
    expect(screen.getByLabelText("편집본 미리보기")).not.toHaveAttribute("autoplay");
    expect(container.querySelectorAll("video, audio")).toHaveLength(1);
    expect(screen.getByText("자막은 영상에 포함되어 재생됩니다.")).toBeInTheDocument();
    expect(container.querySelector(".vb-preview-stage__caption-overlay")).toBeNull();
  });

  it("announces the active burned caption from the actual player time without rendering a second visual caption", () => {
    const { container } = render(<PreviewStage {...current} />);
    const media = screen.getByLabelText("편집본 미리보기") as HTMLVideoElement;
    expect(screen.getByRole("status", { name: "현재 자막" })).toHaveTextContent("첫 번째 안내 자막");
    Object.defineProperty(media, "currentTime", { configurable: true, writable: true, value: 3.5 });
    fireEvent.timeUpdate(media);
    expect(screen.getByRole("status", { name: "현재 자막" })).toHaveTextContent("두 번째 안내 자막");
    expect(container.querySelector(".vb-preview-stage__caption-overlay")).toBeNull();
    expect(container.querySelector(".vb-preview-stage__caption-transcript")).toHaveClass("vb-preview-stage__visually-hidden");
  });

  it("starts an exact selected-range preview at its immutable timeline offset", () => {
    render(<PreviewStage {...current} exactPreview={{ status: "succeeded", url: "/api/range.mp4", artifactRevision: 4, timelineStartSec: 4, timelineEndSec: 8 }} />);
    expect(screen.getAllByRole("status").find((node) => node.classList.contains("vb-preview-stage__status"))).toHaveTextContent("타임라인 4.0초");
  });

  it("keeps the one player and external timeline position synchronized in both directions", () => {
    const onPlaybackTimeChange = vi.fn();
    const rendered = render(<PreviewStage {...current} playbackSec={4} onPlaybackTimeChange={onPlaybackTimeChange} />);
    const media = screen.getByLabelText("편집본 미리보기") as HTMLVideoElement;
    Object.defineProperty(media, "currentTime", { configurable: true, writable: true, value: 0 });

    rendered.rerender(<PreviewStage {...current} playbackSec={6} onPlaybackTimeChange={onPlaybackTimeChange} />);
    expect(media.currentTime).toBe(6);
    Object.defineProperty(media, "currentTime", { configurable: true, writable: true, value: 7 });
    fireEvent.timeUpdate(media);

    expect(onPlaybackTimeChange).toHaveBeenCalledWith(7);
  });

  it("returns the effective selected-range position when an external seek is out of range", () => {
    const onPlaybackTimeChange = vi.fn();
    render(<PreviewStage {...current} exactPreview={{ status: "succeeded", url: "/api/range.mp4", artifactRevision: 4, timelineStartSec: 4, timelineEndSec: 8 }} playbackSec={20} onPlaybackTimeChange={onPlaybackTimeChange} />);

    expect(onPlaybackTimeChange).toHaveBeenCalledWith(8);
  });

  it("never mounts a stale artifact source and offers explicit refresh", async () => {
    const refresh = vi.fn();
    const { container } = render(<PreviewStage {...current} exactPreview={{ status: "stale", url: "/api/old.mp4", artifactRevision: 3 }} onRefresh={refresh} />);
    expect(container.querySelector("video, audio")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "미리보기 새로 만들기" }));
    await waitFor(() => expect(refresh).toHaveBeenCalledOnce());
  });

  it("keeps a failed refresh recoverable instead of leaving an unhandled action", async () => {
    const refresh = vi.fn().mockRejectedValue(new Error("offline"));
    render(<PreviewStage {...current} exactPreview={{ status: "failed" }} onRefresh={refresh} />);
    fireEvent.click(screen.getByRole("button", { name: "미리보기 새로 만들기" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("미리보기를 다시 요청하지 못했어요.");
    expect(screen.getByRole("button", { name: "미리보기 새로 만들기" })).toBeEnabled();
  });

  it("refuses non-local exact and audition URLs before a browser can request them", () => {
    const { container } = render(<PreviewStage {...current} exactPreview={{ status: "succeeded", url: "https://outside.invalid/exact.mp4", artifactRevision: 4 }} sources={[{ ...current.sources[0], url: "https://outside.invalid/source.mp4" }]} />);
    expect(container.querySelector("video, audio")).toBeNull();
    expect(screen.queryByRole("button", { name: /원본 열기/ })).toBeNull();
  });

  it("uses the same shell for a typed source audition, stops exact media, and restores exact mode", () => {
    const { container } = render(<PreviewStage {...current} />);
    const exact = screen.getByLabelText("편집본 미리보기") as HTMLVideoElement;
    const pause = vi.spyOn(exact, "pause").mockImplementation(() => undefined);
    fireEvent.click(screen.getByRole("button", { name: "B-roll A 원본 열기" }));
    expect(pause).toHaveBeenCalled();
    expect(screen.getByLabelText("B-roll A 소스 미리보기")).toHaveAttribute("src", "/api/assets/a/content");
    expect(screen.getByLabelText("B-roll A 소스 미리보기")).not.toHaveAttribute("autoplay");
    expect(screen.getByText("소스 미리보기")).toBeInTheDocument();
    expect(container.querySelectorAll("video, audio")).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "편집본으로 돌아가기" }));
    expect(screen.getByLabelText("편집본 미리보기")).toBeInTheDocument();
  });

  it("consumes a newer card audition request in its existing player", () => {
    const { container, rerender } = render(<PreviewStage {...current} auditionRequest={null} />);
    rerender(<PreviewStage {...current} auditionRequest={{ requestId: 1, source: { id: "broll:image-1", label: "제품 사진", url: "/api/projects/project-a/assets/image-1/content", mediaKind: "video", timelineRange: { startSec: 3, endSec: 7 } } }} />);

    expect(screen.getByLabelText("제품 사진 소스 미리보기")).toBeInTheDocument();
    expect(container.querySelectorAll("audio, video")).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "편집본으로 돌아가기" }));
    rerender(<PreviewStage {...current} auditionRequest={{ requestId: 2, source: { id: "broll:image-1", label: "제품 사진", url: "/api/projects/project-a/assets/image-1/content", mediaKind: "video", timelineRange: { startSec: 3, endSec: 7 } } }} />);
    expect(screen.getByLabelText("제품 사진 소스 미리보기")).toBeInTheDocument();
    expect(container.querySelectorAll("audio, video")).toHaveLength(1);
  });

  it("switches from a playable audition to one non-playable image surface without retaining media", () => {
    const { container, rerender } = render(<PreviewStage {...current} auditionRequest={{ requestId: 1, source: { id: "audio-1", label: "현장 오디오", url: "/api/projects/project-a/assets/audio-1/content", mediaKind: "audio", timelineRange: { startSec: 3, endSec: 7 } } }} />);
    expect(screen.getByLabelText("현장 오디오 소스 미리보기").tagName).toBe("AUDIO");
    expect(container.querySelectorAll("audio, video")).toHaveLength(1);

    rerender(<PreviewStage {...current} auditionRequest={{ requestId: 2, source: { id: "image-1", label: "제품 사진", url: "/api/projects/project-a/assets/image-1/content", mediaKind: "image", timelineRange: { startSec: 3, endSec: 7 } } }} />);
    expect(screen.getByLabelText("제품 사진 소스 미리보기").tagName).toBe("IMG");
    expect(container.querySelectorAll("audio, video")).toHaveLength(0);
    expect(container.querySelectorAll("img")).toHaveLength(1);
    expect(screen.queryByRole("button", { name: "재생 또는 일시정지" })).toBeNull();
  });

  it("keeps an image audition constrained inside the preview shell", () => {
    const css = readFileSync(resolve(process.cwd(), "src/styles/editor-workbench.css"), "utf8");
    const imageRule = css.match(/\.vb-preview-stage__media-shell img\s*\{([^}]*)\}/)?.[1] ?? "";

    expect(imageRule).toContain("display: block");
    expect(imageRule).toMatch(/width:\s*(?:min\()?100%/);
    expect(imageRule).toContain("max-width");
    expect(imageRule).toContain("max-height");
    expect(imageRule).toContain("object-fit: contain");
  });

  it("leaves Enter and Space on controls to their native action without toggling player playback", async () => {
    const refresh = vi.fn();
    const stale = render(<PreviewStage {...current} exactPreview={{ status: "stale", url: "/api/old.mp4", artifactRevision: 3 }} onRefresh={refresh} />);
    const refreshButton = screen.getByRole("button", { name: "미리보기 새로 만들기" });
    expect(fireEvent.keyDown(refreshButton, { key: " " })).toBe(true);
    fireEvent.click(refreshButton);
    await waitFor(() => expect(refresh).toHaveBeenCalledOnce());
    expect(stale.container.querySelector("video, audio")).toBeNull();
    stale.unmount();

    const failed = render(<PreviewStage {...current} exactPreview={{ status: "failed" }} onRefresh={refresh} />);
    const retryButton = screen.getByRole("button", { name: "미리보기 새로 만들기" });
    expect(fireEvent.keyDown(retryButton, { key: "Enter" })).toBe(true);
    fireEvent.click(retryButton);
    await waitFor(() => expect(refresh).toHaveBeenCalledTimes(2));
    expect(failed.container.querySelector("video, audio")).toBeNull();
    failed.unmount();

    const rendered = render(<PreviewStage {...current} />);
    fireEvent.click(screen.getByRole("button", { name: "B-roll A 원본 열기" }));
    const audition = screen.getByLabelText("B-roll A 소스 미리보기") as HTMLVideoElement;
    const play = vi.spyOn(audition, "play").mockResolvedValue(undefined);
    const returnButton = screen.getByRole("button", { name: "편집본으로 돌아가기" });
    expect(fireEvent.keyDown(returnButton, { key: "Enter" })).toBe(true);
    expect(play).not.toHaveBeenCalled();
    fireEvent.click(returnButton);
    expect(rendered.container.querySelectorAll("video, audio")).toHaveLength(1);
    expect(screen.getAllByLabelText("편집본 미리보기")).toHaveLength(1);
  });

  it("maps media time to timeline time, supports keyboard play/pause, and stops on scroll-away and unmount", () => {
    const { unmount } = render(<PreviewStage {...current} />);
    const media = screen.getByLabelText("편집본 미리보기") as HTMLVideoElement;
    const pause = vi.spyOn(media, "pause").mockImplementation(() => undefined);
    Object.defineProperty(media, "currentTime", { configurable: true, writable: true, value: 2.5 });
    Object.defineProperty(media, "paused", { configurable: true, value: false });
    fireEvent.timeUpdate(media);
    expect(screen.getAllByRole("status").find((node) => node.classList.contains("vb-preview-stage__status"))).toHaveTextContent("타임라인 2.5초");
    fireEvent.keyDown(screen.getByRole("region", { name: "미리보기" }), { key: " " });
    expect(pause).toHaveBeenCalled();
    fireEvent.blur(screen.getByRole("region", { name: "미리보기" }));
    expect(pause.mock.calls.length).toBeGreaterThan(1);
    fireEvent.scroll(window);
    expect(pause.mock.calls.length).toBeGreaterThan(2);
    unmount();
    expect(pause.mock.calls.length).toBeGreaterThan(3);
  });
});
