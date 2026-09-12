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
    fireEvent.click(screen.getByRole("button", { name: "캡션 저장" }));
    fireEvent.click(screen.getByRole("button", { name: "크롭·캡션 잠금" }));

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

  it("keeps a made short form remakeable instead of leaving a dead button", () => {
    // 숏폼은 한 편집본에 하나뿐이라(유일 제약) 두 번 만들 수 없다. 전에는
    // `만들기` 단추가 한 번 쓰이면 조용히 죽어 있었고, 대표님에게는 다시 만들
    // 길이 아예 없었다. 지우는 문 대신 **다시 판단해 갈아 끼우는** 단추를 둔다.
    const onRemakeShortForm = vi.fn();
    const highlight = { ...variant, kind: "vertical_highlight" as const, variant_id: "highlight-1" };
    render(
      <VariantServerControls
        variant={highlight}
        onMaterialize={vi.fn()}
        onPatch={vi.fn()}
        onRemakeShortForm={onRemakeShortForm}
        masterSegmentIds={["seg-b", "seg-a"]}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "숏폼 다시 만들기" }));
    expect(onRemakeShortForm).toHaveBeenCalledWith(highlight);
    // 되돌리기는 그대로 있어야 한다 -- 다시 만들기의 안전장치가 그것이다.
    expect(screen.getByRole("button", { name: "전체 장면으로 되돌리기" })).toBeInTheDocument();
  });

  it("lets the owner unfold a short form and says the original stops following", () => {
    // 대표님 문장(2026-09-12) 후반부: "받아봤는데 보정이 좀 더 필요하면 수동으로
    // 수정하면 되잖아." 숏폼에는 장면별 편집을 담을 자리가 없어서, 펼치지 않고
    // 숏폼의 한 장면을 고치면 **원본 영상의 그 장면도 같이 바뀐다.**
    //
    // 규칙은 **누르기 전에** 보여야 한다 -- 원본과의 줄이 끊기는 것은 되돌릴 수
    // 없으니 누른 뒤에 알리면 늦다.
    const onUnfoldShortForm = vi.fn();
    const highlight = { ...variant, kind: "vertical_highlight" as const, variant_id: "highlight-1" };
    render(
      <VariantServerControls
        variant={highlight}
        onMaterialize={vi.fn()}
        onPatch={vi.fn()}
        onUnfoldShortForm={onUnfoldShortForm}
        masterSegmentIds={["seg-b", "seg-a"]}
      />,
    );

    expect(
      screen.getByText("펼치면 독립된 편집본이 되고, 그 뒤 원본을 고쳐도 따라오지 않아요."),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "숏폼을 편집본으로 펼치기" }));
    expect(onUnfoldShortForm).toHaveBeenCalledWith(highlight);
  });

  it("does not offer unfolding where there is nothing to unfold", () => {
    // 없는 기능의 단추는 만들지 않는다(`2026-08-30` 승인 기록). 가로·세로
    // 전체본의 장면 목록은 원본과 같아서 펼칠 것이 없다.
    render(<VariantServerControls variant={variant} onMaterialize={vi.fn()} onPatch={vi.fn()} onUnfoldShortForm={vi.fn()} />);
    expect(screen.queryByRole("button", { name: "숏폼을 편집본으로 펼치기" })).toBeNull();
    expect(
      screen.queryByText("펼치면 독립된 편집본이 되고, 그 뒤 원본을 고쳐도 따라오지 않아요."),
    ).toBeNull();
  });

  it("shows the conflict state without hiding server lineage", () => {
    render(<VariantServerControls variant={{ ...variant, conflicts: [{ field: "crop", reason: "master_changed_while_locked", base_master_revision: 4, current_master_revision: 5 }] }} onMaterialize={vi.fn()} onPatch={vi.fn()} />);
    expect(screen.getByText("서버 충돌 1건")).toBeInTheDocument();
    expect(screen.getByText("마스터 변경을 확인해야 적용할 수 있어요.")).toBeInTheDocument();
  });
});
