import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import * as apiModule from "../../../api";
import { EditorAssetBrowser } from "./EditorAssetBrowser";
import type { EditorAssetCard } from "./editorAssetProjection";

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

const cards: readonly EditorAssetCard[] = [
  {
    id: "broll:image-1",
    kind: "broll",
    assetId: "image-1",
    label: "이미지 B-roll",
    title: "제품 사진",
    durationLabel: "4초",
    status: "준비됨 · 검토 불필요",
    audioPresence: "오디오 정보 확인 중",
    license: "프로젝트 로컬 B-roll",
    canApply: true,
    previewUrl: "/api/projects/project-a/assets/image-1/content",
    previewKind: "image",
    sourceMetadata: { tags: ["제품"], source: "프로젝트 로컬 B-roll", creator: "", officialLicenseUrl: "", attributionRequired: false, attributionText: "" },
  },
  {
    id: "library:bgm-1",
    kind: "bgm",
    assetId: "starter-bgm",
    libraryAssetId: "bgm-1",
    label: "배경 음악",
    title: "배경 음악 1",
    durationLabel: "12초",
    status: "검증됨 · 이용 가능",
    audioPresence: "오디오 있음",
    license: "라이선스: https://license.invalid/bgm · 출처 표기 불필요",
    canApply: true,
    previewUrl: "/api/media-library/assets/bgm-1/preview",
    sourceMetadata: { tags: ["음악"], source: "Starter", creator: "Creator", officialLicenseUrl: "https://license.invalid/bgm", attributionRequired: false, attributionText: "" },
  },
  {
    id: "library:sfx-1",
    kind: "sfx",
    assetId: "starter-sfx",
    libraryAssetId: "sfx-1",
    label: "효과음",
    title: "효과음 1",
    durationLabel: "2초",
    status: "이용 불가 · 검증됨",
    audioPresence: "오디오 있음",
    license: "검증 또는 이용 가능 상태 확인 필요",
    canApply: false,
    previewUrl: "/api/media-library/assets/sfx-1/preview",
    sourceMetadata: { tags: ["효과음"], source: "Starter", creator: "Creator", officialLicenseUrl: "", attributionRequired: false, attributionText: "" },
  },
];

