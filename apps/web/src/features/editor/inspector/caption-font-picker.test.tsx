import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "../../../api";
import { CaptionFontPicker } from "./CaptionFontPicker";

const library = {
  fonts: [
    { family: "Pretendard", label: "프리텐다드", group: "본문" },
    { family: "Black Han Sans", label: "검은고딕", group: "제목" },
    { family: "Gaegu", label: "개구쟁이", group: "손글씨" },
  ],
  default_family: "Pretendard",
  favorites: [],
  recents: [],
};

describe("자막 글꼴 고르기", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(api.api, "markRecentCaptionFont").mockResolvedValue({ recents: [] } as never);
    vi.spyOn(api.api, "toggleCaptionFontFavorite").mockResolvedValue({ favorites: [] } as never);
  });

  it("설치된 글꼴만 보여주고, 고르면 그 이름을 넘긴다", async () => {
    // 자유 입력이던 시절에는 없는 글꼴을 쳐도 화면이 받아들이고, 완성본에서만
    // 다른 글꼴로 나왔다.
    vi.spyOn(api.api, "listCaptionFonts").mockResolvedValue(library as never);
    const onSelect = vi.fn();

    render(<CaptionFontPicker value="Pretendard" onSelect={onSelect} />);

    fireEvent.click(await screen.findByRole("button", { name: "검은고딕 고르기" }));

    await waitFor(() => expect(onSelect).toHaveBeenCalledWith("Black Han Sans"));
  });

  it("고른 글꼴을 최근으로 올린다", async () => {
    vi.spyOn(api.api, "listCaptionFonts").mockResolvedValue(library as never);
    const mark = vi.spyOn(api.api, "markRecentCaptionFont").mockResolvedValue({ recents: ["Gaegu"] } as never);

    render(<CaptionFontPicker value="Pretendard" onSelect={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "개구쟁이 고르기" }));

    await waitFor(() => expect(mark).toHaveBeenCalledWith("Gaegu"));
  });

  it("즐겨찾기한 글꼴을 맨 위에 둔다", async () => {
    vi.spyOn(api.api, "listCaptionFonts").mockResolvedValue({ ...library, favorites: ["Gaegu"] } as never);

    render(<CaptionFontPicker value="Pretendard" onSelect={vi.fn()} />);
    await screen.findByRole("button", { name: "개구쟁이 즐겨찾기 해제" });

    expect(screen.getAllByRole("listitem")[0]).toHaveTextContent("개구쟁이");
  });

  it("즐겨찾기 다음은 최근에 쓴 것이다", async () => {
    vi.spyOn(api.api, "listCaptionFonts").mockResolvedValue(
      { ...library, favorites: ["Gaegu"], recents: ["Black Han Sans"] } as never,
    );

    render(<CaptionFontPicker value="Pretendard" onSelect={vi.fn()} />);
    await screen.findByRole("button", { name: "개구쟁이 즐겨찾기 해제" });

    const items = screen.getAllByRole("listitem");
    expect(items[0]).toHaveTextContent("개구쟁이");
    expect(items[1]).toHaveTextContent("검은고딕");
  });

  it("즐겨찾기가 실패하면 되돌리고 그 사실을 말한다", async () => {
    vi.spyOn(api.api, "listCaptionFonts").mockResolvedValue(library as never);
    vi.spyOn(api.api, "toggleCaptionFontFavorite").mockRejectedValue(new Error("nope"));

    render(<CaptionFontPicker value="Pretendard" onSelect={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "개구쟁이 즐겨찾기" }));

    expect(await screen.findByRole("status")).toHaveTextContent("즐겨찾기를 저장하지 못했어요");
    expect(await screen.findByRole("button", { name: "개구쟁이 즐겨찾기" })).toBeInTheDocument();
  });

  it("목록을 못 읽으면 지금 쓰는 글꼴이라도 보여주고 편집을 막지 않는다", async () => {
    vi.spyOn(api.api, "listCaptionFonts").mockRejectedValue(new Error("nope"));

    render(<CaptionFontPicker value="Gaegu" onSelect={vi.fn()} />);

    expect(await screen.findByText("Gaegu")).toBeInTheDocument();
  });

  it("화면 문구에 내부 용어를 쓰지 않는다", async () => {
    // §10.13: `fontFamily`, `BorderStyle` 같은 말은 사용자 화면에 쓰지 않는다.
    vi.spyOn(api.api, "listCaptionFonts").mockResolvedValue(library as never);

    const { container } = render(<CaptionFontPicker value="Pretendard" onSelect={vi.fn()} />);
    await screen.findByRole("button", { name: "검은고딕 고르기" });

    for (const banned of ["fontFamily", "BorderStyle", "family", "폰트", "런타임", "파이프라인"]) {
      expect(container.textContent).not.toContain(banned);
    }
  });
});
