import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

import { api } from "../../api";
import { ProjectTitleDialog } from "./ProjectTitleDialog";

beforeEach(() => {
  vi.stubGlobal("scrollTo", vi.fn());
  vi.stubGlobal("PointerEvent", MouseEvent);
  vi.stubGlobal("matchMedia", (query: string) => ({ matches: false, media: query, onchange: null, addEventListener: () => {}, removeEventListener: () => {}, addListener: () => {}, removeListener: () => {}, dispatchEvent: () => false }));
  vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

function open(onRename = vi.fn(), onOpenChange = vi.fn()) {
  render(<ProjectTitleDialog projectId="first" currentName="첫 영상" open onOpenChange={onOpenChange} onRename={onRename} />);
  return { onRename, onOpenChange };
}

describe("영상 제목 바꾸기", () => {
  it("지금 제목이 채워진 채로 열린다", () => {
    open();

    expect(screen.getByLabelText("새 제목")).toHaveValue("첫 영상");
  });

  it("고친 제목을 저장하면 그대로 넘어간다", async () => {
    const { onRename, onOpenChange } = open(vi.fn().mockResolvedValue(undefined));

    fireEvent.change(screen.getByLabelText("새 제목"), { target: { value: "  출근길 브이로그  " } });
    fireEvent.click(screen.getByRole("button", { name: "저장" }));

    await waitFor(() => expect(onRename).toHaveBeenCalledWith("first", "출근길 브이로그"));
    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
  });

  it("빈 제목으로는 저장하지 않고 무엇을 해야 하는지 말한다", () => {
    const { onRename } = open();

    fireEvent.change(screen.getByLabelText("새 제목"), { target: { value: "   " } });
    fireEvent.click(screen.getByRole("button", { name: "저장" }));

    expect(onRename).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent("제목을 입력해 주세요.");
  });

  it("저장이 실패하면 창을 닫지 않고 다시 해 보라고 말한다", async () => {
    const { onRename, onOpenChange } = open(vi.fn().mockRejectedValue(new Error("네트워크")));

    fireEvent.change(screen.getByLabelText("새 제목"), { target: { value: "새 제목" } });
    fireEvent.click(screen.getByRole("button", { name: "저장" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("제목을 바꾸지 못했어요");
    expect(onRename).toHaveBeenCalled();
    expect(onOpenChange).not.toHaveBeenCalledWith(false);
  });

  it("유진에게 물으면 추천 제목이 고를 수 있는 단추로 나온다", async () => {
    vi.spyOn(api, "getLatestEditingSession").mockResolvedValue({ session_id: "session-1" } as never);
    vi.spyOn(api, "createDirectorConversation").mockResolvedValue({ conversation_id: "conv-1", project_id: "first", session_id: "session-1" });
    const send = vi.spyOn(api, "sendDirectorMessage").mockResolvedValue({
      kind: "exchange",
      exchange: {
        assistant_message: { text: "1. 출근길 브이로그\n2. 조용한 아침" },
      },
    } as never);
    open();

    fireEvent.click(screen.getByRole("button", { name: "유진에게 제목 추천받기" }));

    const suggestion = await screen.findByRole("button", { name: "출근길 브이로그" });
    expect(screen.getByRole("button", { name: "조용한 아침" })).toBeInTheDocument();
    expect(send).toHaveBeenCalled();

    // 승인된 게이트는 "사람이 고른다"이다. 누른 제목은 입력칸에 채워질 뿐,
    // 저장은 owner가 한 번 더 눌러야 한다.
    fireEvent.click(suggestion);
    expect(screen.getByLabelText("새 제목")).toHaveValue("출근길 브이로그");
  });

  it("유진이 고른 제목을 저절로 저장하지는 않는다", async () => {
    vi.spyOn(api, "getLatestEditingSession").mockResolvedValue({ session_id: "session-1" } as never);
    vi.spyOn(api, "createDirectorConversation").mockResolvedValue({ conversation_id: "conv-1", project_id: "first", session_id: "session-1" });
    vi.spyOn(api, "sendDirectorMessage").mockResolvedValue({
      kind: "exchange",
      exchange: { assistant_message: { text: "1. 출근길 브이로그" } },
    } as never);
    const { onRename } = open();

    fireEvent.click(screen.getByRole("button", { name: "유진에게 제목 추천받기" }));
    fireEvent.click(await screen.findByRole("button", { name: "출근길 브이로그" }));

    expect(onRename).not.toHaveBeenCalled();
  });

  it("편집을 아직 한 번도 열지 않았으면 무엇을 먼저 해야 하는지 말한다", async () => {
    vi.spyOn(api, "getLatestEditingSession").mockResolvedValue(null);
    open();

    fireEvent.click(screen.getByRole("button", { name: "유진에게 제목 추천받기" }));

    expect(await screen.findByRole("status")).toHaveTextContent("편집을 한 번 열고 나면");
  });

  it("유진이 답하지 못하면 그렇다고 말하고 직접 적을 길은 남긴다", async () => {
    vi.spyOn(api, "getLatestEditingSession").mockResolvedValue({ session_id: "session-1" } as never);
    vi.spyOn(api, "createDirectorConversation").mockRejectedValue(new Error("끊김"));
    open();

    fireEvent.click(screen.getByRole("button", { name: "유진에게 제목 추천받기" }));

    expect(await screen.findByRole("status")).toHaveTextContent("유진이 지금 제목을 추천하지 못했어요");
    expect(screen.getByLabelText("새 제목")).toBeEnabled();
  });

  it("화면 문구에 개발 용어를 쓰지 않는다", () => {
    const { container } = render(<ProjectTitleDialog projectId="first" currentName="첫 영상" open onOpenChange={vi.fn()} onRename={vi.fn()} />);
    const copy = (container.textContent ?? "") + (document.body.textContent ?? "");

    for (const prohibited of ["provider", "runtime", "fallback", "API key", "revision", "pipeline", "job", "시스템", "개발", "리비전"]) {
      expect(copy.toLowerCase()).not.toContain(prohibited.toLowerCase());
    }
  });
});
