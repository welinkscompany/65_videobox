import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

import { api } from "../../../api";
import { SavedFormatPicker } from "./SavedFormatPicker";

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

const template = {
  template_id: "format_template_1", name: "내 브이로그 포맷",
  caption_style: { font_size: 48, text_color: "#FFFFFF" },
  width: 1920, height: 1080, scene_count: 4, average_scene_sec: 5, music_asset_id: "asset_m",
};

describe("saved format picker", () => {
  it("hands the saved look to the editor the same way a preset does", async () => {
    // 저장소를 따로 부르지 않는다. 같은 변경이 두 경로를 가지면 하나가 조용히 낡는다.
    vi.spyOn(api, "listFormatTemplates").mockResolvedValue([template] as never);
    const onApply = vi.fn();
    render(<SavedFormatPicker onApply={onApply} />);

    fireEvent.click(await screen.findByRole("button", { name: "내 브이로그 포맷 자막 모양 적용" }));

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
      await screen.findByText("적용하면 자막 모양만 바뀌어요. 화면 크기와 음악은 그대로예요."),
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
