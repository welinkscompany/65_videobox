import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

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
    sourceMetadata: { tags: ["제품"], source: "프로젝트 로컬 B-roll", creator: "", officialLicenseUrl: "", attributionRequired: false, attributionText: "" },
  },
  {
    id: "library:bgm-1",
    kind: "bgm",
    assetId: "starter-bgm",
    libraryAssetId: "bgm-1",
    label: "BGM",
    title: "BGM 1",
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
    label: "SFX",
    title: "SFX 1",
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
    fireEvent.click(screen.getByRole("button", { name: "BGM 필터" }));
    expect(screen.getByRole("button", { name: "BGM 필터" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("heading", { name: "BGM 1" })).toBeVisible();
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

    expect(screen.getByRole("status")).toHaveTextContent("적용할 나레이션 구간을 먼저 선택하세요.");
    screen.getAllByRole("article").forEach((card) => expect(card).toHaveTextContent("적용할 나레이션 구간을 먼저 선택하세요."));
    expect(screen.getByRole("button", { name: "제품 사진 적용" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "SFX 1 적용" })).toBeDisabled();

    rerender(<EditorAssetBrowser cards={cards} target={{ segmentId: "seg-1", startSec: 0, endSec: 1 }} isSaving onPreview={vi.fn()} onApply={onApply} />);
    expect(screen.getByRole("button", { name: "제품 사진 적용" })).toBeDisabled();

    rerender(<EditorAssetBrowser cards={cards} target={{ segmentId: "seg-1", startSec: 0, endSec: 1 }} isSaving={false} onPreview={vi.fn()} onApply={onApply} />);
    fireEvent.click(screen.getByRole("button", { name: "제품 사진 적용" }));
    expect(onApply).toHaveBeenCalledWith(cards[0], "seg-1");
    expect(screen.getByRole("button", { name: "SFX 1 적용" })).toBeDisabled();
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
