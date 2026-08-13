import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "../../api";
import { HomeYujinChat } from "./HomeYujinChat";

const session = {
  session_id: "session-a",
  project_id: "project-a",
  timeline_id: "timeline-a",
  session_revision: 1,
  segments: [],
  history: [],
} as never;

function exchange(userText: string, assistantText: string, blocked = false) {
  return {
    kind: "exchange",
    exchange: {
    user_message: {
      message_id: "u-1", conversation_id: "c-1", project_id: "project-a",
      session_id: "session-a", role: "user", text: userText, proposal_id: null,
      metadata: {}, client_message_id: "cm-1", created_at: "now",
    },
    assistant_message: {
      message_id: "a-1", conversation_id: "c-1", project_id: "project-a",
      session_id: "session-a", role: "assistant", text: assistantText,
      proposal_id: null, metadata: blocked ? { status: "blocked" } : {},
      client_message_id: null, created_at: "now",
    },
    },
  } as never;
}

describe("HomeYujinChat", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(globalThis.crypto, "randomUUID")
      .mockReturnValue("00000000-0000-4000-8000-000000000001");
  });

  it("lets the owner talk to Yujin without leaving home", async () => {
    vi.spyOn(api.api, "getLatestEditingSession").mockResolvedValue(session);
    vi.spyOn(api.api, "createDirectorConversation").mockResolvedValue({
      conversation_id: "c-1", project_id: "project-a", session_id: "session-a",
    } as never);
    const send = vi.spyOn(api.api, "sendDirectorMessage")
      .mockResolvedValue(exchange("자막 어떻게 할까?", "두 줄 이내를 권합니다."));

    render(<HomeYujinChat projectId="project-a" />);

    const input = await screen.findByLabelText("유진에게 물어보기");
    fireEvent.change(input, { target: { value: "자막 어떻게 할까?" } });
    fireEvent.click(screen.getByRole("button", { name: "보내기" }));

    expect(await screen.findByText("두 줄 이내를 권합니다.")).toBeVisible();
    expect(screen.getByText("자막 어떻게 할까?")).toBeVisible();
    await waitFor(() => expect(send).toHaveBeenCalledTimes(1));
  });

  it("reuses one conversation across messages", async () => {
    vi.spyOn(api.api, "getLatestEditingSession").mockResolvedValue(session);
    const create = vi.spyOn(api.api, "createDirectorConversation")
      .mockResolvedValue({
        conversation_id: "c-1", project_id: "project-a", session_id: "session-a",
      } as never);
    vi.spyOn(api.api, "sendDirectorMessage")
      .mockResolvedValue(exchange("하나", "네"));

    render(<HomeYujinChat projectId="project-a" />);
    const input = await screen.findByLabelText("유진에게 물어보기");

    for (const text of ["하나", "둘"]) {
      fireEvent.change(input, { target: { value: text } });
      fireEvent.click(screen.getByRole("button", { name: "보내기" }));
      await waitFor(() => expect(screen.getByLabelText("유진에게 물어보기")).toHaveValue(""));
    }

    expect(create).toHaveBeenCalledTimes(1);
  });

  it("explains itself instead of failing when there is no draft yet", async () => {
    vi.spyOn(api.api, "getLatestEditingSession").mockResolvedValue(null);
    const create = vi.spyOn(api.api, "createDirectorConversation");

    render(<HomeYujinChat projectId="project-a" />);

    expect(await screen.findByText("유진 대화 · 편집 필요")).toBeVisible();
    expect(screen.queryByLabelText("유진에게 물어보기")).toBeNull();
    expect(create).not.toHaveBeenCalled();
  });

  it("shows a plain message when Yujin cannot answer", async () => {
    vi.spyOn(api.api, "getLatestEditingSession").mockResolvedValue(session);
    vi.spyOn(api.api, "createDirectorConversation").mockResolvedValue({
      conversation_id: "c-1", project_id: "project-a", session_id: "session-a",
    } as never);
    vi.spyOn(api.api, "sendDirectorMessage").mockRejectedValue(new Error("offline"));

    render(<HomeYujinChat projectId="project-a" />);
    const input = await screen.findByLabelText("유진에게 물어보기");
    fireEvent.change(input, { target: { value: "안녕" } });
    fireEvent.click(screen.getByRole("button", { name: "보내기" }));

    expect(await screen.findByText(
      "유진이 지금 답하지 못했어요. 잠시 뒤 다시 보내 주세요.",
    )).toBeVisible();
  });

  it("does not send an empty message", async () => {
    vi.spyOn(api.api, "getLatestEditingSession").mockResolvedValue(session);
    vi.spyOn(api.api, "createDirectorConversation").mockResolvedValue({
      conversation_id: "c-1", project_id: "project-a", session_id: "session-a",
    } as never);
    const send = vi.spyOn(api.api, "sendDirectorMessage");

    render(<HomeYujinChat projectId="project-a" />);
    await screen.findByLabelText("유진에게 물어보기");
    fireEvent.click(screen.getByRole("button", { name: "보내기" }));

    expect(send).not.toHaveBeenCalled();
  });

  it("fills the home composer from a starter without sending", async () => {
    vi.spyOn(api.api, "getLatestEditingSession").mockResolvedValue(session);
    const send = vi.spyOn(api.api, "sendDirectorMessage");

    render(<HomeYujinChat projectId="project-a" />);
    const input = await screen.findByLabelText("유진에게 물어보기");
    fireEvent.click(screen.getByRole("button", { name: "이번 촬영으로 만들 만한 영상 형식 추천해 줘" }));

    expect(input).toHaveValue("이번 촬영으로 만들 만한 영상 형식 추천해 줘");
    expect(send).not.toHaveBeenCalled();
  });

  it("does not drop a late reply into a different project", async () => {
    // Switching project while Yujin is still answering must not show that
    // answer under the new project -- the owner would read it as advice about
    // footage it never saw.
    vi.spyOn(api.api, "getLatestEditingSession").mockResolvedValue(session);
    vi.spyOn(api.api, "createDirectorConversation").mockResolvedValue({
      conversation_id: "c-1", project_id: "project-a", session_id: "session-a",
    } as never);
    let release: (value: unknown) => void = () => {};
    vi.spyOn(api.api, "sendDirectorMessage").mockReturnValue(
      new Promise((resolve) => { release = resolve; }) as never,
    );

    const view = render(<HomeYujinChat projectId="project-a" />);
    const input = await screen.findByLabelText("유진에게 물어보기");
    fireEvent.change(input, { target: { value: "가" } });
    fireEvent.click(screen.getByRole("button", { name: "보내기" }));

    view.rerender(<HomeYujinChat projectId="project-b" />);
    release(exchange("가", "프로젝트 가에 대한 답"));
    await waitFor(() => expect(screen.getByLabelText("유진에게 물어보기")).toBeVisible());

    expect(screen.queryByText("프로젝트 가에 대한 답")).toBeNull();
  });
});
