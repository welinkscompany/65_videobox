import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { usePlaceholderConfirmation } from "./usePlaceholderConfirmation";

describe("usePlaceholderConfirmation", () => {
  it("keeps a confirmation for the same readiness after effects flush", () => {
    const readiness = { readiness_id: "readiness_gap", revision: 3 };
    const { result, rerender } = renderHook(({ current }) => usePlaceholderConfirmation(current), {
      initialProps: { current: readiness },
    });

    act(() => result.current.setConfirmed(true));
    rerender({ current: readiness });

    expect(result.current.confirmed).toBe(true);
  });

  it("invalidates a confirmation when the readiness revision changes", () => {
    const { result, rerender } = renderHook(({ current }) => usePlaceholderConfirmation(current), {
      initialProps: { current: { readiness_id: "readiness_gap", revision: 3 } },
    });

    act(() => result.current.setConfirmed(true));
    rerender({ current: { readiness_id: "readiness_gap", revision: 4 } });

    expect(result.current.confirmed).toBe(false);
  });
});
