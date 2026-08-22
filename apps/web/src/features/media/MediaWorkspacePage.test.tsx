import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api, type BrollAsset, type LibraryAsset, type MediaAnalysis, type MediaLibraryAsset } from "../../api";
import { MediaWorkspacePage } from "./MediaWorkspacePage";

/** 개인 라이브러리에 이미 있는 영상. 프로젝트로 가져오는 경로가 없던 대상이다. */
const personalVideo = (): LibraryAsset => ({
  library_asset_id: "user:broll:walk",
  media_type: "broll",
  origin: "user",
  lifecycle: "ready",
  content_sha256: "a".repeat(64),
  byte_count: 2048,
  mime_type: "video/mp4",
  managed_relative_path: "assets/broll/walk.mp4",
  technical_metadata: { duration_seconds: 12, width: 1920, height: 1080 },
  machine_metadata: {},
  user_metadata: { filename: "walk.mp4" },
  created_at: "2026-08-12T00:00:00Z",
  updated_at: "2026-08-12T00:00:00Z",
  trashed_at: null,
  preview_url: "/api/library/assets/user:broll:walk/preview",
  thumbnail_url: "/api/library/assets/user:broll:walk/thumbnail",
  waveform_url: null,
});

const asset = (projectId = "project-a"): BrollAsset => ({
  asset_id: `asset-${projectId}`,
  asset_type: "broll_video",
  storage_uri: `local://${projectId}/asset`,
  created_at: "2026-07-23T00:00:00Z",
  metadata: { title: `${projectId === "project-a" ? "회의" : "산책"} 장면`, duration_seconds: 5 },
});

const analysis = (status: string, index: number): MediaAnalysis => ({
  analysis_id: `analysis-internal-${index}`,
  asset_id: index === 1 ? "asset-project-a" : `asset-internal-${index}`,
  status,
  progress_percent: status === "running" ? 50 : 100,
  queue_position: null,
  error_code: status === "failed" ? "provider_internal" : null,
  error_message: status === "failed" ? "provider session internal" : null,
  result: null,
  created_at: "2026-07-23T00:00:00Z",
});

const libraryAsset = (mediaType: "music" | "sfx"): MediaLibraryAsset => ({
  library_asset_id: `pack:starter-v1:${mediaType}-1`,
  asset_id: `${mediaType}-1`,
  media_type: mediaType,
  duration_seconds: mediaType === "music" ? 82 : 1,
  version: "1.0.0",
  verified: true,
  available: true,
  tags: [],
  source: "local",
  creator: "VideoBox",
  official_license_url: "",
  attribution_required: false,
  attribution_text: "",
});

function makeFile(name: string) {
  return new File(["clip-bytes"], name, { type: "video/mp4" });
}

async function openImportTab() {
  fireEvent.click(screen.getByRole("tab", { name: "가져오기" }));
  await screen.findByText("영상 올리기");
}

beforeEach(() => {
  vi.spyOn(api, "listBrollAssets").mockResolvedValue([asset()]);
  vi.spyOn(api, "listMediaAnalysis").mockResolvedValue({ items: [analysis("needs_review", 1)] });
  vi.spyOn(api, "mediaAnalysisPreview").mockResolvedValue({
    analysis_id: "analysis-internal-1",
    preview: { duration_sec: 5 },
  });
  vi.spyOn(api, "cancelMediaAnalysis").mockResolvedValue(analysis("cancelled", 2));
  vi.spyOn(api, "retryMediaAnalysis").mockResolvedValue(analysis("queued", 3));
  vi.spyOn(api, "reviewMediaAnalysis").mockResolvedValue(analysis("succeeded", 1));
  vi.spyOn(api, "uploadDraftBroll").mockResolvedValue({ asset_id: "asset-uploaded", asset_type: "broll_video", scan_status: "local_ready" });
  vi.spyOn(api, "ingestLibraryAssets").mockResolvedValue({ ingest_batch_id: "batch-project", partial: false, items: [] });
  vi.spyOn(api, "materializeLibraryAsset").mockResolvedValue({ asset: { asset_id: "asset-uploaded", asset_type: "broll_video", storage_uri: "local://project-a/asset-uploaded" }, reference: { reference_id: "ref-project", project_id: "project-a", library_asset_id: "user:broll" } });
  vi.spyOn(api, "listMediaInboxAssets").mockResolvedValue([
    { filename: "촬영-01.mp4", size_bytes: 125829120 },
    { filename: "촬영-02.mp4", size_bytes: 2048 },
  ]);
  vi.spyOn(api, "importMediaInboxAsset").mockResolvedValue({
    asset_id: "asset-imported",
    project_id: "project-a",
    asset_type: "broll_video",
    storage_uri: "local://project-a/asset-imported",
  });
  vi.spyOn(api, "getMediaLibraryInstallState").mockResolvedValue({ status: "installed", installed_asset_count: 2 });
  vi.spyOn(api, "listMediaLibraryAssets").mockResolvedValue({ assets: [libraryAsset("music"), libraryAsset("sfx")] });
  vi.spyOn(api, "listProjectMediaLibraryFavorites").mockResolvedValue({ asset_ids: [] });
  vi.spyOn(api, "listProjectRecentMediaLibraryAssetIds").mockResolvedValue({ asset_ids: [] });
  vi.spyOn(api, "listLibraryAssets").mockResolvedValue({ assets: [personalVideo()], total: 1 });
});

