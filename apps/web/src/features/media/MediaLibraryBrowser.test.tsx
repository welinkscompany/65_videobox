import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "../../api";
import { MediaLibraryBrowser } from "./MediaLibraryBrowser";

function asset(overrides: Partial<api.MediaLibraryAsset> = {}): api.MediaLibraryAsset {
  return {
    library_asset_id: "pack:starter-v1:music-intro",
    asset_id: "music-intro",
    media_type: "music",
    duration_seconds: 82,
    version: "1.0.0",
    verified: true,
    available: true,
    tags: ["밝은"],
    source: "https://example.test",
    creator: "Tozan",
    official_license_url: "https://example.test/license",
    attribution_required: false,
    attribution_text: "",
    ...overrides,
  } as api.MediaLibraryAsset;
}

describe("MediaLibraryBrowser", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(api.api, "listProjectRecentMediaLibraryAssetIds").mockResolvedValue({ asset_ids: [] } as never);
    vi.spyOn(api.api, "getMediaLibraryInstallState")
      .mockResolvedValue({ status: "installed", installed_asset_count: 1 } as never);
  });

  it("loads and saves favourites and recents for the active project", async () => {
    const projectId = "project-scoped";
    const listProjectFavorites = vi.spyOn(api.api, "listProjectMediaLibraryFavorites")
      .mockResolvedValue({ asset_ids: [] } as never);
    const listProjectRecents = vi.spyOn(api.api, "listProjectRecentMediaLibraryAssetIds")
      .mockResolvedValue({ asset_ids: [] } as never);
    const saveProjectFavorite = vi.spyOn(api.api, "setProjectMediaLibraryFavorite")
      .mockResolvedValue({ asset_ids: [asset().library_asset_id] } as never);
    const listGlobalFavorites = vi.spyOn(api.api, "listMediaLibraryFavorites")
      .mockResolvedValue({ asset_ids: [] } as never);
    const saveGlobalFavorite = vi.spyOn(api.api, "setMediaLibraryFavorite")
      .mockResolvedValue({ asset_ids: [] } as never);
    vi.spyOn(api.api, "listMediaLibraryAssets").mockResolvedValue({ assets: [asset()] } as never);

    render(<MediaLibraryBrowser projectId={projectId} />);
    fireEvent.click(await screen.findByRole("button", { name: "음악 1 즐겨찾기" }));

    await waitFor(() => expect(saveProjectFavorite).toHaveBeenCalledWith(projectId, asset().library_asset_id, true));
    expect(listProjectFavorites).toHaveBeenCalledWith(projectId);
    expect(listProjectRecents).toHaveBeenCalledWith(projectId);
    expect(listGlobalFavorites).not.toHaveBeenCalled();
    expect(saveGlobalFavorite).not.toHaveBeenCalled();
  });

  it("lets the owner listen to a track before choosing it", async () => {
    // 130 assets arrived with no way to hear one, so picking meant reading
    // filenames and guessing.
    vi.spyOn(api.api, "listMediaLibraryAssets").mockResolvedValue({ assets: [asset()] } as never);
    vi.spyOn(api.api, "listProjectMediaLibraryFavorites").mockResolvedValue({ asset_ids: [] } as never);

    render(<MediaLibraryBrowser projectId="project-a" />);

    const player = await screen.findByLabelText("음악 1 미리 듣기");
    expect(player).toHaveAttribute(
      "src",
      "/api/media-library/assets/pack%3Astarter-v1%3Amusic-intro/preview",
    );
  });

  it("remembers a favourite and shows it first", async () => {
    const plain = asset({ library_asset_id: "pack:starter-v1:music-plain", asset_id: "music-plain" });
    const loved = asset({ library_asset_id: "pack:starter-v1:music-loved", asset_id: "music-loved" });
    vi.spyOn(api.api, "listMediaLibraryAssets").mockResolvedValue({ assets: [plain, loved] } as never);
    vi.spyOn(api.api, "listProjectMediaLibraryFavorites").mockResolvedValue({
      asset_ids: ["pack:starter-v1:music-loved"],
    } as never);

    render(<MediaLibraryBrowser projectId="project-a" />);

    const items = await screen.findAllByRole("article");
    expect(within(items[0]).getByText("음악 1")).toBeVisible();
  });

  it("saves a new favourite the owner marks", async () => {
    vi.spyOn(api.api, "listMediaLibraryAssets").mockResolvedValue({ assets: [asset()] } as never);
    vi.spyOn(api.api, "listProjectMediaLibraryFavorites").mockResolvedValue({ asset_ids: [] } as never);
    const save = vi.spyOn(api.api, "setProjectMediaLibraryFavorite").mockResolvedValue({
      asset_ids: ["pack:starter-v1:music-intro"],
    } as never);

    render(<MediaLibraryBrowser projectId="project-a" />);
    fireEvent.click(await screen.findByRole("button", { name: "음악 1 즐겨찾기" }));

    await waitFor(() => expect(save).toHaveBeenCalledWith("project-a", "pack:starter-v1:music-intro", true));
    expect(await screen.findByRole("button", { name: "음악 1 즐겨찾기 해제" })).toBeVisible();
  });

  it("separates music from effects so a search is not one long list", async () => {
    const music = asset();
    const effect = asset({
      library_asset_id: "pack:starter-v1:sfx-pop", asset_id: "sfx-pop", media_type: "sfx", duration_seconds: 1,
    });
    vi.spyOn(api.api, "listMediaLibraryAssets").mockResolvedValue({ assets: [music, effect] } as never);
    vi.spyOn(api.api, "listProjectMediaLibraryFavorites").mockResolvedValue({ asset_ids: [] } as never);

    render(<MediaLibraryBrowser projectId="project-a" />);
    await screen.findByText("음악 1");

    fireEvent.click(screen.getByRole("button", { name: "효과음만 보기" }));

    expect(screen.getByText("효과음 1")).toBeVisible();
    expect(screen.queryByText("음악 1")).toBeNull();
  });

  it("marks the active library filter with the primary button treatment", async () => {
    vi.spyOn(api.api, "listMediaLibraryAssets").mockResolvedValue({ assets: [asset()] } as never);
    vi.spyOn(api.api, "listProjectMediaLibraryFavorites").mockResolvedValue({ asset_ids: [] } as never);

    render(<MediaLibraryBrowser projectId="project-a" />);

    const all = await screen.findByRole("button", { name: "전체 보기" });
    const music = screen.getByRole("button", { name: "음악만 보기" });
    expect(all).toHaveAttribute("data-variant", "default");
    expect(music).toHaveAttribute("data-variant", "outline");
    fireEvent.click(music);
    expect(music).toHaveAttribute("data-variant", "default");
    expect(all).toHaveAttribute("data-variant", "outline");
  });

  it("says the pack has not been brought in yet, rather than only a heading", async () => {
    // 빈 화면은 세 가지 사정을 같은 얼굴로 보여 준다. 무엇을 해야 할지가
    // 셋 다 다르므로 뭉뚱그리면 owner는 멈춘다.
    vi.spyOn(api.api, "getMediaLibraryInstallState")
      .mockResolvedValue({ status: "not_installed", installed_asset_count: 0 } as never);
    vi.spyOn(api.api, "listMediaLibraryAssets").mockResolvedValue({ assets: [] } as never);
    vi.spyOn(api.api, "listProjectMediaLibraryFavorites").mockResolvedValue({ asset_ids: [] } as never);

    render(<MediaLibraryBrowser projectId="project-a" />);

    expect(await screen.findByText(
      "음악과 효과음 꾸러미를 아직 들여놓지 않았어요. 꾸러미를 넣으면 여기에서 바로 들어볼 수 있어요.",
    )).toBeVisible();
  });

  it("separates a library it could not read from a library that is empty", async () => {
    vi.spyOn(api.api, "listMediaLibraryAssets").mockRejectedValue(new Error("unreadable"));
    vi.spyOn(api.api, "listProjectMediaLibraryFavorites").mockResolvedValue({ asset_ids: [] } as never);

    render(<MediaLibraryBrowser projectId="project-a" />);

    expect(await screen.findByText("음악과 효과음을 불러오지 못했어요. 잠시 뒤 다시 열어 주세요."))
      .toBeVisible();
  });

  it("says how many arrived when some of them are not usable yet", async () => {
    vi.spyOn(api.api, "getMediaLibraryInstallState")
      .mockResolvedValue({ status: "degraded", installed_asset_count: 130 } as never);
    vi.spyOn(api.api, "listMediaLibraryAssets").mockResolvedValue({ assets: [asset()] } as never);
    vi.spyOn(api.api, "listProjectMediaLibraryFavorites").mockResolvedValue({ asset_ids: [] } as never);

    render(<MediaLibraryBrowser projectId="project-a" />);

    expect(await screen.findByText("들여놓은 130개 가운데 일부는 확인이 끝나지 않아 아직 쓸 수 없어요."))
      .toBeVisible();
  });

  it("puts what the owner used most recently under the favourites", async () => {
    // 프로젝트로 들여온 것은 이미 최근 목록에 쌓이고 있었는데 아무도 다시
    // 읽지 않아서, 방금 쓴 곡을 다음에도 아래에서 찾아 내려가야 했다.
    const plain = asset({ library_asset_id: "pack:starter-v1:music-a", asset_id: "music-a" });
    const used = asset({ library_asset_id: "pack:starter-v1:music-b", asset_id: "music-b" });
    const loved = asset({ library_asset_id: "pack:starter-v1:music-c", asset_id: "music-c" });
    vi.spyOn(api.api, "listMediaLibraryAssets")
      .mockResolvedValue({ assets: [plain, used, loved] } as never);
    vi.spyOn(api.api, "listProjectMediaLibraryFavorites")
      .mockResolvedValue({ asset_ids: ["pack:starter-v1:music-c"] } as never);
    vi.spyOn(api.api, "listProjectRecentMediaLibraryAssetIds")
      .mockResolvedValue({ asset_ids: ["pack:starter-v1:music-b"] } as never);

    render(<MediaLibraryBrowser projectId="project-a" />);

    const items = await screen.findAllByRole("article");
    expect(items[0]).toHaveTextContent("음악 3");
    expect(items[1]).toHaveTextContent("음악 2");
    expect(items[1]).toHaveTextContent("최근에 썼어요");
    expect(items[2]).toHaveTextContent("음악 1");
  });

  it("does not blame the pack when a filter is what emptied the list", async () => {
    vi.spyOn(api.api, "listMediaLibraryAssets").mockResolvedValue({ assets: [asset()] } as never);
    vi.spyOn(api.api, "listProjectMediaLibraryFavorites").mockResolvedValue({ asset_ids: [] } as never);

    render(<MediaLibraryBrowser projectId="project-a" />);
    fireEvent.click(await screen.findByRole("button", { name: "효과음만 보기" }));

    expect(screen.getByText("고른 조건에 맞는 것이 없어요.")).toBeVisible();
  });

  it("renders at most 24 audio cards and pages the remainder", async () => {
    const assets = Array.from({ length: 25 }, (_, index) => asset({
      library_asset_id: `pack:starter-v1:music-${String(index + 1).padStart(3, "0")}`,
      asset_id: `music-${String(index + 1).padStart(3, "0")}`,
    }));
    vi.spyOn(api.api, "listMediaLibraryAssets").mockResolvedValue({ assets } as never);
    vi.spyOn(api.api, "listProjectMediaLibraryFavorites").mockResolvedValue({ asset_ids: [] } as never);

    const { container } = render(<MediaLibraryBrowser projectId="project-a" />);

    await screen.findByText("음악 1");
    expect(container.querySelectorAll("article")).toHaveLength(24);
    expect(screen.getByText("1 / 2페이지")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "다음 페이지" }));
    expect(await screen.findByText("음악 25")).toBeVisible();
    expect(container.querySelectorAll("article")).toHaveLength(1);
  });
});

