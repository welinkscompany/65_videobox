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
    expect(screen.getByText(/자막은 영상에 포함되어 재생됩니다/)).toBeInTheDocument();
    expect(container.querySelector(".vb-preview-stage__caption-overlay")).toBeNull();
  });

  it("puts the burned-caption note and the timeline status in one row, not two", () => {
    // These were two separate <p> elements (16px + status row); merged into
    // one so the stage recovers a line of vertical space.
    const { container } = render(<PreviewStage {...current} />);
    expect(container.querySelector(".vb-preview-stage__burned-caption")).toBeNull();
    const status = container.querySelector(".vb-preview-stage__status");
    expect(status).not.toBeNull();
    expect(status).toHaveTextContent("자막은 영상에 포함되어 재생됩니다");
    expect(status).toHaveTextContent("타임라인 0.0초");
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

  it("does not drag the playhead back when the seek is outside what it can show", () => {
    // 2026-08-17에 실제 앱에서 확인: 타임라인을 눌러도 재생 위치가 한 번 움직인 뒤
    // 그 자리에 붙박였다. 미리보기가 자기 구간 밖 재생 위치를 **되돌려 올려보내고**
    // 있었기 때문이다. 그래서 `나누기`가 영영 열리지 않았다.
    // 미리보기가 스스로 알리는 것(timeupdate)은 올려보내야 하지만, 못 보여 주는
    // 자리로 옮긴 사용자를 되미는 것은 다른 일이다.
    const onPlaybackTimeChange = vi.fn();
    render(<PreviewStage {...current} exactPreview={{ status: "succeeded", url: "/api/range.mp4", artifactRevision: 4, timelineStartSec: 4, timelineEndSec: 8 }} playbackSec={20} onPlaybackTimeChange={onPlaybackTimeChange} />);

    expect(onPlaybackTimeChange).not.toHaveBeenCalled();
  });

  it("puts the whole stage into fullscreen so the transport buttons come along", () => {
    // 마지막 확인은 크게 봐야 한다. 영상 요소만 키우면 재생·프레임 단추를 잃으므로
    // 판 전체를 올린다. 켜짐 표시는 브라우저 이벤트가 정답이다 -- Esc로도 나간다.
    const requestFullscreen = vi.fn().mockResolvedValue(undefined);
    HTMLElement.prototype.requestFullscreen = requestFullscreen;
    const { container } = render(<PreviewStage {...current} />);
    const stage = container.querySelector(".vb-preview-stage") as HTMLElement;
    const button = screen.getByRole("button", { name: "미리보기 전체화면" });
    expect(button).toHaveAttribute("aria-pressed", "false");

    fireEvent.click(button);
    expect(requestFullscreen).toHaveBeenCalledTimes(1);

    Object.defineProperty(document, "fullscreenElement", { configurable: true, value: stage });
    fireEvent(document, new Event("fullscreenchange"));
    expect(screen.getByRole("button", { name: "미리보기 전체화면" })).toHaveAttribute("aria-pressed", "true");

    Object.defineProperty(document, "fullscreenElement", { configurable: true, value: null });
    fireEvent(document, new Event("fullscreenchange"));
    expect(screen.getByRole("button", { name: "미리보기 전체화면" })).toHaveAttribute("aria-pressed", "false");
  });

  it("says the picture is not from where the playhead is", () => {
    render(<PreviewStage {...current} exactPreview={{ status: "succeeded", url: "/api/range.mp4", artifactRevision: 4, timelineStartSec: 4, timelineEndSec: 8 }} playbackSec={20} />);

    expect(screen.getByRole("status", { name: "미리보기 위치 안내" })).toHaveTextContent("8.0초");
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
    // The source-review buttons that used to trigger this live in the asset
    // dock now (Task 2), so the production path here is the auditionRequest
    // prop -- the same one the dock uses.
    const { container, rerender } = render(<PreviewStage {...current} exactPreview={{ status: "succeeded", url: "https://outside.invalid/exact.mp4", artifactRevision: 4 }} />);
    expect(container.querySelector("video, audio")).toBeNull();

    rerender(<PreviewStage {...current} exactPreview={{ status: "succeeded", url: "https://outside.invalid/exact.mp4", artifactRevision: 4 }} auditionRequest={{ requestId: 1, source: { ...current.sources[0], url: "https://outside.invalid/source.mp4" } }} />);
    expect(container.querySelector("video, audio")).toBeNull();
  });

  it("uses the same shell for a typed source audition, stops exact media, and restores exact mode", () => {
    const { container, rerender } = render(<PreviewStage {...current} />);
    const exact = screen.getByLabelText("편집본 미리보기") as HTMLVideoElement;
    const pause = vi.spyOn(exact, "pause").mockImplementation(() => undefined);
    rerender(<PreviewStage {...current} auditionRequest={{ requestId: 1, source: current.sources[0] }} />);
    expect(pause).toHaveBeenCalled();
    expect(screen.getByLabelText("B-roll A 소스 미리보기")).toHaveAttribute("src", "/api/assets/a/content");
    expect(screen.getByLabelText("B-roll A 소스 미리보기")).not.toHaveAttribute("autoplay");
    expect(screen.getByText("소스 미리보기")).toBeInTheDocument();
    expect(container.querySelectorAll("video, audio")).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "편집본으로 돌아가기" }));
    expect(screen.getByLabelText("편집본 미리보기")).toBeInTheDocument();
  });

  it("guides a browser-incompatible source back to the exact edited preview", () => {
    const { rerender } = render(<PreviewStage {...current} />);
    rerender(<PreviewStage {...current} auditionRequest={{ requestId: 1, source: current.sources[0] }} />);
    const audition = screen.getByLabelText("B-roll A 소스 미리보기") as HTMLVideoElement;
    Object.defineProperty(audition, "videoWidth", { configurable: true, value: 0 });
    Object.defineProperty(audition, "videoHeight", { configurable: true, value: 0 });

    fireEvent.loadedMetadata(audition);

    expect(screen.getByRole("alert")).toHaveTextContent(
      "이 원본은 여기서 화면을 열 수 없어요. 적용한 뒤 편집본 미리보기에서 확인해 주세요.",
    );
    expect(screen.queryByRole("button", { name: "재생 또는 일시정지" })).toBeNull();
    expect(screen.getByRole("button", { name: "편집본으로 돌아가기" })).toBeInTheDocument();
  });

  it("replaces an audition compatibility notice with current exact-preview recovery", async () => {
    const rendered = render(<PreviewStage {...current} />);
    rendered.rerender(<PreviewStage {...current} auditionRequest={{ requestId: 1, source: current.sources[0] }} />);
    const audition = screen.getByLabelText("B-roll A 소스 미리보기") as HTMLVideoElement;
    Object.defineProperty(audition, "videoWidth", { configurable: true, value: 0 });
    Object.defineProperty(audition, "videoHeight", { configurable: true, value: 0 });
    fireEvent.loadedMetadata(audition);
    expect(screen.getByRole("alert")).toBeInTheDocument();

    rendered.rerender(<PreviewStage {...current} exactPreview={{ status: "stale", url: "/api/old.mp4", artifactRevision: 3 }} auditionRequest={{ requestId: 1, source: current.sources[0] }} />);

    await waitFor(() => expect(screen.queryByText("원본 화면을 열지 못했어요")).toBeNull());
    expect(screen.getByRole("button", { name: "미리보기 새로 만들기" })).toBeInTheDocument();
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

  it("keeps the video visible in a fixed preview viewport and limits scrolling to source details", () => {
    const css = readFileSync(resolve(process.cwd(), "src/styles/editor-workbench.css"), "utf8");
    const previewRule = css.match(/^\.vb-editor-workbench__preview\s*\{([^}]*)\}/m)?.[1] ?? "";
    const stageRule = css.match(/^\.vb-preview-stage\s*\{([^}]*)\}/m)?.[1] ?? "";
    const mediaRule = css.match(/^\.vb-preview-stage__media-shell\s*\{([^}]*)\}/m)?.[1] ?? "";
    const videoRule = css.match(/^\.vb-preview-stage__media-shell video\s*\{([^}]*)\}/m)?.[1] ?? "";
    // Source review moved into the asset dock (Task 2), which already scrolls
    // its own overflow, so the preview stage no longer needs a scrolling
    // sources section of its own.
    const dockRule = css.match(/^\.vb-editor-workbench__dock\s*\{([^}]*)\}/m)?.[1] ?? "";

    expect(previewRule).toContain("overflow: hidden");
    expect(stageRule).toContain("height: 100%");
    expect(stageRule).toContain("grid-template-rows");
    expect(mediaRule).toContain("min-height: 0");
    expect(videoRule).toContain("width: 100%");
    expect(videoRule).toContain("height: 100%");
    expect(videoRule).toContain("min-height: 0");
    expect(videoRule).toContain("max-height: 100%");
    expect(videoRule).toContain("object-fit: contain");
    expect(dockRule).toContain("overflow: auto");
  });

  it("bounds the output variants strip so it cannot starve the preview", () => {
    const css = readFileSync(resolve(process.cwd(), "src/styles/editor-workbench.css"), "utf8");
    const variantsRule = css.match(/^\.vb-editor-variants\s*\{([\s\S]*?)\}/m)?.[1] ?? "";

    expect(variantsRule).toContain("max-height: 10rem");
    expect(variantsRule).toContain("overflow: auto");
    // 데스크톱에서는 더 조인다. 폭 구간마다 따로 적지 않고 한 번만 건다 --
    // 768~1499와 1500 위에 같은 규칙을 두 벌 두었더니 그 경계에서 미리보기 크기가
    // 튀었다.
    expect(css).toMatch(/@media \(min-width: 768px\) \{[\s\S]*?\.vb-editor-variants \{ max-height: 6rem;/);
  });

  it("bounds the timeline by screen height only, never by screen width", () => {
    const css = readFileSync(resolve(process.cwd(), "src/styles/editor-workbench.css"), "utf8");
    // 타임라인이 먹는 높이는 화면 폭과 아무 상관이 없다. 예전에는 1499px를 경계로
    // 상한이 두 벌 있었고 그 둘이 맞지 않아, 같은 900px 높이에서 1600px 화면이
    // 1440px 화면보다 미리보기를 107px **작게** 그렸다. 이 테스트가 잡는 것은
    // 그 형태(폭으로 자르지 않는다)뿐이고, 실제 높이는
    // `apps/web/e2e/exact-preview.spec.mjs`가 브라우저에서 재서 지킨다.
    const capRules = [...css.matchAll(/\.vb-editor-workbench__timeline[^{]*\{([^}]*max-height:[^;]*;)/g)].map((match) => match[1]);
    expect(capRules.length).toBeGreaterThan(0);
    // 편집자가 손잡이로 정한 값이 있으면 그것이 이기고, 없으면 화면 높이에 맞춘
    // 기본값이 쓰인다. 어느 쪽이든 **폭으로 자르지 않는다**는 것이 요점이다.
    for (const rule of capRules) expect(rule).toMatch(/max-height:\s*(var\(--vb-timeline-height,\s*)?clamp\([^;]*vh/);
    const widthScoped = css.match(/@media \(min-width: 768px\) and \(max-width: 1499px\) \{([\s\S]*?)\n\}/)?.[1] ?? "";
    expect(widthScoped).not.toContain("max-height");
  });

  it("makes the creator's timeline height actually take effect, not just cap it", () => {
    // `max-height`만 걸면 **제한만** 되고 늘어나지 않는다. 배포된 화면에서 손잡이를
    // 올려 변수는 24rem이 됐는데 타임라인은 293px 그대로였다 -- 내용이 그보다
    // 짧으면 상한을 올려도 아무 일이 없기 때문이다.
    // 편집자가 위로 끌면 **자리를 더 주는 것**이 뜻이므로 높이도 함께 잡는다.
    const css = readFileSync(resolve(process.cwd(), "src/styles/editor-workbench.css"), "utf8");
    const rules = [...css.matchAll(/\.vb-editor-workbench__timeline[^{]*\{([^}]*--vb-timeline-height[^}]*)\}/g)].map((match) => match[1]);

    expect(rules.length).toBeGreaterThan(0);
    for (const rule of rules) expect(rule).toMatch(/(^|;|\s)height:\s*var\(--vb-timeline-height/);
  });

  it("keeps a floor under the preview row so the timeline can never crush it to nothing", () => {
    const css = readFileSync(resolve(process.cwd(), "src/styles/editor-workbench.css"), "utf8");
    const workbenchRule = css.match(/^\.vb-editor-workbench\s*\{([^}]*)\}/m)?.[1] ?? "";

    // 2026-08-17에 타임라인 상한을 40vh로 올렸더니 390x844에서 타임라인이 364px를
    // 가져가 **미리보기 영상이 0px**가 됐다. 상한은 다시 계산해 고쳤지만, 다음에
    // 누가 또 늘려도 미리보기가 통째로 사라지지는 않도록 행 자체에 바닥을 둔다.
    expect(workbenchRule).toMatch(/grid-template-rows:\s*auto minmax\((?!0[,)])[^,]+, 1fr\) auto/);
  });

  it("ignores the player's own position while a requested seek is still settling", () => {
    // 자리를 옮겨 달라고 하면 플레이어는 잠깐 **옛 위치**를 그대로 알려 준다. 그걸
    // 그대로 위로 올리면 소유자가 옛 위치를 되돌려 보내고, 두 쪽이 서로 밀며 제자리를
    // 맴돈다. 실제 컨테이너에서 `다음 프레임`을 눌렀을 때 새 위치 → 옛 위치 →
    // 새 위치가 번갈아 찍히는 것을 확인했다. 가라앉은 뒤에 오는 `seeked`만 믿는다.
    const onPlaybackTimeChange = vi.fn();
    render(<PreviewStage {...current} playbackSec={4} onPlaybackTimeChange={onPlaybackTimeChange} />);
    const media = screen.getByLabelText("편집본 미리보기") as HTMLVideoElement;
    Object.defineProperty(media, "currentTime", { configurable: true, writable: true, value: 4 });
    Object.defineProperty(media, "seeking", { configurable: true, writable: true, value: true });
    onPlaybackTimeChange.mockClear();

    fireEvent.seeking(media);
    fireEvent.timeUpdate(media);
    expect(onPlaybackTimeChange).not.toHaveBeenCalled();

    Object.defineProperty(media, "seeking", { configurable: true, writable: true, value: false });
    Object.defineProperty(media, "currentTime", { configurable: true, writable: true, value: 4.5 });
    fireEvent.seeked(media);
    expect(onPlaybackTimeChange).toHaveBeenLastCalledWith(4.5);
  });

  it("steps one frame at a time from the fps the timeline actually uses", () => {
    // 컷을 어디서 자를지는 프레임 단위로 정해진다. `0.1초 뒤로`가 아니라 한 프레임씩
    // 움직여야 자를 자리를 고를 수 있다 -- 캡컷도 그렇다.
    const onPlaybackTimeChange = vi.fn();
    render(<PreviewStage {...current} fps={{ num: 25, den: 1 }} playbackSec={4} onPlaybackTimeChange={onPlaybackTimeChange} />);
    const media = screen.getByLabelText("편집본 미리보기") as HTMLVideoElement;
    Object.defineProperty(media, "currentTime", { configurable: true, writable: true, value: 4 });

    fireEvent.click(screen.getByRole("button", { name: "다음 프레임" }));
    expect(media.currentTime).toBeCloseTo(4.04, 5);
    expect(onPlaybackTimeChange).toHaveBeenLastCalledWith(expect.closeTo(4.04, 5));

    fireEvent.click(screen.getByRole("button", { name: "이전 프레임" }));
    expect(media.currentTime).toBeCloseTo(4, 5);
  });

  it("never steps outside the range the preview actually covers", () => {
    // 구간 밖으로 나가면 미리보기는 그 순간을 갖고 있지 않다. 끝에서 한 번 더
    // 누르면 조용히 제자리에 있어야지, 없는 곳을 가리키면 안 된다.
    render(<PreviewStage {...current} exactPreview={{ status: "succeeded", url: "/api/range.mp4", artifactRevision: 4, timelineStartSec: 4, timelineEndSec: 8 }} fps={{ num: 30, den: 1 }} />);
    const media = screen.getByLabelText("편집본 미리보기") as HTMLVideoElement;
    Object.defineProperty(media, "currentTime", { configurable: true, writable: true, value: 0 });

    fireEvent.click(screen.getByRole("button", { name: "이전 프레임" }));
    expect(media.currentTime).toBe(0);

    Object.defineProperty(media, "currentTime", { configurable: true, writable: true, value: 4 });
    fireEvent.click(screen.getByRole("button", { name: "다음 프레임" }));
    expect(media.currentTime).toBe(4);
  });

  it("repeats only the selected scene while the creator is judging it", () => {
    // 컷을 확인할 때는 그 장면만 몇 번씩 본다. 매번 되감는 대신 반복을 켜 둔다.
    // 구간은 화면이 이미 `적용 구간`으로 보여 주는 것과 같은 것이다.
    render(<PreviewStage {...current} loopRange={{ startSec: 3, endSec: 8 }} />);
    const media = screen.getByLabelText("편집본 미리보기") as HTMLVideoElement;
    Object.defineProperty(media, "currentTime", { configurable: true, writable: true, value: 9 });

    // 꺼져 있으면 지나간다.
    fireEvent.timeUpdate(media);
    expect(media.currentTime).toBe(9);

    fireEvent.click(screen.getByRole("button", { name: "선택한 장면 반복" }));
    Object.defineProperty(media, "currentTime", { configurable: true, writable: true, value: 9 });
    fireEvent.timeUpdate(media);
    expect(media.currentTime).toBe(3);
  });

  it("does not fight the player when the chosen scene is outside what the preview holds", () => {
    // 부분 구간 미리보기(4~8초)를 보는 중에 9~12초 장면을 고르면, 반복이 도달할 수
    // 없는 자리를 계속 노려 매 tick마다 되감는다 -- 재생이 그 자리에 붙박인다.
    // 담고 있지 않은 구간은 반복하지 않는다.
    render(<PreviewStage
      {...current}
      exactPreview={{ status: "succeeded", url: "/api/range.mp4", artifactRevision: 4, timelineStartSec: 4, timelineEndSec: 8 }}
      loopRange={{ startSec: 9, endSec: 12 }}
    />);
    const media = screen.getByLabelText("편집본 미리보기") as HTMLVideoElement;
    fireEvent.click(screen.getByRole("button", { name: "선택한 장면 반복" }));
    Object.defineProperty(media, "currentTime", { configurable: true, writable: true, value: 3 });

    fireEvent.timeUpdate(media);

    expect(media.currentTime).toBe(3);
  });

  it("offers no repeat control when no scene is selected", () => {
    // 반복할 구간이 없는데 단추만 있으면, 눌러도 아무 일이 없는 단추가 된다.
    render(<PreviewStage {...current} />);
    expect(screen.queryByRole("button", { name: "선택한 장면 반복" })).toBeNull();
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
    rendered.rerender(<PreviewStage {...current} auditionRequest={{ requestId: 1, source: current.sources[0] }} />);
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
