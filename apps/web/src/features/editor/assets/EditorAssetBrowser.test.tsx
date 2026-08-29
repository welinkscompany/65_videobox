import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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

/** **갱신 이유(2026-08-27).** 왼쪽 도크가 캡컷처럼 `미디어 · 오디오 · 전환`
 *  최상위 탭으로 갈렸다. 아래 시험들은 소리 자산이 **기본 화면에 같이 있다**는
 *  전제로 쓰여 있었는데 그 전제가 바뀌었다. 지키려는 것(줄로 눕는가, 적용이
 *  되는가, 소리 유무를 사실대로 말하는가)은 그대로 두고 **가는 길만** 맞춘다. */
function openAudioPane(): void {
  fireEvent.click(screen.getByRole("tab", { name: "오디오" }));
}

describe("EditorAssetBrowser", () => {
  it("filters by type and query, shows the selected range, and previews through a callback without media", () => {
    const onPreview = vi.fn();
    const { container } = render(<EditorAssetBrowser cards={cards} target={{ segmentId: "seg-1", startSec: 3, endSec: 7 }} isSaving={false} onPreview={onPreview} onApply={vi.fn()} />);

    screen.getAllByRole("article").forEach((card) => expect(card).toHaveTextContent("적용 구간: 3.00–7.00초"));
    // **갱신 이유(2026-08-22).** 알약이 캡컷식 탭이 됐다(owner: "캡컷은 대부분
    // 메뉴들을 탭으로 정리해서 깔끔하게 만들었어"). 이름에서 `필터`가 빠지고
    // 역할이 `button`에서 `tab`이 됐다. 지키려는 것은 "종류로 좁힐 수 있다"이지
    // 알약이 아니었으므로, 지키는 것은 그대로 두고 부르는 이름만 맞춘다.
    openAudioPane();
    fireEvent.click(screen.getByRole("tab", { name: "음악" }));
    expect(screen.getByRole("tab", { name: "음악" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("heading", { name: "배경 음악 1" })).toBeVisible();
    expect(screen.queryByRole("heading", { name: "제품 사진" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: "미디어" }));
    fireEvent.change(screen.getByRole("searchbox", { name: "미디어 검색" }), { target: { value: "제품" } });
    fireEvent.click(screen.getByRole("button", { name: "제품 사진 원본 미리보기" }));

    expect(onPreview).toHaveBeenCalledWith(cards[0]);
    expect(screen.getByRole("status")).toHaveTextContent("적용 구간: 3.00–7.00초");
    expect(screen.getByRole("article")).toHaveTextContent("적용 구간: 3.00–7.00초");
    expect(screen.getByText("직접 선택한 미디어")).toBeVisible();
    expect(container.querySelectorAll("audio, video")).toHaveLength(0);
  });

  it("lays sound assets out as rows and keeps picture assets as cards", () => {
    // `capcut-observed` 기록 §5 오디오: "오른쪽은 격자가 아니라 목록이다 --
    // 앨범 그림 + 곡명 + `아티스트 · 길이`". 음악·효과음은 썸네일이 없어
    // 카드로 그리면 글자만 든 빈 상자가 되고, 효과음이 100개면 한 화면에 몇
    // 개 못 본다. 같은 `article`을 눕히는 방식이라 단추는 그대로 살아 있다.
    const { container } = render(<EditorAssetBrowser cards={cards} target={{ segmentId: "seg-1", startSec: 3, endSec: 7 }} isSaving={false} onPreview={vi.fn()} onApply={vi.fn()} />);

    const rowOf = (title: string) => screen.getByRole("heading", { name: title }).closest("article");
    // 그림은 미디어 탭에서 카드로.
    expect(rowOf("제품 사진")).not.toHaveClass("vb-editor-assets__card--row");
    // 소리는 오디오 탭에서 줄로. 이제 둘은 같은 탭에 함께 있지 않다.
    openAudioPane();
    expect(rowOf("배경 음악 1")).toHaveClass("vb-editor-assets__card--row");
    // 소리 줄에도 눈에 걸리는 것이 있어야 한다 -- 캡컷 오디오 줄의 앨범 그림 자리.
    expect(rowOf("배경 음악 1")?.querySelector(".vb-editor-assets__wave")).not.toBeNull();
    // 눕혀도 적용·미리듣기는 그대로다. 이게 깨지면 보기 좋아지고 못 쓰게 된다.
    expect(screen.getByRole("button", { name: "배경 음악 1 적용" })).toBeInTheDocument();
    expect(container.querySelectorAll("audio, video")).toHaveLength(0);
  });

  it("keeps rights wording on a sound row, where attribution actually applies", () => {
    // 줄로 눕히면서 되풀이되는 설명을 접었는데, 처음엔 라이선스 줄까지 같이
    // 접혔다. 음악·효과음이 **출처 표기가 걸리는 바로 그 자산**이라, 상태와
    // 라이선스는 접으면 안 된다. 접는 것은 `소리 있음`(음악에선 당연한 말),
    // `직접 선택한 미디어`(모든 카드가 같은 문구), 적용 구간(패널 맨 위가 말함)뿐.
    render(<EditorAssetBrowser cards={cards} target={{ segmentId: "seg-1", startSec: 3, endSec: 7 }} isSaving={false} onPreview={vi.fn()} onApply={vi.fn()} />);
    openAudioPane();

    const row = screen.getByRole("heading", { name: "배경 음악 1" }).closest("article");
    // 줄에서는 짧은 표기만 보이고, URL을 포함한 전체 문구는 `title`에 남는다.
    const attribution = row?.querySelector(".vb-editor-assets__attribution");
    expect(attribution?.textContent).toContain("출처 표기");
    expect(attribution?.getAttribute("title")).toContain("라이선스:");
    expect(row?.querySelector(".vb-editor-assets__status")?.textContent).toContain("이용 가능");
  });

  it("applies the exact card and target segment only when target, save state, and availability permit", () => {
    const onApply = vi.fn();
    const { rerender } = render(<EditorAssetBrowser cards={cards} target={null} isSaving={false} onPreview={vi.fn()} onApply={onApply} />);

    expect(screen.getByRole("status")).toHaveTextContent("적용할 내레이션 구간을 먼저 선택하세요.");
    screen.getAllByRole("article").forEach((card) => expect(card).toHaveTextContent("적용할 내레이션 구간을 먼저 선택하세요."));
    expect(screen.getByRole("button", { name: "제품 사진 적용" })).toBeDisabled();
    openAudioPane();
    expect(screen.getByRole("button", { name: "효과음 1 적용" })).toBeDisabled();
    fireEvent.click(screen.getByRole("tab", { name: "미디어" }));

    rerender(<EditorAssetBrowser cards={cards} target={{ segmentId: "seg-1", startSec: 0, endSec: 1 }} isSaving onPreview={vi.fn()} onApply={onApply} />);
    expect(screen.getByRole("button", { name: "제품 사진 적용" })).toBeDisabled();

    rerender(<EditorAssetBrowser cards={cards} target={{ segmentId: "seg-1", startSec: 0, endSec: 1 }} isSaving={false} onPreview={vi.fn()} onApply={onApply} />);
    fireEvent.click(screen.getByRole("button", { name: "제품 사진 적용" }));
    expect(onApply).toHaveBeenCalledWith(cards[0], "seg-1");
    openAudioPane();
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

  it("offers a picture filter so the shared library's pictures can be narrowed to", () => {
    const pictureCard: EditorAssetCard = {
      id: "library-image:user_image_1",
      kind: "image",
      assetId: "",
      libraryAssetId: "user_image_1",
      label: "그림",
      title: "바다.png",
      durationLabel: "",
      status: "준비됨",
      audioPresence: "오디오 없음",
      license: "내 그림",
      canApply: true,
      previewUrl: "/api/library/assets/user_image_1/preview",
      previewKind: "image",
      sourceMetadata: { tags: [], source: "미디어", creator: "", officialLicenseUrl: "", attributionRequired: false, attributionText: "" },
    };
    render(<EditorAssetBrowser cards={[...cards, pictureCard]} target={{ segmentId: "seg-1", startSec: 0, endSec: 1 }} isSaving={false} onPreview={vi.fn()} onApply={vi.fn()} onApplyOverlay={vi.fn()} />);

    fireEvent.click(screen.getByRole("tab", { name: "그림" }));
    expect(screen.getByRole("button", { name: "바다.png 화면에 얹기" })).toBeEnabled();
    expect(screen.queryByRole("button", { name: "제품 사진 화면에 얹기" })).toBeNull();
  });

  it("keeps the card actions unchanged when no overlay callback is wired", () => {
    render(<EditorAssetBrowser cards={cards} target={{ segmentId: "seg-1", startSec: 0, endSec: 1 }} isSaving={false} onPreview={vi.fn()} onApply={vi.fn()} />);

    expect(screen.queryByRole("button", { name: "제품 사진 화면에 얹기" })).toBeNull();
  });

  it("explains when no card matches the active filters", () => {
    render(<EditorAssetBrowser cards={cards} target={null} isSaving={false} onPreview={vi.fn()} onApply={vi.fn()} />);

    fireEvent.change(screen.getByRole("searchbox", { name: "미디어 검색" }), { target: { value: "없는 미디어" } });

    expect(screen.getByText("일치하는 미디어가 없어요.")).toBeVisible();
  });

  it("groups type filters with an accessible name", () => {
    render(<EditorAssetBrowser cards={cards} target={null} isSaving={false} onPreview={vi.fn()} onApply={vi.fn()} />);

    expect(screen.getByRole("tablist", { name: "미디어 종류" })).toBeVisible();
  });

  it("shows truthful audio presence on every card", () => {
    render(<EditorAssetBrowser cards={cards} target={null} isSaving={false} onPreview={vi.fn()} onApply={vi.fn()} />);

    // 탭이 갈렸으므로 미디어 탭의 영상과 오디오 탭의 음악·효과음을 각각 본다.
    expect(screen.getAllByRole("article")[0]).toHaveTextContent("오디오 정보 확인 중");
    openAudioPane();
    expect(screen.getAllByRole("article")[0]).toHaveTextContent("오디오 있음");
    expect(screen.getAllByRole("article")[1]).toHaveTextContent("오디오 있음");
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
    // 미디어 탭 1장 + 오디오 탭 2줄 = 셋. 좁은 서랍에서 줄바꿈이 안전한지가 요점이다.
    expect(screen.getAllByRole("article")).toHaveLength(1);
    openAudioPane();
    expect(screen.getAllByRole("article")).toHaveLength(2);
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

    fireEvent.click(screen.getByRole("button", { name: "세로" }));

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
    // 음악은 이제 오디오 탭에 있다(캡컷식 최상위 탭 분리, 2026-08-27).
    openAudioPane();
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

describe("자산 내역 길이", () => {
  // owner: "자산 내역에 스크롤이 엄청 길다니까.. 대체 이건 몇번 말해"
  //
  // 카드 한 장에 썸네일·제목·설명·태그·단추가 다 들어간다. 맞는 것을 전부 그리면
  // 자산이 늘어나는 만큼 스크롤이 길어지고, 아래쪽은 아무도 못 본다.
  function manyCards(count: number) {
    return Array.from({ length: count }, (_, index) => ({
      id: `broll:${index}`, kind: "broll" as const, assetId: `asset-${index}`,
      label: `장면 영상 ${index}`, title: `촬영본 ${index}`, durationLabel: "4초",
      status: "준비됨", audioPresence: "오디오 없음" as const, license: "프로젝트 로컬 B-roll",
      canApply: true, previewUrl: `/api/x/${index}`, previewKind: "video" as const,
      sourceMetadata: { tags: [], source: "", creator: "", officialLicenseUrl: "", attributionRequired: false, attributionText: "" },
    }));
  }

  it("한 화면에서 훑을 만큼만 그리고, 나머지는 눌러서 편다", () => {
    render(<EditorAssetBrowser cards={manyCards(30) as never} target={null as never} isSaving={false} onPreview={vi.fn()} onApply={vi.fn()} onApplyOverlay={vi.fn()} />);

    expect(screen.getAllByRole("button", { name: /촬영본 \d+ 적용/ }).length).toBeLessThanOrEqual(8);
    expect(screen.getByRole("button", { name: "22개 더 보기" })).toBeVisible();
  });

  it("적을 때는 더 보기가 나오지 않는다", () => {
    render(<EditorAssetBrowser cards={manyCards(3) as never} target={null as never} isSaving={false} onPreview={vi.fn()} onApply={vi.fn()} onApplyOverlay={vi.fn()} />);

    expect(screen.queryByRole("button", { name: /더 보기/ })).toBeNull();
  });
});

/** owner(2026-08-27): "우리 메뉴가 너무 각각 페이지별로 따로 놀아. 이걸 캡컷처럼
 *  편집기 기반처럼 쉽게 확인하도록 팝업으로 만든다던지 하는게 나을거 같어."
 *
 *  재 보니 **편집기 안에서는 새 미디어를 추가할 길이 아예 없었다.** 파일 입력도,
 *  미디어 화면으로 나가는 링크조차 없었다. 쓰려면 위 띠에서 미디어 단계를 눌러
 *  화면을 떠나야 한다는 것을 스스로 알아내야 했다.
 *
 *  캡컷은 미디어 탭 안에서 바로 가져온다. 여기서 지키는 것은 **편집기를 떠나지
 *  않고 미디어를 더할 수 있는가**다.
 *  → `docs/decisions/2026-08-27-editor-centered-shell-direction.ko.md` */
describe("편집기에서 미디어 더하기", () => {
  it("편집기를 떠나지 않고 파일을 더할 수 있다", () => {
    render(<EditorAssetBrowser cards={cards as never} target={null as never} isSaving={false} onPreview={vi.fn()} onApply={vi.fn()} onApplyOverlay={vi.fn()} projectId="project-a" />);

    // **갱신 이유(2026-08-27).** 네이티브 파일칸을 그대로 두니 좁은 도크에서
    // `파일 선택 | 선택된 파일 없음`까지 그려 한 줄을 통째로 먹었다. 입력은 감추고
    // 단추로 연다. 지키려던 것은 **떠나지 않고 더할 수 있는가**이지 입력칸이
    // 눈에 보이는 것이 아니었으므로, 지키는 것은 그대로 두고 잡는 곳만 옮긴다.
    expect(screen.getByRole("button", { name: "파일 추가" })).toBeVisible();
    expect(screen.getByLabelText("파일 추가")).toHaveAttribute("type", "file");
  });

  it("고른 파일을 라이브러리에 넣고 이 프로젝트로 가져온다", async () => {
    const ingest = vi.spyOn(apiModule.api, "ingestLibraryAssets").mockResolvedValue({ items: [{ library_asset_id: "lib-1", state: "ready", filename: "a.mp4" }] } as never);
    const materialize = vi.spyOn(apiModule.api, "materializeLibraryAsset").mockResolvedValue({} as never);
    const onAdded = vi.fn();
    render(<EditorAssetBrowser cards={cards as never} target={null as never} isSaving={false} onPreview={vi.fn()} onApply={vi.fn()} onApplyOverlay={vi.fn()} projectId="project-a" onMediaAdded={onAdded} />);

    fireEvent.change(screen.getByLabelText("파일 추가"), { target: { files: [new File(["x"], "a.mp4", { type: "video/mp4" })] } });

    await waitFor(() => expect(materialize).toHaveBeenCalledWith("lib-1", "project-a"));
    expect(ingest).toHaveBeenCalled();
    // 더해진 것이 목록에 바로 보이도록 부른 쪽에 알린다.
    await waitFor(() => expect(onAdded).toHaveBeenCalled());
  });
});

/** owner(2026-08-27): "이걸 캡컷처럼 편집기 기반처럼 쉽게 확인하도록 팝업으로
 *  만든다던지 하는게 나을거 같어."
 *
 *  내레이션은 영상·음악·효과음과 같은 **미디어**다(`VoiceMaterialPanel` 주석).
 *  그런데 그 자리가 미디어 화면에만 있어서, 편집하다 목소리를 넣으려면 화면을
 *  떠나야 했다.
 *
 *  좁은 도크(220~400px)에 목소리 등록·후보 생성까지 밀어 넣지 않는다 -- **팝업으로
 *  연다.** 지키는 것은 **편집기를 떠나지 않고 내레이션에 닿는가**다.
 *  → `docs/decisions/2026-08-27-editor-centered-shell-direction.ko.md` */
describe("편집기에서 내레이션 열기", () => {
  it("편집기를 떠나지 않고 내레이션을 연다", async () => {
    render(<EditorAssetBrowser cards={cards as never} target={null as never} isSaving={false} onPreview={vi.fn()} onApply={vi.fn()} onApplyOverlay={vi.fn()} projectId="project-a" />);

    fireEvent.click(screen.getByRole("button", { name: "내레이션" }));

    expect(await screen.findByRole("dialog", { name: "내레이션" })).toBeVisible();
  });

  it("프로젝트를 모르면 내레이션을 열지 않는다", () => {
    // 프로젝트 없이 열면 빈 화면이 뜬다. 없는 길을 흉내 내지 않는다.
    render(<EditorAssetBrowser cards={cards as never} target={null as never} isSaving={false} onPreview={vi.fn()} onApply={vi.fn()} onApplyOverlay={vi.fn()} />);

    expect(screen.queryByRole("button", { name: "내레이션" })).toBeNull();
  });
});

/** 미디어 화면의 `가져오기` 탭에는 길이 둘이었다 -- 새 파일 올리기와, 따로 모아 둔
 *  **촬영본**에서 고르기. 앞의 것은 도크에 바로 붙였고(`미디어 파일 추가`), 뒤의
 *  것은 목록을 보여 줘야 해서 팝업으로 연다.
 *  → `docs/decisions/2026-08-27-editor-centered-shell-direction.ko.md` */
describe("편집기에서 촬영본 가져오기", () => {
  it("따로 모아 둔 촬영본을 골라 이 프로젝트로 가져온다", async () => {
    vi.spyOn(apiModule.api, "listMediaInboxAssets").mockResolvedValue([{ filename: "cut-01.mp4", size_bytes: 1024 }] as never);
    const importAsset = vi.spyOn(apiModule.api, "importMediaInboxAsset").mockResolvedValue({} as never);
    const onAdded = vi.fn();
    render(<EditorAssetBrowser cards={cards as never} target={null as never} isSaving={false} onPreview={vi.fn()} onApply={vi.fn()} onApplyOverlay={vi.fn()} projectId="project-a" onMediaAdded={onAdded} />);

    fireEvent.click(screen.getByRole("button", { name: "촬영본" }));
    const dialog = await screen.findByRole("dialog", { name: "촬영본 가져오기" });

    fireEvent.click(await within(dialog).findByRole("button", { name: "cut-01.mp4 가져오기" }));

    await waitFor(() => expect(importAsset).toHaveBeenCalledWith("project-a", "cut-01.mp4"));
    await waitFor(() => expect(onAdded).toHaveBeenCalled());
  });

  it("모아 둔 촬영본이 없으면 그렇게 말한다", async () => {
    vi.spyOn(apiModule.api, "listMediaInboxAssets").mockResolvedValue([] as never);
    render(<EditorAssetBrowser cards={cards as never} target={null as never} isSaving={false} onPreview={vi.fn()} onApply={vi.fn()} onApplyOverlay={vi.fn()} projectId="project-a" />);

    fireEvent.click(screen.getByRole("button", { name: "촬영본" }));
    const dialog = await screen.findByRole("dialog", { name: "촬영본 가져오기" });

    expect(await within(dialog).findByText("아직 따로 모아 둔 영상이 없어요.")).toBeVisible();
  });

  /** 재설계안 §2.3 item 3: `/footage`에서 이미 장면을 나눠 승인해 둔 가상
   *  묶음을, 편집기 촬영본 팝업 안 새 탭에서 곧장 가져올 수 있어야 한다.
   *  `/footage`의 나누기·타임라인 UI는 복제하지 않는다 -- 여기는 "묶음 하나를
   *  고르는 목록"일 뿐이다.
   *  → `docs/superpowers/specs/2026-08-27-library-footage-projects-redesign-plan.ko.md` §2.3, §2.4 */
  it("이미 정리한 묶음 탭에서 승인된 가상 묶음을 골라 이 프로젝트로 가져온다", async () => {
    vi.spyOn(apiModule.api, "listMediaInboxAssets").mockResolvedValue([] as never);
    vi.spyOn(apiModule.api, "listApprovedFootageSequences").mockResolvedValue({
      sequences: [
        {
          sequence_id: "vseq-1",
          source_id: "source-1",
          source_sha256: "hash-1",
          sources: [{ source_id: "source-1", source_sha256: "hash-1", library_asset_id: "asset-take" }],
          name: "해변 장면 묶음",
          revision: 1,
          items: [
            { item_id: "item-1", source_segment_id: "seg-1", source_id: "source-1", item_order: 1, start_sec: 0, end_sec: 2 },
            { item_id: "item-2", source_segment_id: "seg-2", source_id: "source-1", item_order: 2, start_sec: 2, end_sec: 4 },
          ],
        },
      ],
    } as never);
    const materialize = vi.spyOn(apiModule.api, "materializeLibraryAsset").mockResolvedValue({} as never);
    const onAdded = vi.fn();
    render(<EditorAssetBrowser cards={cards as never} target={null as never} isSaving={false} onPreview={vi.fn()} onApply={vi.fn()} onApplyOverlay={vi.fn()} projectId="project-a" onMediaAdded={onAdded} />);

    fireEvent.click(screen.getByRole("button", { name: "촬영본" }));
    const dialog = await screen.findByRole("dialog", { name: "촬영본 가져오기" });

    fireEvent.click(within(dialog).getByRole("tab", { name: "이미 정리한 묶음" }));
    fireEvent.click(await within(dialog).findByRole("button", { name: "해변 장면 묶음 가져오기" }));

    await waitFor(() => expect(materialize).toHaveBeenCalledWith("asset-take", "project-a"));
    await waitFor(() => expect(onAdded).toHaveBeenCalled());
  });

  it("승인된 묶음이 없으면 그렇게 말한다", async () => {
    vi.spyOn(apiModule.api, "listMediaInboxAssets").mockResolvedValue([] as never);
    vi.spyOn(apiModule.api, "listApprovedFootageSequences").mockResolvedValue({ sequences: [] } as never);
    render(<EditorAssetBrowser cards={cards as never} target={null as never} isSaving={false} onPreview={vi.fn()} onApply={vi.fn()} onApplyOverlay={vi.fn()} projectId="project-a" />);

    fireEvent.click(screen.getByRole("button", { name: "촬영본" }));
    const dialog = await screen.findByRole("dialog", { name: "촬영본 가져오기" });

    fireEvent.click(within(dialog).getByRole("tab", { name: "이미 정리한 묶음" }));

    expect(await within(dialog).findByText("아직 승인해 둔 묶음이 없어요.")).toBeVisible();
  });
});

/** 여러 프로젝트가 함께 쓰는 `/library`(전체 관리 화면)에서 편집기를 떠나지 않고
 *  자산 하나를 골라 들여올 길. 관리(올리기·휴지통·사용처 확인)는 이 팝업에
 *  넣지 않는다 -- "고르기"만 한다.
 *  → `docs/superpowers/specs/2026-08-27-library-footage-projects-redesign-plan.ko.md` §1.3 */
describe("편집기에서 라이브러리 자산 가져오기", () => {
  it("라이브러리에서 골라 이 프로젝트로 가져온다", async () => {
    vi.spyOn(apiModule.api, "listLibraryAssets").mockResolvedValue({
      assets: [{ library_asset_id: "lib-9", media_type: "broll", origin: "upload", lifecycle: "ready", user_metadata: { filename: "해변.mp4" } }],
      total: 1,
    } as never);
    const materialize = vi.spyOn(apiModule.api, "materializeLibraryAsset").mockResolvedValue({} as never);
    const onAdded = vi.fn();
    render(<EditorAssetBrowser cards={cards as never} target={null as never} isSaving={false} onPreview={vi.fn()} onApply={vi.fn()} onApplyOverlay={vi.fn()} projectId="project-a" onMediaAdded={onAdded} />);

    fireEvent.click(screen.getByRole("button", { name: "라이브러리에서 가져오기" }));
    const dialog = await screen.findByRole("dialog", { name: "라이브러리에서 가져오기" });

    fireEvent.click(await within(dialog).findByRole("article", { name: "해변.mp4" }));
    fireEvent.click(within(dialog).getByRole("button", { name: "가져오기" }));

    await waitFor(() => expect(materialize).toHaveBeenCalledWith("lib-9", "project-a"));
    await waitFor(() => expect(onAdded).toHaveBeenCalled());
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "라이브러리에서 가져오기" })).toBeNull());
  });
});

/** owner(2026-08-27): "캡컷 메뉴 하나하나 세세하게 확인해서 우리거에 벤치마킹해줘"
 *  → 확인 결과 owner 결정: **있는 것만 자리 맞추기.**
 *
 *  공식 매뉴얼로 대조하니 캡컷 왼쪽 패널은 `미디어 · 오디오 · 텍스트 · 스티커 ·
 *  효과 · 전환 · 필터`가 **최상위 탭**이다. 우리는 영상·음악·효과음·그림이 한 줄에
 *  섞여 있었고, **전환은 아예 오른쪽 속성 패널 안에 있었다** -- 기능은 6종 다
 *  있는데 캡컷을 아는 사람이 왼쪽에서 찾으면 없다.
 *
 *  스티커·효과·필터는 우리에게 없으므로 **탭을 만들지 않는다.** 없는 기능의 자리를
 *  흉내 내면 배치가 거짓말을 한다.
 *  → `docs/decisions/2026-08-27-editor-centered-shell-direction.ko.md` */
describe("왼쪽 도크는 캡컷처럼 최상위 탭으로 갈린다", () => {
  it("가진 것만 최상위 탭으로 둔다", () => {
    render(<EditorAssetBrowser cards={cards as never} target={null as never} isSaving={false} onPreview={vi.fn()} onApply={vi.fn()} onApplyOverlay={vi.fn()} projectId="project-a" />);

    const panes = screen.getByRole("tablist", { name: "왼쪽 패널" });
    expect(Array.from(panes.querySelectorAll('[role="tab"]')).map((tab) => tab.textContent?.trim())).toEqual(["미디어", "오디오", "전환"]);
    // 없는 것은 탭도 만들지 않는다.
    for (const absent of ["스티커", "효과", "필터"]) {
      expect(screen.queryByRole("tab", { name: absent })).toBeNull();
    }
  });

  it("오디오 탭은 소리만 보여 준다", () => {
    render(<EditorAssetBrowser cards={cards as never} target={null as never} isSaving={false} onPreview={vi.fn()} onApply={vi.fn()} onApplyOverlay={vi.fn()} projectId="project-a" />);

    fireEvent.click(screen.getByRole("tab", { name: "오디오" }));

    expect(screen.getByText("배경 음악 1")).toBeVisible();
    expect(screen.queryByText("제품 사진")).toBeNull();
  });

  it("전환 탭에서 고르면 앞 장면에서 넘어오는 방법이 저장된다", () => {
    const onInspectorAction = vi.fn();
    render(<EditorAssetBrowser cards={cards as never} target={null as never} isSaving={false} onPreview={vi.fn()} onApply={vi.fn()} onApplyOverlay={vi.fn()} projectId="project-a" transitionTarget={{ segmentId: "scene-2", hasPrevious: true }} onInspectorAction={onInspectorAction} />);

    fireEvent.click(screen.getByRole("tab", { name: "전환" }));
    fireEvent.click(screen.getByRole("button", { name: "서서히 겹치기 적용" }));

    expect(onInspectorAction).toHaveBeenCalledWith(expect.objectContaining({
      kind: "set-transition", segmentId: "scene-2",
    }));
  });

  it("앞 장면이 없으면 전환을 걸 수 없다고 말한다", () => {
    render(<EditorAssetBrowser cards={cards as never} target={null as never} isSaving={false} onPreview={vi.fn()} onApply={vi.fn()} onApplyOverlay={vi.fn()} projectId="project-a" transitionTarget={{ segmentId: "scene-1", hasPrevious: false }} onInspectorAction={vi.fn()} />);

    fireEvent.click(screen.getByRole("tab", { name: "전환" }));

    expect(screen.getByText("첫 장면에는 넘어올 앞 장면이 없어요.")).toBeVisible();
  });
});

/** owner(2026-08-27): "지금 사진 부분이 스크롤이 너무 길다고, 여길 뭔가 정리를
 *  해야지, 내용을 쉽게 찾고, 검색하고 정리해서 가져올거 아니야"
 *
 *  실측: 왼쪽 도크는 보이는 높이 **137px**인데 내용이 **1,608px**이었다 --
 *  **11.7배 스크롤**. 미디어 아래에 `영상 구성 · 소스 확인 · 대본 · 자막`이
 *  세로로 더 쌓여 있었기 때문이다. 캡컷 왼쪽 패널은 **한 번에 하나**만 보여 준다.
 *
 *  `영상 구성`은 타임라인 머리말이 이미 같은 말을 하므로(`n개 트랙 · n개 자막 ·
 *  n개 미디어 공백`) 없앤다. 자막은 캡컷 `텍스트` 자리에 해당하므로 탭이 된다.
 *  → `docs/decisions/2026-08-27-editor-centered-shell-direction.ko.md` */
describe("왼쪽 도크는 한 번에 하나만 보여 준다", () => {
  it("자막이 있으면 탭이 되고, 다른 탭에서는 안 보인다", () => {
    render(<EditorAssetBrowser cards={cards as never} target={null as never} isSaving={false} onPreview={vi.fn()} onApply={vi.fn()} onApplyOverlay={vi.fn()} projectId="project-a" transcript={<p>대본 자리</p>} />);

    const panes = screen.getByRole("tablist", { name: "왼쪽 패널" });
    expect(Array.from(panes.querySelectorAll('[role="tab"]')).map((tab) => tab.textContent?.trim())).toEqual(["미디어", "오디오", "자막", "전환"]);
    // 미디어 탭에서는 대본이 같이 쌓이지 않는다 -- 이것이 11.7배 스크롤의 원인이었다.
    expect(screen.queryByText("대본 자리")).toBeNull();

    fireEvent.click(screen.getByRole("tab", { name: "자막" }));
    expect(screen.getByText("대본 자리")).toBeVisible();
    // 자막 탭에서는 미디어 카드가 섞이지 않는다.
    expect(screen.queryByRole("heading", { name: "제품 사진" })).toBeNull();
  });

  it("자막을 주지 않으면 그 탭도 만들지 않는다", () => {
    render(<EditorAssetBrowser cards={cards as never} target={null as never} isSaving={false} onPreview={vi.fn()} onApply={vi.fn()} onApplyOverlay={vi.fn()} projectId="project-a" />);

    expect(screen.queryByRole("tab", { name: "자막" })).toBeNull();
  });

  it("소스 확인은 미디어 탭 안에 둔다", () => {
    render(<EditorAssetBrowser cards={cards as never} target={null as never} isSaving={false} onPreview={vi.fn()} onApply={vi.fn()} onApplyOverlay={vi.fn()} projectId="project-a" sourceCheck={<p>소스 자리</p>} />);

    expect(screen.getByText("소스 자리")).toBeVisible();
    fireEvent.click(screen.getByRole("tab", { name: "오디오" }));
    expect(screen.queryByText("소스 자리")).toBeNull();
  });
});
