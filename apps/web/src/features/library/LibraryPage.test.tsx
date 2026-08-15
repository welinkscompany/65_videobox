import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { api, type LibraryAsset } from "../../api";
import { LibraryPage } from "./LibraryPage";

function asset(overrides: Partial<LibraryAsset> = {}): LibraryAsset {
  return {
    library_asset_id: "user_asset_1",
    media_type: "broll",
    origin: "user",
    lifecycle: "ready",
    content_sha256: "a".repeat(64),
    byte_count: 1200,
    mime_type: "video/mp4",
    managed_relative_path: "assets/a.mp4",
    technical_metadata: { duration_seconds: 12.5, width: 1920, height: 1080 },
    machine_metadata: { description: "도시를 걷는 장면" },
    user_metadata: { filename: "walk.mp4", tags: ["도시"] },
    created_at: "2026-08-12T00:00:00Z",
    updated_at: "2026-08-12T00:00:00Z",
    trashed_at: null,
    preview_url: "/api/library/assets/user_asset_1/preview",
    thumbnail_url: "/api/library/assets/user_asset_1/thumbnail",
    waveform_url: "/api/library/assets/user_asset_1/waveform",
    ...overrides,
  };
}

beforeEach(() => {
  vi.restoreAllMocks();
  vi.spyOn(api, "listLibraryAssets").mockResolvedValue({ assets: [asset()], total: 1 });
  vi.spyOn(api, "getLibraryAssetUsage").mockResolvedValue({ library_asset_id: "user_asset_1", locations: [] });
  vi.spyOn(api, "ingestLibraryAssets").mockResolvedValue({ ingest_batch_id: "batch_1", partial: false, items: [] });
});

