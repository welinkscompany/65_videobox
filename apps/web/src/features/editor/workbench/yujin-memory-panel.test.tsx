import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { RightDock } from "./RightDock";

afterEach(cleanup);

const pending = {
  candidateId: "memory-1",
  text: "빠른 컷 편집을 선호합니다.",
  category: "pacing",
  status: "pending",
  storageStatus: "not_requested",
  retryable: false,
  action: "idle",
  error: null,
} as const;

const memoryCallbacks = () => ({
  candidateDraft: "",
  candidateCategory: "pacing" as const,
  createAction: "idle" as const,
  createError: null,
  canCreateCandidate: true,
  onCandidateDraftChange: vi.fn(),
  onCandidateCategoryChange: vi.fn(),
  onCreateCandidate: vi.fn(),
  onApproveAndStore: vi.fn(),
  onReject: vi.fn(),
  onStore: vi.fn(),
  onDelete: vi.fn(),
});

function renderDock(memory: Record<string, unknown>) {
  const rendered = render(
    <RightDock
      draft=""
      onDraftChange={vi.fn()}
      onSendMessage={vi.fn()}
      onManualEdit={vi.fn()}
      memory={memory as never}
      conversationScroll={{
        key: "route-a",
        top: 64,
        pinnedToBottom: false,
      }}
      inspectorTargets={[
        { id: "segment-1", label: "장면 1", kind: "caption" },
      ]}
    />,
  );
  // 이 파일은 기억 패널을 다룬다 -- 탭으로 나뉜 뒤(2026-08-30)로는 `유진`
  // 탭을 먼저 열어야 그 안의 기억 패널이 보인다(기억은 따로 탭이 아니라
  // 그 대화 다음 자리에 있다).
  fireEvent.click(screen.getByRole("tab", { name: "유진" }));
  return rendered;
}


// 편집 항목은 `속성` 탭 안에 있고 그 탭이 기본이다(2026-08-30, 캡컷처럼
// 고른 것의 속성이 바로 보인다). 다른 탭에 가 있을 때만 넘어간다.
function openInspector(): void {
  if (screen.queryByRole("region", { name: "편집 항목" })) return;
  fireEvent.click(screen.getByRole("tab", { name: "속성" }));
}

