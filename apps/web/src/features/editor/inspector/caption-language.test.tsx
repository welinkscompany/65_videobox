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
  label: "캡션",
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
    shadowBlurPx: 0, bold: false, italic: false, letterSpacingPx: 0,
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
  // 2026-09-03: 자막 언어·목소리 더빙은 `번역·더빙` 탭으로 옮겨졌다(owner
  // 지적 -- 세부 정보 칸이 다섯 뭉치를 한 줄로 쌓아 스크롤이 보이는 높이의
  // 3.5배였다). 이 파일의 모든 시험이 그 안의 내용을 보므로 여기서 한 번만 연다.
  fireEvent.click(screen.getByRole("tab", { name: "번역·더빙" }));
  return onAction;
}

describe("캡션 언어", () => {
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

    expect(onAction).toHaveBeenCalledWith({ kind: "dub-narration", language: "en", voiceSampleAssetId: null });
  });
});

describe("더빙에 쓸 목소리", () => {
  it("목소리가 여럿이면 고를 수 있고, 고른 것이 실려 간다", async () => {
    const onAction = renderControls({
      translatedLanguages: ["en"],
      loadVoiceSamples: async () => [
        { assetId: "asset_a", label: "내 목소리 1" },
        { assetId: "asset_b", label: "내 목소리 2" },
      ],
    });

    const picker = await screen.findByLabelText("쓸 목소리");
    fireEvent.change(picker, { target: { value: "asset_b" } });
    fireEvent.click(screen.getByRole("button", { name: "영어 목소리로 더빙" }));

    expect(onAction).toHaveBeenCalledWith({
      kind: "dub-narration", language: "en", voiceSampleAssetId: "asset_b",
    });
  });

  it("목소리가 하나뿐이면 고르게 하지 않고 그것을 쓴다", async () => {
    const onAction = renderControls({
      translatedLanguages: ["en"],
      loadVoiceSamples: async () => [{ assetId: "asset_only", label: "내 목소리" }],
    });

    await screen.findByRole("button", { name: "영어 목소리로 더빙" });
    expect(screen.queryByLabelText("쓸 목소리")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "영어 목소리로 더빙" }));

    expect(onAction).toHaveBeenCalledWith({
      kind: "dub-narration", language: "en", voiceSampleAssetId: "asset_only",
    });
  });

  it("목소리가 없으면 어디로 가면 되는지 말해 준다", async () => {
    /** 눌러도 안 되는 이유를 안 말하면 창작자는 눌러 보다 포기한다. */
    renderControls({ translatedLanguages: ["en"], loadVoiceSamples: async () => [] });

    expect(await screen.findByText(/자료실의 내 목소리/)).toBeInTheDocument();
  });

  it("목소리를 못 읽어도 더빙 자리는 남는다", async () => {
    /** 목소리를 복제하지 않는 엔진은 샘플이 필요 없다 -- 화면은 엔진을 모른다. */
    renderControls({
      translatedLanguages: ["en"],
      loadVoiceSamples: async () => { throw new Error("no voice samples"); },
    });

    expect(await screen.findByRole("button", { name: "영어 목소리로 더빙" })).toBeInTheDocument();
  });

  it("다시 그려도 목소리 목록을 **한 번만** 읽는다", async () => {
    /** 이 시험이 잡는 것: effect가 자기 setState 때문에 끝없이 다시 도는 문제.
     *
     *  **부모가 매번 새 함수를 넘기는 상황을 흉내 내야 잡힌다.** 부르는 쪽은
     *  early return 아래에서 이 함수를 만들어 memo를 못 쓰기 때문이다. 처음 쓴
     *  시험은 같은 함수를 계속 넘겨서 이 결함을 못 잡았다(2026-09-02).
     */
    let calls = 0;
    const freshLoader = () => async () => {
      calls += 1;
      return [{ assetId: "asset_a", label: "내 목소리" }];
    };
    const draw = () => (
      <InspectorControls
        loadVoiceSamples={freshLoader()}
        onAction={vi.fn()}
        selectedSegment={null}
        target={captionTarget}
        translatedLanguages={["en"]}
      />
    );

    const { rerender } = render(draw());
    fireEvent.click(screen.getByRole("tab", { name: "번역·더빙" }));
    await screen.findByRole("button", { name: "영어 목소리로 더빙" });
    for (let index = 0; index < 3; index += 1) rerender(draw());
    await new Promise((resolve) => setTimeout(resolve, 50));

    expect(calls).toBe(1);
  });
});
