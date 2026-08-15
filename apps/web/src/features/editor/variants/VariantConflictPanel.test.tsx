import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { VariantConflictPanel } from "./VariantConflictPanel";

describe("VariantConflictPanel", () => {
  it("makes keep-local and rebase decisions visible", () => {
    const onKeep = vi.fn();
    const onRebase = vi.fn();
    render(<VariantConflictPanel conflicts={[{ field: "crop", reason: "마스터가 변경됨" }]} onKeep={onKeep} onRebase={onRebase} />);

    expect(screen.getByText("세로 편집과 마스터가 달라요")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "직접 조정 유지" }));
    fireEvent.click(screen.getByRole("button", { name: "마스터 기준 다시 맞추기" }));
    expect(onKeep).toHaveBeenCalledWith("crop");
    expect(onRebase).toHaveBeenCalledWith("crop");
  });
});
