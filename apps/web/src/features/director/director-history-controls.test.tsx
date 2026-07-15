import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { DirectorHistoryControls, selectCurrentArtifacts } from "./DirectorHistoryControls";

describe("DirectorHistoryControls", () => {
  it("stale artifact는 현재 action에서 제외하고 revision과 사유를 history로 남긴다", () => {
    const artifacts = [
      { kind: "preview", source_session_revision: 3, is_current: true, invalidated_at: null, invalidated_reason: null },
      { kind: "final", source_session_revision: 2, is_current: false, invalidated_at: "2026-07-16T00:00:00Z", invalidated_reason: "session_revision_changed" },
    ];
    expect(selectCurrentArtifacts(artifacts)).toEqual([artifacts[0]]);
    render(<DirectorHistoryControls history={[{ mutation_type: "broll_override", segment_id: "seg-1", action_id: "a-1", label: "B-roll 변경", created_at: "2026-07-16T00:00:00Z", reversible: true, blocked_reason: null }]} artifacts={artifacts} onUndo={vi.fn()} onRedo={vi.fn()} />);
    expect(screen.getByText("preview")).toBeVisible();
    expect(screen.queryByRole("button", { name: "final 열기" })).not.toBeInTheDocument();
    expect(screen.getByText(/revision 2.*session_revision_changed/)).toBeVisible();
  });

  it("legacy artifact에 freshness 필드가 없으면 current로 유지한다", () => {
    const legacy = { kind: "subtitle", source_session_revision: 1 };
    expect(selectCurrentArtifacts([legacy])).toEqual([legacy]);
    render(<DirectorHistoryControls history={[]} artifacts={[legacy]} onUndo={vi.fn()} onRedo={vi.fn()} />);
    expect(screen.getByRole("button", { name: "subtitle 열기" })).toBeVisible();
  });
});
