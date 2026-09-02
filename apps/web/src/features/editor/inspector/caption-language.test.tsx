/**
 * 자막 언어 고르기.
 *
 * 가장 중요한 것: **이미 옮겨 둔 언어를 다시 번역하지 않는다.** 다시 부르면
 * 기다림도 길고, 손봐 둔 번역까지 모델이 갈아치운다.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { InspectorControls, type InspectorAction } from "./InspectorControls";

const captionTarget = {
  id: "caption:segment_001",
  kind: "caption",
  label: "자막",
  segmentId: "segment_001",
  fields: ["style"],
  style: {
    fontFamily: "Pretendard",
    fontSizePx: 28,
    textColor: "#ffffff",
    outlineColor: "#000000",
    outlineWidthPx: 2,
    backgroundColor: "#00000000",
    positionXPercent: 50,
    positionYPercent: 90,
    horizontalAlign: "center",
    safeAreaEnabled: true,
    shadowBlurPx: 0,
  },
} as never;

function renderControls(props: Partial<Parameters<typeof InspectorControls>[0]> = {}) {
  const onAction = vi.fn<(action: InspectorAction) => void>();
  render(
    <InspectorControls
      onAction={onAction}
      selectedSegment={null}
      target={captionTarget}
      {...props}
    />,
  );
  return onAction;
}

describe("자막 언어", () => {
  it("아직 안 옮긴 언어는 누르면 번역한다", () => {
    const onAction = renderControls();

    fireEvent.click(screen.getByRole("button", { name: "영어로 번역" }));

    expect(onAction).toHaveBeenCalledWith({ kind: "translate-captions", language: "en" });
  });

  it("이미 옮겨 둔 언어는 고르기만 한다", () => {
    const onAction = renderControls({ translatedLanguages: ["en"] });

    fireEvent.click(screen.getByRole("button", { name: "영어" }));

    expect(onAction).toHaveBeenCalledWith({ kind: "set-caption-language", language: "en" });
  });

  it("원본으로 되돌릴 자리가 늘 있다", () => {
    const onAction = renderControls({ captionLanguage: "en", translatedLanguages: ["en"] });

    expect(screen.getByRole("button", { name: "영어" })).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(screen.getByRole("button", { name: "원본" }));

    expect(onAction).toHaveBeenCalledWith({ kind: "set-caption-language", language: null });
  });

  it("아무것도 안 골랐으면 원본이 눌려 있다", () => {
    renderControls();

    expect(screen.getByRole("button", { name: "원본" })).toHaveAttribute("aria-pressed", "true");
  });
});

describe("목소리 더빙", () => {
  it("옮긴 언어만 더빙할 수 있다", () => {
    /** 옮겨 둔 자막이 곧 대본이다 -- 번역 안 한 언어는 **읽을 것이 없다.** */
    renderControls({ translatedLanguages: ["en"] });

    expect(screen.getByRole("button", { name: "영어 목소리로 더빙" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "일본어 목소리로 더빙" })).not.toBeInTheDocument();
  });

  it("아무것도 안 옮겼으면 더빙 자리 자체가 없다", () => {
    renderControls();

    expect(screen.queryByText("목소리 더빙")).not.toBeInTheDocument();
  });

  it("누르면 그 언어로 더빙한다", () => {
    const onAction = renderControls({ translatedLanguages: ["en"] });

    fireEvent.click(screen.getByRole("button", { name: "영어 목소리로 더빙" }));

    expect(onAction).toHaveBeenCalledWith({ kind: "dub-narration", language: "en" });
  });
});
