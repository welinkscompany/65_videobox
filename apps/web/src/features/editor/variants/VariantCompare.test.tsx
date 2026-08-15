import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { VariantCompare } from "./VariantCompare";
import type { VariantProjection } from "./variantProjection";

const master: VariantProjection = {
  variantId: "master", label: "마스터", kind: "master", aspectRatio: "16:9", playheadSec: 2,
  durationSec: 10, safeArea: "표시 안 함", crop: "전체 화면", focalPoint: { x: 0.5, y: 0.5 },
  captionLayout: "마스터 자막", lockedFields: [], conflicts: [], ownsAudio: true,
};
const vertical: VariantProjection = { ...master, variantId: "vertical", label: "세로", kind: "vertical_full", aspectRatio: "9:16", ownsAudio: false };

describe("VariantCompare", () => {
  it("shows synchronized panes, safe area and one audio owner", () => {
    const onSeek = vi.fn();
    render(<VariantCompare master={master} variant={vertical} onSeek={onSeek} />);

    expect(screen.getByRole("region", { name: "마스터 미리보기" })).toBeVisible();
    expect(screen.getByRole("region", { name: "세로 미리보기" })).toBeVisible();
    expect(screen.getAllByText("재생 위치 2.0초")).toHaveLength(2);
    expect(screen.getByText("오디오는 마스터만 재생")).toBeVisible();
    expect(screen.getAllByText("안전 영역: 표시 안 함")).toHaveLength(2);
    fireEvent.click(screen.getAllByRole("button", { name: "재생 위치 5.0초로 이동" })[0]);
    expect(onSeek).toHaveBeenCalledWith(5);
  });
});
