/** 편집기 안에서 인포그래픽을 만드는 자리 (owner 지시 2026-09-07).
 *
 *  여기서 지키는 것 셋:
 *  1. **적어 준 숫자가 그대로 서버로 간다.** 여기서 흘리면 엉뚱한 숫자의 그림이 나온다.
 *  2. **1~2분 걸리는 동안 단추가 잠긴다.** 안 잠그면 창작자가 두 번 누른다.
 *  3. **아쉬운 점을 숨기지 않는다.** 숨기면 다 된 줄 알고 영상에 넣는다. */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { InfographicPanel } from "./InfographicPanel";
import { api, type InfographicResult } from "../../../api";

const STYLES = {
  styles: [
    { key: "dark_glass", korean_name: "어두운 유리", direction: "깊은 배경 위에 유리판" },
    { key: "editorial", korean_name: "잡지 편집", direction: "여백으로 말한다" },
  ],
};

function madeResult(overrides: Partial<InfographicResult> = {}): InfographicResult {
  return {
    library_asset_id: "user_abc", title: "수수료", style: "dark_glass",
    attempts: 1, corrected: [], remaining_problems: [], library_error: null, ...overrides,
  };
}

/** 결 목록이 실려 온 뒤라야 "지금 걸린 결"이 정해진다 -- 그 전에 누르면 결이
 *  빈 채로 나간다. 화면이 실제로 밟는 순서와 같게 기다린다. */
async function readyThenFill() {
  await waitFor(() => expect(screen.getByRole("button", { name: "어두운 유리" })).toBeTruthy());
  fireEvent.change(screen.getByPlaceholderText("스마트스토어 판매 수수료 구조"), { target: { value: "수수료 구조" } });
  fireEvent.change(screen.getByLabelText("1번째 이름"), { target: { value: "네이버 결제 수수료" } });
  fireEvent.change(screen.getByLabelText("1번째 값"), { target: { value: "3.4" } });
}

function make() {
  fireEvent.click(screen.getByRole("button", { name: "인포그래픽 만들기" }));
}

describe("InfographicPanel", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(api, "listInfographicStyles").mockResolvedValue(STYLES);
  });

  afterEach(cleanup);

  it("고를 수 있는 결을 서버에서 받아 온다 — 화면이 이름을 베껴 적지 않는다", async () => {
    render(<InfographicPanel />);
    await waitFor(() => expect(screen.getByRole("button", { name: "어두운 유리" })).toBeTruthy());
    expect(screen.getByRole("button", { name: "잡지 편집" })).toBeTruthy();
    // **목록과 "지금 걸린 것"은 한 쌍이다.** 걸린 것을 안 보여 주면 되돌릴 수 없다.
    expect(screen.getByRole("button", { name: "어두운 유리" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "잡지 편집" })).toHaveAttribute("aria-pressed", "false");
  });

  it("다른 결로 바꾸면 그 결로 보낸다", async () => {
    const create = vi.spyOn(api, "createInfographic").mockResolvedValue(madeResult());
    render(<InfographicPanel />);
    await readyThenFill();
    fireEvent.click(screen.getByRole("button", { name: "잡지 편집" }));
    make();
    await waitFor(() => expect(create).toHaveBeenCalled());
    expect(create.mock.calls[0][0].style).toBe("editorial");
  });

  it("적어 준 숫자를 그대로 보낸다", async () => {
    const create = vi.spyOn(api, "createInfographic").mockResolvedValue(madeResult());
    render(<InfographicPanel />);
    await readyThenFill();
    make();

    await waitFor(() => expect(create).toHaveBeenCalled());
    expect(create.mock.calls[0][0]).toEqual({
      topic: "수수료 구조",
      facts: [{ label: "네이버 결제 수수료", value: 3.4, unit: "%" }],
      style: "dark_glass",
    });
  });

  it("주제나 숫자가 없으면 만들 수 없다 — 2분 기다린 뒤 실패하는 것보다 낫다", async () => {
    render(<InfographicPanel />);
    await waitFor(() => expect(screen.getByRole("button", { name: "어두운 유리" })).toBeTruthy());
    expect(screen.getByRole("button", { name: "인포그래픽 만들기" })).toHaveProperty("disabled", true);
  });

  it("만드는 동안 단추가 잠기고 얼마나 걸리는지 말한다", async () => {
    let release: (value: InfographicResult) => void = () => {};
    vi.spyOn(api, "createInfographic").mockReturnValue(
      new Promise<InfographicResult>((resolve) => { release = resolve; }),
    );
    render(<InfographicPanel />);
    await readyThenFill();
    make();

    const busy = await screen.findByRole("button", { name: /그리는 중입니다/ });
    expect(busy).toHaveProperty("disabled", true);
    expect(busy.textContent).toContain("1~2분");
    release(madeResult());
    await screen.findByRole("status");
  });

  it("만들고 나면 어디 갔는지 말하고, 목록을 다시 읽게 한다", async () => {
    vi.spyOn(api, "createInfographic").mockResolvedValue(madeResult());
    const onMade = vi.fn();
    render(<InfographicPanel onMade={onMade} />);
    await readyThenFill();
    make();

    const told = await screen.findByRole("status");
    expect(told.textContent).toContain("자료실 그림");
    await waitFor(() => expect(onMade).toHaveBeenCalled());
  });

  it("아직 아쉬운 점이 있으면 숨기지 않는다", async () => {
    vi.spyOn(api, "createInfographic").mockResolvedValue(
      madeResult({ attempts: 2, corrected: ["아래가 182px 넘쳤다"], remaining_problems: ["글자가 겹친다"] }),
    );
    render(<InfographicPanel />);
    await readyThenFill();
    make();

    const warned = await screen.findByRole("alert");
    expect(warned.textContent).toContain("글자가 겹친다");
    expect((await screen.findByRole("status")).textContent).toContain("아래가 182px 넘쳤다");
  });

  it("모델이 지어낸 숫자를 그대로 알려 준다 — 문자열로만 다루면 [object Object]가 된다", async () => {
    vi.spyOn(api, "createInfographic").mockRejectedValue({
      detail: { reason: "infographic_did_not_pass_checks", problems: "준 적 없는 숫자가 그림에 있다: 316000" },
    });
    render(<InfographicPanel />);
    await readyThenFill();
    make();

    const failed = await screen.findByRole("alert");
    expect(failed.textContent).toContain("316000");
    expect(failed.textContent).not.toContain("object Object");
  });

  it("다리가 안 켜져 있으면 다시 누르라고 하지 않는다", async () => {
    vi.spyOn(api, "createInfographic").mockRejectedValue({ detail: "infographic_bridge_not_running" });
    render(<InfographicPanel />);
    await readyThenFill();
    make();

    const failed = await screen.findByRole("alert");
    expect(failed.textContent).toContain("VideoBox를 다시 켜 주세요");
    // **개발 낱말을 화면에 쓰지 않는다** (§10.13 creator-language).
    expect(failed.textContent).not.toContain("bridge");
  });
});
