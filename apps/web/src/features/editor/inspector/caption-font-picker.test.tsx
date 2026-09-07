import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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

  /** **owner가 두 번 지시한 자리다**: "글자폰트도 다양한 무료 폰트를
   *  드롭다운으로 만들라고 했는데도 무시하고"(2026-09-04).
   *
   *  실기에서 재 보니 글꼴 **15개에 단추 30개**, 세로 **260px**이었다 --
   *  글꼴마다 `고르기`와 `즐겨찾기` 단추가 하나씩 붙어 있었다. 캡컷은 글꼴을
   *  드롭다운 하나로 준다.
   *
   *  즐겨찾기는 없애지 않는다 -- **지금 고른 글꼴 하나에 대해서만** 단추를
   *  둔다. 순서(즐겨찾기 → 최근 → 나머지)는 드롭다운 안에서 그대로다. */
  it("글꼴은 드롭다운 하나로 고른다 -- 글꼴마다 단추를 두지 않는다", async () => {
    vi.spyOn(api.api, "listCaptionFonts").mockResolvedValue(library as never);

    render(<CaptionFontPicker value="Pretendard" onSelect={vi.fn()} />);

    const select = await screen.findByRole("combobox", { name: "글꼴" });
    expect(select).toBeInTheDocument();
    expect(within(select).getAllByRole("option").map((o) => o.textContent)).toEqual(
      expect.arrayContaining(["프리텐다드", "검은고딕", "개구쟁이"]),
    );
    // 글꼴마다 붙던 단추가 사라졌다. 남는 단추는 즐겨찾기 하나뿐이다.
    expect(screen.queryByRole("button", { name: "검은고딕 고르기" })).toBeNull();
    expect(screen.queryByRole("button", { name: "개구쟁이 고르기" })).toBeNull();
    expect(screen.getAllByRole("button")).toHaveLength(1);
  });

  it("드롭다운에서 고르면 그 이름을 넘기고 최근으로 올린다", async () => {
    vi.spyOn(api.api, "listCaptionFonts").mockResolvedValue(library as never);
    const mark = vi.spyOn(api.api, "markRecentCaptionFont").mockResolvedValue({ recents: ["Gaegu"] } as never);
    const onSelect = vi.fn();

    render(<CaptionFontPicker value="Pretendard" onSelect={onSelect} />);
    fireEvent.change(await screen.findByRole("combobox", { name: "글꼴" }), { target: { value: "Gaegu" } });

    await waitFor(() => expect(onSelect).toHaveBeenCalledWith("Gaegu"));
    await waitFor(() => expect(mark).toHaveBeenCalledWith("Gaegu"));
  });

  it("즐겨찾기는 지금 고른 글꼴 하나에만 붙는다", async () => {
    vi.spyOn(api.api, "listCaptionFonts").mockResolvedValue({ ...library, favorites: ["Gaegu"] } as never);
    const toggle = vi.spyOn(api.api, "toggleCaptionFontFavorite").mockResolvedValue({ favorites: [] } as never);

    render(<CaptionFontPicker value="Gaegu" onSelect={vi.fn()} />);

    const button = await screen.findByRole("button", { name: "개구쟁이 즐겨찾기 해제" });
    fireEvent.click(button);
    await waitFor(() => expect(toggle).toHaveBeenCalledWith("Gaegu", false));
  });
  it("설치된 글꼴만 보여주고, 고르면 그 이름을 넘긴다", async () => {
    // 자유 입력이던 시절에는 없는 글꼴을 쳐도 화면이 받아들이고, 완성본에서만
    // 다른 글꼴로 나왔다.
    vi.spyOn(api.api, "listCaptionFonts").mockResolvedValue(library as never);
    const onSelect = vi.fn();

    render(<CaptionFontPicker value="Pretendard" onSelect={onSelect} />);

    fireEvent.change(await screen.findByRole("combobox", { name: "글꼴" }), { target: { value: "Black Han Sans" } });

    await waitFor(() => expect(onSelect).toHaveBeenCalledWith("Black Han Sans"));
  });

  it("고른 글꼴을 최근으로 올린다", async () => {
    vi.spyOn(api.api, "listCaptionFonts").mockResolvedValue(library as never);
    const mark = vi.spyOn(api.api, "markRecentCaptionFont").mockResolvedValue({ recents: ["Gaegu"] } as never);

    render(<CaptionFontPicker value="Pretendard" onSelect={vi.fn()} />);
    fireEvent.change(await screen.findByRole("combobox", { name: "글꼴" }), { target: { value: "Gaegu" } });

    await waitFor(() => expect(mark).toHaveBeenCalledWith("Gaegu"));
  });

  it("즐겨찾기한 글꼴을 맨 위에 둔다", async () => {
    vi.spyOn(api.api, "listCaptionFonts").mockResolvedValue({ ...library, favorites: ["Gaegu"] } as never);

    render(<CaptionFontPicker value="Pretendard" onSelect={vi.fn()} />);

    const options = within(await screen.findByRole("combobox", { name: "글꼴" })).getAllByRole("option");
    expect(options[0]).toHaveTextContent("개구쟁이");
  });

  it("즐겨찾기 다음은 최근에 쓴 것이다", async () => {
    vi.spyOn(api.api, "listCaptionFonts").mockResolvedValue(
      { ...library, favorites: ["Gaegu"], recents: ["Black Han Sans"] } as never,
    );

    render(<CaptionFontPicker value="Pretendard" onSelect={vi.fn()} />);

    const options = within(await screen.findByRole("combobox", { name: "글꼴" })).getAllByRole("option");
    expect(options[0]).toHaveTextContent("개구쟁이");
    expect(options[1]).toHaveTextContent("검은고딕");
  });

  it("즐겨찾기가 실패하면 되돌리고 그 사실을 말한다", async () => {
    vi.spyOn(api.api, "listCaptionFonts").mockResolvedValue(library as never);
    vi.spyOn(api.api, "toggleCaptionFontFavorite").mockRejectedValue(new Error("nope"));

    render(<CaptionFontPicker value="Pretendard" onSelect={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "프리텐다드 즐겨찾기" }));

    expect(await screen.findByRole("status")).toHaveTextContent("즐겨찾기를 저장하지 못했어요");
    expect(await screen.findByRole("button", { name: "프리텐다드 즐겨찾기" })).toBeInTheDocument();
  });

  it("지금 쓰는 글꼴이 이 컴퓨터에 없으면 먼저 말해 준다", async () => {
    // 목록에는 글꼴 파일이 실제로 있는 것만 담겨 온다. 그 안에 없다는 것은
    // 완성본이 조용히 다른 글꼴로 나온다는 뜻이라 owner에게 먼저 알린다.
    vi.spyOn(api.api, "listCaptionFonts").mockResolvedValue(library as never);

    render(<CaptionFontPicker value="NanumGothic" onSelect={vi.fn()} />);

    expect(await screen.findByText(/이 컴퓨터에 없어요/)).toBeInTheDocument();
  });

  it("지금 쓰는 글꼴이 목록에 있으면 아무 말도 하지 않는다", async () => {
    vi.spyOn(api.api, "listCaptionFonts").mockResolvedValue(library as never);

    render(<CaptionFontPicker value="Gaegu" onSelect={vi.fn()} />);
    await screen.findByRole("combobox", { name: "글꼴" });

    expect(screen.queryByText(/이 컴퓨터에 없어요/)).not.toBeInTheDocument();
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
    await screen.findByRole("combobox", { name: "글꼴" });

    for (const banned of ["fontFamily", "BorderStyle", "family", "폰트", "런타임", "파이프라인"]) {
      expect(container.textContent).not.toContain(banned);
    }
  });
});
