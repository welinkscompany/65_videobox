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

  // task-3-brief.md: `conflict.field`/`conflict.reason`을 그대로 찍으면
  // (`crop`, `master_changed_while_locked`) owner가 뭘 골라야 하는지 알 수
  // 없다. 백엔드 사유는 `output_variants.py`의 닫힌 Literal 두 값뿐이다 --
  // 둘 다 사람 말로 옮긴다.
  it("서버가 보내는 실제 사유 코드를 한국어 문장으로 보여준다", () => {
    render(
      <VariantConflictPanel
        conflicts={[{ field: "crop", reason: "master_changed_while_locked" }]}
        onKeep={vi.fn()}
        onRebase={vi.fn()}
      />,
    );
    expect(screen.queryByText("crop", { exact: true })).not.toBeInTheDocument();
    expect(screen.queryByText("master_changed_while_locked")).not.toBeInTheDocument();
    expect(screen.getByText(/고정/)).toBeVisible();
  });

  it("표에 없는 항목·사유가 와도 코드를 그대로 보여주지 않는다", () => {
    render(
      <VariantConflictPanel
        conflicts={[{ field: "unknown_field_x", reason: "unknown_reason_x" }]}
        onKeep={vi.fn()}
        onRebase={vi.fn()}
      />,
    );
    expect(screen.queryByText("unknown_field_x")).not.toBeInTheDocument();
    expect(screen.queryByText("unknown_reason_x")).not.toBeInTheDocument();
  });
});
