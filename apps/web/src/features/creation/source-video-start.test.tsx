import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

import { api, ApiRequestError } from "../../api";
import { SourceVideoStart } from "./SourceVideoStart";

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

const pick = (name = "찍어둔-영상.mp4") =>
  fireEvent.change(screen.getByLabelText("찍어 둔 영상 선택"), {
    target: { files: [new File(["v"], name, { type: "video/mp4" })] },
  });

/** 찍어 둔 영상으로 시작하는 길.
 *
 *  여기서 지키는 것은 셋이다.
 *  1. **받아쓴 글을 그대로 확정하지 않는다.** 받아쓰기는 틀린다 -- owner가 고칠
 *     칸을 먼저 보여 주고, 확인을 눌러야 기획으로 넘어간다.
 *  2. **기다리는 동안 화면이 멈춘 것처럼 보이지 않는다.** 10분짜리 영상이면 몇
 *     분이다. 상태를 말하고, 그동안 두 번 눌리지 않게 막는다.
 *  3. **실패 이유를 구분해서 말한다.** 소리가 없는 영상과 열 수 없는 형식은
 *     owner가 할 다음 행동이 서로 다르다. 한 문장으로 뭉치면 무엇을 고쳐야
 *     하는지 알 수 없다. */
describe("찍어 둔 영상으로 시작", () => {
  it("받아쓴 글을 고칠 수 있는 칸에 보여 주고, 확인해야 넘어간다", async () => {
    vi.spyOn(api, "uploadSourceVideo").mockResolvedValue({ asset_id: "asset_1", script_text: "오늘은 신제품을 소개합니다.", spoken_segment_count: 3 });
    const onReady = vi.fn();
    render(<SourceVideoStart projectId="project_1" onReady={onReady} />);

    pick();
    fireEvent.click(screen.getByRole("button", { name: "영상에서 대본 만들기" }));

    const edited = await screen.findByLabelText("영상에서 받아쓴 대본");
    expect(edited).toHaveValue("오늘은 신제품을 소개합니다.");
    // 받아쓰기는 틀린다. 확인 전에는 아무것도 확정하지 않는다.
    expect(onReady).not.toHaveBeenCalled();

    fireEvent.change(edited, { target: { value: "오늘은 새 제품을 소개합니다." } });
    fireEvent.click(screen.getByRole("button", { name: "이 대본으로 기획 시작" }));

    expect(onReady).toHaveBeenCalledWith({ assetId: "asset_1", scriptText: "오늘은 새 제품을 소개합니다." });
  });

  it("받아쓰는 동안 무엇을 하고 있는지 말하고, 그 사이 다시 눌리지 않는다", async () => {
    let finish: ((value: { asset_id: string; script_text: string; spoken_segment_count: number }) => void) | null = null;
    const upload = vi.spyOn(api, "uploadSourceVideo").mockReturnValue(new Promise((resolve) => { finish = resolve; }));
    render(<SourceVideoStart projectId="project_1" onReady={vi.fn()} />);

    pick();
    const button = screen.getByRole("button", { name: "영상에서 대본 만들기" });
    fireEvent.click(button);

    const busy = await screen.findByRole("button", { name: "영상에서 말을 받아쓰고 있어요" });
    expect(busy).toBeDisabled();
    expect(screen.getByRole("status")).toHaveTextContent(/몇 분/);

    fireEvent.click(busy);
    expect(upload).toHaveBeenCalledTimes(1);

    finish!({ asset_id: "asset_1", script_text: "받아쓴 말", spoken_segment_count: 1 });
    await screen.findByLabelText("영상에서 받아쓴 대본");
  });

  it("소리가 없는 영상과 열 수 없는 형식을 다르게 말한다", async () => {
    const upload = vi.spyOn(api, "uploadSourceVideo")
      .mockRejectedValueOnce(new ApiRequestError("source_video_has_no_speech", 422, "/api/x"))
      .mockRejectedValueOnce(new ApiRequestError("source_video_upload_invalid", 400, "/api/x"));
    render(<SourceVideoStart projectId="project_1" onReady={vi.fn()} />);

    pick();
    fireEvent.click(screen.getByRole("button", { name: "영상에서 대본 만들기" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/말소리가 없어요/);

    fireEvent.click(screen.getByRole("button", { name: "영상에서 대본 만들기" }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/열 수 없는 형식이에요/));
    expect(upload).toHaveBeenCalledTimes(2);
  });

  it("영상이 길어 시간 안에 못 끝내면 잘라서 올리라고 말한다", async () => {
    // nginx가 330초에서 끊는다(`docker/workspace-nginx.conf`). 그보다 긴 영상은
    // 받아쓰기가 끝나기 전에 연결이 죽는다 -- "다시 시도해 주세요"라고 하면
    // owner는 같은 영상을 몇 번이고 다시 올린다.
    vi.spyOn(api, "uploadSourceVideo").mockRejectedValue(new ApiRequestError(null, 504, "/api/x"));
    render(<SourceVideoStart projectId="project_1" onReady={vi.fn()} />);

    pick();
    fireEvent.click(screen.getByRole("button", { name: "영상에서 대본 만들기" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/잘라서 올려/);
  });

  it("영상을 고르지 않았으면 올리지 않는다", () => {
    const upload = vi.spyOn(api, "uploadSourceVideo");
    render(<SourceVideoStart projectId="project_1" onReady={vi.fn()} />);

    fireEvent.click(screen.getByRole("button", { name: "영상에서 대본 만들기" }));

    expect(upload).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent(/영상을 먼저 골라/);
  });

  it("받아쓴 글을 다 지우면 그 글로는 시작할 수 없다", async () => {
    vi.spyOn(api, "uploadSourceVideo").mockResolvedValue({ asset_id: "asset_1", script_text: "받아쓴 말", spoken_segment_count: 1 });
    const onReady = vi.fn();
    render(<SourceVideoStart projectId="project_1" onReady={onReady} />);

    pick();
    fireEvent.click(screen.getByRole("button", { name: "영상에서 대본 만들기" }));

    const edited = await screen.findByLabelText("영상에서 받아쓴 대본");
    fireEvent.change(edited, { target: { value: "   " } });

    expect(screen.getByRole("button", { name: "이 대본으로 기획 시작" })).toBeDisabled();
    expect(onReady).not.toHaveBeenCalled();
  });
});
