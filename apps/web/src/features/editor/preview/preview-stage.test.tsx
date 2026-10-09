import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { PreviewStage } from "./preview-stage";
import { createPlaybackClock } from "./playbackClock";
import { playbackShortcutFor } from "./playbackShortcuts";
import { EDITOR_SHORTCUTS } from "../editorShortcuts";
import { PLAYBACK_RATE_HINT_STORAGE_KEY, PLAYBACK_RATE_STORAGE_KEY } from "./playbackRate";

beforeEach(() => { vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => undefined); });
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

const current = { expectedRevision: 4, exactPreview: { status: "succeeded" as const, url: "/api/exact.mp4", artifactRevision: 4, timelineStartSec: 0, timelineEndSec: 12 }, captions: [{ text: "첫 번째 안내 자막", startSec: 0, endSec: 3 }, { text: "두 번째 안내 자막", startSec: 3, endSec: 8 }], sources: [{ id: "clip-a", label: "B-roll A", url: "/api/assets/a/content", mediaKind: "video" as const, timelineRange: { startSec: 3, endSec: 8 } }] };

describe("PreviewStage", () => {
  const setupEchoPlayer = (initialSec = 2) => {
    let reported = 0;
    const onPlaybackTimeChange = vi.fn((seconds: number) => { reported = seconds; });
    const view = render(<PreviewStage {...current} playbackSec={initialSec} onPlaybackTimeChange={onPlaybackTimeChange} />);
    const media = screen.getByLabelText("편집본 미리보기") as HTMLVideoElement;
    let time = 2.5;
    const writes: number[] = [];
    Object.defineProperty(media, "currentTime", { configurable: true, get: () => time, set: (value: number) => { writes.push(value); time = value; } });
    Object.defineProperty(media, "paused", { configurable: true, value: false });
    Object.defineProperty(media, "seeking", { configurable: true, value: false });
    return { ...view, media, writes, onPlaybackTimeChange, getReported: () => reported, setTime: (v: number) => { time = v; } };
  };
  it("재생 중 자기가 올려보낸 위치가 되돌아와도 재생기를 되감지 않는다(2026-10-09 실측: 20초에 67~74번)", () => {
    const { rerender, media, writes, onPlaybackTimeChange, getReported, setTime } = setupEchoPlayer();
    fireEvent.timeUpdate(media);
    expect(getReported()).toBe(2.5);
    setTime(2.517);
    rerender(<PreviewStage {...current} playbackSec={getReported()} onPlaybackTimeChange={onPlaybackTimeChange} />);
    expect(writes).toEqual([]);
  });
  it("재생 중이라도 메아리가 아닌 위치(타임라인 클릭·장면 고르기·화살표)는 재생기를 옮긴다", () => {
    const { rerender, media, writes, onPlaybackTimeChange, getReported, setTime } = setupEchoPlayer();
    fireEvent.timeUpdate(media);
    setTime(2.517);
    rerender(<PreviewStage {...current} playbackSec={getReported()} onPlaybackTimeChange={onPlaybackTimeChange} />);
    rerender(<PreviewStage {...current} playbackSec={7.25} onPlaybackTimeChange={onPlaybackTimeChange} />);
    expect(writes).toEqual([7.25]);
  });
  it("메아리 뒤 사용자가 같은 위치를 다시 눌러도(2.5 → 1.0 → 2.5) 둘 다 옮긴다", () => {
    const { rerender, media, writes, onPlaybackTimeChange, getReported, setTime } = setupEchoPlayer();
    fireEvent.timeUpdate(media);
    setTime(2.517);
    rerender(<PreviewStage {...current} playbackSec={getReported()} onPlaybackTimeChange={onPlaybackTimeChange} />);
    rerender(<PreviewStage {...current} playbackSec={1} onPlaybackTimeChange={onPlaybackTimeChange} />);
    rerender(<PreviewStage {...current} playbackSec={2.5} onPlaybackTimeChange={onPlaybackTimeChange} />);
    expect(writes).toEqual([1, 2.5]);
  });
  it("편집 뒤 재생기가 사라지는 동안 바뀌기 전 마지막 장면을 그림으로 남기고, 새 미리보기가 오면 버린다", () => {
    const video = (width: number) => Object.defineProperty(HTMLVideoElement.prototype, "videoWidth", { configurable: true, get: () => width });
    video(1280);
    Object.defineProperty(HTMLVideoElement.prototype, "videoHeight", { configurable: true, get: () => 720 });
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({ drawImage: vi.fn() } as unknown as CanvasRenderingContext2D);
    vi.spyOn(HTMLCanvasElement.prototype, "toDataURL").mockReturnValue("data:image/jpeg;base64,STILL");
    const { container, rerender } = render(<PreviewStage {...current} />);
    fireEvent.pause(screen.getByLabelText("편집본 미리보기"));

    rerender(<PreviewStage {...current} exactPreview={{ status: "running" }} />);
    const still = container.querySelector("img.vb-preview-stage__still");
    expect(still).not.toBeNull();
    expect(still).toHaveAttribute("src", "data:image/jpeg;base64,STILL");
    expect(screen.getByText("새 미리보기를 만드는 중이에요 · 바뀌기 전 화면")).toBeVisible();

    rerender(<PreviewStage {...current} />);
    expect(container.querySelector("img.vb-preview-stage__still")).toBeNull();
    delete (HTMLVideoElement.prototype as unknown as Record<string, unknown>).videoWidth;
    delete (HTMLVideoElement.prototype as unknown as Record<string, unknown>).videoHeight;
  });

  it("편집본 영상은 미리 받아 둔다(preload=auto) -- metadata면 탐색마다 범위 요청이 7~8개로 쪼개져 탐색 p95가 0.7~8.5초였다(2026-10-09 실측)", () => {
    render(<PreviewStage {...current} />);
    expect((screen.getByLabelText("편집본 미리보기") as HTMLVideoElement).getAttribute("preload")).toBe("auto");
  });
  it("mounts a single exact video with burned-caption guidance and no duplicate visual caption", () => {
    const { container } = render(<PreviewStage {...current} />);
    expect(screen.getByLabelText("편집본 미리보기")).toHaveAttribute("src", "/api/exact.mp4");
    expect(screen.getByLabelText("편집본 미리보기")).not.toHaveAttribute("autoplay");
    expect(container.querySelectorAll("video, audio")).toHaveLength(1);
    expect(screen.getByText(/캡션도 함께 재생돼요/)).toBeInTheDocument();
    expect(container.querySelector(".vb-preview-stage__caption-overlay")).toBeNull();
  });

  it("shows the total length next to the playback position when the caller knows it", () => {
    // `capcut-observed` 기록 §2: "아래 00:00:00:00 / 00:10:00:00" -- 재생
    // 위치 옆에 전체 길이가 붙는다. 프레임 단위 타임코드까지는 만들지 않고,
    // 이 화면이 이미 쓰는 초 단위 표기에 전체 길이만 더한다.
    const { container } = render(<PreviewStage {...current} durationSec={20} />);
    const output = container.querySelector(".vb-preview-stage__playback output");
    expect(output).toHaveTextContent("타임라인 0.0 / 20.0초");
  });

  it("falls back to just the playback position when the total length is unknown", () => {
    const { container } = render(<PreviewStage {...current} />);
    const output = container.querySelector(".vb-preview-stage__playback output");
    expect(output).toHaveTextContent("타임라인 0.0초");
    expect(output).not.toHaveTextContent("/");
  });

  it("puts the burned-caption note and the timeline status in one row, not two", () => {
    // These were two separate <p> elements (16px + status row); merged into
    // one so the stage recovers a line of vertical space.
    const { container } = render(<PreviewStage {...current} />);
    expect(container.querySelector(".vb-preview-stage__burned-caption")).toBeNull();
    const status = container.querySelector(".vb-preview-stage__status");
    expect(status).not.toBeNull();
    expect(status).toHaveTextContent("캡션도 함께 재생돼요");
    expect(status).toHaveTextContent("타임라인 0.0초");
  });

  it("announces the active burned caption from the actual player time without rendering a second visual caption", () => {
    const { container } = render(<PreviewStage {...current} />);
    const media = screen.getByLabelText("편집본 미리보기") as HTMLVideoElement;
    expect(screen.getByRole("status", { name: "현재 캡션" })).toHaveTextContent("첫 번째 안내 자막");
    Object.defineProperty(media, "currentTime", { configurable: true, writable: true, value: 3.5 });
    fireEvent.timeUpdate(media);
    expect(screen.getByRole("status", { name: "현재 캡션" })).toHaveTextContent("두 번째 안내 자막");
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
    expect(screen.getByLabelText("B-roll A 원본 재생")).toHaveAttribute("src", "/api/assets/a/content");
    expect(screen.getByLabelText("B-roll A 원본 재생")).not.toHaveAttribute("autoplay");
    expect(screen.getByText("원본 미리보기")).toBeInTheDocument();
    expect(container.querySelectorAll("video, audio")).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "편집본으로 돌아가기" }));
    expect(screen.getByLabelText("편집본 미리보기")).toBeInTheDocument();
  });

  it("guides a browser-incompatible source back to the exact edited preview", () => {
    const { rerender } = render(<PreviewStage {...current} />);
    rerender(<PreviewStage {...current} auditionRequest={{ requestId: 1, source: current.sources[0] }} />);
    const audition = screen.getByLabelText("B-roll A 원본 재생") as HTMLVideoElement;
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
    const audition = screen.getByLabelText("B-roll A 원본 재생") as HTMLVideoElement;
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

    expect(screen.getByLabelText("제품 사진 원본 재생")).toBeInTheDocument();
    expect(container.querySelectorAll("audio, video")).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "편집본으로 돌아가기" }));
    rerender(<PreviewStage {...current} auditionRequest={{ requestId: 2, source: { id: "broll:image-1", label: "제품 사진", url: "/api/projects/project-a/assets/image-1/content", mediaKind: "video", timelineRange: { startSec: 3, endSec: 7 } } }} />);
    expect(screen.getByLabelText("제품 사진 원본 재생")).toBeInTheDocument();
    expect(container.querySelectorAll("audio, video")).toHaveLength(1);
  });

  it("switches from a playable audition to one non-playable image surface without retaining media", () => {
    const { container, rerender } = render(<PreviewStage {...current} auditionRequest={{ requestId: 1, source: { id: "audio-1", label: "현장 오디오", url: "/api/projects/project-a/assets/audio-1/content", mediaKind: "audio", timelineRange: { startSec: 3, endSec: 7 } } }} />);
    expect(screen.getByLabelText("현장 오디오 원본 재생").tagName).toBe("AUDIO");
    expect(container.querySelectorAll("audio, video")).toHaveLength(1);

    rerender(<PreviewStage {...current} auditionRequest={{ requestId: 2, source: { id: "image-1", label: "제품 사진", url: "/api/projects/project-a/assets/image-1/content", mediaKind: "image", timelineRange: { startSec: 3, endSec: 7 } } }} />);
    expect(screen.getByLabelText("제품 사진 원본 재생").tagName).toBe("IMG");
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

  it("styles the elsewhere hint -- a class with no CSS is a promise the screen never kept", () => {
    // `vb-preview-stage__elsewhere`는 재생 위치가 미리보기 밖일 때 그 사실을
    // 알리는 안내문이다. 대응 CSS가 없어 기본 문단으로 굴러다녔다.
    const css = readFileSync(resolve(process.cwd(), "src/styles/editor-workbench.css"), "utf8");
    const elsewhereRule = css.match(/\.vb-preview-stage__elsewhere\s*\{([^}]*)\}/)?.[1] ?? "";

    expect(elsewhereRule).toContain("color: var(--muted-foreground)");
    expect(elsewhereRule).toContain("font-size: var(--vb-text-xs)");
    // 전체화면은 어두운 배경이라 밝은 글자로 바꿔야 읽힌다 -- status와 같은 규칙.
    expect(css).toMatch(/\.vb-preview-stage:fullscreen[^{]*\.vb-preview-stage__elsewhere/);
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

  it("plays and pauses from the space bar anywhere, not only inside the preview", () => {
    // 캡컷은 어디서나 스페이스다. 우리는 미리보기 판을 클릭해 둔 상태에서만
    // 들었고, 타임라인을 만지다 스페이스를 누르면 아무 일도 없었다 -- 편집 중에
    // 가장 자주 누르는 키가 자리를 타면 안 쓰게 된다.
    render(<PreviewStage {...current} />);
    const media = screen.getByLabelText("편집본 미리보기") as HTMLVideoElement;
    const play = vi.spyOn(media, "play").mockResolvedValue(undefined);
    Object.defineProperty(media, "paused", { configurable: true, value: true });

    fireEvent.keyDown(document.body, { key: " " });

    expect(play).toHaveBeenCalledTimes(1);
  });

  it("pauses in place instead of jumping the playhead back to zero (owner report, 2026-09-01)", () => {
    // 스페이스로 멈출 때 `stopActiveMedia`(소스 전환용 함수)를 재사용했더니
    // 재생 위치가 0초로 튀는 실사용 버그가 있었다 -- 여기서는 순수 pause만
    // 부르고 위치를 안 건드리는지 확인한다.
    render(<PreviewStage {...current} />);
    const media = screen.getByLabelText("편집본 미리보기") as HTMLVideoElement;
    const pause = vi.spyOn(media, "pause").mockImplementation(() => undefined);
    Object.defineProperty(media, "paused", { configurable: true, value: false });
    Object.defineProperty(media, "currentTime", { configurable: true, writable: true, value: 7.5 });

    fireEvent.keyDown(document.body, { key: " " });

    expect(pause).toHaveBeenCalledTimes(1);
    expect(media.currentTime).toBe(7.5);
  });

  it("still plays when the space bar is pressed on a timeline clip (owner report)", () => {
    // owner: "타임라인에서 스페이스바를 누르면 멈춰야 되는데, 그것도 안되고".
    // 장면 칸이 `<button>`이라 아래의 "단추 위에서는 가로채지 않는다" 규칙에
    // 그대로 걸렸다 -- 장면을 한 번 고르면(포커스가 그 단추에 남는다) 스페이스가
    // 영영 안 먹는다. 편집기 타임라인에서 스페이스는 재생/정지가 업계 표준이고
    // 캡컷도 그렇다. 그래서 타임라인 면만 예외로 둔다.
    render(<PreviewStage {...current} />);
    const media = screen.getByLabelText("편집본 미리보기") as HTMLVideoElement;
    const play = vi.spyOn(media, "play").mockResolvedValue(undefined);
    Object.defineProperty(media, "paused", { configurable: true, value: true });

    const timeline = document.createElement("section");
    timeline.setAttribute("data-timeline-surface", "true");
    const clip = document.createElement("button");
    timeline.append(clip);
    document.body.append(timeline);
    fireEvent.keyDown(clip, { key: " " });

    expect(play).toHaveBeenCalledTimes(1);
    timeline.remove();
  });

  it("still respects a text field that happens to sit inside the timeline", () => {
    // 타임라인 예외가 입력칸까지 삼키면 이름을 못 고친다.
    render(<PreviewStage {...current} />);
    const media = screen.getByLabelText("편집본 미리보기") as HTMLVideoElement;
    const play = vi.spyOn(media, "play").mockResolvedValue(undefined);
    Object.defineProperty(media, "paused", { configurable: true, value: true });

    const timeline = document.createElement("section");
    timeline.setAttribute("data-timeline-surface", "true");
    const field = document.createElement("input");
    timeline.append(field);
    document.body.append(timeline);
    fireEvent.keyDown(field, { key: " " });

    expect(play).not.toHaveBeenCalled();
    timeline.remove();
  });

  it("leaves the space bar alone while the creator is typing or on a control", () => {
    // 글을 쓰다 스페이스를 누르면 띄어쓰기여야 한다. 단추 위에서는 그 단추를
    // 누르는 것이고 -- 여기서 가로채면 접근성이 깨진다.
    render(<PreviewStage {...current} />);
    const media = screen.getByLabelText("편집본 미리보기") as HTMLVideoElement;
    const play = vi.spyOn(media, "play").mockResolvedValue(undefined);
    Object.defineProperty(media, "paused", { configurable: true, value: true });

    const field = document.createElement("textarea");
    document.body.append(field);
    fireEvent.keyDown(field, { key: " " });
    fireEvent.keyDown(screen.getByRole("button", { name: "다음 프레임" }), { key: " " });

    expect(play).not.toHaveBeenCalled();
    field.remove();
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
    const audition = screen.getByLabelText("B-roll A 원본 재생") as HTMLVideoElement;
    const play = vi.spyOn(audition, "play").mockResolvedValue(undefined);
    const returnButton = screen.getByRole("button", { name: "편집본으로 돌아가기" });
    expect(fireEvent.keyDown(returnButton, { key: "Enter" })).toBe(true);
    expect(play).not.toHaveBeenCalled();
    fireEvent.click(returnButton);
    expect(rendered.container.querySelectorAll("video, audio")).toHaveLength(1);
    expect(screen.getAllByLabelText("편집본 미리보기")).toHaveLength(1);
  });

  it("maps media time to timeline time, supports keyboard play/pause, keeps playing in place when focus or the page moves, and stops on unmount", () => {
    const { unmount } = render(<PreviewStage {...current} />);
    const media = screen.getByLabelText("편집본 미리보기") as HTMLVideoElement;
    const pause = vi.spyOn(media, "pause").mockImplementation(() => undefined);
    Object.defineProperty(media, "currentTime", { configurable: true, writable: true, value: 2.5 });
    Object.defineProperty(media, "paused", { configurable: true, value: false });
    fireEvent.timeUpdate(media);
    expect(screen.getAllByRole("status").find((node) => node.classList.contains("vb-preview-stage__status"))).toHaveTextContent("타임라인 2.5초");
    fireEvent.keyDown(screen.getByRole("region", { name: "미리보기" }), { key: " " });
    expect(pause).toHaveBeenCalledTimes(1);
    // 행동 변경(2026-10-09 실측: 재생 중 타임라인 제목 클릭 -> 2.2초 -> 0초·정지):
    // 초점이 밖으로 가거나 창이 굴러도 재생은 제자리에서 이어진다.
    fireEvent.blur(screen.getByRole("region", { name: "미리보기" }));
    fireEvent.scroll(window);
    expect(pause).toHaveBeenCalledTimes(1);
    expect(media.currentTime).toBe(2.5);
    unmount();
    expect(pause.mock.calls.length).toBeGreaterThan(1);
  });

  it("미리보기 판(영상 그림을 누른 뒤)에서 스페이스를 누르면 한 번만 재생된다(2026-10-09 실측: 둘이 상쇄)", () => {
    render(<PreviewStage {...current} />);
    const media = screen.getByLabelText("편집본 미리보기") as HTMLVideoElement;
    const play = vi.spyOn(media, "play").mockResolvedValue(undefined);
    let paused = true;
    Object.defineProperty(media, "paused", { configurable: true, get: () => paused });
    play.mockImplementation(async () => { paused = false; });
    const stage = screen.getByRole("region", { name: "미리보기" });
    stage.focus();
    fireEvent.keyDown(stage, { key: " " });
    expect(play).toHaveBeenCalledTimes(1);
    expect(paused).toBe(false);
    expect(HTMLMediaElement.prototype.pause).not.toHaveBeenCalled();
  });

  describe("재생 시계(2026-10-09 계획 P Task 2)", () => {
    // rAF를 직접 잡아 부른다 -- 고리가 멈추면 예약된 콜백이 남지 않아야 한다.
    const pending = new Map<number, FrameRequestCallback>();
    let nextId = 1;
    beforeEach(() => {
      pending.clear(); nextId = 1;
      vi.spyOn(window, "requestAnimationFrame").mockImplementation((callback) => { const id = nextId++; pending.set(id, callback); return id; });
      vi.spyOn(window, "cancelAnimationFrame").mockImplementation((id) => { pending.delete(id); });
    });
    const runFrame = () => { const entries = [...pending.entries()]; pending.clear(); for (const [, callback] of entries) callback(0); };
    const playerAt = (seconds: number, state: { paused?: boolean; seeking?: boolean; ended?: boolean } = {}) => {
      const clock = createPlaybackClock();
      const view = render(<PreviewStage {...current} playbackClock={clock} playbackSec={0} durationSec={12} />);
      const media = screen.getByLabelText("편집본 미리보기") as HTMLVideoElement;
      const flags = { paused: false, seeking: false, ended: false, time: seconds, ...state };
      Object.defineProperty(media, "currentTime", { configurable: true, get: () => flags.time, set: (value: number) => { flags.time = value; } });
      Object.defineProperty(media, "paused", { configurable: true, get: () => flags.paused });
      Object.defineProperty(media, "seeking", { configurable: true, get: () => flags.seeking });
      Object.defineProperty(media, "ended", { configurable: true, get: () => flags.ended });
      return { clock, media, flags, ...view };
    };
    it("재생이 시작되면 화면 프레임마다 재생기 시각을 시계에 알린다", () => {
      const { clock, media, flags } = playerAt(3.2);
      fireEvent.play(media);
      runFrame();
      expect(clock.read()).toEqual({ seconds: 3.2, playing: true });
      flags.time = 3.25;
      runFrame();
      expect(clock.read()).toEqual({ seconds: 3.25, playing: true });
      expect(pending.size).toBe(1);
    });
    it("일시정지하면 멈춘 시각을 알리고 프레임 고리를 멈춘다", () => {
      const { clock, media, flags } = playerAt(3.2);
      fireEvent.play(media);
      runFrame();
      flags.paused = true; flags.time = 3.3;
      fireEvent.pause(media);
      expect(clock.read()).toEqual({ seconds: 3.3, playing: false });
      expect(pending.size).toBe(0);
    });
    it("끝까지 가면 고리를 멈춘다", () => {
      const { clock, media, flags } = playerAt(11.9);
      fireEvent.play(media);
      runFrame();
      flags.paused = true; flags.ended = true; flags.time = 12;
      fireEvent.ended(media);
      expect(clock.read()).toEqual({ seconds: 12, playing: false });
      expect(pending.size).toBe(0);
    });
    it("옮기는 중(seeking)에는 시계를 건드리지 않는다", () => {
      const { clock, media, flags } = playerAt(3.2);
      fireEvent.play(media);
      runFrame();
      flags.seeking = true; flags.time = 9;
      runFrame();
      expect(clock.read().seconds).toBe(3.2);
      expect(pending.size).toBe(1);
    });
    it("재생 중에 옮김이 끝나면(seeked) 새 자리를 알리고 고리는 계속 돈다", () => {
      const { clock, media, flags } = playerAt(3.2);
      fireEvent.play(media);
      runFrame();
      flags.time = 9;
      fireEvent.seeked(media);
      expect(clock.read()).toEqual({ seconds: 9, playing: true });
      expect(pending.size).toBe(1);
    });
    it("재생 중에 사라지면 프레임 예약을 거두고 멈춤으로 알린다", () => {
      const { clock, media, unmount } = playerAt(3.2);
      fireEvent.play(media);
      runFrame();
      expect(pending.size).toBe(1);
      unmount();
      expect(pending.size).toBe(0);
      expect(clock.read().playing).toBe(false);
    });
    it("재생 중이 아니면 프레임을 예약하지 않는다", () => {
      const { media } = playerAt(3.2, { paused: true });
      fireEvent.pause(media);
      fireEvent.seeked(media);
      expect(pending.size).toBe(0);
    });
    it("시계가 시각을 알리면 시간 글자만 직접 고친다(React 상태 없이)", () => {
      const { clock } = playerAt(0);
      const output = () => document.querySelector(".vb-preview-stage__playback output") as HTMLElement;
      expect(output().textContent).toBe("타임라인 0.0 / 12.0초");
      clock.publish(4.26, true);
      expect(output().textContent).toBe("타임라인 4.3 / 12.0초");
      expect(output().getAttribute("aria-live")).toBe("off");
    });
    it("시계 없이도 시간 글자는 예전과 같다", () => {
      render(<PreviewStage {...current} durationSec={12} playbackSec={2} />);
      expect(document.querySelector(".vb-preview-stage__playback output")?.textContent).toBe("타임라인 2.0 / 12.0초");
    });
  });
});

describe("재생 빠르기와 J·K·L·화살표 (2026-10-09 계획 P Task 4)", () => {
  beforeEach(() => { try { window.localStorage.removeItem(PLAYBACK_RATE_STORAGE_KEY); window.localStorage.removeItem(PLAYBACK_RATE_HINT_STORAGE_KEY); } catch { /* ignore */ } });
  const player = (props: Partial<React.ComponentProps<typeof PreviewStage>> = {}, state: { paused: boolean; time?: number } = { paused: true }) => {
    const view = render(<PreviewStage {...current} fps={{ num: 30, den: 1 }} {...props} />);
    const media = screen.getByLabelText("편집본 미리보기") as HTMLVideoElement;
    const flags = { paused: state.paused, time: state.time ?? 0 };
    Object.defineProperty(media, "paused", { configurable: true, get: () => flags.paused });
    Object.defineProperty(media, "currentTime", { configurable: true, get: () => flags.time, set: (value: number) => { flags.time = value; } });
    const play = vi.spyOn(media, "play").mockImplementation(async () => { flags.paused = false; });
    const pause = vi.spyOn(media, "pause").mockImplementation(() => { flags.paused = true; });
    return { media, flags, play, pause, ...view };
  };
  const select = () => screen.getByLabelText("재생 빠르기") as HTMLSelectElement;
  const press = (key: string, init: KeyboardEventInit = {}) => fireEvent.keyDown(document.body, { key, ...init });

  it("처음에는 1배이고 재생기도 1배다", () => {
    const { media } = player();
    expect(select().value).toBe("1");
    expect(media.playbackRate).toBe(1);
    expect(select().tagName).toBe("SELECT");
    expect([...select().options].map((option) => option.textContent)).toEqual(["0.25배", "0.5배", "0.75배", "1배", "1.5배", "2배", "3배", "4배", "6배", "8배"]);
  });
  it("0.5를 고르면 재생기에 바로 걸고 기억한다", () => {
    const { media } = player();
    fireEvent.change(select(), { target: { value: "0.5" } });
    expect(media.playbackRate).toBe(0.5);
    expect(media.defaultPlaybackRate).toBe(0.5);
    expect(window.localStorage.getItem(PLAYBACK_RATE_STORAGE_KEY)).toBe("0.5");
  });
  it("저장된 0.75가 있으면 처음부터 0.75다", () => {
    window.localStorage.setItem(PLAYBACK_RATE_STORAGE_KEY, "0.75");
    const { media } = player();
    expect(select().value).toBe("0.75");
    fireEvent.loadedMetadata(media);
    expect(media.playbackRate).toBe(0.75);
  });
  it("새 소스가 열려도 같은 빠르기를 다시 건다(소스가 바뀌면 재생기가 1배로 돌아간다)", () => {
    const { media, rerender } = player();
    fireEvent.change(select(), { target: { value: "0.5" } });
    rerender(<PreviewStage {...current} fps={{ num: 30, den: 1 }} exactPreview={{ ...current.exactPreview, url: "/api/exact-2.mp4" }} />);
    const next = screen.getByLabelText("편집본 미리보기") as HTMLVideoElement;
    fireEvent.loadedMetadata(next);
    expect(next.playbackRate).toBe(0.5);
    expect(media.defaultPlaybackRate).toBe(0.5);
  });
  it("원본 보기(audition)로 바꿔도 같은 빠르기가 걸린다", () => {
    const { rerender } = player();
    fireEvent.change(select(), { target: { value: "2" } });
    rerender(<PreviewStage {...current} fps={{ num: 30, den: 1 }} auditionRequest={{ requestId: 1, source: { ...current.sources[0], label: "B-roll A" } }} />);
    const audition = screen.getByLabelText("B-roll A 원본 재생") as HTMLVideoElement;
    fireEvent.loadedMetadata(audition);
    expect(audition.playbackRate).toBe(2);
  });
  it("소리 원본(새 <audio> 요소)으로 바꿔도 같은 빠르기가 걸린다", () => {
    const { rerender } = player();
    fireEvent.change(select(), { target: { value: "0.5" } });
    rerender(<PreviewStage {...current} fps={{ num: 30, den: 1 }} auditionRequest={{ requestId: 2, source: { id: "song", label: "배경 음악", url: "/api/assets/song/content", mediaKind: "audio", timelineRange: { startSec: 0, endSec: 5 } } }} />);
    const audio = screen.getByLabelText("배경 음악 원본 재생") as HTMLAudioElement;
    expect(audio.tagName).toBe("AUDIO");
    expect(audio.playbackRate).toBe(0.5);
    fireEvent.loadedMetadata(audio);
    expect(audio.playbackRate).toBe(0.5);
  });
  it("재생기가 스스로 빠르기를 바꾸면(ratechange) 고르기가 따라간다", () => {
    const { media } = player();
    act(() => { media.playbackRate = 1.5; });
    fireEvent.rateChange(media);
    expect(select().value).toBe("1.5");
  });
  it("재생 빠르기 고르기에서 스페이스는 재생을 건드리지 않는다", () => {
    const { play, pause } = player();
    fireEvent.keyDown(select(), { key: " " });
    expect(play).not.toHaveBeenCalled();
    expect(pause).not.toHaveBeenCalled();
  });
  it("재생 빠르기 고르기에서는 J·K·L도 건드리지 않는다(글자 찾기용)", () => {
    const { play } = player();
    fireEvent.keyDown(select(), { key: "l" });
    expect(play).not.toHaveBeenCalled();
    expect(select().value).toBe("1");
  });
  it("멈춘 상태에서 L은 지금 빠르기로 재생만 한다", () => {
    const { play } = player();
    press("l");
    expect(play).toHaveBeenCalledTimes(1);
    expect(select().value).toBe("1");
  });
  it("재생 중 L은 1.5 -> 2 -> 3 -> 4 -> 6 -> 8 -> 8", () => {
    const { media } = player({}, { paused: false });
    press("l"); expect(media.playbackRate).toBe(1.5); expect(select().value).toBe("1.5");
    const seen: number[] = [];
    for (let i = 0; i < 6; i += 1) { press("l"); seen.push(media.playbackRate); }
    expect(seen).toEqual([2, 3, 4, 6, 8, 8]);
    expect(select().value).toBe("8");
  });
  it("8배에서 J는 6 -> 4 -> 3 -> 2로 내려온다", () => {
    window.localStorage.setItem(PLAYBACK_RATE_STORAGE_KEY, "8");
    const { media } = player({}, { paused: false });
    const seen: number[] = [];
    for (let i = 0; i < 4; i += 1) { press("j"); seen.push(media.playbackRate); }
    expect(seen).toEqual([6, 4, 3, 2]);
  });
  it("4배로 바꾼 뒤 새 소스가 열려도 4배를 다시 건다", () => {
    const { media, rerender } = player();
    fireEvent.change(select(), { target: { value: "4" } });
    expect(media.playbackRate).toBe(4);
    rerender(<PreviewStage {...current} fps={{ num: 30, den: 1 }} exactPreview={{ ...current.exactPreview, url: "/api/exact-3.mp4" }} />);
    const next = screen.getByLabelText("편집본 미리보기") as HTMLVideoElement;
    fireEvent.loadedMetadata(next);
    expect(next.playbackRate).toBe(4);
  });
  describe("L 키 첫 사용 안내", () => {
    const HINT = "빠르게 보려면 L 키를 눌러요";
    it("저장소가 비었고 1배이면 재생줄에 뜬다(소리 알림은 없다)", () => {
      player();
      const hint = screen.getByText(HINT);
      expect(hint.getAttribute("aria-live")).toBeNull();
    });
    it("재생 중 L로 올리면 사라지고 기억한다", () => {
      player({}, { paused: false });
      press("l");
      expect(screen.queryByText(HINT)).toBeNull();
      expect(window.localStorage.getItem(PLAYBACK_RATE_HINT_STORAGE_KEY)).toBe("1");
    });
    it("고르기에서 바꿔도 사라지고 기억한다", () => {
      player();
      fireEvent.change(select(), { target: { value: "2" } });
      expect(screen.queryByText(HINT)).toBeNull();
      expect(window.localStorage.getItem(PLAYBACK_RATE_HINT_STORAGE_KEY)).toBe("1");
    });
    it("다시 그려도, 1배로 돌아와도 다시 뜨지 않는다", () => {
      const { unmount } = player();
      fireEvent.change(select(), { target: { value: "2" } });
      fireEvent.change(select(), { target: { value: "1" } });
      expect(screen.queryByText(HINT)).toBeNull();
      unmount();
      player();
      expect(screen.queryByText(HINT)).toBeNull();
    });
    it("1배가 아니면 처음부터 안 뜬다", () => {
      window.localStorage.setItem(PLAYBACK_RATE_STORAGE_KEY, "2");
      player();
      expect(screen.queryByText(HINT)).toBeNull();
    });
  });
  it("재생 중 J는 한 단계씩 느리게(2에서 시작: 1.5 -> 1 -> 0.75 -> 0.5)", () => {
    window.localStorage.setItem(PLAYBACK_RATE_STORAGE_KEY, "2");
    const { media } = player({}, { paused: false });
    const seen: number[] = [];
    for (let i = 0; i < 4; i += 1) { press("j"); seen.push(media.playbackRate); }
    expect(seen).toEqual([1.5, 1, 0.75, 0.5]);
  });
  it("멈춘 상태에서 J는 한 단계 느리게 하고 재생한다", () => {
    const { media, play } = player();
    press("j");
    expect(media.playbackRate).toBe(0.75);
    expect(play).toHaveBeenCalledTimes(1);
  });
  it("K는 빠르기를 그대로 두고 멈춘다", () => {
    window.localStorage.setItem(PLAYBACK_RATE_STORAGE_KEY, "1.5");
    const { pause, media } = player({}, { paused: false });
    press("k");
    expect(pause).toHaveBeenCalledTimes(1);
    expect(media.currentTime).toBe(0);
    expect(select().value).toBe("1.5");
  });
  it("오른쪽 화살표는 멈추고 한 프레임 앞, 왼쪽은 한 프레임 뒤", () => {
    const { pause, flags } = player({}, { paused: false, time: 2 });
    press("ArrowRight");
    expect(pause).toHaveBeenCalledTimes(1);
    expect(flags.time).toBeCloseTo(2 + 1 / 30, 5);
    press("ArrowLeft");
    expect(flags.time).toBeCloseTo(2, 5);
  });
  it("타임라인 면 안의 화살표는 미리보기가 받지 않는다(타임라인이 받는다)", () => {
    const { flags } = player({}, { paused: true, time: 2 });
    const surface = document.createElement("div");
    surface.setAttribute("data-timeline-surface", "true");
    const clip = document.createElement("button");
    surface.appendChild(clip); document.body.appendChild(surface);
    fireEvent.keyDown(clip, { key: "ArrowRight" });
    expect(flags.time).toBe(2);
    surface.remove();
  });
  it("화살표를 쓰는 슬라이더 위에서는 한 프레임 이동을 가로채지 않는다", () => {
    const { flags } = player({}, { paused: true, time: 2 });
    const slider = document.createElement("div");
    slider.setAttribute("role", "slider"); document.body.appendChild(slider);
    fireEvent.keyDown(slider, { key: "ArrowRight" });
    expect(flags.time).toBe(2);
    slider.remove();
  });
  it("글쓰는 중에는 L이 글자 그대로다", () => {
    const { play } = player();
    const field = document.createElement("input"); document.body.appendChild(field);
    fireEvent.keyDown(field, { key: "l" });
    expect(play).not.toHaveBeenCalled();
    field.remove();
  });
});

describe("재생줄의 단축키 안내 (2026-10-09 계획 P Task 5)", () => {
  beforeEach(() => { try { window.localStorage.removeItem(PLAYBACK_RATE_STORAGE_KEY); } catch { /* ignore */ } });
  const shortcutButton = () => screen.getByRole("button", { name: "단축키" });
  const note = () => screen.queryByRole("note", { name: "편집 단축키" });
  const withPlayer = () => {
    const view = render(<PreviewStage {...current} fps={{ num: 30, den: 1 }} />);
    const media = screen.getByLabelText("편집본 미리보기") as HTMLVideoElement;
    const flags = { paused: true, time: 0 };
    Object.defineProperty(media, "paused", { configurable: true, get: () => flags.paused });
    Object.defineProperty(media, "currentTime", { configurable: true, get: () => flags.time, set: (value: number) => { flags.time = value; } });
    const play = vi.spyOn(media, "play").mockImplementation(async () => { flags.paused = false; });
    return { ...view, media, play };
  };

  it("단축키 단추를 누르면 안내가 열리고 다시 누르면 닫힌다", () => {
    render(<PreviewStage {...current} />);
    expect(note()).toBeNull();
    expect(shortcutButton().getAttribute("aria-expanded")).toBe("false");
    expect(shortcutButton().getAttribute("aria-controls")).toBe("vb-playback-shortcuts");
    fireEvent.click(shortcutButton());
    const opened = note() as HTMLElement;
    expect(opened.id).toBe("vb-playback-shortcuts");
    for (const text of ["스페이스바", "J 키", "K 키", "L 키", "보는 속도"]) expect(opened.textContent).toContain(text);
    expect(opened.getAttribute("aria-label")).toBe("편집 단축키");
    expect(shortcutButton().getAttribute("aria-expanded")).toBe("true");
    fireEvent.click(shortcutButton());
    expect(note()).toBeNull();
    expect(shortcutButton().getAttribute("aria-expanded")).toBe("false");
  });
  it("Esc나 바깥을 누르면 닫히고, 안내 안을 누르면 그대로다", () => {
    render(<PreviewStage {...current} />);
    fireEvent.click(shortcutButton());
    fireEvent.pointerDown(note() as HTMLElement);
    expect(note()).not.toBeNull();
    fireEvent.keyDown(document.body, { key: "Escape" });
    expect(note()).toBeNull();
    fireEvent.click(shortcutButton());
    fireEvent.pointerDown(document.body);
    expect(note()).toBeNull();
  });
  it("안내를 열어 둬도 스페이스는 재생을 바꾼다(대화 상자가 아니다)", () => {
    const { play } = withPlayer();
    fireEvent.click(shortcutButton());
    expect(screen.queryByRole("dialog")).toBeNull();
    fireEvent.keyDown(document.body, { key: " " });
    expect(play).toHaveBeenCalledTimes(1);
  });
  it("단추에 키가 title로 붙는다(aria-label은 그대로)", () => {
    render(<PreviewStage {...current} />);
    expect(screen.getByRole("button", { name: "재생 또는 일시정지" }).getAttribute("title")).toBe("스페이스바");
    expect(screen.getByRole("button", { name: "이전 프레임" }).getAttribute("title")).toBe("← 키");
    expect(screen.getByRole("button", { name: "다음 프레임" }).getAttribute("title")).toBe("→ 키");
  });
  it("안내에 적힌 키는 전부 실제로 재생기를 움직인다(적고 안 되는 키가 없다)", () => {
    render(<PreviewStage {...current} />);
    fireEvent.click(shortcutButton());
    const text = (note() as HTMLElement).textContent ?? "";
    const listed: Array<[label: string, key: string, command: string]> = [
      ["스페이스바", " ", "toggle"], ["K 키", "k", "pause"], ["L 키", "l", "faster"], ["J 키", "j", "slower"], ["←", "ArrowLeft", "step"], ["→", "ArrowRight", "step"],
    ];
    for (const [label, key, command] of listed) {
      expect(text).toContain(label);
      const result = playbackShortcutFor({ key, ctrlKey: false, metaKey: false, altKey: false, shiftKey: false, repeat: false, isComposing: false, defaultPrevented: false, target: document.body });
      expect(result?.type).toBe(command);
    }
    // 안내에 재생기 줄 여섯이 모두 있다(나머지 줄은 아래 "표에서 그린다" 시험이 맡는다).
    expect(listed.length).toBe(EDITOR_SHORTCUTS.filter((row) => row.owner === "preview").length);
  });

  describe("안내는 단축키 표에서 그린다", () => {
    const open = () => { render(<PreviewStage {...current} />); fireEvent.click(shortcutButton()); return note() as HTMLElement; };
    const lineOf = (root: HTMLElement, keys: string) => Array.from(root.querySelectorAll("li")).find((li) => (li.textContent ?? "").startsWith(keys)) as HTMLElement;
    it("표의 모든 줄이 키와 이름 그대로 나온다(손으로 적은 목록이면 갈라질 때 걸린다)", () => {
      const root = open();
      expect(root.querySelectorAll("li").length).toBe(EDITOR_SHORTCUTS.length);
      for (const row of EDITOR_SHORTCUTS) {
        const text = root.textContent ?? "";
        expect(text).toContain(row.keys);
        expect(text).toContain(row.label);
        if (row.note) expect(text).toContain(row.note);
        const line = lineOf(root, row.keys);
        expect(line.textContent).toContain(row.capcut === "same" ? "캡컷과 같아요" : "캡컷과 달라요");
        expect(line.textContent).not.toContain(row.capcut === "same" ? "캡컷과 달라요" : "캡컷과 같아요");
      }
    });
    it("묶음 이름이 재생·이동·자르기·되돌리기·타임라인 보기 순이다", () => {
      const root = open();
      const heads = Array.from(root.querySelectorAll("h3")).map((h) => h.textContent);
      expect(heads).toEqual(["재생", "이동", "자르기", "되돌리기", "타임라인 보기"]);
    });
    it("Q 키는 캡컷과 같고 J 키는 캡컷과 달라서 이유가 붙는다", () => {
      const root = open();
      expect(lineOf(root, "Q 키").textContent).toContain("캡컷과 같아요");
      const j = lineOf(root, "J 키").textContent ?? "";
      expect(j).toContain("캡컷과 달라요");
      expect(j).toContain("거꾸로");
    });
    it("맨 아래에 보는 속도·빈자리 안내와, 캡컷 공식 목록이 아니라는 솔직한 말이 있다", () => {
      const text = open().textContent ?? "";
      expect(text).toContain("빠르기는 보는 속도예요. 영상은 바뀌지 않아요.");
      expect(text).toContain("빈자리는 그대로 둬요. 되돌리기로 원래대로 돌아와요.");
      expect(text).toContain("캡컷 공식 목록이 아니라 여러 사용자 목록으로 맞춘 키예요");
    });
  });
});
