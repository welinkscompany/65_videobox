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

  it("clears a prior confirmation after every readiness identity transition, including A to B to A", () => {
    const readinessA = { readiness_id: "readiness_a", revision: 3 };
    const readinessB = { readiness_id: "readiness_b", revision: 3 };
    const { result, rerender } = renderHook(({ current }) => usePlaceholderConfirmation(current), {
      initialProps: { current: readinessA },
    });

    act(() => result.current.setConfirmed(true));
    rerender({ current: { ...readinessA } });
    expect(result.current.confirmed).toBe(true);

    rerender({ current: readinessB });
    expect(result.current.confirmed).toBe(false);

    rerender({ current: readinessA });
    expect(result.current.confirmed).toBe(false);
  });
});
