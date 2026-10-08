/** 편집기에서 설명 모션을 만드는 자리 (2026-10-08 결정 2단계).
 *  지키는 것: 적은 그대로 간다 · 장면 길이를 기본 길이로 쓴다 · 기다리는 동안 잠그고 말한다 ·
 *  만든 것을 이 프로젝트로 가져온다 · 실패 이유마다 다른 말을 한다 · < >는 보내기 전에 막는다. */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { MotionPanel } from "./MotionPanel";
import { api, ApiRequestError, type MotionResult } from "../../../api";

const TEMPLATES = { templates: [
  { key: "bar_compare", korean_name: "막대 비교", description: "숫자 몇 개를 막대로 견줘요", default_duration_sec: 6, min_duration_sec: 3, max_duration_sec: 30, limits: { title: 24, subtitle: 40, unit: 4, label: 10, min_items: 2, max_items: 5 } },
  { key: "money_counter", korean_name: "금액 카운터", description: "금액이 0부터 올라가요", default_duration_sec: 5, min_duration_sec: 3, max_duration_sec: 30, limits: { lead: 20, suffix: 4, caption: 30 } },
  { key: "step_list", korean_name: "단계 목록", description: "순서를 하나씩 보여 줘요", default_duration_sec: 6, min_duration_sec: 3, max_duration_sec: 30, limits: { title: 24, step: 24, min_items: 2, max_items: 5 } },
] };

function made(overrides: Partial<MotionResult> = {}): MotionResult {
  return { library_asset_id: "user_m1", template: "bar_compare", title: "월 수익 비교", duration_sec: 6, layout: "full", format: "mp4", byte_size: 316548, elapsed_sec: 14.2, library_error: null, ...overrides };
}

async function fillBars() {
  await waitFor(() => expect(screen.getByRole("button", { name: "막대 비교" })).toHaveAttribute("aria-pressed", "true"));
  fireEvent.change(screen.getByLabelText("제목"), { target: { value: "월 수익 비교" } });
  fireEvent.change(screen.getByLabelText("단위(선택)"), { target: { value: "만" } });
  fireEvent.change(screen.getByLabelText("1번째 이름"), { target: { value: "쿠팡" } });
  fireEvent.change(screen.getByLabelText("1번째 값"), { target: { value: "1280" } });
  fireEvent.change(screen.getByLabelText("2번째 이름"), { target: { value: "스마트스토어" } });
  fireEvent.change(screen.getByLabelText("2번째 값"), { target: { value: "860" } });
}

const make = () => fireEvent.click(screen.getByRole("button", { name: "모션 만들기" }));

