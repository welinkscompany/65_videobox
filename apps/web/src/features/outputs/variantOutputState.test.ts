import { describe, expect, it } from "vitest";

import { isVariantPlayable, mergeVariantRenderItems, variantContentUrl, variantLabel, variantRenderSummary } from "./variantOutputState";

describe("variant output state", () => {
  it("labels and exposes only succeeded outputs as playable", () => {
    const item = { variant_id: "vertical", variant_kind: "vertical_full", job_id: "job-1", status: "succeeded" };
    expect(variantLabel(item.variant_kind)).toBe("세로 영상");
    expect(isVariantPlayable(item)).toBe(true);
    expect(variantContentUrl("project-a", item)).toBe("/api/projects/project-a/final-renders/job-1/content");
    expect(isVariantPlayable({ ...item, status: "failed" })).toBe(false);
  });

  it("summarizes sibling failure without hiding a successful output", () => {
    expect(variantRenderSummary([
      { variant_id: "horizontal", variant_kind: "horizontal", status: "succeeded" },
      { variant_id: "vertical", variant_kind: "vertical_full", status: "failed", error_code: "renderer_failed" },
    ])).toBe("1개 완료 · 1개 확인 필요");
  });

  it("keeps non-requested siblings when one failed variant is retried", () => {
    const current = [
      { variant_id: "horizontal", variant_kind: "horizontal", status: "failed", error_code: "renderer_failed" },
      { variant_id: "vertical", variant_kind: "vertical_full", status: "failed", error_code: "renderer_failed" },
    ];
    const retried = [
      { variant_id: "horizontal", variant_kind: "horizontal", status: "succeeded", job_id: "job-horizontal" },
    ];

    expect(mergeVariantRenderItems(current, retried, ["horizontal"])).toEqual([
      retried[0],
      current[1],
    ]);
  });
});
