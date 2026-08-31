import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

import { RightDock } from "./RightDock";

afterEach(cleanup);

/** 이 도크는 이제 `속성` 하나뿐이다(2026-08-30 두 차례 후속: 유진 대화와
 *  추천 후보 둘 다 `YujinPanel`로 빠졌다 --
 *  `docs/reference/capcut-observed-2026-08-22.ko.md` §7,
 *  `YujinPanel.test.tsx` 참고). 탭 줄 자체가 없으니 내용이 바로 보인다. */
describe("RightDock", () => {
  it("shows the selected clip's properties directly, with no tabs to switch", () => {
    render(<RightDock
      inspectorTargets={[{ id: "segment-1", label: "세그먼트 1", kind: "caption" }]}
    />);

    expect(screen.queryByRole("tab")).toBeNull();
    expect(screen.getByRole("region", { name: "편집 항목" })).toBeInTheDocument();
  });

  it("offers only the approved shortform scene lengths for the selected scene", () => {
    const onSetSegmentRippleSpeed = vi.fn();
    render(<RightDock
      selectedSegment={{
        segmentId: "segment-2", startSec: 4, endSec: 8, nextSegmentId: "segment-3",
        cutAction: "keep", draftApplied: false, ripplePlaybackRate: 1.5,
      }}
      onSetSegmentRippleSpeed={onSetSegmentRippleSpeed}
    />);

    const speed = screen.getByRole("group", { name: "장면 길이" });
    expect(speed).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "1.5배" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "2배" })).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(screen.getByRole("button", { name: "2배" }));
    expect(onSetSegmentRippleSpeed).toHaveBeenCalledWith({ segmentId: "segment-2", rate: 2 });
  });

  it("offers a selected scene preview without changing the timeline", () => {
    const onPreviewSelectedRange = vi.fn();
    render(<RightDock
      selectedSegment={{ segmentId: "segment-2", startSec: 4, endSec: 8, nextSegmentId: null, cutAction: "keep", draftApplied: false }}
      onPreviewSelectedRange={onPreviewSelectedRange}
    />);

    fireEvent.click(screen.getByRole("button", { name: "선택 구간 미리보기" }));
    expect(onPreviewSelectedRange).toHaveBeenCalledWith({ segmentId: "segment-2", startSec: 4, endSec: 8 });
  });

  it("offers keyword shortcuts for video, captions, and screen elements", () => {
    render(<RightDock
      inspectorTargets={[
        { id: "media-1", kind: "media", label: "영상", mediaKind: "broll", segmentId: "segment-1", fields: [], assetId: "asset-1", controls: {}, clearOnly: false },
        { id: "caption-1", kind: "caption", label: "자막", segmentId: "segment-1", fields: ["style"], style: {} as never },
        { id: "overlay-1", kind: "overlay", overlayKind: "shape", label: "화면 요소", segmentId: "segment-1", fields: [], value: { shape: "highlight_box", vertical: "middle", horizontal: "center", size: "medium", motion: "none" } },
      ]}
    />);

    expect(screen.getByRole("button", { name: "영상·소리" })).toBeVisible();
    expect(screen.getByRole("button", { name: "자막" })).toBeVisible();
    expect(screen.getByRole("button", { name: "화면 요소" })).toBeVisible();
  });
});
