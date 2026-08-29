import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

import { api } from "../../api";
import { SceneImageStudio } from "./SceneImageStudio";

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

const gap = { gapSlotId: "gap-broll-2", segmentId: "script-2", sceneNumber: 2, sceneText: "이렇게 하면 편집이 반으로 줄어요.", durationSec: 5 };

describe("장면 그림 만들기", () => {
  it("장면의 자막을 그대로 첫 설명으로 깔아 준다", () => {
    // 빈 칸을 주면 owner가 매번 처음부터 쓴다. 그 장면에서 무슨 말을 하는지는
    // 이미 대본이 알고 있다.
    render(<SceneImageStudio projectId="project_a" gap={gap} />);

    expect(screen.getByLabelText("2번째 장면 그림·영상 설명")).toHaveValue("이렇게 하면 편집이 반으로 줄어요.");
  });

  it("만든 그림을 보여 준다 — 만들었다고 말만 하지 않는다", async () => {
    const created = vi.spyOn(api, "createSceneImage").mockResolvedValue({
      image_asset_id: "asset_image_1", scene_asset_id: "asset_clip_1", segment_id: "script-2",
      title: "2번째 장면 그림", prompt: "이렇게 하면 편집이 반으로 줄어요.", seed: 12, elapsed_sec: 22.3,
      commercial_use_is_unrestricted: false,
    } as never);

    const { container } = render(<SceneImageStudio projectId="project_a" gap={gap} />);
    fireEvent.click(screen.getByRole("button", { name: "그림 만들기" }));

    await waitFor(() => expect(created).toHaveBeenCalledWith("project_a", {
      prompt: "이렇게 하면 편집이 반으로 줄어요.", segment_id: "script-2", gap_slot_id: "gap-broll-2",
      duration_sec: 5, vertical: false,
    }));
    await waitFor(() => expect(container.querySelector("img")).toHaveAttribute(
      "src", api.assetContentUrl("project_a", "asset_image_1"),
    ));
  });

  it("기다리는 동안 무엇을 하고 있는지 말하고, 두 번 눌리지 않게 한다", async () => {
    let finish: (value: unknown) => void = () => {};
    vi.spyOn(api, "createSceneImage").mockReturnValue(new Promise((resolve) => { finish = resolve; }) as never);

    render(<SceneImageStudio projectId="project_a" gap={gap} />);
    fireEvent.click(screen.getByRole("button", { name: "그림 만들기" }));

    await waitFor(() => expect(screen.getByRole("button", { name: "그림을 만들고 있어요" })).toBeDisabled());
    finish({ image_asset_id: "a", scene_asset_id: "b", segment_id: "script-2", title: "t", prompt: "p", seed: 1 });
  });

  it("꺼져 있는 것과 고장 난 것을 다른 말로 알려 준다", async () => {
    // 2026-08-20에 503 둘이 같은 문구로 보여 켜지지 않은 기능을 결함으로 볼 뻔했다.
    vi.spyOn(api, "createSceneImage").mockRejectedValue(
      Object.assign(new Error("scene_image_generation_unavailable"), { detail: "scene_image_generation_unavailable" }),
    );

    render(<SceneImageStudio projectId="project_a" gap={gap} />);
    fireEvent.click(screen.getByRole("button", { name: "그림 만들기" }));

    expect(await screen.findByText("그림 만들기가 아직 켜져 있지 않아요.")).toBeVisible();
  });

  it("그림 만드는 곳이 꺼져 있으면 켜라고 말한다", async () => {
    vi.spyOn(api, "createSceneImage").mockRejectedValue(
      Object.assign(new Error("blocked"), { detail: "scene_image_generation_blocked" }),
    );

    render(<SceneImageStudio projectId="project_a" gap={gap} />);
    fireEvent.click(screen.getByRole("button", { name: "그림 만들기" }));

    expect(await screen.findByText("그림 만드는 프로그램에 닿지 않았어요. 켜져 있는지 확인한 뒤 다시 눌러 주세요.")).toBeVisible();
  });

  it("설명이 비어 있으면 부르지 않고 먼저 말해 준다", async () => {
    const created = vi.spyOn(api, "createSceneImage");

    render(<SceneImageStudio projectId="project_a" gap={{ ...gap, sceneText: "" }} />);
    fireEvent.click(screen.getByRole("button", { name: "그림 만들기" }));

    expect(await screen.findByText("어떤 그림을 원하는지 먼저 적어 주세요.")).toBeVisible();
    expect(created).not.toHaveBeenCalled();
  });

  it("숏폼이면 세로로 만든다", async () => {
    const created = vi.spyOn(api, "createSceneImage").mockResolvedValue({
      image_asset_id: "a", scene_asset_id: "b", segment_id: "script-2", title: "t", prompt: "p", seed: 1,
    } as never);

    render(<SceneImageStudio projectId="project_a" gap={gap} vertical />);
    fireEvent.click(screen.getByRole("button", { name: "그림 만들기" }));

    await waitFor(() => expect(created).toHaveBeenCalledWith("project_a", expect.objectContaining({ vertical: true })));
  });

  it("만들고 나면 초안을 다시 준비하라고 알려 준다", async () => {
    // 자산이 생긴 것과 그 장면이 채워진 것은 다른 일이다. 준비를 다시 돌려야
    // 공백 목록이 바뀐다 -- 그걸 안 알려 주면 owner는 아무 일도 안 일어난 줄 안다.
    const onGenerated = vi.fn();
    vi.spyOn(api, "createSceneImage").mockResolvedValue({
      image_asset_id: "a", scene_asset_id: "b", segment_id: "script-2", title: "t", prompt: "p", seed: 1,
    } as never);

    render(<SceneImageStudio projectId="project_a" gap={gap} onGenerated={onGenerated} />);
    fireEvent.click(screen.getByRole("button", { name: "그림 만들기" }));

    await waitFor(() => expect(onGenerated).toHaveBeenCalled());
  });
});
