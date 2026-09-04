import { describe, expect, it } from "vitest";

import {
  projectVariant,
  projectServerVariant,
  resolveVariantConflict,
  synchronizeVariantPlayhead,
  type VariantProjection,
} from "./variantProjection";

const master: VariantProjection = {
  variantId: "master",
  label: "마스터",
  kind: "master",
  aspectRatio: "16:9",
  playheadSec: 3,
  durationSec: 12,
  safeArea: "표시 안 함",
  crop: "전체 화면",
  focalPoint: { x: 0.5, y: 0.5 },
  captionLayout: "마스터 캡션",
  lockedFields: [],
  conflicts: [],
  ownsAudio: true,
};

describe("variantProjection", () => {
  it("projects horizontal and vertical output without duplicating the master audio owner", () => {
    const vertical = projectVariant({
      variantId: "vertical-full",
      kind: "vertical_full",
      source: master,
      overrides: {
        crop: "세로 안전 크롭",
        focalPoint: { x: 0.62, y: 0.42 },
        captionLayout: "하단 두 줄",
      },
    });

    expect(vertical.aspectRatio).toBe("9:16");
    expect(vertical.crop).toBe("세로 안전 크롭");
    expect(vertical.focalPoint).toEqual({ x: 0.62, y: 0.42 });
    expect(vertical.ownsAudio).toBe(false);
  });

  it("moves both compare panes to one playback clock", () => {
    const vertical = projectVariant({ variantId: "vertical-full", kind: "vertical_full", source: master });
    expect(synchronizeVariantPlayhead([master, vertical], 8.5).map((item) => item.playheadSec)).toEqual([8.5, 8.5]);
  });

  it("keeps conflict decisions explicit and never silently overwrites a lock", () => {
    const conflicted = projectVariant({
      variantId: "vertical-full",
      kind: "vertical_full",
      source: master,
      lockedFields: ["crop"],
      conflicts: [{ field: "crop", reason: "마스터가 변경됨" }],
    });
    expect(resolveVariantConflict(conflicted, "crop", "keep_local").lockedFields).toEqual(["crop"]);
    expect(resolveVariantConflict(conflicted, "crop", "rebase_master").lockedFields).toEqual([]);
    expect(resolveVariantConflict(conflicted, "crop", "rebase_master").conflicts).toEqual([]);
  });

  it("projects the authoritative server revision, overrides, locks, and conflicts", () => {
    const projected = projectServerVariant({
      variant: {
        variant_id: "vertical-full",
        kind: "vertical_full",
        source_session_id: "session-1",
        source_session_revision: 4,
        variant_revision: 3,
        overrides: {
          crop: { mode: "creator_crop" },
          focal: { x: 0.7, y: 0.3 },
          caption: { layout: "two_line_bottom" },
          safe_area: { mode: "title_safe" },
          audio: null,
        },
        locks: [{ field: "crop", base_master_revision: 4 }],
        conflicts: [{ field: "crop", reason: "master_changed_while_locked", base_master_revision: 4, current_master_revision: 5 }],
      },
      source: master,
    });

    expect(projected.variantId).toBe("vertical-full");
    expect(projected.crop).toBe("creator_crop");
    expect(projected.focalPoint).toEqual({ x: 0.7, y: 0.3 });
    expect(projected.captionLayout).toBe("two_line_bottom");
    expect(projected.safeArea).toBe("title_safe");
    expect(projected.lockedFields).toEqual(["crop"]);
    expect(projected.conflicts).toEqual([{ field: "crop", reason: "master_changed_while_locked" }]);
  });
});