describe("EditorAssetBrowser", () => {
  it("filters by type and query, shows the selected range, and previews through a callback without media", () => {
    const onPreview = vi.fn();
    const { container } = render(<EditorAssetBrowser cards={cards} target={{ segmentId: "seg-1", startSec: 3, endSec: 7 }} isSaving={false} onPreview={onPreview} onApply={vi.fn()} />);

    screen.getAllByRole("article").forEach((card) => expect(card).toHaveTextContent("적용 구간: 3.00–7.00초"));
    fireEvent.click(screen.getByRole("button", { name: "음악 필터" }));
    expect(screen.getByRole("button", { name: "음악 필터" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("heading", { name: "배경 음악 1" })).toBeVisible();
    expect(screen.queryByRole("heading", { name: "제품 사진" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "전체 필터" }));
    fireEvent.change(screen.getByRole("searchbox", { name: "자산 검색" }), { target: { value: "제품" } });
    fireEvent.click(screen.getByRole("button", { name: "제품 사진 원본 미리보기" }));

    expect(onPreview).toHaveBeenCalledWith(cards[0]);
    expect(screen.getByRole("status")).toHaveTextContent("적용 구간: 3.00–7.00초");
    expect(screen.getByRole("article")).toHaveTextContent("적용 구간: 3.00–7.00초");
    expect(screen.getByText("직접 선택한 자산")).toBeVisible();
    expect(container.querySelectorAll("audio, video")).toHaveLength(0);
  });

  it("applies the exact card and target segment only when target, save state, and availability permit", () => {
    const onApply = vi.fn();
    const { rerender } = render(<EditorAssetBrowser cards={cards} target={null} isSaving={false} onPreview={vi.fn()} onApply={onApply} />);

    expect(screen.getByRole("status")).toHaveTextContent("적용할 내레이션 구간을 먼저 선택하세요.");
    screen.getAllByRole("article").forEach((card) => expect(card).toHaveTextContent("적용할 내레이션 구간을 먼저 선택하세요."));
    expect(screen.getByRole("button", { name: "제품 사진 적용" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "효과음 1 적용" })).toBeDisabled();

    rerender(<EditorAssetBrowser cards={cards} target={{ segmentId: "seg-1", startSec: 0, endSec: 1 }} isSaving onPreview={vi.fn()} onApply={onApply} />);
    expect(screen.getByRole("button", { name: "제품 사진 적용" })).toBeDisabled();

    rerender(<EditorAssetBrowser cards={cards} target={{ segmentId: "seg-1", startSec: 0, endSec: 1 }} isSaving={false} onPreview={vi.fn()} onApply={onApply} />);
    fireEvent.click(screen.getByRole("button", { name: "제품 사진 적용" }));
    expect(onApply).toHaveBeenCalledWith(cards[0], "seg-1");
    expect(screen.getByRole("button", { name: "효과음 1 적용" })).toBeDisabled();
  });

  // 렌더러와 편집 명령은 처음부터 이미지 오버레이를 만들 수 있었는데, 이미지를
  // 고를 자리가 화면에 없었다. 자산 목록이 그 선택기다.
  it("offers to lay an image over the scene, image cards only, through an explicit callback", () => {
    const onApplyOverlay = vi.fn();
    const { rerender } = render(<EditorAssetBrowser cards={cards} target={null} isSaving={false} onPreview={vi.fn()} onApply={vi.fn()} onApplyOverlay={onApplyOverlay} />);

    expect(screen.getByRole("button", { name: "제품 사진 화면에 얹기" })).toBeDisabled();
    expect(screen.queryByRole("button", { name: "배경 음악 1 화면에 얹기" })).toBeNull();
    expect(screen.queryByRole("button", { name: "효과음 1 화면에 얹기" })).toBeNull();

    rerender(<EditorAssetBrowser cards={cards} target={{ segmentId: "seg-1", startSec: 0, endSec: 1 }} isSaving={false} onPreview={vi.fn()} onApply={vi.fn()} onApplyOverlay={onApplyOverlay} />);
    fireEvent.click(screen.getByRole("button", { name: "제품 사진 화면에 얹기" }));

    expect(onApplyOverlay).toHaveBeenCalledWith(cards[0], "seg-1");
  });

  it("keeps the card actions unchanged when no overlay callback is wired", () => {
    render(<EditorAssetBrowser cards={cards} target={{ segmentId: "seg-1", startSec: 0, endSec: 1 }} isSaving={false} onPreview={vi.fn()} onApply={vi.fn()} />);

    expect(screen.queryByRole("button", { name: "제품 사진 화면에 얹기" })).toBeNull();
  });

  it("explains when no card matches the active filters", () => {
    render(<EditorAssetBrowser cards={cards} target={null} isSaving={false} onPreview={vi.fn()} onApply={vi.fn()} />);

    fireEvent.change(screen.getByRole("searchbox", { name: "자산 검색" }), { target: { value: "없는 자산" } });

    expect(screen.getByText("일치하는 자산이 없어요.")).toBeVisible();
  });

  it("groups type filters with an accessible name", () => {
    render(<EditorAssetBrowser cards={cards} target={null} isSaving={false} onPreview={vi.fn()} onApply={vi.fn()} />);

    expect(screen.getByRole("group", { name: "자산 유형 필터" })).toBeVisible();
  });

  it("shows truthful audio presence on every card", () => {
    render(<EditorAssetBrowser cards={cards} target={null} isSaving={false} onPreview={vi.fn()} onApply={vi.fn()} />);

    expect(screen.getAllByRole("article")[0]).toHaveTextContent("오디오 정보 확인 중");
    expect(screen.getAllByRole("article")[1]).toHaveTextContent("오디오 있음");
    expect(screen.getAllByRole("article")[2]).toHaveTextContent("오디오 있음");
  });

  it("shows bounded preparation and failure recovery without blocking manual apply", () => {
    const video = { ...cards[0], id: "broll:video-1", assetId: "video-1", title: "HEVC 영상", previewKind: "video" as const, requiresBrowserPreviewPreparation: true };
    const onPreview = vi.fn();
    const onRefreshExactPreview = vi.fn();
    const { rerender } = render(<EditorAssetBrowser cards={[video]} target={{ segmentId: "seg-1", startSec: 0, endSec: 1 }} isSaving={false} onPreview={onPreview} onApply={vi.fn()} previewStates={{ [video.id]: { status: "preparing" } }} onRefreshExactPreview={onRefreshExactPreview} />);

    expect(screen.getByText("원본 미리보기를 준비하고 있어요")).toBeVisible();
    expect(screen.getByRole("button", { name: "HEVC 영상 원본 미리보기" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "HEVC 영상 적용" })).toBeEnabled();

    rerender(<EditorAssetBrowser cards={[video]} target={{ segmentId: "seg-1", startSec: 0, endSec: 1 }} isSaving={false} onPreview={onPreview} onApply={vi.fn()} previewStates={{ [video.id]: { status: "failed" } }} onRefreshExactPreview={onRefreshExactPreview} />);
    fireEvent.click(screen.getByRole("button", { name: "HEVC 영상 다시 준비" }));
    fireEvent.click(screen.getByRole("button", { name: "정확한 미리보기 새로고침" }));
    expect(onPreview).toHaveBeenCalledWith(video);
    expect(onRefreshExactPreview).toHaveBeenCalledOnce();
    expect(screen.getByRole("button", { name: "HEVC 영상 적용" })).toBeEnabled();
  });

  it("keeps long card fields wrap-safe in a 390px narrow drawer fixture", () => {
    const originalWidth = window.innerWidth;
    Object.defineProperty(window, "innerWidth", { configurable: true, value: 390 });
    render(<EditorAssetBrowser cards={cards} target={null} isSaving={false} onPreview={vi.fn()} onApply={vi.fn()} />);
    const css = readFileSync(resolve(process.cwd(), "src/styles/editor-workbench.css"), "utf8");

    expect(window.innerWidth).toBe(390);
    expect(screen.getAllByRole("article")).toHaveLength(3);
    expect(css).toMatch(/\.vb-editor-assets__title,\s*\.vb-editor-assets__detail\s*\{[^}]*overflow-wrap:\s*anywhere;/);
    expect(css).toMatch(/@media \(max-width: 480px\)\s*\{\s*\.vb-editor-assets__actions > button/);

    Object.defineProperty(window, "innerWidth", { configurable: true, value: originalWidth });
  });
});

describe("orientation on the asset browser", () => {
  const card = (id: string, title: string, orientation: "가로" | "세로") => ({
    id,
    kind: "broll" as const,
    assetId: id,
    label: "영상 B-roll",
    title,
    durationLabel: "12초",
    status: "준비됨 · 검토 불필요",
    audioPresence: "오디오 없음" as const,
    orientation,
    license: "프로젝트 로컬 B-roll",
    canApply: true,
    previewUrl: "/x",
    sourceMetadata: { tags: [], source: "", creator: "", officialLicenseUrl: "", attributionRequired: false, attributionText: "" },
  });

  const cards = [card("wide", "가로 장면", "가로"), card("tall", "세로 장면", "세로")];

  it("shows which way a clip was shot", () => {
    render(<EditorAssetBrowser cards={cards} target={null} isSaving={false} onPreview={() => {}} onApply={() => {}} />);

    expect(screen.getByText(/가로 장면/)).toBeVisible();
    expect(screen.getAllByText("가로").length).toBeGreaterThan(0);
    expect(screen.getAllByText("세로").length).toBeGreaterThan(0);
  });

  it("narrows the list to vertical footage for shortform", () => {
    render(<EditorAssetBrowser cards={cards} target={null} isSaving={false} onPreview={() => {}} onApply={() => {}} />);

    fireEvent.click(screen.getByRole("button", { name: "세로 필터" }));

    expect(screen.getByText("세로 장면")).toBeVisible();
    expect(screen.queryByText("가로 장면")).toBeNull();
  });
});

describe("thumbnails in the asset browser", () => {
  const base = {
    kind: "broll" as const,
    label: "영상 B-roll",
    durationLabel: "12초",
    status: "준비됨 · 검토 불필요",
    audioPresence: "오디오 없음" as const,
    license: "프로젝트 로컬 B-roll",
    canApply: true,
    previewUrl: "/x",
    sourceMetadata: { tags: [], source: "", creator: "", officialLicenseUrl: "", attributionRequired: false, attributionText: "" },
  };

  it("shows the still so a clip can be picked by eye", () => {
    const cards = [{ ...base, id: "a", assetId: "a", title: "카페 외부", thumbnailUrl: "/api/projects/p/assets/a/thumbnail" }];
    render(<EditorAssetBrowser cards={cards} target={null} isSaving={false} onPreview={() => {}} onApply={() => {}} />);

    const image = screen.getByRole("img", { name: "카페 외부 미리 이미지" });
    expect(image).toHaveAttribute("src", "/api/projects/p/assets/a/thumbnail");
  });

  it("keeps the text label when a clip has no still", () => {
    const cards = [{ ...base, id: "b", assetId: "b", title: "예전 자산" }];
    render(<EditorAssetBrowser cards={cards} target={null} isSaving={false} onPreview={() => {}} onApply={() => {}} />);

    expect(screen.queryByRole("img")).toBeNull();
    expect(screen.getByText("예전 자산")).toBeVisible();
  });
});

describe("유진에게 알려 주는 자산 취향", () => {
  // 백엔드는 이 네 목록을 이미 읽고 있었다 -- 뺀 자산은 후보에서 아예 빠지고
  // 항상 쓰기로 둔 자산은 점수를 더 받는다. 저장하는 화면이 없어서 입력이
  // 영원히 비어 있었고 두 항목은 늘 0이었다.
  const saved = {
    pin_asset: [] as string[],
    exclude_asset: [] as string[],
    exclude_creator: [] as string[],
    exclude_tag: [] as string[],
  };

  it("프로젝트를 모르면 취향을 묻지도 보여주지도 않는다", () => {
    const read = vi.spyOn(apiModule.api, "getDirectorPreferences");
    render(<EditorAssetBrowser cards={cards} target={null} isSaving={false} onPreview={vi.fn()} onApply={vi.fn()} />);

    expect(read).not.toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: "제품 사진 항상 쓰기" })).toBeNull();
  });

  it("항상 쓰기를 저장할 때 앞서 빼 둔 자산을 지우지 않는다", async () => {
    vi.spyOn(apiModule.api, "getDirectorPreferences").mockResolvedValue({
      ...saved, exclude_asset: ["starter-sfx"], exclude_creator: ["예전 만든이"],
    } as never);
    const write = vi.spyOn(apiModule.api, "updateDirectorPreferences")
      .mockImplementation(async (_projectId, payload) => payload as never);

    render(<EditorAssetBrowser cards={cards} projectId="project-a" target={null} isSaving={false} onPreview={vi.fn()} onApply={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "제품 사진 항상 쓰기" }));

    await waitFor(() => expect(write).toHaveBeenCalledWith("project-a", {
      pin_asset: ["image-1"],
      exclude_asset: ["starter-sfx"],
      exclude_creator: ["예전 만든이"],
      exclude_tag: [],
    }));
    expect(await screen.findByRole("button", { name: "제품 사진 항상 쓰기" }))
      .toHaveAttribute("aria-pressed", "true");
  });

  it("쓰지 않기를 누르면 항상 쓰기가 함께 풀린다", async () => {
    vi.spyOn(apiModule.api, "getDirectorPreferences")
      .mockResolvedValue({ ...saved, pin_asset: ["image-1"] } as never);
    const write = vi.spyOn(apiModule.api, "updateDirectorPreferences")
      .mockImplementation(async (_projectId, payload) => payload as never);

    render(<EditorAssetBrowser cards={cards} projectId="project-a" target={null} isSaving={false} onPreview={vi.fn()} onApply={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "제품 사진 쓰지 않기" }));

    await waitFor(() => expect(write).toHaveBeenCalledWith("project-a", {
      pin_asset: [], exclude_asset: ["image-1"], exclude_creator: [], exclude_tag: [],
    }));
  });

  it("만든이와 분위기를 빼고 다시 되돌릴 수 있다", async () => {
    vi.spyOn(apiModule.api, "getDirectorPreferences").mockResolvedValue(saved as never);
    const write = vi.spyOn(apiModule.api, "updateDirectorPreferences")
      .mockImplementation(async (_projectId, payload) => payload as never);

    render(<EditorAssetBrowser cards={cards} projectId="project-a" target={null} isSaving={false} onPreview={vi.fn()} onApply={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "배경 음악 1의 만든이 Creator 빼기" }));

    await waitFor(() => expect(write).toHaveBeenCalledWith("project-a", {
      pin_asset: [], exclude_asset: [], exclude_creator: ["Creator"], exclude_tag: [],
    }));

    fireEvent.click(await screen.findByRole("button", { name: "배경 음악 1의 분위기 음악 빼기" }));
    await waitFor(() => expect(write).toHaveBeenLastCalledWith("project-a", {
      pin_asset: [], exclude_asset: [], exclude_creator: ["Creator"], exclude_tag: ["음악"],
    }));

    // 뺀 뒤에도 되돌릴 자리가 있어야 한다 -- 카드가 걸러져 사라지면 취소할
    // 방법이 없다.
    fireEvent.click(await screen.findByRole("button", { name: "Creator 만든이 다시 쓰기" }));

    await waitFor(() => expect(write).toHaveBeenLastCalledWith("project-a", {
      pin_asset: [], exclude_asset: [], exclude_creator: [], exclude_tag: ["음악"],
    }));
  });

  it("저장에 실패하면 눌린 상태를 되돌리고 그렇게 말한다", async () => {
    vi.spyOn(apiModule.api, "getDirectorPreferences").mockResolvedValue(saved as never);
    vi.spyOn(apiModule.api, "updateDirectorPreferences").mockRejectedValue(new Error("nope"));

    render(<EditorAssetBrowser cards={cards} projectId="project-a" target={null} isSaving={false} onPreview={vi.fn()} onApply={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "제품 사진 항상 쓰기" }));

    expect(await screen.findByText("추천 취향을 저장하지 못했어요. 잠시 뒤 다시 눌러 주세요.")).toBeVisible();
    expect(screen.getByRole("button", { name: "제품 사진 항상 쓰기" }))
      .toHaveAttribute("aria-pressed", "false");
  });
});