describe("MotionPanel", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(api, "listMotionTemplates").mockResolvedValue(TEMPLATES);
  });
  afterEach(cleanup);

  it("고를 수 있는 종류를 서버에서 받아 오고 첫째가 골라져 있다", async () => {
    render(<MotionPanel projectId="project-a" />);
    await waitFor(() => expect(screen.getByRole("button", { name: "막대 비교" })).toHaveAttribute("aria-pressed", "true"));
    expect(screen.getByRole("button", { name: "금액 카운터" })).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByRole("button", { name: "단계 목록" })).toBeTruthy();
  });

  it("막대 비교는 적은 그대로 보낸다", async () => {
    const create = vi.spyOn(api, "createMotion").mockResolvedValue(made());
    vi.spyOn(api, "materializeLibraryAsset").mockResolvedValue({} as never);
    render(<MotionPanel projectId="project-a" />);
    await fillBars();
    make();
    await waitFor(() => expect(create).toHaveBeenCalled());
    expect(create.mock.calls[0][0]).toEqual({
      template: "bar_compare",
      variables: { title: "월 수익 비교", subtitle: "", unit: "만", bars: [{ label: "쿠팡", value: 1280 }, { label: "스마트스토어", value: 860 }] },
      duration_sec: 6,
      layout: "full",
    });
  });

  it("작은 창(투명)을 고르면 overlay로 보내고, 결과 말에 화면에 얹기를 알려 준다", async () => {
    const create = vi.spyOn(api, "createMotion").mockResolvedValue(made({ layout: "overlay", format: "webm" }));
    vi.spyOn(api, "materializeLibraryAsset").mockResolvedValue({} as never);
    render(<MotionPanel projectId="project-a" />);
    await fillBars();
    expect(screen.getByRole("button", { name: "전체 화면" })).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(screen.getByRole("button", { name: "작은 창(투명)" }));
    expect(screen.getByText(/영상 위에 작게 얹어요/)).toBeTruthy();
    make();
    await waitFor(() => expect(create).toHaveBeenCalled());
    expect(create.mock.calls[0][0].layout).toBe("overlay");
    await waitFor(() => expect(screen.getByRole("status").textContent).toContain("화면에 얹기"));
  });

  it("장면 길이를 기본 길이로 쓴다 — 짧으면 숫자가 처음부터 다시 돈다", async () => {
    const create = vi.spyOn(api, "createMotion").mockResolvedValue(made());
    vi.spyOn(api, "materializeLibraryAsset").mockResolvedValue({} as never);
    render(<MotionPanel projectId="project-a" sceneSeconds={8.44} />);
    await fillBars();
    expect(screen.getByLabelText("길이(초)")).toHaveValue("8.4");
    make();
    await waitFor(() => expect(create.mock.calls[0][0].duration_sec).toBe(8.4));
  });

  it("장면이 길어도 30초, 짧아도 3초로 맞춘다", async () => {
    const { unmount } = render(<MotionPanel projectId="project-a" sceneSeconds={45} />);
    await waitFor(() => expect(screen.getByLabelText("길이(초)")).toHaveValue("30"));
    unmount();
    render(<MotionPanel projectId="project-a" sceneSeconds={1} />);
    await waitFor(() => expect(screen.getByLabelText("길이(초)")).toHaveValue("3"));
  });

  it("만드는 동안 잠기고 얼마나 걸리는지 말한다", async () => {
    let release: (value: MotionResult) => void = () => {};
    vi.spyOn(api, "createMotion").mockReturnValue(new Promise<MotionResult>((resolve) => { release = resolve; }));
    vi.spyOn(api, "materializeLibraryAsset").mockResolvedValue({} as never);
    render(<MotionPanel projectId="project-a" />);
    await fillBars();
    make();
    const busy = await screen.findByRole("button", { name: /만드는 중/ });
    expect(busy).toHaveProperty("disabled", true);
    expect(busy.textContent).toContain("1분");
    release(made());
    await screen.findByRole("status");
  });

  it("만들면 이 프로젝트로 가져오고 목록을 다시 읽게 한다", async () => {
    vi.spyOn(api, "createMotion").mockResolvedValue(made());
    const materialize = vi.spyOn(api, "materializeLibraryAsset").mockResolvedValue({} as never);
    const onMade = vi.fn();
    render(<MotionPanel projectId="project-a" onMade={onMade} />);
    await fillBars();
    make();
    await waitFor(() => expect(materialize).toHaveBeenCalledWith("user_m1", "project-a"));
    await waitFor(() => expect(onMade).toHaveBeenCalled());
    expect((await screen.findByRole("status")).textContent).toContain("장면을 고르고");
  });

  it("가져오지 못하면 자료실에서 꺼내 쓰라고 말한다", async () => {
    vi.spyOn(api, "createMotion").mockResolvedValue(made());
    vi.spyOn(api, "materializeLibraryAsset").mockRejectedValue(new Error("x"));
    render(<MotionPanel projectId="project-a" />);
    await fillBars();
    make();
    expect((await screen.findByRole("status")).textContent).toContain("자료실에서 가져오기");
  });

  it.each([
    ["motion_engine_not_prepared", "처음 한 번 준비하는 중"],
    ["motion_bridge_not_running", "VideoBox를 다시 켜 주세요"],
    ["motion_busy", "다른 모션을 만드는 중"],
    ["motion_took_too_long", "길이를 줄이고"],
    ["motion_variables_invalid", "적은 내용을 다시 확인"],
  ])("%s 이면 그에 맞는 말을 한다", async (reason, expected) => {
    vi.spyOn(api, "createMotion").mockRejectedValue(new ApiRequestError(reason, 503, "/api/library/motions", reason));
    render(<MotionPanel projectId="project-a" />);
    await fillBars();
    make();
    expect((await screen.findByRole("alert")).textContent).toContain(expected);
  });

  it("< > 기호를 적으면 보내기 전에 막고 이유를 말한다", async () => {
    const create = vi.spyOn(api, "createMotion");
    render(<MotionPanel projectId="project-a" />);
    await fillBars();
    fireEvent.change(screen.getByLabelText("제목"), { target: { value: "<b>굵게</b>" } });
    expect(screen.getByRole("button", { name: "모션 만들기" })).toHaveProperty("disabled", true);
    expect(screen.getByText("< > 기호는 쓸 수 없어요.")).toBeTruthy();
    expect(create).not.toHaveBeenCalled();
  });

  it("단계 목록과 금액 카운터도 적은 그대로 보낸다", async () => {
    const create = vi.spyOn(api, "createMotion").mockResolvedValue(made());
    vi.spyOn(api, "materializeLibraryAsset").mockResolvedValue({} as never);
    render(<MotionPanel projectId="project-a" />);
    await waitFor(() => expect(screen.getByRole("button", { name: "단계 목록" })).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: "단계 목록" }));
    fireEvent.change(screen.getByLabelText("제목"), { target: { value: "처음 3단계" } });
    fireEvent.change(screen.getByLabelText("1번째 단계"), { target: { value: "소싱" } });
    fireEvent.change(screen.getByLabelText("2번째 단계"), { target: { value: "정산" } });
    make();
    await waitFor(() => expect(create).toHaveBeenCalledTimes(1));
    expect(create.mock.calls[0][0]).toMatchObject({ template: "step_list", variables: { title: "처음 3단계", steps: ["소싱", "정산"] } });

    fireEvent.click(screen.getByRole("button", { name: "금액 카운터" }));
    fireEvent.change(screen.getByLabelText("금액"), { target: { value: "12345678" } });
    fireEvent.click(screen.getByRole("button", { name: "$" }));
    make();
    await waitFor(() => expect(create).toHaveBeenCalledTimes(2));
    expect(create.mock.calls[1][0]).toMatchObject({ template: "money_counter", variables: { lead: "", amount: 12345678, prefix: "$", suffix: "", caption: "" } });
  });
  it("글자 수 한도는 서버가 준 값으로 한 줄 알려 주고, 소수 금액은 막는다", async () => {
    const create = vi.spyOn(api, "createMotion");
    render(<MotionPanel projectId="project-a" />);
    await waitFor(() => expect(screen.getByRole("button", { name: "금액 카운터" })).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: "금액 카운터" }));
    expect(screen.getByText(/글자 수: 위 문구 20자/)).toBeTruthy();
    fireEvent.change(screen.getByLabelText("금액"), { target: { value: "12.5" } });
    expect(screen.getByRole("button", { name: "모션 만들기" })).toHaveProperty("disabled", true);
    expect(create).not.toHaveBeenCalled();
  });
  it("단계 줄은 넓은 틀을 쓰고(입력·지우기 둘뿐), 막대 줄은 네 칸 틀을 그대로 쓴다", async () => {
    render(<MotionPanel projectId="project-a" />);
    await waitFor(() => expect(screen.getByRole("button", { name: "단계 목록" })).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: "단계 목록" }));
    const row = (await screen.findByLabelText("1번째 단계")).closest(".vb-infographic__fact");
    expect(row?.className).toContain("vb-infographic__fact--wide");
    fireEvent.click(screen.getByRole("button", { name: "막대 비교" }));
    const bar = (await screen.findByLabelText("1번째 이름")).closest(".vb-infographic__fact");
    expect(bar?.className).not.toContain("--wide");
  });

  it("만드는 동안 바쁨을 알리고 끝나면 거둔다", async () => {
    let release: (value: MotionResult) => void = () => {};
    vi.spyOn(api, "createMotion").mockReturnValue(new Promise<MotionResult>((resolve) => { release = resolve; }));
    vi.spyOn(api, "materializeLibraryAsset").mockResolvedValue({} as never);
    const onBusyChange = vi.fn();
    render(<MotionPanel projectId="project-a" onBusyChange={onBusyChange} />);
    await fillBars();
    make();
    await waitFor(() => expect(onBusyChange).toHaveBeenLastCalledWith(true));
    release(made());
    await screen.findByRole("status");
    await waitFor(() => expect(onBusyChange).toHaveBeenLastCalledWith(false));
  });
  it("280초가 지나도 답이 없으면 놓여나서 닫을 수 있고, 늦게 온 답은 쓰지 않는다", async () => {
    let release: (value: MotionResult) => void = () => {};
    vi.spyOn(api, "createMotion").mockReturnValue(new Promise<MotionResult>((resolve) => { release = resolve; }));
    const materialize = vi.spyOn(api, "materializeLibraryAsset").mockResolvedValue({} as never);
    const onBusyChange = vi.fn();
    render(<MotionPanel projectId="project-a" onBusyChange={onBusyChange} />);
    await fillBars();
    vi.useFakeTimers();
    try {
      make();
      expect(onBusyChange).toHaveBeenCalledWith(true);
      await vi.advanceTimersByTimeAsync(280_000);
    } finally { vi.useRealTimers(); }
    expect((await screen.findByRole("alert")).textContent).toContain("너무 오래 걸려요");
    expect(screen.getByRole("button", { name: "모션 만들기" })).toHaveProperty("disabled", false);
    expect(onBusyChange).toHaveBeenLastCalledWith(false);
    release(made());
    await Promise.resolve();
    expect(materialize).not.toHaveBeenCalled();
    expect(screen.queryByRole("status")).toBeNull();
  });
});