afterEach(() => vi.restoreAllMocks());

describe("MediaWorkspacePage", () => {
  it("separates project assets, library search, new files, and footage intake in the project flow", async () => {
    render(<MediaWorkspacePage projectId="project-a" />);

    expect(await screen.findByRole("heading", { name: "프로젝트 자산" })).toBeVisible();
    fireEvent.click(screen.getByRole("tab", { name: "음악" }));
    expect(await screen.findByRole("heading", { name: "라이브러리에서 찾기" })).toBeVisible();
    fireEvent.click(screen.getByRole("tab", { name: "가져오기" }));
    expect(await screen.findByRole("heading", { name: "새 파일 추가" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "촬영본 가져오기" })).toBeVisible();
  });

  it("pulls a video that is already in the library into the project, without a re-upload", async () => {
    // 이 경로가 없어서 owner는 라이브러리에 있는 영상을 프로젝트에 쓰려면 같은
    // 파일을 다시 올려야 했다. 음악·효과음은 처음부터 이 경로가 있었다.
    render(<MediaWorkspacePage projectId="project-a" />);

    expect(await screen.findByRole("heading", { name: "라이브러리 영상" })).toBeVisible();
    fireEvent.click(await screen.findByRole("button", { name: "walk.mp4 프로젝트에 추가" }));

    await waitFor(() => expect(api.materializeLibraryAsset).toHaveBeenCalledWith("user:broll:walk", "project-a"));
    // 추가 직후 위쪽 프로젝트 자산 목록이 스스로 갱신된다.
    await waitFor(() => expect(api.listBrollAssets).toHaveBeenCalledTimes(2));
  });

  it("says 영상 on the video tab and keeps 음악과 효과음 wording on the audio tabs", async () => {
    render(<MediaWorkspacePage projectId="project-a" />);

    expect(await screen.findByRole("heading", { name: "라이브러리 영상" })).toBeVisible();
    expect(screen.queryByText("음악과 효과음")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: "음악" }));
    expect(await screen.findByText("음악과 효과음")).toBeVisible();
    expect(screen.queryByRole("heading", { name: "라이브러리 영상" })).not.toBeInTheDocument();
  });

  it("removes a project copy through its reference without trashing the global library asset", async () => {
    vi.mocked(api.listBrollAssets).mockResolvedValue([{
      ...asset(),
      metadata: { title: "공원 장면", source_library_asset_id: "user:broll:1" },
    }]);
    const usage = vi.spyOn(api, "getLibraryAssetUsage").mockResolvedValue({
      library_asset_id: "user:broll:1",
      locations: [{ project_id: "project-a", materialized_asset_id: "asset-project-a", reference_id: "ref-1", location: { kind: "project_asset" } }],
    });
    const remove = vi.spyOn(api, "removeLibraryReference").mockResolvedValue(undefined);
    const trash = vi.spyOn(api, "trashLibraryAsset");
    render(<MediaWorkspacePage projectId="project-a" />);

    fireEvent.click(await screen.findByRole("button", { name: "공원 장면 프로젝트에서 빼기" }));
    await waitFor(() => expect(usage).toHaveBeenCalledWith("user:broll:1"));
    await waitFor(() => expect(remove).toHaveBeenCalledWith("user:broll:1", "ref-1"));
    expect(trash).not.toHaveBeenCalled();
  });

  it("keeps the default 내 영상 tab focused and moves imports into 가져오기", async () => {
    render(<MediaWorkspacePage projectId="project-a" />);

    expect(await screen.findByRole("tab", { name: "내 영상" })).toHaveAttribute("aria-selected", "true");
    expect((await screen.findAllByText("회의 장면"))[0]).toBeVisible();
    expect(screen.queryByText("따로 모아둔 영상 가져오기")).not.toBeInTheDocument();
    expect(screen.queryByText("음악과 효과음")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: "가져오기" }));
    expect(screen.getByText("따로 모아둔 영상 가져오기")).toBeVisible();
    expect(screen.getByLabelText("장면 영상 파일 추가")).toBeVisible();
    expect(screen.queryByText("음악과 효과음")).not.toBeInTheDocument();
  });

  it("renders only the selected library type and exposes bounded project pages", async () => {
    render(<MediaWorkspacePage projectId="project-a" />);
    await screen.findByRole("heading", { name: "내 영상" });

    fireEvent.click(screen.getByRole("tab", { name: "음악" }));
    expect(await screen.findByText("음악과 효과음")).toBeVisible();
    expect(screen.getByText("음악 1")).toBeVisible();
    expect(screen.queryByText("효과음 1")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: "효과음" }));
    expect(screen.getByText("음악과 효과음")).toBeVisible();
    expect(screen.queryByText("음악 1")).not.toBeInTheDocument();
  });

  it("keeps the active tab panel reference valid and supports arrow-key navigation", async () => {
    render(<MediaWorkspacePage projectId="project-a" />);
    const videosTab = await screen.findByRole("tab", { name: "내 영상" });
    const musicTab = screen.getByRole("tab", { name: "음악" });

    expect(videosTab).toHaveAttribute("aria-controls", "media-panel-videos");
    expect(musicTab).not.toHaveAttribute("aria-controls");
    expect(screen.getByRole("tabpanel", { name: "내 영상" })).toBeVisible();

    videosTab.focus();
    fireEvent.keyDown(videosTab, { key: "ArrowRight" });
    await waitFor(() => expect(musicTab).toHaveAttribute("aria-selected", "true"));
    expect(musicTab).toHaveAttribute("aria-controls", "media-panel-music");
    expect(videosTab).not.toHaveAttribute("aria-controls");
    expect(musicTab).toHaveFocus();
  });

  it("loads local assets and analysis without mutating or exposing raw contracts", async () => {
    vi.mocked(api.listBrollAssets).mockResolvedValue([
      asset(),
      {
        ...asset(),
        asset_id: "asset-image-internal",
        asset_type: "broll_image",
        metadata: { title: "숨겨진 사진" },
      },
    ]);
    render(<MediaWorkspacePage projectId="project-a" />);

    expect(await screen.findByRole("heading", { name: "자산 보관함" })).toBeVisible();
    // **갱신 이유(2026-08-22).** 문구만 바뀌었다 -- owner 지시로 설명 문장을
    // 키워드로 옮기는 중이다. 이 줄은 바로 위 제목(`자산 보관함`)을 말만 바꿔
    // 되풀이하고 있었다.
    expect(screen.getByText("영상 · 분석 상태")).toBeVisible();
    expect(screen.getAllByText("회의 장면")).toHaveLength(2);
    expect(screen.queryByText("숨겨진 사진")).not.toBeInTheDocument();
    expect(screen.queryByText("사진")).not.toBeInTheDocument();
    expect(screen.getByText(/확인이 필요해요/)).toBeVisible();
    expect(api.cancelMediaAnalysis).not.toHaveBeenCalled();
    expect(api.retryMediaAnalysis).not.toHaveBeenCalled();
    expect(api.reviewMediaAnalysis).not.toHaveBeenCalled();
    expect(document.body.textContent).not.toMatch(/asset-project-a|analysis-internal|needs_review|provider session/i);

    fireEvent.click(screen.getByRole("button", { name: "미리보기" }));
    expect(await screen.findByText("미리보기 길이 5초")).toBeVisible();
    expect(api.mediaAnalysisPreview).toHaveBeenCalledWith("project-a", "asset-project-a");
  });

  // 반입은 `duration_sec`으로 쓴다. 화면이 `duration_seconds`만 읽어서 길이를 아는
  // 자산까지 전부 "길이를 확인하고 있어요"로 굳어 있었다. 편집기 카드에서 같은 실수를
  // 이미 한 번 고쳤는데(`editorAssetProjection.ts`) 이 화면이 남아 있었다.
  it("shows the length the intake actually recorded", async () => {
    vi.mocked(api.listBrollAssets).mockResolvedValue([
      { ...asset(), metadata: { title: "회의 장면", duration_sec: 34 } },
      { ...asset(), asset_id: "asset-pack", metadata: { title: "팩 장면", duration_seconds: 12 } },
      { ...asset(), asset_id: "asset-unknown", metadata: { title: "아직 못 잰 장면" } },
    ]);
    render(<MediaWorkspacePage projectId="project-a" />);

    expect(await screen.findByText("길이 34초")).toBeVisible();
    expect(screen.getByText("길이 12초")).toBeVisible();
    expect(screen.getByText("길이 정보 없음")).toBeVisible();
  });

  it("supports cancel, retry, and review with one in-flight action and an authoritative two-list refresh", async () => {
    let releaseCancel!: (value: MediaAnalysis) => void;
    vi.mocked(api.listMediaAnalysis).mockResolvedValue({
      items: [analysis("running", 2), analysis("failed", 3), analysis("needs_review", 1)],
    });
    vi.mocked(api.cancelMediaAnalysis).mockImplementation(() => new Promise((resolve) => {
      releaseCancel = resolve;
    }));
    render(<MediaWorkspacePage projectId="project-a" />);

    const cancel = await screen.findByRole("button", { name: "분석 멈추기" });
    fireEvent.click(cancel);
    fireEvent.click(cancel);
    expect(api.cancelMediaAnalysis).toHaveBeenCalledTimes(1);
    await act(async () => releaseCancel(analysis("cancelled", 2)));
    await waitFor(() => {
      expect(api.listBrollAssets).toHaveBeenCalledTimes(2);
      expect(api.listMediaAnalysis).toHaveBeenCalledTimes(2);
    });

    fireEvent.click(screen.getByRole("button", { name: "다시 분석하기" }));
    await waitFor(() => expect(api.retryMediaAnalysis).toHaveBeenCalledWith("project-a", "analysis-internal-3"));
    await waitFor(() => expect(api.listBrollAssets).toHaveBeenCalledTimes(3));
    expect(api.listMediaAnalysis).toHaveBeenCalledTimes(3);

    fireEvent.change(screen.getByLabelText("미디어 3 태그"), { target: { value: "회의, 실내" } });
    fireEvent.click(screen.getByRole("button", { name: "태그 확인" }));
    await waitFor(() => expect(api.reviewMediaAnalysis).toHaveBeenCalledWith(
      "project-a",
      "analysis-internal-1",
      { place: ["회의", "실내"] },
    ));
    await waitFor(() => expect(api.listBrollAssets).toHaveBeenCalledTimes(4));
    expect(api.listMediaAnalysis).toHaveBeenCalledTimes(4);
  });

  it("shows loading, empty, failure, and refresh recovery in creator language", async () => {
    let rejectInitial!: (reason?: unknown) => void;
    vi.mocked(api.listBrollAssets)
      .mockImplementationOnce(() => new Promise((_resolve, reject) => { rejectInitial = reject; }))
      .mockResolvedValue([]);
    vi.mocked(api.listMediaAnalysis).mockResolvedValue({ items: [] });
    render(<MediaWorkspacePage projectId="project-a" />);

    expect(screen.getByText("자산을 불러오고 있어요.")).toBeVisible();
    await act(async () => rejectInitial(new Error("raw provider failure")));
    expect(await screen.findByText("자산을 불러오지 못했어요. 다시 시도해 주세요.")).toBeVisible();
    expect(document.body.textContent).not.toContain("raw provider failure");

    fireEvent.click(screen.getByRole("button", { name: "다시 불러오기" }));
    expect(await screen.findByText("아직 준비한 영상이 없어요. 가져오기 탭에서 영상을 추가해 보세요.")).toBeVisible();
    expect(screen.getByText("확인할 분석이 없어요.")).toBeVisible();
  });

  it("does not claim a media mutation succeeded when either authoritative list refresh fails", async () => {
    vi.mocked(api.listMediaAnalysis)
      .mockResolvedValueOnce({ items: [analysis("failed", 3)] })
      .mockRejectedValueOnce(new Error("refresh failed"));
    render(<MediaWorkspacePage projectId="project-a" />);

    fireEvent.click(await screen.findByRole("button", { name: "다시 분석하기" }));

    expect(await screen.findByText("자산을 불러오지 못했어요. 다시 시도해 주세요.")).toBeVisible();
    expect(screen.queryByText("변경 내용을 확인했어요.")).not.toBeInTheDocument();
  });

  it("discards late project A results after switching to project B", async () => {
    let resolveA!: (value: BrollAsset[]) => void;
    vi.mocked(api.listBrollAssets).mockImplementation((projectId) => (
      projectId === "project-a"
        ? new Promise((resolve) => { resolveA = resolve; })
        : Promise.resolve([asset("project-b")])
    ));
    vi.mocked(api.listMediaAnalysis).mockResolvedValue({ items: [] });
    const { rerender } = render(<MediaWorkspacePage projectId="project-a" />);

    rerender(<MediaWorkspacePage projectId="project-b" />);
    expect(await screen.findByText("산책 장면")).toBeVisible();
    await act(async () => resolveA([asset("project-a")]));
    expect(screen.queryByText("회의 장면")).not.toBeInTheDocument();
    expect(screen.getByTestId("media-workspace-page")).toHaveAttribute("data-project-id", "project-b");
  });

  it("uploads one or more files from the asset screen and refreshes the list", async () => {
    render(<MediaWorkspacePage projectId="project-a" />);
    await openImportTab();
    await screen.findByRole("heading", { name: "자산 보관함" });
    expect(api.listBrollAssets).toHaveBeenCalledTimes(1);

    const input = screen.getByLabelText("장면 영상 파일 추가") as HTMLInputElement;
    const fileA = makeFile("clip-a.mp4");
    const fileB = makeFile("clip-b.mp4");
    vi.mocked(api.ingestLibraryAssets).mockResolvedValueOnce({ ingest_batch_id: "batch-project", partial: false, items: [
      { filename: "clip-a.mp4", state: "ready", library_asset_id: "user:clip-a" },
      { filename: "clip-b.mp4", state: "ready", library_asset_id: "user:clip-b" },
    ] });
    fireEvent.change(input, { target: { files: [fileA, fileB] } });

    await waitFor(() => expect(api.ingestLibraryAssets).toHaveBeenCalledTimes(1));
    expect(api.ingestLibraryAssets).toHaveBeenCalledWith([fileA, fileB], "broll", expect.any(String));
    await waitFor(() => expect(api.listBrollAssets).toHaveBeenCalledTimes(2));
    expect(await screen.findByText(/영상 2개를 추가했어요/)).toBeVisible();
  });

  it("keeps failed uploads visible in creator language instead of silently dropping them", async () => {
    vi.mocked(api.ingestLibraryAssets).mockResolvedValue({ ingest_batch_id: "batch", partial: true, items: [
      { filename: "good.mp4", state: "ready", library_asset_id: "user:good" },
      { filename: "bad.mp4", state: "needs_attention", error_code: "invalid_media" },
    ] });
    render(<MediaWorkspacePage projectId="project-a" />);
    await openImportTab();
    await screen.findByRole("heading", { name: "자산 보관함" });

    const input = screen.getByLabelText("장면 영상 파일 추가") as HTMLInputElement;
    fireEvent.change(input, { target: { files: [makeFile("good.mp4"), makeFile("bad.mp4")] } });

    expect(await screen.findByText(/1개를 추가하지 못했어요/)).toBeVisible();
    expect(document.body.textContent).not.toContain("raw provider failure");
  });

  it("blocks another upload while one is already in flight", async () => {
    let release!: () => void;
    vi.mocked(api.ingestLibraryAssets).mockImplementation(() => new Promise((resolve) => { release = () => resolve({ ingest_batch_id: "batch", partial: false, items: [{ filename: "one.mp4", state: "ready", library_asset_id: "user:one" }] }); }));
    render(<MediaWorkspacePage projectId="project-a" />);
    await openImportTab();
    await screen.findByRole("heading", { name: "자산 보관함" });

    const input = screen.getByLabelText("장면 영상 파일 추가") as HTMLInputElement;
    fireEvent.change(input, { target: { files: [makeFile("one.mp4")] } });
    expect(input).toBeDisabled();

    await act(async () => release());
    await waitFor(() => expect(input).not.toBeDisabled());
  });

  it("brings a chosen file from the shared collection into this project and reflects it on the page", async () => {
    // Task 22: the import registers B-roll, so the imported clip has to turn
    // up in the very list this screen already shows. A counter standing in for
    // that would hide the case where the import lands somewhere unusable.
    vi.mocked(api.listBrollAssets)
      .mockResolvedValueOnce([])
      .mockResolvedValue([{ ...asset(), asset_id: "asset-imported", metadata: { title: "촬영-01" } }]);
    render(<MediaWorkspacePage projectId="project-a" />);
    await openImportTab();

    expect(await screen.findByText("촬영-01.mp4")).toBeVisible();
    expect(screen.getByText("120.0MB")).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: "촬영-01.mp4 가져오기" }));

    await waitFor(() => expect(api.importMediaInboxAsset).toHaveBeenCalledWith("project-a", "촬영-01.mp4"));
    expect(await screen.findByText("「촬영-01.mp4」을 이 프로젝트로 가져왔어요.")).toBeVisible();
    fireEvent.click(screen.getByRole("tab", { name: "내 영상" }));
    expect(await screen.findByText("촬영-01")).toBeVisible();
    expect(screen.queryByText("아직 준비한 자산이 없어요.")).not.toBeInTheDocument();
    expect(document.body.textContent).not.toContain("asset-imported");
  });

  it("shows an empty shared collection in creator language", async () => {
    vi.mocked(api.listMediaInboxAssets).mockResolvedValue([]);
    render(<MediaWorkspacePage projectId="project-a" />);
    await openImportTab();

    expect(await screen.findByText("아직 따로 모아둔 영상이 없어요.")).toBeVisible();
    expect(screen.queryByRole("button", { name: /가져오기$/ })).not.toBeInTheDocument();
  });

  it("reports a failed import in creator language without leaking the raw failure", async () => {
    vi.mocked(api.importMediaInboxAsset).mockRejectedValue(new Error("media_inbox_asset_missing"));
    render(<MediaWorkspacePage projectId="project-a" />);
    await openImportTab();

    fireEvent.click(await screen.findByRole("button", { name: "촬영-01.mp4 가져오기" }));

    expect(await screen.findByText("이 영상을 가져오지 못했어요. 다시 시도해 주세요.")).toBeVisible();
    expect(document.body.textContent).not.toContain("media_inbox_asset_missing");
  });

  it("blocks a second import while one is already in flight", async () => {
    let release!: (value: { asset_id: string; project_id: string; asset_type: string; storage_uri: string }) => void;
    vi.mocked(api.importMediaInboxAsset).mockImplementation(() => new Promise((resolve) => { release = resolve; }));
    render(<MediaWorkspacePage projectId="project-a" />);
    await openImportTab();

    fireEvent.click(await screen.findByRole("button", { name: "촬영-01.mp4 가져오기" }));
    expect(screen.getByRole("button", { name: "촬영-02.mp4 가져오기" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "촬영-02.mp4 가져오기" }));
    expect(api.importMediaInboxAsset).toHaveBeenCalledTimes(1);

    await act(async () => release({
      asset_id: "asset-imported",
      project_id: "project-a",
      asset_type: "broll_video",
      storage_uri: "local://project-a/asset-imported",
    }));
    await waitFor(() => expect(screen.getByRole("button", { name: "촬영-02.mp4 가져오기" })).not.toBeDisabled());
  });

  it("keeps an old A preview from overwriting or unlocking a newer A preview after A-B-A", async () => {
    let releaseOld!: (value: { analysis_id: string; preview: unknown }) => void;
    let releaseNew!: (value: { analysis_id: string; preview: unknown }) => void;
    vi.mocked(api.listBrollAssets).mockImplementation((projectId) => Promise.resolve([asset(projectId)]));
    vi.mocked(api.listMediaAnalysis).mockResolvedValue({ items: [analysis("succeeded", 1)] });
    vi.mocked(api.mediaAnalysisPreview)
      .mockImplementationOnce(() => new Promise((resolve) => { releaseOld = resolve; }))
      .mockImplementationOnce(() => new Promise((resolve) => { releaseNew = resolve; }));
    const { rerender } = render(<MediaWorkspacePage projectId="project-a" />);
    fireEvent.click(await screen.findByRole("button", { name: "미리보기" }));
    rerender(<MediaWorkspacePage projectId="project-b" />);
    await screen.findByText("산책 장면");
    rerender(<MediaWorkspacePage projectId="project-a" />);
    const newerPreview = await screen.findByRole("button", { name: "미리보기" });
    fireEvent.click(newerPreview);

    await act(async () => releaseOld({ analysis_id: "old", preview: { duration_sec: 1 } }));
    expect(screen.queryByText("미리보기 길이 1초")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "미리보기" })).toBeDisabled();

    await act(async () => releaseNew({ analysis_id: "new", preview: { duration_sec: 9 } }));
    expect(await screen.findByText("미리보기 길이 9초")).toBeVisible();
  });
});

