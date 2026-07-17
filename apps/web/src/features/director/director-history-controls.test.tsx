import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { DirectorHistoryControls, selectCurrentArtifacts } from "./DirectorHistoryControls";

describe("DirectorHistoryControls", () => {
  it("오래된 결과는 현재 작업에서 제외하고 다시 만들 수 있다고 안내한다", () => {
    const artifacts = [
      { kind: "preview", source_session_revision: 3, is_current: true, invalidated_at: null, invalidated_reason: null },
      { kind: "final", source_session_revision: 2, is_current: false, invalidated_at: "2026-07-16T00:00:00Z", invalidated_reason: "session_revision_changed" },
    ];
    expect(selectCurrentArtifacts(artifacts)).toEqual([artifacts[0]]);
    render(<DirectorHistoryControls history={[{ mutation_type: "broll_override", segment_id: "seg-1", action_id: "a-1", label: "B-roll 변경", created_at: "2026-07-16T00:00:00Z", reversible: true, blocked_reason: null }]} artifacts={artifacts} onUndo={vi.fn()} onRedo={vi.fn()} />);
    expect(screen.getByText("미리보기")).toBeVisible();
    expect(screen.queryByRole("button", { name: "완성본 열기" })).not.toBeInTheDocument();
    expect(screen.getByText("이전 결과예요. 현재 편집본으로 다시 만들 수 있어요.")).toBeVisible();
  });

  it("legacy artifact에 freshness 필드가 없으면 current로 유지한다", () => {
    const legacy = { kind: "subtitle", source_session_revision: 1 };
    expect(selectCurrentArtifacts([legacy])).toEqual([legacy]);
    render(<DirectorHistoryControls history={[]} artifacts={[legacy]} onUndo={vi.fn()} onRedo={vi.fn()} />);
    expect(screen.getByRole("button", { name: "자막 열기" })).toBeVisible();
  });

  it("결과 종류와 차단 사유를 내부 값 대신 사용자 언어로 표시한다", () => {
    const artifacts = [
      { kind: "preview", source_session_revision: 3, is_current: true, invalidated_at: null, invalidated_reason: null },
      { kind: "final", source_session_revision: 2, is_current: false, invalidated_at: "2026-07-16T00:00:00Z", invalidated_reason: "session_revision_changed" },
    ];
    render(<DirectorHistoryControls history={[{ mutation_type: "broll_override", segment_id: "seg-1", action_id: "a-1", label: null, created_at: "2026-07-16T00:00:00Z", reversible: true, blocked_reason: "stale_output_asset" }]} artifacts={artifacts} onUndo={vi.fn()} onRedo={vi.fn()} />);

    expect(screen.getByRole("button", { name: "미리보기 열기" })).toBeVisible();
    expect(screen.getByText("영상 추천 변경 · 지금은 적용할 수 없어요. 다시 확인해 주세요.")).toBeVisible();
    expect(screen.queryByText(/preview|final|broll_override|stale_output_asset/i)).not.toBeInTheDocument();
  });

  it("내부 구현 라벨 대신 변경 종류를 사용자 언어로 표시한다", () => {
    render(<DirectorHistoryControls history={[{ mutation_type: "broll_override", segment_id: "seg-1", action_id: "a-1", label: "broll_override seg-1 revision 4 stale_output_asset", created_at: "2026-07-16T00:00:00Z", reversible: true, blocked_reason: null }]} artifacts={[]} onUndo={vi.fn()} onRedo={vi.fn()} />);

    expect(screen.getByText("영상 추천 변경")).toBeVisible();
    expect(screen.queryByText(/broll_override|seg-1|revision|stale_output_asset/i)).not.toBeInTheDocument();
  });
});
