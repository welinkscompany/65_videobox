import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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

  it("takes the owner from a usage location straight to that project's assets", async () => {
    vi.mocked(api.getLibraryAssetUsage).mockResolvedValue({
      library_asset_id: "user_asset_1",
      locations: [
        { project_id: "project_1", location: { kind: "timeline", id: "timeline_1", label: "프로젝트 편집본" } },
        // 프로젝트를 특정할 수 없는 위치는 지금처럼 글자로만 남는다.
        { location: { kind: "derived_sequence", id: "seq_1", label: "묶음" } },
      ],
    });
    render(<LibraryPage />);
    await screen.findAllByText("walk.mp4");
    fireEvent.click(screen.getByTestId("library-asset-card"));

    const entry = await screen.findByRole("link", { name: "프로젝트 편집본 자산 화면 열기" });
    expect(entry).toHaveAttribute("href", "/projects/project_1/assets");
    expect(screen.getByText("묶음")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "묶음 자산 화면 열기" })).toBeNull();
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

  it("offers a footage-organizer entry for the selected video, and none for audio", async () => {
    render(<LibraryPage />);
    await screen.findAllByText("walk.mp4");
    fireEvent.click(screen.getByTestId("library-asset-card"));

    const entry = await screen.findByRole("link", { name: "구간 정리하기" });
    expect(entry).toHaveAttribute("href", "/footage?library_asset_id=user_asset_1");
    cleanup();

    vi.mocked(api.listLibraryAssets).mockResolvedValue({ assets: [asset({ media_type: "music", user_metadata: { filename: "bgm.mp3" } })], total: 1 });
    const audioView = render(<LibraryPage />);
    await audioView.findAllByText("bgm.mp3");
    fireEvent.click(audioView.getByRole("button", { name: "bgm.mp3 미리 듣기" }));
    expect(await audioView.findByTestId("library-preview-player")).toBeInTheDocument();
    expect(audioView.queryByRole("link", { name: "구간 정리하기" })).toBeNull();
  });

  it("offers a footage-organizer entry directly on each video card, without changing the current selection", async () => {
    vi.mocked(api.listLibraryAssets).mockResolvedValue({
      assets: [asset(), asset({ library_asset_id: "user_asset_2", user_metadata: { filename: "second.mp4" } })],
      total: 2,
    });
    render(<LibraryPage />);
    await screen.findAllByText("second.mp4");
    // 두 번째 자산을 먼저 선택해 둔다.
    fireEvent.click(screen.getByRole("article", { name: "second.mp4" }));
    expect(screen.getByRole("heading", { name: "second.mp4" })).toBeInTheDocument();

    // 첫 번째 카드(선택되지 않은 카드)의 링크는 여전히 보이고, 클릭해도 선택은 안 바뀐다.
    const firstCard = screen.getByRole("article", { name: "walk.mp4" });
    const entry = within(firstCard).getByRole("link", { name: "walk.mp4 구간 정리하기" });
    expect(entry).toHaveAttribute("href", "/footage?library_asset_id=user_asset_1");

    fireEvent.click(entry);
    expect(screen.getByRole("heading", { name: "second.mp4" })).toBeInTheDocument();
  });

  it("does not let the card's select-on-Enter handler swallow keyboard activation of its crosslink", async () => {
    vi.mocked(api.listLibraryAssets).mockResolvedValue({
      assets: [asset(), asset({ library_asset_id: "user_asset_2", user_metadata: { filename: "second.mp4" } })],
      total: 2,
    });
    render(<LibraryPage />);
    await screen.findAllByText("second.mp4");
    fireEvent.click(screen.getByRole("article", { name: "second.mp4" }));
    expect(screen.getByRole("heading", { name: "second.mp4" })).toBeInTheDocument();

    // 선택되지 않은 첫 카드(walk.mp4)의 링크에서 Enter를 누른다. 카드의
    // onSelect(Enter/Space) 핸들러로 전파됐다면 선택이 walk.mp4로 바뀐다 --
    // 링크는 네이티브 <a>라 실제로는 이동해야 할 키 입력이다.
    const firstCard = screen.getByRole("article", { name: "walk.mp4" });
    const entry = within(firstCard).getByRole("link", { name: "walk.mp4 구간 정리하기" });
    fireEvent.keyDown(entry, { key: "Enter", code: "Enter" });

    expect(screen.getByRole("heading", { name: "second.mp4" })).toBeInTheDocument();
  });

  it("keeps the selected video's crosslink reachable after switching to the music tab (the video card disappears from that tab)", async () => {
    render(<LibraryPage />);
    await screen.findAllByText("walk.mp4");
    fireEvent.click(screen.getByTestId("library-asset-card"));
    expect(screen.getByRole("heading", { name: "walk.mp4" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: "음악" }));

    // walk.mp4는 여전히 선택된 채 미리보기에 남아 있지만, 음악 탭에는 그 영상의
    // 카드가 없다 -- 미리보기 패널의 링크가 유일한 경로여야 한다.
    expect(screen.queryByTestId("library-asset-card")).toBeNull();
    expect(screen.getByRole("heading", { name: "walk.mp4" })).toBeInTheDocument();
    const entry = screen.getByRole("link", { name: "구간 정리하기" });
    expect(entry).toHaveAttribute("href", "/footage?library_asset_id=user_asset_1");
  });

  it("preselects the video asset a footage-organizer link named in the URL", async () => {
    window.history.replaceState({}, "", "/library?library_asset_id=user_asset_1");
    vi.mocked(api.listLibraryAssets).mockResolvedValue({
      assets: [asset({ library_asset_id: "user_asset_0", user_metadata: { filename: "first.mp4" } }), asset()],
      total: 2,
    });

    render(<LibraryPage />);

    expect(await screen.findByTestId("library-preview-player")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "walk.mp4" })).toBeInTheDocument();
  });
});
