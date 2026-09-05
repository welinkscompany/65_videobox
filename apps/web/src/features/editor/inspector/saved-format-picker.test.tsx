import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";

import { api } from "../../../api";
import { SavedFormatPicker } from "./SavedFormatPicker";

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

const template = {
  template_id: "format_template_1", name: "내 브이로그 포맷",
  caption_style: { font_size: 48, text_color: "#FFFFFF" },
  width: 1920, height: 1080, scene_count: 4, average_scene_sec: 5, music_asset_id: "asset_m",
};

describe("saved format picker", () => {
  /** **글꼴·캡션 모양과 같은 정리다**(owner 지시 2026-09-05). 포맷마다
   *  `캡션 모양 적용` 단추가 하나씩 붙어서 포맷을 저장할수록 늘어난다.
   *  드롭다운으로 고르고 단추는 하나만 둔다. 무엇이 걸려 있는지(크기·장면 수)는
   *  **고른 것에 대해** 그 아래 한 줄로 그대로 말한다 -- 눌러 보고 알게 하지
   *  않는다는 원래 뜻은 유지한다. */
  it("포맷은 드롭다운으로 고른다 -- 포맷마다 단추를 두지 않는다", async () => {
    vi.spyOn(api, "listFormatTemplates").mockResolvedValue([
      template,
      { ...template, template_id: "format_template_2", name: "쇼츠 포맷", width: 1080, height: 1920 },
    ] as never);

    render(<SavedFormatPicker onApply={vi.fn()} />);

    const select = await screen.findByRole("combobox", { name: "저장한 포맷" });
    expect(within(select).getAllByRole("option").map((o) => o.textContent)).toEqual(["내 브이로그 포맷", "쇼츠 포맷"]);
    expect(screen.queryByRole("button", { name: "내 브이로그 포맷 캡션 모양 적용" })).toBeNull();
    expect(screen.getAllByRole("button")).toHaveLength(1);
    // 고른 포맷이 무엇을 담고 있는지는 그대로 말한다.
    expect(screen.getByText(/1920×1080/)).toBeVisible();
  });

  it("고른 포맷의 캡션 모양을 적용한다", async () => {
    vi.spyOn(api, "listFormatTemplates").mockResolvedValue([
      template,
      { ...template, template_id: "format_template_2", name: "쇼츠 포맷", caption_style: { font_size: 30 } },
    ] as never);
    const onApply = vi.fn();
    render(<SavedFormatPicker onApply={onApply} />);

    fireEvent.change(await screen.findByRole("combobox", { name: "저장한 포맷" }), { target: { value: "format_template_2" } });
    fireEvent.click(screen.getByRole("button", { name: "고른 포맷의 캡션 모양 적용" }));

    expect(onApply).toHaveBeenCalledWith({ font_size: 30 });
  });
  it("hands the saved look to the editor the same way a preset does", async () => {
    // 저장소를 따로 부르지 않는다. 같은 변경이 두 경로를 가지면 하나가 조용히 낡는다.
    vi.spyOn(api, "listFormatTemplates").mockResolvedValue([template] as never);
    const onApply = vi.fn();
    render(<SavedFormatPicker onApply={onApply} />);

    fireEvent.click(await screen.findByRole("button", { name: "고른 포맷의 캡션 모양 적용" }));

    expect(onApply).toHaveBeenCalledWith({ font_size: 48, text_color: "#FFFFFF" });
  });

  it("says what else that format implies before it is applied", async () => {
    // 세로 영상에 가로 포맷을 씌우는 실수가 여기서 걸린다.
    vi.spyOn(api, "listFormatTemplates").mockResolvedValue([template] as never);
    render(<SavedFormatPicker onApply={vi.fn()} />);

    expect(await screen.findByText("1920×1080 · 장면 4개")).toBeVisible();
  });

  it("promises exactly what applying does: captions change, size and music do not", async () => {
    // 크기를 실제로 바꾸는 경로가 없다. 카드가 크기를 보여 주는 이상,
    // "적용해도 크기는 안 바뀐다"를 화면이 직접 말해야 약속과 동작이 맞는다.
    vi.spyOn(api, "listFormatTemplates").mockResolvedValue([template] as never);
    render(<SavedFormatPicker onApply={vi.fn()} />);

    expect(
      await screen.findByText("적용하면 캡션 모양만 바뀌어요. 화면 크기와 음악은 그대로예요."),
    ).toBeVisible();
  });

  it("points at where formats come from when there are none", async () => {
    vi.spyOn(api, "listFormatTemplates").mockResolvedValue([] as never);
    render(<SavedFormatPicker onApply={vi.fn()} />);

    expect(await screen.findByText("아직 저장한 포맷이 없어요. 마음에 든 완성본에서 저장해 보세요.")).toBeVisible();
  });

  it("stays quiet rather than blocking the inspector when the list fails", async () => {
    vi.spyOn(api, "listFormatTemplates").mockRejectedValue(new Error("offline"));
    render(<SavedFormatPicker onApply={vi.fn()} />);

    expect(await screen.findByText("저장한 포맷을 불러오지 못했어요.")).toBeVisible();
  });
});
