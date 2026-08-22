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

  it("offers each media type once, not twice, between the sidebar and the results tabs", async () => {
    // `capcut-observed` 기록 §5: "탭을 누르면 왼쪽에 분류 목록, 오른쪽에 격자" --
    // 한 축에 목록이 하나다. 예전엔 왼쪽 사이드바와 결과 위 탭이 영상·음악·
    // 효과음·그림을 똑같이 두 번 물었다.
    render(<LibraryPage />);
    await screen.findAllByText("walk.mp4");

    const sidebar = screen.getByTestId("library-sidebar");
    expect(within(sidebar).getByRole("button", { name: /^전체/ })).toBeInTheDocument();
    expect(within(sidebar).getByRole("button", { name: /^즐겨찾기/ })).toBeInTheDocument();
    expect(within(sidebar).getByRole("button", { name: /^휴지통/ })).toBeInTheDocument();
    expect(within(sidebar).queryByRole("button", { name: /^영상/ })).toBeNull();
    expect(within(sidebar).queryByRole("button", { name: /^음악/ })).toBeNull();
    expect(within(sidebar).queryByRole("button", { name: /^효과음/ })).toBeNull();
    expect(within(sidebar).queryByRole("button", { name: /^그림/ })).toBeNull();

    expect(screen.getByRole("tab", { name: "영상" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "음악" })).toBeInTheDocument();
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

  it("searches by meaning when a media type is chosen, and says which way it found things", async () => {
    // `/api/library/search`(의미검색)는 백엔드에 있는데 부르는 화면이 하나도
    // 없었다 -- 검색은 언제나 단어 매칭이었다. 종류 탭을 고르고 검색하면
    // 의미검색을 부르고, 어느 방식으로 찾았는지 말한다.
    const search = vi.spyOn(api, "searchLibraryAssets").mockResolvedValue({
      matches: [
        { ...asset({ library_asset_id: "match_1", user_metadata: { filename: "calm-walk.mp4", tags: [] } }), score: 0.9, reason: "묘사 일치", semantic_match: true },
        // 촬영본 색인 조각(자산 아님)은 이 화면이 다룰 수 없어 걸러야 한다.
        { library_asset_id: null, score: 0.8, semantic_match: true } as never,
        // 같은 자산이 두 번 오면 한 번만 그린다 -- React key가 겹친다.
        { ...asset({ library_asset_id: "match_1", user_metadata: { filename: "calm-walk.mp4", tags: [] } }), score: 0.5, semantic_match: true },
      ],
      semantic: true,
    });
    render(<LibraryPage />);
    fireEvent.click(await screen.findByRole("tab", { name: "영상" }));
    fireEvent.change(screen.getByLabelText("검색"), { target: { value: "차분한 산책" } });

    await waitFor(() => expect(search).toHaveBeenCalledWith("차분한 산책", "broll", undefined));
    expect((await screen.findAllByText("calm-walk.mp4")).length).toBeGreaterThan(0);
    // 조각 행은 걸러지고, 중복 자산은 카드 하나만 남는다.
    expect(screen.getAllByTestId("library-asset-card")).toHaveLength(1);
    expect(screen.getByRole("status", { name: "찾은 방식" })).toHaveTextContent("뜻으로 찾음");
  });

  it("says when a search fell back to word matching", async () => {
    vi.spyOn(api, "searchLibraryAssets").mockResolvedValue({
      matches: [{ ...asset(), score: 0.5, reason: "파일명 또는 분석 메타데이터 일치" }],
      semantic: false,
    });
    render(<LibraryPage />);
    fireEvent.click(await screen.findByRole("tab", { name: "영상" }));
    fireEvent.change(screen.getByLabelText("검색"), { target: { value: "걷기" } });

    expect(await screen.findByRole("status", { name: "찾은 방식" })).toHaveTextContent("단어로만 찾음");
  });

  it("does not claim meaning-based results when every semantic row was unusable", async () => {
    // 의미검색이 돌았어도(semantic: true) 남은 행이 전부 단어 매칭이면
    // `뜻으로 찾음` 배지는 거짓말이다 -- 실제로 걸러 낸 뒤 기준으로 말한다.
    vi.spyOn(api, "searchLibraryAssets").mockResolvedValue({
      matches: [
        { ...asset(), score: 0.5, reason: "파일명 또는 분석 메타데이터 일치" },
        { library_asset_id: null, score: 0.9, semantic_match: true } as never,
      ],
      semantic: true,
    });
    render(<LibraryPage />);
    fireEvent.click(await screen.findByRole("tab", { name: "영상" }));
    fireEvent.change(screen.getByLabelText("검색"), { target: { value: "노을" } });

    expect(await screen.findByRole("status", { name: "찾은 방식" })).toHaveTextContent("단어로만 찾음");
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

  // 사진·일러스트를 여러 프로젝트가 나눠 쓰는 자리 (owner 승인 2026-08-20).
  function imageAsset(overrides: Partial<LibraryAsset> = {}): LibraryAsset {
    return asset({
      library_asset_id: "user_image_1",
      media_type: "image",
      mime_type: "image/png",
      managed_relative_path: "assets/image/aa/aa.png",
      technical_metadata: {},
      machine_metadata: {},
      user_metadata: { filename: "바다.png", tags: [] },
      preview_url: "/api/library/assets/user_image_1/preview",
      thumbnail_url: "/api/library/assets/user_image_1/thumbnail",
      // 그림에는 소리가 없다. 서버도 이 칸을 안 내려보낸다.
      waveform_url: undefined,
      ...overrides,
    });
  }

  it("accepts pictures instead of turning them away as an unsupported file", async () => {
    render(<LibraryPage />);
    const png = new File(["p"], "바다.png", { type: "image/png" });
    const jpg = new File(["j"], "노을.JPG", { type: "" });
    const webp = new File(["w"], "로고.webp", { type: "image/webp" });

    await act(async () => {
      fireEvent.change(screen.getByTestId("library-folder-input"), { target: { files: [png, jpg, webp] } });
    });

    expect(api.ingestLibraryAssets).toHaveBeenCalledWith([png, jpg, webp], "image", expect.any(String));
    expect(screen.queryByText(/다시 시도/)).toBeNull();
  });

  it("gives pictures their own tab and shows them as thumbnails, not as sound rows", async () => {
    vi.mocked(api.listLibraryAssets).mockResolvedValue({ assets: [imageAsset()], total: 1 });
    render(<LibraryPage />);
    await screen.findAllByText("바다.png");

    fireEvent.click(screen.getByRole("tab", { name: "그림" }));
    const card = await screen.findByRole("article", { name: "바다.png" });
    expect(within(card).getByRole("presentation")).toHaveAttribute("src", "/api/library/assets/user_image_1/thumbnail");
    // 구간 정리는 영상에만 있는 길이다. 그림에 붙이면 열어 봐야 아무것도 없다.
    expect(within(card).queryByRole("link", { name: /구간 정리하기/ })).toBeNull();
    expect(screen.queryByTestId("library-audio-rows")).toBeNull();
  });

  it("shows a picture as a picture, and never as an empty sound player", async () => {
    vi.mocked(api.listLibraryAssets).mockResolvedValue({ assets: [imageAsset()], total: 1 });
    vi.mocked(api.getLibraryAssetUsage).mockResolvedValue({ library_asset_id: "user_image_1", locations: [] });
    render(<LibraryPage />);
    await screen.findAllByText("바다.png");
    fireEvent.click(screen.getByRole("article", { name: "바다.png" }));

    const player = await screen.findByTestId("library-preview-player");
    expect(player.querySelector("audio")).toBeNull();
    expect(player.querySelector("video")).toBeNull();
    expect(player.querySelector("img")).toHaveAttribute("src", "/api/library/assets/user_image_1/preview");
    // 종류 칸이 `효과음`으로 떨어지지 않는지 본다 -- 옛 갈래의 마지막 칸이었다.
    const preview = screen.getByTestId("library-preview");
    expect([...preview.querySelectorAll("dd")].map((node) => node.textContent)).toContain("그림");
    expect(within(preview).queryByRole("link", { name: "구간 정리하기" })).toBeNull();
  });

  it("says plainly that pictures are only found by word, because nothing reads them yet", async () => {
    // 그림에는 의미 색인이 없다. `뜻으로 찾음`이라고 하면 거짓말이다.
    const search = vi.spyOn(api, "searchLibraryAssets").mockResolvedValue({
      matches: [{ ...imageAsset(), score: 1, reason: "파일명 또는 분석 메타데이터 일치" }],
      semantic: false,
    });
    render(<LibraryPage />);
    fireEvent.click(screen.getByRole("tab", { name: "그림" }));
    fireEvent.change(screen.getByLabelText("검색"), { target: { value: "바다" } });

    await waitFor(() => expect(search).toHaveBeenCalledWith("바다", "image", undefined));
    expect(await screen.findByLabelText("찾은 방식")).toHaveTextContent("단어로만 찾음");
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
