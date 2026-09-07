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
    // **갱신 이유(2026-08-27).** 이 시험은 `이어서`가 첫째로 오는 것과, 나머지 길이
    // 같이 보이는 것을 함께 잡고 있었다. 지키려던 것은 **순서**다 -- 만들던 것이
    // 있으면 그것이 먼저다. 이제 나머지 길은 접히므로 순서만 그대로 잡는다.
    render(<StartChooser hasDraft onStart={vi.fn()} />);

    expect(screen.getAllByRole("button")[0]).toHaveAccessibleName(/이어서/);

    fireEvent.click(screen.getByRole("button", { name: /다르게 시작하기/ }));
    expect(screen.getByRole("button", { name: /대본이 있어요/ })).toBeVisible();
    // 펴고 나서도 이어서가 여전히 먼저다.
    expect(screen.getAllByRole("button")[0]).toHaveAccessibleName(/이어서/);
  });

  it("고른 길을 그대로 알려 준다", () => {
    const onStart = vi.fn();
    render(<StartChooser hasDraft onStart={onStart} />);

    fireEvent.click(screen.getByRole("button", { name: /이어서/ }));
    expect(onStart).toHaveBeenCalledWith("continue");

    // 접힌 길도 펴고 나면 똑같이 그대로 알려 준다.
    fireEvent.click(screen.getByRole("button", { name: /다르게 시작하기/ }));
    fireEvent.click(screen.getByRole("button", { name: /대본이 있어요/ }));
    expect(onStart).toHaveBeenCalledWith("script");
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

  it("아무것도 없는 사람에게도 들어갈 길을 준다", () => {
    // **갱신 이유(2026-08-21).** 이 시험은 원래 "아직 만들지 않은 길은 아예
    // 보여 주지 않는다"였고, 유진이 처음부터 대본을 써 주는 길이 없다는 것을
    // 고정하고 있었다. 그 사이 그 길이 실제로 뚫렸다
    // (`POST .../script-drafts`) -- 이제는 **감추는 쪽이** 거짓말이다.
    // 지키려던 것은 "없는 길을 흉내 내지 않는다"이지 "유진 대본 길이 없다"가
    // 아니었으므로, 지키는 것은 그대로 두고 값만 현재 사실에 맞춘다.
    //
    // 앞의 세 길은 전부 **이미 가진 것**을 전제한다 -- 만들던 편집본, 써 둔
    // 대본, 찍어 둔 영상. 아무것도 없는 사람은 들어갈 문이 없었다.
    render(<StartChooser hasDraft={false} onStart={vi.fn()} />);

    expect(screen.getByRole("button", { name: /유진이 대본 초안/ })).toBeVisible();
  });

  it("고른 길이 유진 대본이면 그것도 그대로 알려 준다", () => {
    const onStart = vi.fn();
    render(<StartChooser hasDraft={false} onStart={onStart} />);

    fireEvent.click(screen.getByRole("button", { name: /아직 아무것도 없어요/ }));
    expect(onStart).toHaveBeenCalledWith("draft");
  });

  it("고른 길이 영상이면 그것도 그대로 알려 준다", () => {
    const onStart = vi.fn();
    render(<StartChooser hasDraft={false} onStart={onStart} />);

    fireEvent.click(screen.getByRole("button", { name: /찍어 둔 영상이 있어요/ }));
    expect(onStart).toHaveBeenCalledWith("footage");
  });

  it("만들던 것이 있으면 시작하는 길을 되묻지 않는다", () => {
    // owner(2026-08-27): "우리 메뉴가 너무 각각 페이지별로 따로 놀아."
    //
    // 재 보니 첫 화면에 "다음에 할 일"로 보이는 것이 **16~17개**였다. 2026-08-21에
    // 다섯을 세고 이 선택창을 만들었는데 그 뒤로 도로 늘었다.
    //
    // 원인 하나가 여기다. **이미 만들던 영상이 있는 프로젝트에서도 `어떻게
    // 시작할까요?`라고 묻는다.** 이미 답이 나온 질문이고, 나머지 세 길은 전부
    // "처음부터 다시"라서 지금 할 일과 경쟁한다.
    //
    // 지키는 것은 앞의 상한 시험과 같다 -- **이 화면이 다시 목록이 되지 않는 것**.
    // 상한을 넷에서 더 내리는 것이지 성격이 바뀌는 게 아니다.
    render(<StartChooser hasDraft onStart={vi.fn()} />);

    expect(screen.getByRole("button", { name: /이어서/ })).toBeVisible();
    // 처음부터 다시 시작하는 길은 접어 둔다. 없애지는 않는다 -- 감추면 거짓말이다.
    expect(screen.queryByRole("button", { name: /대본이 있어요/ })).toBeNull();
    expect(screen.getByRole("button", { name: /다르게 시작하기/ })).toBeVisible();
  });

  it("다르게 시작하고 싶으면 그때 나머지 길을 편다", () => {
    const onStart = vi.fn();
    render(<StartChooser hasDraft onStart={onStart} />);

    fireEvent.click(screen.getByRole("button", { name: /다르게 시작하기/ }));

    fireEvent.click(screen.getByRole("button", { name: /대본이 있어요/ }));
    expect(onStart).toHaveBeenCalledWith("script");
  });

  it("고를 것이 넷을 넘지 않는다", () => {
    // **갱신 이유(2026-08-21, 두 번째).** 상한이 둘 → 셋 → 넷으로 왔다. 매번
    // "지금 뚫려 있는 길이 몇인가"라는 당시 사실을 적은 것이지, 그 수가 옳다는
    // 결정이 아니었다. 지키려는 것은 수가 아니라 **이 화면이 다시 목록이 되지
    // 않는 것**이다 -- 이 선택창이 생긴 이유가 "다섯 개가 다 그럴듯해 보인다"였다.
    //
    // **갱신 이유(2026-08-27, 세 번째).** 상한이 내려갔다. 만들던 것이 있으면
    // 처음에 보이는 것은 `이어서` 하나와 `다르게 시작하기`뿐이다. 지키는 것은
    // 바뀌지 않았다 -- 오히려 더 세게 지킨다.
    //
    // 다음에 길을 또 더하고 싶으면 상한을 올리기 전에 먼저 물어라: 새 길이 정말
    // 다른 시작점인가, 아니면 이미 있는 길의 변형인가. 변형이면 그 길 안에서
    // 고르게 한다.
    render(<StartChooser hasDraft onStart={vi.fn()} />);

    expect(screen.getAllByRole("button")).toHaveLength(2);

    fireEvent.click(screen.getByRole("button", { name: /다르게 시작하기/ }));
    // 다 펴도 넷을 넘지 않는다.
    expect(screen.getAllByRole("button")).toHaveLength(4);
  });
});