describe("Yujin memory panel", () => {
  it("has one separate explicit typed producer and never fires it automatically", () => {
    const callbacks = memoryCallbacks();
    renderDock({
      candidates: [],
      loadError: null,
      ...callbacks,
      candidateDraft: "자막은 두 줄 이내를 선호합니다.",
      candidateCategory: "caption",
    });

    const panel = screen.getByRole("region", { name: "유진 기억" });
    expect(callbacks.onCreateCandidate).not.toHaveBeenCalled();
    fireEvent.change(within(panel).getByLabelText("기억 종류"), {
      target: { value: "caption" },
    });
    fireEvent.change(within(panel).getByLabelText("기억 후보"), {
      target: { value: "자막은 한 줄을 선호합니다." },
    });
    expect(callbacks.onCandidateCategoryChange).toHaveBeenCalledWith("caption");
    expect(callbacks.onCandidateDraftChange).toHaveBeenCalledWith(
      "자막은 한 줄을 선호합니다.",
    );
    expect(callbacks.onCreateCandidate).not.toHaveBeenCalled();

    fireEvent.click(within(panel).getByRole(
      "button", { name: "기억 후보 만들기" },
    ));
    expect(callbacks.onCreateCandidate).toHaveBeenCalledTimes(1);
    expect(callbacks.onApproveAndStore).not.toHaveBeenCalled();
    expect(callbacks.onStore).not.toHaveBeenCalled();
  });

  it("requires explicit approve-and-store or reject and renders no source/provider data", () => {
    const callbacks = memoryCallbacks();
    renderDock({
      candidates: [pending],
      loadError: null,
      ...callbacks,
    });

    const panel = screen.getByRole("region", { name: "유진 기억" });
    expect(panel).toHaveTextContent("빠른 컷 편집을 선호합니다.");
    expect(panel).toHaveTextContent("편집 템포");
    expect(panel).not.toHaveTextContent(/source_message|provider|memory_ref/i);
    expect(callbacks.onApproveAndStore).not.toHaveBeenCalled();
    expect(callbacks.onStore).not.toHaveBeenCalled();

    fireEvent.click(within(panel).getByRole(
      "button", { name: "승인하고 저장" },
    ));
    expect(callbacks.onApproveAndStore).toHaveBeenCalledWith("memory-1");
    expect(callbacks.onStore).not.toHaveBeenCalled();

    fireEvent.click(within(panel).getByRole(
      "button", { name: "거절" },
    ));
    expect(callbacks.onReject).toHaveBeenCalledWith("memory-1");
  });

  it("shows controlled saving, stored, failed retry, and delete states", () => {
    const callbacks = memoryCallbacks();
    const rendered = renderDock({
      candidates: [{ ...pending, action: "saving" }],
      loadError: null,
      ...callbacks,
    });
    const panel = screen.getByRole("region", { name: "유진 기억" });
    expect(within(panel).getByText("저장 중")).toBeVisible();
    expect(within(panel).queryByRole(
      "button", { name: "승인하고 저장" },
    )).toBeNull();
    expect(within(panel).getByRole(
      "button", { name: "기억 후보 만들기" },
    )).toBeVisible();

    rendered.rerender(
      <RightDock
        draft=""
        onDraftChange={vi.fn()}
        memory={{
          candidates: [{
            ...pending,
            status: "approved",
            storageStatus: "failed_retryable",
            retryable: true,
            action: "idle",
            error: "save",
          }],
          loadError: null,
          ...callbacks,
        } as never}
      />,
    );
    expect(within(panel).getByText(
      "기억을 저장하지 못했어요. 편집과 대화는 계속할 수 있어요.",
    )).toBeVisible();
    fireEvent.click(within(panel).getByRole(
      "button", { name: "저장 다시 시도" },
    ));
    expect(callbacks.onStore).toHaveBeenCalledWith("memory-1");

    rendered.rerender(
      <RightDock
        draft=""
        onDraftChange={vi.fn()}
        memory={{
          candidates: [{
            ...pending,
            status: "approved",
            storageStatus: "claimed",
            action: "idle",
          }],
          loadError: null,
          ...callbacks,
        } as never}
      />,
    );
    expect(within(panel).getByText("저장 처리 중")).toBeVisible();
    expect(within(panel).queryByRole(
      "button", { name: /저장|시도/ },
    )).toBeNull();

    rendered.rerender(
      <RightDock
        draft=""
        onDraftChange={vi.fn()}
        memory={{
          candidates: [{
            ...pending,
            status: "approved",
            storageStatus: "claimed",
            retryable: true,
            action: "idle",
          }],
          loadError: null,
          ...callbacks,
        } as never}
      />,
    );
    expect(within(panel).getByRole(
      "button", { name: "저장 다시 시도" },
    )).toBeEnabled();
    fireEvent.click(within(panel).getByRole(
      "button", { name: "저장 다시 시도" },
    ));
    expect(callbacks.onStore).toHaveBeenCalledWith("memory-1");

    rendered.rerender(
      <RightDock
        draft=""
        onDraftChange={vi.fn()}
        memory={{
          candidates: [{
            ...pending,
            status: "approved",
            storageStatus: "stored",
            action: "idle",
          }],
          loadError: null,
          ...callbacks,
        } as never}
      />,
    );
    expect(within(panel).getByText("저장됨")).toBeVisible();
    fireEvent.click(within(panel).getByRole(
      "button", { name: "기억 삭제" },
    ));
    expect(callbacks.onDelete).toHaveBeenCalledWith("memory-1");

    rendered.rerender(
      <RightDock
        draft=""
        onDraftChange={vi.fn()}
        memory={{
          candidates: [{
            ...pending,
            status: "approved",
            storageStatus: "stored",
            action: "idle",
            error: "delete",
          }],
          loadError: null,
          ...callbacks,
        } as never}
      />,
    );
    expect(within(panel).getByText(
      "기억을 삭제하지 못했어요. 다시 시도할 수 있어요.",
    )).toBeVisible();
    fireEvent.click(within(panel).getByRole(
      "button", { name: "삭제 다시 시도" },
    ));
    expect(callbacks.onDelete).toHaveBeenCalledTimes(2);
  });

  it("keeps candidate and conversation usable across Inspector and memory failure", () => {
    const callbacks = memoryCallbacks();
    renderDock({
      candidates: [pending],
      loadError: "기억을 불러오지 못했어요.",
      ...callbacks,
    });
    openInspector();
    // 탭으로 나뉜 뒤(2026-08-30)로는 `속성`을 떠나는 것 자체가 예전의
    // "편집 항목 닫기"다 -- `유진` 탭 안에서 대화와 기억이 둘 다 멀쩡한지 본다
    // (기억은 따로 탭이 아니라 그 대화 다음 자리에 있다).
    fireEvent.click(screen.getByRole("tab", { name: "유진" }));
    expect(screen.getByRole("log", { name: "유진 대화" }).scrollTop)
      .toBe(64);
    expect(screen.getByLabelText("유진에게 요청하기")).toBeEnabled();
    expect(screen.getByRole("button", { name: "요청 보내기" }))
      .toBeDisabled();
    expect(screen.getByRole("region", { name: "유진 기억" }))
      .toHaveTextContent("빠른 컷 편집을 선호합니다.");
  });
});
