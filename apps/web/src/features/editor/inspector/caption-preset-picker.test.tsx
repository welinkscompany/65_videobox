import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "../../../api";
import { CaptionPresetPicker, fromSnapshot } from "./CaptionPresetPicker";

const presets = [
  { preset_id: "builtin:clean", name: "Clean", scope: "built_in", style: { font_size: 42 } },
  { preset_id: "builtin:highlight", name: "Highlight", scope: "built_in", style: { font_size: 52 } },
] as never;

describe("자막 모양 고르기", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(api.api, "listRecentEditorPresetIds").mockResolvedValue([] as never);
    vi.spyOn(api.api, "markRecentEditorPreset").mockResolvedValue([] as never);
  });

  it("모양을 보여주고 고르면 그 모양을 넘긴다", async () => {
    // 백엔드에 프리셋이 있는데 부르는 화면이 없었다.
    vi.spyOn(api.api, "listEditorPresets").mockResolvedValue(presets);
    vi.spyOn(api.api, "listEditorFavorites").mockResolvedValue([] as never);
    const onApply = vi.fn();

    render(<CaptionPresetPicker projectId="project-a" onApply={onApply} />);

    fireEvent.click(await screen.findByRole("button", { name: "Clean 적용" }));

    await waitFor(() => expect(onApply).toHaveBeenCalledWith({ font_size: 42 }));
  });

  it("즐겨찾기한 모양을 먼저 보여준다", async () => {
    // 자주 쓰는 모양을 매번 찾아 내려가지 않게 하는 것이 즐겨찾기의 뜻이다.
    vi.spyOn(api.api, "listEditorPresets").mockResolvedValue(presets);
    vi.spyOn(api.api, "listEditorFavorites").mockResolvedValue(
      [{ favorite_id: "builtin:highlight", favorite_type: "preset" }] as never,
    );

    render(<CaptionPresetPicker projectId="project-a" onApply={vi.fn()} />);

    const items = await screen.findAllByRole("article");
    expect(items[0]).toHaveTextContent("Highlight");
  });

  it("즐겨찾기를 저장하고, 실패하면 되돌리며 그 사실을 말한다", async () => {
    // 즐겨찾기가 되는 것은 프로젝트에 저장한 모양뿐이다.
    const mine = [{ preset_id: "project:project-a:mine", name: "내 모양", scope: "project", style: {} }] as never;
    vi.spyOn(api.api, "listEditorPresets").mockResolvedValue(mine);
    vi.spyOn(api.api, "listEditorFavorites").mockResolvedValue([] as never);
    const save = vi.spyOn(api.api, "toggleEditorFavorite").mockRejectedValue(new Error("nope"));

    render(<CaptionPresetPicker projectId="project-a" onApply={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "내 모양 즐겨찾기" }));

    await waitFor(() =>
      expect(save).toHaveBeenCalledWith("project-a", "project:project-a:mine", {
        favorite_type: "preset",
        enabled: true,
      }),
    );
    expect(await screen.findByText("즐겨찾기를 저장하지 못했어요. 잠시 뒤 다시 눌러 주세요.")).toBeVisible();
    // 되돌렸으므로 다시 "즐겨찾기"로 보인다.
    expect(screen.getByRole("button", { name: "내 모양 즐겨찾기" })).toBeVisible();
  });

  it("모양이 없으면 그렇게 말한다", async () => {
    vi.spyOn(api.api, "listEditorPresets").mockResolvedValue([] as never);
    vi.spyOn(api.api, "listEditorFavorites").mockResolvedValue([] as never);

    render(<CaptionPresetPicker projectId="project-a" onApply={vi.fn()} />);

    expect(await screen.findByText("아직 저장된 자막 모양이 없어요.")).toBeVisible();
  });

  it("최근에 쓴 모양을 즐겨찾기 바로 아래에 보여준다", async () => {
    // 최근 목록은 적용할 때마다 기록되고 있었는데 아무도 다시 읽지 않아서,
    // 방금 쓴 모양을 다음에도 아래에서 찾아 내려가야 했다.
    vi.spyOn(api.api, "listEditorPresets").mockResolvedValue([
      { preset_id: "builtin:clean", name: "Clean", scope: "built_in", style: {} },
      { preset_id: "builtin:highlight", name: "Highlight", scope: "built_in", style: {} },
      { preset_id: "builtin:bold", name: "Bold", scope: "built_in", style: {} },
    ] as never);
    vi.spyOn(api.api, "listEditorFavorites").mockResolvedValue(
      [{ favorite_id: "builtin:bold", favorite_type: "preset" }] as never,
    );
    vi.spyOn(api.api, "listRecentEditorPresetIds")
      .mockResolvedValue(["builtin:highlight"] as never);

    render(<CaptionPresetPicker projectId="project-a" onApply={vi.fn()} />);

    const items = await screen.findAllByRole("article");
    expect(items[0]).toHaveTextContent("Bold");
    expect(items[1]).toHaveTextContent("Highlight");
    expect(items[1]).toHaveTextContent("최근에 썼어요");
    expect(items[2]).toHaveTextContent("Clean");
  });

  it("방금 쓴 모양을 다시 열지 않아도 최근으로 옮긴다", async () => {
    vi.spyOn(api.api, "listEditorPresets").mockResolvedValue(presets);
    vi.spyOn(api.api, "listEditorFavorites").mockResolvedValue([] as never);
    vi.spyOn(api.api, "markRecentEditorPreset").mockResolvedValue(["builtin:highlight"] as never);

    render(<CaptionPresetPicker projectId="project-a" onApply={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "Highlight 적용" }));

    await waitFor(() => expect(screen.getAllByRole("article")[0]).toHaveTextContent("Highlight"));
    expect(screen.getAllByRole("article")[0]).toHaveTextContent("최근에 썼어요");
  });
});

