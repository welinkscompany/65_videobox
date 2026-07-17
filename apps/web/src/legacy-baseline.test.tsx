import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";
import { DirectorHistoryControls } from "./features/director/DirectorHistoryControls";
import { DirectorWorkspace } from "./features/director/DirectorWorkspace";

const projects = [
  { project_id: "project-1", name: "첫 번째 프로젝트", status: "active", root_storage_uri: "local://project-1" },
  { project_id: "project-2", name: "두 번째 프로젝트", status: "active", root_storage_uri: "local://project-2" },
];

describe("legacy dashboard baseline", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("프로젝트를 바꾸면 현재 프로젝트를 눌린 항목으로 알린다", async () => {
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) =>
      String(input) === "/api/projects"
        ? Promise.resolve(new Response(JSON.stringify({ projects })))
        : new Promise<Response>(() => undefined),
    ));

    render(<App />);

    const first = await screen.findByRole("button", { name: /첫 번째 프로젝트/ });
    const second = screen.getByRole("button", { name: /두 번째 프로젝트/ });
    expect(first).toHaveAttribute("aria-pressed", "true");

    fireEvent.click(second);

    expect(first).toHaveAttribute("aria-pressed", "false");
    expect(second).toHaveAttribute("aria-pressed", "true");
  });

  it("작업 영역을 바꾸면 이전 탭은 해제하고 설정 내용을 보여 준다", () => {
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>(() => undefined)));

    render(<App />);

    const overview = screen.getByRole("button", { name: "개요" });
    const settings = screen.getByRole("button", { name: "설정" });
    expect(overview).toHaveAttribute("aria-pressed", "true");

    fireEvent.click(settings);

    expect(overview).toHaveAttribute("aria-pressed", "false");
    expect(settings).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("heading", { name: "음성 샘플" })).toBeVisible();
  });

  it("루미를 사용할 수 없으면 직접 편집으로 계속할 수 있다", () => {
    const onManualMode = vi.fn();

    render(<DirectorWorkspace
      state="blocked"
      projectId="project-1"
      sessionId="session-1"
      sessionRevision={1}
      proposal={null}
      sendMessage={vi.fn()}
      preflightProposal={vi.fn()}
      materializeCandidate={vi.fn()}
      applyProposal={vi.fn()}
      onManualMode={onManualMode}
    />);

    fireEvent.click(screen.getByRole("button", { name: "직접 편집하기" }));

    expect(onManualMode).toHaveBeenCalledOnce();
  });

  it("현재 미리보기·완성본 결과를 표시하고 이전 결과는 다시 만들도록 안내한다", () => {
    render(<DirectorHistoryControls
      history={[]}
      artifacts={[
        { kind: "preview", source_session_revision: 2, is_current: true },
        { kind: "final", source_session_revision: 2, is_current: true },
        { kind: "final", source_session_revision: 1, is_current: false },
      ]}
      onUndo={vi.fn()}
      onRedo={vi.fn()}
    />);

    expect(screen.getByRole("button", { name: "미리보기 열기" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "완성본 열기" })).toBeEnabled();
    expect(screen.getByText("이전 결과예요. 현재 편집본으로 다시 만들 수 있어요.")).toBeVisible();
  });
});
