import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { api, type HermesYujinStatus as HermesYujinStatusDto } from "../../api";
import { HermesYujinStatus } from "./HermesYujinStatus";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.restoreAllMocks();
});

function status(
  state: HermesYujinStatusDto["state"],
  checkedAt = "2026-07-30T12:00:00Z",
): HermesYujinStatusDto {
  return {
    state,
    http_ready: ["http_ready", "provider_ready", "chat_verified", "degraded"].includes(state),
    provider_ready: ["provider_ready", "chat_verified"].includes(state),
    chat_verified: state === "chat_verified",
    checked_at: checkedAt,
    last_chat_verified_at: state === "chat_verified" || state === "degraded"
      ? "2026-07-30T11:59:00Z"
      : null,
    restart_available: false,
    status_basis: "application_path",
  };
}

describe("HermesYujinStatus", () => {
  it.each([
    ["not_configured", "유진 연결이 아직 준비되지 않았어요."],
    ["stopped", "유진과 연결할 수 없어요."],
    ["starting", "유진 연결을 준비하고 있어요."],
    ["http_ready", "유진 연결은 됐지만 대화 확인은 아직이에요."],
    ["provider_ready", "유진이 답변을 준비하고 있어요."],
    ["chat_verified", "유진과 대화할 준비가 확인됐어요."],
    ["degraded", "최근에는 유진과 대화가 원활하지 않았어요."],
  ] as const)("shows plain creator copy for %s", async (state, copy) => {
    vi.spyOn(api, "getHermesYujinStatus").mockResolvedValue(status(state));

    render(<HermesYujinStatus />);

    expect(await screen.findByText(copy)).toBeVisible();
    expect(screen.queryByText(/provider|runtime|docker|api|fallback/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /재시작/ })).not.toBeInTheDocument();
  });

  it("keeps refresh single-flight and ignores an older checked-at response", async () => {
    let resolveRefresh!: (value: HermesYujinStatusDto) => void;
    const getStatus = vi.spyOn(api, "getHermesYujinStatus")
      .mockResolvedValueOnce(status("chat_verified", "2026-07-30T12:00:00Z"))
      .mockImplementationOnce(() => new Promise((resolve) => {
        resolveRefresh = resolve;
      }));
    render(<HermesYujinStatus />);
    expect(await screen.findByText("유진과 대화할 준비가 확인됐어요.")).toBeVisible();

    const refresh = screen.getByRole("button", { name: "다시 확인" });
    fireEvent.click(refresh);
    fireEvent.click(refresh);

    expect(refresh).toBeDisabled();
    expect(getStatus).toHaveBeenCalledTimes(2);
    resolveRefresh(status("stopped", "2026-07-30T11:59:59Z"));
    await waitFor(() => expect(refresh).toBeEnabled());
    expect(screen.getByText("유진과 대화할 준비가 확인됐어요.")).toBeVisible();
    expect(screen.queryByText("유진과 연결할 수 없어요.")).not.toBeInTheDocument();
  });

  it("shows manual editing guidance on failure and never polls", async () => {
    vi.useFakeTimers();
    const getStatus = vi.spyOn(api, "getHermesYujinStatus")
      .mockRejectedValue(new Error("PRIVATE upstream detail"));
    render(<HermesYujinStatus />);

    await act(async () => {
      await Promise.resolve();
    });
    expect(screen.getByRole("alert")).toHaveTextContent(
      "유진 없이도 편집을 계속할 수 있어요.",
    );
    expect(screen.queryByText(/PRIVATE|upstream/i)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "다시 확인" })).toBeEnabled();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000);
    });
    expect(getStatus).toHaveBeenCalledTimes(1);
  });
});
