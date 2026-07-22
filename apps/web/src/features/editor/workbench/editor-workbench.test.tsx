import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

import { EditorWorkbench, persistedPanelPixels } from "./EditorWorkbench";

beforeEach(() => { vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} }); vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue({ width: 1000 } as DOMRect); vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => undefined); Object.defineProperty(window, "innerWidth", { configurable: true, value: 1920 }); });
afterEach(() => { cleanup(); vi.restoreAllMocks(); window.localStorage.clear(); });

const view = { projectId: "project-a", sessionId: "session-a", timelineId: "timeline-a", timelineVersion: "v1", expectedRevision: 1, timebase: "seconds", fps: { num: 30, den: 1 }, output: { width: 1080, height: 1920, sampleAspectRatio: "1:1", rotation: 0, durationSec: 1 }, tracks: [], captions: [], gaps: [], source: { status: "current" }, playback: { auditionUrls: {}, exactPreview: { status: "unavailable" } }, local: { selectedSegmentId: null, seekSec: 0 } } as const;

describe("EditorWorkbench", () => {
  it("uses the measured workbench width rather than viewport width", async () => {
    render(<EditorWorkbench view={view} />);
    expect(await screen.findByRole("region", { name: "편집 작업판" })).toHaveAttribute("data-editor-density", "desktop-single");
    expect(screen.getByText("편집 작업판", { selector: "strong" })).toBeInTheDocument();
    expect(screen.queryByText("읽기 전용 편집 작업판", { selector: "strong" })).toBeNull();
    expect(screen.getByRole("region", { name: "미리보기" }).parentElement).toHaveAttribute("data-preview-min-width", "640");
  });

  it("opens a narrow drawer, focuses it, and restores the trigger after Escape", async () => {
    Object.defineProperty(window, "innerWidth", { configurable: true, value: 390 });
    render(<EditorWorkbench view={view} />);
    const trigger = screen.getByRole("button", { name: "유진과 Inspector" });
    fireEvent.click(trigger);
    const dialog = await screen.findByRole("dialog", { name: "유진과 Inspector" });
    expect(dialog).toHaveFocus();
    fireEvent.keyDown(dialog, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
    await waitFor(() => expect(trigger).toHaveFocus());
  });

  it("keeps the disabled Eugene draft in browser-local UI state without enabling any request", () => {
    window.localStorage.setItem("videobox.editor-workbench.eugene-draft", "다음에 확인할 추천 초안");
    window.localStorage.setItem("videobox.editor-workbench.ui", JSON.stringify({ leftOpen: false, rightOpen: true, activeDrawer: null, leftSize: 280, rightSize: 320 }));
    const rendered = render(<EditorWorkbench view={view} />);
    const composer = screen.getByLabelText("유진에게 요청하기");
    expect(composer).toHaveValue("다음에 확인할 추천 초안");
    expect(composer).toBeDisabled();
    rendered.unmount();
    render(<EditorWorkbench view={view} />);
    expect(screen.getByLabelText("유진에게 요청하기")).toHaveValue("다음에 확인할 추천 초안");
  });

  it("persists finite panel pixel values and rejects invalid resize values", () => {
    expect(persistedPanelPixels({ asPercentage: 30, inPixels: 401.2 }, 260, 320)).toBe(401);
    expect(persistedPanelPixels({ asPercentage: 30, inPixels: Number.NaN }, 260, 320)).toBe(320);
  });

  it("replaces only the preview slot with the exact-preview stage while keeping read-only docks and timeline", () => {
    const currentView = {
      ...view,
      playback: { auditionUrls: { "asset-b": "/api/projects/project-a/assets/asset-b/content" }, exactPreview: { status: "succeeded", url: "/api/projects/project-a/exact-previews/g4/content", artifactRevision: 1, timelineStartSec: 0, timelineEndSec: 1 } },
      tracks: [{ trackId: "broll", role: "broll", clips: [{ clipId: "clip-b", segmentId: "segment-b", type: "broll", assetId: "asset-b", assetUri: null, startSec: 0, endSec: 1, controls: {} }] }],
    } as const;
    render(<EditorWorkbench view={currentView} />);
    expect(screen.getByRole("region", { name: "미리보기" })).toBeInTheDocument();
    expect(screen.getByLabelText("편집본 미리보기")).toHaveAttribute("src", "/api/projects/project-a/exact-previews/g4/content");
    expect(screen.getByRole("region", { name: "타임라인" })).toHaveTextContent("1개 트랙");
  });

  it("uses an audio element for a narration audition and never mounts a second player", () => {
    const narrationView = {
      ...view,
      playback: { auditionUrls: { "asset-n": "/api/projects/project-a/assets/asset-n/content" }, exactPreview: { status: "succeeded", url: "/api/projects/project-a/exact-previews/g4/content", artifactRevision: 1, timelineStartSec: 0, timelineEndSec: 1 } },
      tracks: [{ trackId: "narration", role: "narration", clips: [{ clipId: "clip-n", segmentId: "segment-n", type: "narration", assetId: "asset-n", assetUri: null, startSec: 0, endSec: 1, controls: {} }] }],
    } as const;
    const { container } = render(<EditorWorkbench view={narrationView} />);
    fireEvent.click(screen.getByRole("button", { name: "NARRATION · segment-n 원본 열기" }));
    expect(screen.getByLabelText("NARRATION · segment-n 소스 미리보기").tagName).toBe("AUDIO");
    expect(screen.getByLabelText("NARRATION · segment-n 소스 미리보기")).not.toHaveAttribute("autoplay");
    expect(container.querySelectorAll("audio, video")).toHaveLength(1);
  });

  it("uses a video element for a source-backed visual overlay audition rather than treating it as audio", () => {
    const overlayView = {
      ...view,
      playback: { auditionUrls: { "asset-o": "/api/projects/project-a/assets/asset-o/content" }, exactPreview: { status: "succeeded", url: "/api/projects/project-a/exact-previews/g4/content", artifactRevision: 1, timelineStartSec: 0, timelineEndSec: 1 } },
      tracks: [{ trackId: "overlay", role: "overlay", clips: [{ clipId: "clip-o", segmentId: "segment-o", type: "overlay", assetId: "asset-o", assetUri: null, startSec: 0, endSec: 1, controls: {}, overlayType: null, overlayPayload: {} }] }],
    } as const;
    render(<EditorWorkbench view={overlayView} />);
    fireEvent.click(screen.getByRole("button", { name: "OVERLAY · segment-o 원본 열기" }));
    expect(screen.getByLabelText("OVERLAY · segment-o 소스 미리보기").tagName).toBe("VIDEO");
  });

  it("excludes an image overlay from the video or audio audition player", () => {
    const imageOverlayView = {
      ...view,
      playback: { auditionUrls: { "asset-image": "/api/projects/project-a/assets/asset-image/content.png" }, exactPreview: { status: "succeeded", url: "/api/projects/project-a/exact-previews/g4/content", artifactRevision: 1, timelineStartSec: 0, timelineEndSec: 1 } },
      tracks: [{ trackId: "overlay", role: "overlay", clips: [{ clipId: "clip-image", segmentId: "segment-image", type: "overlay", assetId: "asset-image", assetUri: null, startSec: 0, endSec: 1, controls: {}, overlayType: "image_overlay", overlayPayload: {} }] }],
    } as const;
    const { container } = render(<EditorWorkbench view={imageOverlayView} />);
    expect(screen.queryByRole("button", { name: "OVERLAY · segment-image 원본 열기" })).toBeNull();
    expect(container.querySelectorAll("video, audio")).toHaveLength(1);
    expect(screen.getByLabelText("편집본 미리보기")).toBeInTheDocument();
  });
});
