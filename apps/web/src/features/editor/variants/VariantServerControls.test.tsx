import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { OutputVariant } from "../../../api";
import { VariantServerControls } from "./VariantServerControls";

const variant: OutputVariant = {
  variant_id: "vertical-full",
  kind: "vertical_full",
  source_session_id: "session-1",
  source_session_revision: 4,
  variant_revision: 3,
  overrides: { crop: null, focal: null, caption: null, safe_area: null, audio: null },
  locks: [],
  conflicts: [],
};

describe("VariantServerControls", () => {
  it("exposes explicit server-backed materialize, edit, and lock actions", () => {
    const onMaterialize = vi.fn();
    const onPatch = vi.fn();
    render(<VariantServerControls variant={variant} onMaterialize={onMaterialize} onPatch={onPatch} onCreateHighlight={vi.fn()} />);

    expect(screen.getByText("서버 변형 버전 3")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "세로 변형 준비" }));
    fireEvent.click(screen.getByRole("button", { name: "크롭 저장" }));
    fireEvent.click(screen.getByRole("button", { name: "자막 저장" }));
    fireEvent.click(screen.getByRole("button", { name: "크롭·자막 잠금" }));

    expect(onMaterialize).toHaveBeenCalledWith(variant);
    expect(onPatch).toHaveBeenNthCalledWith(1, variant, {
      overrides: { crop: { mode: "creator_adjusted" } },
    });
    expect(onPatch).toHaveBeenNthCalledWith(2, variant, {
      overrides: { caption: { layout: "creator_adjusted" } },
    });
    expect(onPatch).toHaveBeenNthCalledWith(3, variant, { lock_fields: ["crop", "caption"] });
  });

  it("creates an optional highlight and explicitly saves its master order", () => {
    const onCreateHighlight = vi.fn();
    const onPatch = vi.fn();
    render(<VariantServerControls variant={variant} onMaterialize={vi.fn()} onPatch={onPatch} onCreateHighlight={onCreateHighlight} masterSegmentIds={["seg-b", "seg-a"]} />);

    fireEvent.click(screen.getByRole("button", { name: "하이라이트 변형 만들기" }));
    expect(onCreateHighlight).toHaveBeenCalledOnce();

    render(<VariantServerControls variant={{ ...variant, kind: "vertical_highlight", variant_id: "highlight-1" }} onMaterialize={vi.fn()} onPatch={onPatch} masterSegmentIds={["seg-b", "seg-a"]} />);
    fireEvent.click(screen.getByRole("button", { name: "전체 장면으로 되돌리기" }));
    expect(onPatch).toHaveBeenCalledWith(expect.objectContaining({ kind: "vertical_highlight" }), { selected_segment_ids: ["seg-b", "seg-a"] });
  });

  it("shows the conflict state without hiding server lineage", () => {
    render(<VariantServerControls variant={{ ...variant, conflicts: [{ field: "crop", reason: "master_changed_while_locked", base_master_revision: 4, current_master_revision: 5 }] }} onMaterialize={vi.fn()} onPatch={vi.fn()} />);
    expect(screen.getByText("서버 충돌 1건")).toBeInTheDocument();
    expect(screen.getByText("마스터 변경을 확인해야 적용할 수 있어요.")).toBeInTheDocument();
  });
});
