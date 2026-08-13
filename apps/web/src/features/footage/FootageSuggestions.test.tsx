import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { FootageSuggestions } from "./FootageSuggestions";

describe("FootageSuggestions", () => {
  it("renders the shared footage starter registry and only fills the request", () => {
    const onChange = vi.fn();
    const onInterpret = vi.fn();

    render(<FootageSuggestions value="" onChange={onChange} onInterpret={onInterpret} />);

    const group = screen.getByRole("group", { name: "대화 스타터" });
    expect(within(group).getByRole("button", { name: "장면 변화로 나누기" })).toBeVisible();
    expect(within(group).getByRole("button", { name: "30초 묶음 만들기" })).toBeVisible();

    fireEvent.click(within(group).getByRole("button", { name: "장면 변화로 나누기" }));

    expect(onChange).toHaveBeenCalledWith("장면 변화로 나누기");
    expect(onInterpret).not.toHaveBeenCalled();
  });
});
