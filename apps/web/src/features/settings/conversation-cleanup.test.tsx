import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "../../api";
import { ConversationCleanup } from "./ConversationCleanup";

describe("유진 대화 정리", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("쌓인 대화를 보여주고 지운 것만 목록에서 뺀다", async () => {
    // 대화는 쌓이기만 하고 지울 방법이 없었다 -- 점검 시점에 28건이었다.
    vi.spyOn(api.api, "listDirectorConversations").mockResolvedValue({
      conversations: [
        { conversation_id: "conv-1", session_id: "s1", created_at: "2026-08-01T00:00:00Z", updated_at: "2026-08-01T00:00:00Z", message_count: 4 },
        { conversation_id: "conv-2", session_id: "s1", created_at: "2026-08-02T00:00:00Z", updated_at: "2026-08-02T00:00:00Z", message_count: 0 },
      ],
    } as never);
    const remove = vi.spyOn(api.api, "deleteDirectorConversation").mockResolvedValue(undefined as never);

    render(<ConversationCleanup projectId="project-a" />);

    expect(await screen.findByText(/주고받은 말 4개/)).toBeVisible();
    expect(screen.getByText(/아직 주고받은 말이 없어요/)).toBeVisible();

    fireEvent.click(screen.getAllByRole("button", { name: "이 대화 지우기" })[0]);

    await waitFor(() => expect(remove).toHaveBeenCalledWith("project-a", "conv-1"));
    await waitFor(() => expect(screen.queryByText(/주고받은 말 4개/)).toBeNull());
    expect(screen.getByText(/아직 주고받은 말이 없어요/)).toBeVisible();
  });

  it("지우지 못하면 목록을 되돌리고 그 사실을 말한다", async () => {
    vi.spyOn(api.api, "listDirectorConversations").mockResolvedValue({
      conversations: [
        { conversation_id: "conv-1", session_id: "s1", created_at: "2026-08-01T00:00:00Z", updated_at: "2026-08-01T00:00:00Z", message_count: 2 },
      ],
    } as never);
    vi.spyOn(api.api, "deleteDirectorConversation").mockRejectedValue(new Error("nope"));

    render(<ConversationCleanup projectId="project-a" />);
    fireEvent.click(await screen.findByRole("button", { name: "이 대화 지우기" }));

    expect(await screen.findByText("대화를 지우지 못했어요. 잠시 뒤 다시 눌러 주세요.")).toBeVisible();
    expect(screen.getByText(/주고받은 말 2개/)).toBeVisible();
  });

  it("지울 대화가 없으면 그렇게 말한다", async () => {
    vi.spyOn(api.api, "listDirectorConversations").mockResolvedValue({ conversations: [] } as never);

    render(<ConversationCleanup projectId="project-a" />);

    expect(await screen.findByText("아직 나눈 대화가 없어요.")).toBeVisible();
  });
});