describe("항목 이름", () => {
  it("팩 내부 슬러그 대신 제품 언어로 항목을 부른다", async () => {
    // 음악 이름이 `music-005` 하나뿐이면 owner는 영어 슬러그를 읽어야 한다.
    const first = asset({ library_asset_id: "pack:starter-v1:music-005", asset_id: "music-005" });
    const second = asset({ library_asset_id: "pack:starter-v1:music-zeta", asset_id: "music-zeta" });
    const effect = asset({
      library_asset_id: "pack:starter-v1:sfx-pop",
      asset_id: "sfx-pop",
      media_type: "sfx",
    });
    vi.spyOn(api.api, "listMediaLibraryAssets").mockResolvedValue({
      assets: [second, effect, first],
    } as never);
    vi.spyOn(api.api, "listProjectMediaLibraryFavorites").mockResolvedValue({ asset_ids: [] } as never);

    render(<MediaLibraryBrowser projectId="project-a" />);

    // 번호는 표시 순서가 아니라 종류별 고정 순서에서 나온다.
    expect(await screen.findByLabelText("음악 1 미리 듣기")).toBeInTheDocument();
    expect(screen.getByLabelText("음악 2 미리 듣기")).toBeInTheDocument();
    expect(screen.getByLabelText("효과음 1 미리 듣기")).toBeInTheDocument();
    expect(screen.queryByText(/music-005|sfx-pop/)).toBeNull();
  });
});
