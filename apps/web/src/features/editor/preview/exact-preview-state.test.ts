import { describe, expect, it } from "vitest";

import { toExactPreviewState } from "./exact-preview-state";

describe("toExactPreviewState", () => {
  it("accepts only the current revision's succeeded artifact as an exact playable preview", () => {
    expect(toExactPreviewState({ status: "succeeded", url: "/api/exact.mp4", artifactRevision: 4 }, 4)).toMatchObject({ kind: "current", url: "/api/exact.mp4", label: "편집본 미리보기" });
    expect(toExactPreviewState({ status: "succeeded", url: "/api/old.mp4", artifactRevision: 3 }, 4)).toMatchObject({ kind: "stale" });
    expect(toExactPreviewState({ status: "succeeded", url: "/api/unfenced.mp4" }, 4)).toMatchObject({ kind: "stale" });
    expect(toExactPreviewState({ status: "current", url: "/api/unfenced-current.mp4" }, 4)).toMatchObject({ kind: "stale" });
    expect(toExactPreviewState({ status: "current", url: "/api/wrong-current.mp4", artifactRevision: 3 }, 4)).toMatchObject({ kind: "stale" });
    expect(toExactPreviewState({ status: "current", url: "/api/current.mp4", artifactRevision: 4 }, 4)).toMatchObject({ kind: "current" });
  });

  it.each([
    ["pending", "미리보기를 준비하고 있어요."],
    ["running", "편집본 미리보기를 만드는 중이에요."],
    ["failed", "미리보기를 만들지 못했어요."],
    ["stale", "이전 편집본 미리보기는 재생하지 않아요."],
    ["unavailable", "아직 편집본 미리보기가 없어요."],
  ] as const)("maps %s to clear Korean recovery copy", (status, copy) => {
    expect(toExactPreviewState({ status }, 4)).toMatchObject({ copy, action: "refresh" });
  });
});