describe("저장된 모양을 화면 값으로 옮기기", () => {
  it("실제 프리셋이 쓰는 이름을 화면 이름으로 바꾼다", () => {
    // 백엔드 프리셋은 `font_size`, `text_color`, `font_family`로 온다.
    expect(fromSnapshot({ font_size: 42, text_color: "#FFFFFFFF", font_family: "Noto Sans KR" }))
      .toEqual({ fontSizePx: 42, textColor: "#FFFFFFFF", fontFamily: "Noto Sans KR" });
  });

  it("모르는 값은 옮기지 않는다", () => {
    // 화면 값을 지어내면 owner가 고르지 않은 모양이 적용된다.
    expect(fromSnapshot({ unknown_thing: 1, font_size: "크게" })).toEqual({});
  });

  it("빈 것도 그대로 견딘다", () => {
    expect(fromSnapshot({})).toEqual({});
  });
});

describe("즐겨찾기할 수 없는 모양", () => {
  it("내장 모양에는 즐겨찾기 버튼을 띄우지 않는다", async () => {
    // 저장소가 `project:` 또는 `pack:` 으로 시작하는 것만 받는다. 내장 모양에
    // 버튼을 띄우면 눌러도 422로 실패한다 -- 화면이 못 하는 일을 권한 셈이다.
    vi.spyOn(api.api, "listEditorPresets").mockResolvedValue(presets);
    vi.spyOn(api.api, "listEditorFavorites").mockResolvedValue([] as never);

    render(<CaptionPresetPicker projectId="project-a" onApply={vi.fn()} />);

    expect(await screen.findByRole("button", { name: "Clean 적용" })).toBeVisible();
    expect(screen.queryByRole("button", { name: "Clean 즐겨찾기" })).toBeNull();
  });

  it("프로젝트에 저장한 모양에는 띄운다", async () => {
    vi.spyOn(api.api, "listEditorPresets").mockResolvedValue(
      [{ preset_id: "project:project-a:mine", name: "내 모양", scope: "project", style: {} }] as never,
    );
    vi.spyOn(api.api, "listEditorFavorites").mockResolvedValue([] as never);

    render(<CaptionPresetPicker projectId="project-a" onApply={vi.fn()} />);

    expect(await screen.findByRole("button", { name: "내 모양 즐겨찾기" })).toBeVisible();
  });
});
