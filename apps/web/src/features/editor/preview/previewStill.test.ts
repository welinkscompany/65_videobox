import { afterEach, describe, expect, it, vi } from "vitest";

import { capturePreviewStill } from "./previewStill";

function fakeVideo(width: number, height: number): HTMLVideoElement {
  const video = document.createElement("video");
  Object.defineProperty(video, "videoWidth", { value: width });
  Object.defineProperty(video, "videoHeight", { value: height });
  return video;
}

describe("capturePreviewStill", () => {
  afterEach(() => vi.restoreAllMocks());

  it("jsdom처럼 그릴 수 없으면 null을 돌려준다", () => {
    expect(capturePreviewStill(fakeVideo(1920, 1080))).toBeNull();
  });

  it("영상 크기를 모르면(아직 안 열림) null", () => {
    expect(capturePreviewStill(document.createElement("video"))).toBeNull();
  });

  it("그릴 수 있으면 960폭 이하 jpeg 데이터 주소를 돌려준다", () => {
    const drawImage = vi.fn();
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({ drawImage } as unknown as CanvasRenderingContext2D);
    const toDataURL = vi.spyOn(HTMLCanvasElement.prototype, "toDataURL").mockReturnValue("data:image/jpeg;base64,AAAA");
    const still = capturePreviewStill(fakeVideo(1920, 1080));
    expect(still?.startsWith("data:image/jpeg")).toBe(true);
    expect(drawImage).toHaveBeenCalledWith(expect.anything(), 0, 0, 960, 540);
    expect(toDataURL).toHaveBeenCalledWith("image/jpeg", 0.7);
  });

  it("그리다 예외가 나도(오염된 캔버스) 던지지 않고 null", () => {
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({ drawImage: vi.fn() } as unknown as CanvasRenderingContext2D);
    vi.spyOn(HTMLCanvasElement.prototype, "toDataURL").mockImplementation(() => { throw new Error("SecurityError"); });
    expect(capturePreviewStill(fakeVideo(640, 360))).toBeNull();
  });
});