describe("프로젝트 영상 정리", () => {
  // owner 지적: "자산 폴더는 분류도 안 되고, 그냥 나열만 하고 있고".
  // 라이브러리 쪽은 좁힐 수 있게 됐지만 기본으로 열리는 "내 영상" 위쪽은
  // 여전히 그냥 나열이었다.
  // 보관함은 오래된 것부터 도착한다(`local_project_store.list_assets`가 `created_at ASC`).
  const twoClips = (): BrollAsset[] => ([
    { asset_id: "asset-old", asset_type: "broll_video", storage_uri: "local://project-a/old", created_at: "2026-07-01T00:00:00Z", metadata: { title: "산책 장면", duration_seconds: 5 } },
    { asset_id: "asset-new", asset_type: "broll_video", storage_uri: "local://project-a/new", created_at: "2026-07-30T00:00:00Z", metadata: { title: "회의 장면", duration_seconds: 7 } },
  ]);
  const cards = () => Array.from(document.querySelectorAll(".vb-media-project-card"));

  it("이름으로 프로젝트 영상을 좁힌다", async () => {
    vi.mocked(api.listBrollAssets).mockResolvedValue(twoClips());
    render(<MediaWorkspacePage projectId="project-a" />);
    await screen.findByText("산책 장면");

    fireEvent.change(screen.getByLabelText("프로젝트 영상 이름으로 찾기"), { target: { value: "회의" } });

    expect(screen.getByText("회의 장면")).toBeVisible();
    expect(screen.queryByText("산책 장면")).toBeNull();
  });

  it("최근에 넣은 영상을 앞에 두고, 이름 순으로도 다시 세운다", async () => {
    vi.mocked(api.listBrollAssets).mockResolvedValue(twoClips());
    render(<MediaWorkspacePage projectId="project-a" />);
    await screen.findByText("산책 장면");

    expect(cards()[0]).toHaveTextContent("회의 장면");
    expect(cards()[1]).toHaveTextContent("산책 장면");

    fireEvent.click(screen.getByRole("button", { name: "프로젝트 영상 이름 순" }));

    expect(cards()[0]).toHaveTextContent("산책 장면");
    expect(cards()[1]).toHaveTextContent("회의 장면");
  });
});
