import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { VariantSelector } from "./VariantSelector";

describe("VariantSelector", () => {
  it("offers master, horizontal, vertical and side-by-side in creator language", () => {
    const onSelect = vi.fn();
    render(<VariantSelector selected="master" onSelect={onSelect} />);

    expect(screen.getByRole("tab", { name: "마스터" })).toBeVisible();
    expect(screen.getByRole("tab", { name: "가로" })).toBeVisible();
    expect(screen.getByRole("tab", { name: "세로" })).toBeVisible();
    expect(screen.getByRole("tab", { name: "나란히" })).toBeVisible();
    fireEvent.click(screen.getByRole("tab", { name: "세로" }));
    expect(onSelect).toHaveBeenCalledWith("vertical_full");
  });
});
