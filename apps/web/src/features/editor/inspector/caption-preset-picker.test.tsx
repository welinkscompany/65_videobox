import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "../../../api";
import { CaptionPresetPicker, fromSnapshot } from "./CaptionPresetPicker";

const presets = [
  { preset_id: "builtin:clean", name: "Clean", scope: "built_in", style: { font_size: 42 } },
  { preset_id: "builtin:highlight", name: "Highlight", scope: "built_in", style: { font_size: 52 } },
] as never;

describe("캡션 모양 고르기", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(api.api, "listRecentEditorPresetIds").mockResolvedValue([] as never);
    vi.spyOn(api.api, "markRecentEditorPreset").mockResolvedValue([] as never);
  });

  /** **글꼴과 같은 정리다**(owner 지시 2026-09-05: "캡션 모양이랑 저장한
   *  포맷도 재서 똑같이 정리해"). 모양마다 `적용`·`즐겨찾기` 단추가 둘씩
   *  붙어 있어서 모양을 저장할수록 단추가 2N+1로 늘어난다 -- 글꼴에서 15개가
   *  30단추가 됐던 것과 같은 구조다.
   *
   *  드롭다운으로 고르고 단추는 고른 것에 대한 것만 남긴다. 순서(즐겨찾기 →
   *  최근 → 나머지)는 드롭다운 안에서 그대로다. */
  it("모양은 드롭다운으로 고른다 -- 모양마다 단추를 두지 않는다", async () => {
    vi.spyOn(api.api, "listEditorPresets").mockResolvedValue(presets);
    vi.spyOn(api.api, "listEditorFavorites").mockResolvedValue([] as never);

    render(<CaptionPresetPicker projectId="project-a" onApply={vi.fn()} />);

    const select = await screen.findByRole("combobox", { name: "캡션 모양" });
    expect(within(select).getAllByRole("option").map((o) => o.textContent)).toEqual(["Clean", "Highlight"]);
    expect(screen.queryByRole("button", { name: "Clean 적용" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Highlight 적용" })).toBeNull();
    expect(screen.getByRole("button", { name: "고른 모양 적용" })).toBeVisible();
  });

  it("드롭다운에서 고른 모양을 적용한다", async () => {
    vi.spyOn(api.api, "listEditorPresets").mockResolvedValue(presets);
    vi.spyOn(api.api, "listEditorFavorites").mockResolvedValue([] as never);
    const onApply = vi.fn();

    render(<CaptionPresetPicker projectId="project-a" onApply={onApply} />);
    fireEvent.change(await screen.findByRole("combobox", { name: "캡션 모양" }), { target: { value: "builtin:highlight" } });
    fireEvent.click(screen.getByRole("button", { name: "고른 모양 적용" }));

    await waitFor(() => expect(onApply).toHaveBeenCalledWith({ font_size: 52 }));
  });
  it("모양을 보여주고 고르면 그 모양을 넘긴다", async () => {
    // 백엔드에 프리셋이 있는데 부르는 화면이 없었다.
    vi.spyOn(api.api, "listEditorPresets").mockResolvedValue(presets);
    vi.spyOn(api.api, "listEditorFavorites").mockResolvedValue([] as never);
    const onApply = vi.fn();

    render(<CaptionPresetPicker projectId="project-a" onApply={onApply} />);

    await screen.findByRole("combobox", { name: "캡션 모양" });
    fireEvent.click(screen.getByRole("button", { name: "고른 모양 적용" }));

    await waitFor(() => expect(onApply).toHaveBeenCalledWith({ font_size: 42 }));
  });

  it("즐겨찾기한 모양을 먼저 보여준다", async () => {
    // 자주 쓰는 모양을 매번 찾아 내려가지 않게 하는 것이 즐겨찾기의 뜻이다.
    vi.spyOn(api.api, "listEditorPresets").mockResolvedValue(presets);
    vi.spyOn(api.api, "listEditorFavorites").mockResolvedValue(
      [{ favorite_id: "builtin:highlight", favorite_type: "preset" }] as never,
    );

    render(<CaptionPresetPicker projectId="project-a" onApply={vi.fn()} />);

    const options = within(await screen.findByRole("combobox", { name: "캡션 모양" })).getAllByRole("option");
    expect(options[0]).toHaveTextContent("Highlight");
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

    expect(await screen.findByText("아직 저장된 캡션 모양이 없어요.")).toBeVisible();
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

    const options = within(await screen.findByRole("combobox", { name: "캡션 모양" })).getAllByRole("option");
    expect(options.map((option) => option.textContent)).toEqual(["Bold", "Highlight", "Clean"]);
  });

  it("방금 쓴 모양을 다시 열지 않아도 최근으로 옮긴다", async () => {
    vi.spyOn(api.api, "listEditorPresets").mockResolvedValue(presets);
    vi.spyOn(api.api, "listEditorFavorites").mockResolvedValue([] as never);
    vi.spyOn(api.api, "markRecentEditorPreset").mockResolvedValue(["builtin:highlight"] as never);

    render(<CaptionPresetPicker projectId="project-a" onApply={vi.fn()} />);
    fireEvent.change(await screen.findByRole("combobox", { name: "캡션 모양" }), { target: { value: "builtin:highlight" } });
    fireEvent.click(screen.getByRole("button", { name: "고른 모양 적용" }));

    await waitFor(() => {
      const options = within(screen.getByRole("combobox", { name: "캡션 모양" })).getAllByRole("option");
      expect(options[0]).toHaveTextContent("Highlight");
    });
    // 고른 것이 최근이라는 표시는 드롭다운 아래 한 줄로 남는다.
    expect(screen.getByText("최근에 썼어요")).toBeVisible();
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

  it("편집본과 포맷이 쓰는 정본 이름(_px·_percent)도 화면 이름으로 바꾼다", () => {
    // 저장한 포맷의 자막 모양은 편집본에서 그대로 떠 와서 `font_size_px` 같은
    // 정본 이름을 쓴다. 이 이름을 모르면 포맷을 적용해도 글자 크기·외곽선
    // 두께·위치가 조용히 빠진다 -- 왕복이 끊겨 있던 자리 중 하나다.
    expect(
      fromSnapshot({
        font_size_px: 54,
        outline_width_px: 3,
        position_x_percent: 50,
        position_y_percent: 88,
        shadow_blur_px: 2,
        horizontal_align: "center",
        font_family: "Noto Sans KR",
        text_color: "#FFFFFFFF",
      }),
    ).toEqual({
      fontSizePx: 54,
      outlineWidthPx: 3,
      positionXPercent: 50,
      positionYPercent: 88,
      shadowBlurPx: 2,
      horizontalAlign: "center",
      fontFamily: "Noto Sans KR",
      textColor: "#FFFFFFFF",
    });
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

    expect(await screen.findByRole("button", { name: "고른 모양 적용" })).toBeVisible();
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

  it("lets the creator keep the style they just made, so favourites have something to hold", async () => {
    // 즐겨찾기는 백엔드도 화면도 다 있었는데 **즐겨찾기할 수 있는 것이 0개**였다.
    // 프리셋 목록에 `builtin:clean`·`builtin:highlight` 둘뿐이고, 즐겨찾기는
    // `project:`로 시작하는 것만 걸 수 있기 때문이다. `자막 스타일 저장`이 만든
    // 모양이 프리셋이 되지 않아 목록이 영원히 비어 있었다.
    const save = vi.spyOn(api.api, "saveEditorPreset").mockResolvedValue({
      preset_id: "project:project-a:1", name: "내 모양 1", style: {},
    } as never);
    vi.spyOn(api.api, "listEditorPresets").mockResolvedValue([] as never);
    vi.spyOn(api.api, "listEditorFavorites").mockResolvedValue([] as never);

    render(<CaptionPresetPicker projectId="project-a" onApply={vi.fn()} currentStyle={{ font_family: "Pretendard", font_size: 28 }} />);

    fireEvent.click(await screen.findByRole("button", { name: "이 모양 저장해 두기" }));

    await waitFor(() => expect(save).toHaveBeenCalledTimes(1));
    // 즐겨찾기가 걸리려면 `project:`로 시작해야 한다.
    expect(save.mock.calls[0][1]).toMatch(/^project:project-a:/);
  });

  it("저장한 모양을 다시 적용하면 같은 모양이 돌아온다 -- 왕복이 끊기면 안 된다", async () => {
    // 저장할 때 화면 이름(camelCase)으로 바꿔 저장하면, 적용할 때 다시
    // `fromSnapshot`이 스냅샷 이름(snake_case)을 기대해서 **아무것도 적용되지
    // 않는다.** 저장은 스냅샷 그대로, 변환은 적용할 때 한 번만 한다.
    const snapshot = { font_family: "Pretendard", font_size: 28, text_color: "#112233FF" };
    const save = vi.spyOn(api.api, "saveEditorPreset").mockImplementation(
      (_projectId, presetId, payload) => Promise.resolve({
        preset_id: presetId, name: payload.name, scope: "project", style: payload.style,
      } as never),
    );
    vi.spyOn(api.api, "listEditorPresets").mockResolvedValue([] as never);
    vi.spyOn(api.api, "listEditorFavorites").mockResolvedValue([] as never);
    const onApply = vi.fn();

    render(<CaptionPresetPicker projectId="project-a" onApply={onApply} currentStyle={snapshot} />);
    fireEvent.click(await screen.findByRole("button", { name: "이 모양 저장해 두기" }));

    await waitFor(() => expect(save).toHaveBeenCalledTimes(1));
    // 저장된 것은 스냅샷 그대로여야 한다.
    expect(save.mock.calls[0][2].style).toEqual(snapshot);

    // 방금 저장한 모양을 바로 적용하면 화면 값으로 온전히 돌아와야 한다.
    // 방금 저장한 것 하나뿐이라 드롭다운이 이미 그것을 고르고 있다.
    fireEvent.click(await screen.findByRole("button", { name: "고른 모양 적용" }));
    await waitFor(() => expect(onApply).toHaveBeenCalledWith(snapshot));
    expect(fromSnapshot(onApply.mock.calls[0][0])).toEqual({
      fontFamily: "Pretendard", fontSizePx: 28, textColor: "#112233FF",
    });
  });
});