describe("LibraryPage", () => {
  it("keeps the desktop library bounded to three panes and a center scroll region", async () => {
    render(<LibraryPage />);
    expect(screen.getByTestId("library-workspace")).toHaveAttribute("data-layout", "three-pane");
    expect(screen.getByTestId("library-sidebar")).toBeInTheDocument();
    expect(screen.getByTestId("library-results")).toBeInTheDocument();
    expect(screen.getByTestId("library-preview")).toBeInTheDocument();
    expect(screen.getByTestId("library-results-scroll")).toHaveAttribute("data-bounded", "true");
    expect((await screen.findAllByText("walk.mp4")).length).toBeGreaterThan(0);
  });

  it("shows only 24 results in the bounded center and switches keyboard tabs", async () => {
    const many = Array.from({ length: 40 }, (_, index) => asset({
      library_asset_id: `asset_${index}`,
      user_metadata: { filename: `clip-${index}.mp4`, tags: [] },
    }));
    vi.mocked(api.listLibraryAssets).mockResolvedValue({ assets: many, total: many.length });
    render(<LibraryPage />);
    expect((await screen.findAllByTestId("library-asset-card"))).toHaveLength(24);
    const musicTab = screen.getByRole("tab", { name: "음악" });
    fireEvent.keyDown(musicTab, { key: "Enter" });
    expect(musicTab).toHaveAttribute("aria-selected", "true");
  });

  it("reconciles a mixed drop and keeps a failed item visible", async () => {
    vi.mocked(api.ingestLibraryAssets)
      .mockResolvedValueOnce({ ingest_batch_id: "batch_b", partial: false, items: [{ filename: "clip.mp4", state: "ready", library_asset_id: "new_clip" }] })
      .mockResolvedValueOnce({ ingest_batch_id: "batch_a", partial: true, items: [{ filename: "song.mp3", state: "needs_attention", error_code: "unsupported_media" }] });
    render(<LibraryPage />);
    const dropzone = screen.getByTestId("library-dropzone");
    const files = [
      new File(["video"], "clip.mp4", { type: "video/mp4" }),
      new File(["audio"], "song.mp3", { type: "audio/mpeg" }),
    ];
    await act(async () => {
      fireEvent.drop(dropzone, { dataTransfer: { files } });
    });
    expect(await screen.findByText("song.mp3")).toBeInTheDocument();
    expect(screen.getByText(/주의가 필요한 항목/)).toBeInTheDocument();
    expect(api.ingestLibraryAssets).toHaveBeenCalledTimes(2);
    expect(screen.getByText("clip.mp4")).toBeInTheDocument();
  });

  it("offers folder addition and uploads the selected nested files", async () => {
    render(<LibraryPage />);
    const folderInput = screen.getByTestId("library-folder-input");
    expect(screen.getByRole("button", { name: "폴더 추가" })).toBeVisible();
    expect(folderInput).toHaveAttribute("webkitdirectory");
    expect(folderInput).toHaveAttribute("multiple");

    const first = new File(["video"], "clip.mp4", { type: "video/mp4" });
    const second = new File(["audio"], "music.mp3", { type: "audio/mpeg" });
    Object.defineProperty(first, "webkitRelativePath", { value: "촬영본/clip.mp4" });
    Object.defineProperty(second, "webkitRelativePath", { value: "음악/music.mp3" });
    await act(async () => {
      fireEvent.change(folderInput, { target: { files: [first, second] } });
    });

    expect(api.ingestLibraryAssets).toHaveBeenCalledTimes(2);
    expect(api.ingestLibraryAssets).toHaveBeenCalledWith([first], "broll", expect.any(String));
    expect(api.ingestLibraryAssets).toHaveBeenCalledWith([second], "music", expect.any(String));
  });

  it("keeps same-named files from different folders independently retryable", async () => {
    vi.mocked(api.ingestLibraryAssets)
      .mockResolvedValueOnce({ ingest_batch_id: "batch", partial: true, items: [
        { filename: "clip.mp4", state: "needs_attention", error_code: "network_error" },
        { filename: "clip.mp4", state: "needs_attention", error_code: "network_error" },
      ] })
      .mockResolvedValue({ ingest_batch_id: "retry", partial: false, items: [{ filename: "clip.mp4", state: "ready", library_asset_id: "retry-asset" }] });
    render(<LibraryPage />);
    const first = new File(["first"], "clip.mp4", { type: "video/mp4" });
    const second = new File(["second"], "clip.mp4", { type: "video/mp4" });
    Object.defineProperty(first, "webkitRelativePath", { value: "첫번째/clip.mp4" });
    Object.defineProperty(second, "webkitRelativePath", { value: "두번째/clip.mp4" });

    await act(async () => {
      fireEvent.change(screen.getByTestId("library-folder-input"), { target: { files: [first, second] } });
    });
    const retryButtons = await screen.findAllByRole("button", { name: "다시 시도" });
    fireEvent.click(retryButtons[0]);
    await waitFor(() => expect(api.ingestLibraryAssets).toHaveBeenCalledTimes(2));
    expect(api.ingestLibraryAssets).toHaveBeenNthCalledWith(2, [first], "broll", expect.any(String));
  });

  it("previews an asset and blocks trash when the usage endpoint reports a location", async () => {
    vi.mocked(api.getLibraryAssetUsage).mockResolvedValue({
      library_asset_id: "user_asset_1",
      locations: [{ project_id: "project_1", location: { kind: "timeline", id: "timeline_1", label: "프로젝트 편집본" } }],
    });
    render(<LibraryPage />);
    await screen.findAllByText("walk.mp4");
    fireEvent.click(screen.getByTestId("library-asset-card"));
    expect(await screen.findByTestId("library-preview-player")).toBeInTheDocument();
    expect(await screen.findByText(/사용 중인 위치/)).toBeInTheDocument();
    const trash = screen.getByRole("button", { name: "휴지통으로 이동" });
    expect(trash).toBeDisabled();
    expect(screen.getByText(/프로젝트 편집본/)).toBeInTheDocument();
  });

  it("has one primary action in the dropzone and can restore a trashed asset", async () => {
    vi.mocked(api.listLibraryAssets).mockResolvedValue({ assets: [asset({ lifecycle: "trashed" })], total: 1 });
    vi.spyOn(api, "restoreLibraryAsset").mockResolvedValue({ asset: asset({ lifecycle: "ready" }) });
    render(<LibraryPage />);
    fireEvent.click(screen.getByRole("button", { name: /휴지통/ }));
    expect((await screen.findAllByText("walk.mp4")).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("button", { name: /파일 추가/ })).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "복원" }));
    await waitFor(() => expect(api.restoreLibraryAsset).toHaveBeenCalledWith("user_asset_1"));
  });
});
