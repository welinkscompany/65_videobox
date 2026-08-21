import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

import { StartChooser } from "./StartChooser";

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

/** owner: "어떤 버튼을 눌러야 할지 하나도 모르겠어."
 *
 *  첫 화면을 세어 보니 누를 수 있는 것이 50개쯤이고 그중 **다음에 할 일로 보이는
 *  것이 다섯 개**였다 — 새 영상 만들기·편집 계속하기·자산 준비하기·편집 열기·
 *  출력 확인. 다 그럴듯해서 어느 것이 지금 할 일인지 화면이 말해 주지 않았다.
 *
 *  Vrew처럼 **들어가는 길을 먼저 고르게** 한다(owner 지시 2026-08-21).
 *  여기서 지키는 것은 하나다 — 이 화면에서 고를 수 있는 길은 **실제로 뚫려 있는
 *  길뿐이다.** 없는 기능의 자리를 흉내 내면 배치가 거짓말을 한다. */
describe("시작 선택창", () => {
  it("만들던 것이 없으면 이어서 하는 길을 감춘다", () => {
    render(<StartChooser hasDraft={false} onStart={vi.fn()} />);

    expect(screen.getByRole("button", { name: /대본이 있어요/ })).toBeVisible();
    // 만들던 것이 없는데 "이어서"를 보여 주면 눌렀을 때 빈 편집판이 뜬다.
    expect(screen.queryByRole("button", { name: /이어서/ })).toBeNull();
  });

  it("만들던 것이 있으면 이어서 하는 길이 먼저 온다", () => {
    render(<StartChooser hasDraft onStart={vi.fn()} />);

    const buttons = screen.getAllByRole("button");
    expect(buttons[0]).toHaveAccessibleName(/이어서/);
    expect(screen.getByRole("button", { name: /대본이 있어요/ })).toBeVisible();
  });

  it("고른 길을 그대로 알려 준다", () => {
    const onStart = vi.fn();
    render(<StartChooser hasDraft onStart={onStart} />);

    fireEvent.click(screen.getByRole("button", { name: /대본이 있어요/ }));
    expect(onStart).toHaveBeenCalledWith("script");

    fireEvent.click(screen.getByRole("button", { name: /이어서/ }));
    expect(onStart).toHaveBeenCalledWith("continue");
  });

  it("찍어 둔 영상으로 들어가는 길을 준다", () => {
    // **갱신 이유(2026-08-21).** 이 시험은 원래 "아직 만들지 않은 길은 아예
    // 보여 주지 않는다"였고, 영상으로 들어가는 길이 없다는 것을 고정하고 있었다.
    // 그 사이 그 길이 실제로 뚫렸다(`POST .../source-video/upload`, 7ed84d040) --
    // 이제는 **감추는 쪽이** 거짓말이다. 지키려던 것은 "없는 길을 흉내 내지
    // 않는다"이지 "영상 길이 없다"가 아니었으므로, 지키는 것은 그대로 두고
    // 값만 현재 사실에 맞춘다.
    render(<StartChooser hasDraft={false} onStart={vi.fn()} />);

    expect(screen.getByRole("button", { name: /찍어 둔 영상이 있어요/ })).toBeVisible();
  });

  it("아직 만들지 않은 길은 아예 보여 주지 않는다", () => {
    // 유진이 처음부터 대본을 써 주는 길은 아직 없다. 회색으로 띄워 두는 것도
    // 안 한다 -- 누를 수 없는 단추는 고장으로 읽힌다.
    render(<StartChooser hasDraft={false} onStart={vi.fn()} />);

    expect(screen.queryByRole("button", { name: /유진이 대본/ })).toBeNull();
  });

  it("고른 길이 영상이면 그것도 그대로 알려 준다", () => {
    const onStart = vi.fn();
    render(<StartChooser hasDraft={false} onStart={onStart} />);

    fireEvent.click(screen.getByRole("button", { name: /찍어 둔 영상이 있어요/ }));
    expect(onStart).toHaveBeenCalledWith("footage");
  });

  it("고를 것이 셋을 넘지 않는다", () => {
    // **갱신 이유(2026-08-21).** 원래 상한이 둘이었다. 그 둘은 "지금 뚫려 있는
    // 길이 둘"이라는 당시 사실을 적은 것이지, 둘이 옳은 수라는 결정이 아니었다.
    // 지키려는 것은 수가 아니라 **이 화면이 다시 목록이 되지 않는 것**이다 --
    // 이 선택창이 생긴 이유가 "다섯 개가 다 그럴듯해 보인다"였다.
    // 길이 하나 늘었으므로 상한도 하나 올린다. 더 올릴 때는 이 이유를 다시 본다.
    render(<StartChooser hasDraft onStart={vi.fn()} />);

    expect(screen.getAllByRole("button")).toHaveLength(3);
  });
});
