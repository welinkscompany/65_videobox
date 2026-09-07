import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

import { api } from "../../../api";
import { ScriptPane } from "./ScriptPane";

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

/** 편집기 안 `대본` 자리 (계획 §10 5단계).
 *
 *  완성의 정의는 계획서가 정했다: **"새 프로젝트가 `이야기`를 안 거치고도
 *  대본을 넣을 수 있다"**.
 *
 *  이 저장소는 이 자리를 한 번 **일부러 안 만들었다** -- `EditorAssetBrowser`
 *  주석: "지금 탭만 만들면 대본을 붙여넣은 뒤 갈 곳이 없는 막다른 자리가 된다".
 *  그 경고를 지킨다: 붙여넣어 저장까지 하되, **그 다음에 어디로 가는지**를
 *  같은 자리에서 알려 준다. 대본만 삼키고 아무 말도 안 하지 않는다.
 */
describe("대본 자리", () => {
  const props = { projectId: "project-a", onOpenStory: vi.fn() };

  it("붙여넣은 대본을 저장하고, 다음에 갈 곳을 알려 준다", async () => {
    const create = vi.spyOn(api, "createCreationBrief").mockResolvedValue({ brief_id: "brief-1" } as never);
    const onOpenStory = vi.fn();

    render(<ScriptPane {...props} onOpenStory={onOpenStory} />);
    fireEvent.change(screen.getByRole("textbox", { name: "대본" }), { target: { value: "오늘은 셀러 이야기예요" } });
    fireEvent.click(screen.getByRole("button", { name: "대본 저장" }));

    await waitFor(() => expect(create).toHaveBeenCalledWith("project-a", expect.objectContaining({
      script_text: "오늘은 셀러 이야기예요",
    })));
    // **막다른 자리가 되지 않게** 다음 걸음을 같은 자리에서 준다.
    expect(await screen.findByRole("button", { name: "이야기 이어서 하기" })).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "이야기 이어서 하기" }));
    expect(onOpenStory).toHaveBeenCalled();
  });

  it("빈 대본은 저장하지 않고 그렇게 말한다", async () => {
    const create = vi.spyOn(api, "createCreationBrief");

    render(<ScriptPane {...props} />);
    fireEvent.click(screen.getByRole("button", { name: "대본 저장" }));

    expect(await screen.findByText("대본을 붙여넣어 주세요.")).toBeVisible();
    expect(create).not.toHaveBeenCalled();
  });

  it("저장하지 못하면 쓴 것을 지우지 않고 그 자리에서 말한다", async () => {
    vi.spyOn(api, "createCreationBrief").mockRejectedValue(new Error("boom"));

    render(<ScriptPane {...props} />);
    fireEvent.change(screen.getByRole("textbox", { name: "대본" }), { target: { value: "쓰던 글" } });
    fireEvent.click(screen.getByRole("button", { name: "대본 저장" }));

    expect(await screen.findByText(/대본을 저장하지 못했어요/)).toBeVisible();
    expect(screen.getByRole("textbox", { name: "대본" })).toHaveValue("쓰던 글");
  });
});
