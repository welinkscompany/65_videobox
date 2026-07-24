import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

import type { EditorCaptionStyle } from "../editorViewModel";
import { InspectorControls, type InspectorAction } from "./InspectorControls";
import type { InspectorTarget } from "./inspectorRegistry";

afterEach(cleanup);

const style: EditorCaptionStyle = {
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
};

function renderControls({
  target = null,
  onAction = vi.fn(),
}: {
  target?: InspectorTarget | null;
  onAction?: (action: InspectorAction) => void;
} = {}) {
  render(
    <InspectorControls
      onAction={onAction}
      partialRegeneration={{ canResume: true, canRun: true, fields: ["caption", "music"] }}
      selectedSegment={{
        cutAction: "keep",
        endSec: 5,
        nextSegmentId: "segment-internal-next",
        segmentId: "segment-internal-current",
        startSec: 1,
      }}
      target={target}
    />,
  );
  return onAction;
}

describe("InspectorControls", () => {
  it("emits narration, cut, and partial regeneration intents only from explicit buttons", () => {
    const onAction = renderControls();

    expect(onAction).not.toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: /자동.*적용/ })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "구간 중간에서 나누기" }));
    fireEvent.click(screen.getByRole("button", { name: "다음 구간과 합치기" }));
    fireEvent.change(screen.getByLabelText("선택 구간 처리"), { target: { value: "remove" } });
    expect(onAction).toHaveBeenCalledTimes(2);
    fireEvent.click(screen.getByRole("button", { name: "컷 저장" }));
    fireEvent.click(screen.getByRole("button", { name: "재생성 범위 미리보기" }));
    fireEvent.click(screen.getByRole("button", { name: "부분 재생성 실행" }));
    fireEvent.click(screen.getByRole("button", { name: "이전 결과 열기" }));

    expect(onAction).toHaveBeenNthCalledWith(1, {
      kind: "split-narration",
      segmentId: "segment-internal-current",
      splitSec: 3,
    });
    expect(onAction).toHaveBeenNthCalledWith(2, {
      kind: "merge-narration",
      leftSegmentId: "segment-internal-current",
      rightSegmentId: "segment-internal-next",
    });
    expect(onAction).toHaveBeenNthCalledWith(3, {
      kind: "set-cut-action",
      cutAction: "remove",
      segmentId: "segment-internal-current",
    });
    expect(onAction).toHaveBeenNthCalledWith(4, {
      fields: ["caption", "music"],
      kind: "partial-preflight",
      segmentIds: ["segment-internal-current"],
    });
    expect(onAction).toHaveBeenNthCalledWith(5, {
      fields: ["caption", "music"],
      kind: "partial-run",
      segmentIds: ["segment-internal-current"],
    });
    expect(onAction).toHaveBeenNthCalledWith(6, {
      fields: ["caption", "music"],
      kind: "partial-resume",
      segmentIds: ["segment-internal-current"],
    });
  });

  it("lets the creator include B-roll, music, SFX, overlays, cut, and voice fields without auto-running", () => {
    const onAction = vi.fn();
    render(
      <InspectorControls
        onAction={onAction}
        partialRegeneration={{
          canResume: false,
          canRun: false,
          defaultFields: ["caption", "music"],
          fields: ["caption", "cut_action", "broll", "visual_overlay", "music", "sfx", "tts_replacement"],
        }}
        selectedSegment={{ cutAction: "keep", endSec: 5, nextSegmentId: null, segmentId: "segment-internal-current", startSec: 1 }}
        target={null}
      />,
    );

    expect(screen.getByLabelText("자막")).toBeChecked();
    expect(screen.getByLabelText("배경 음악")).toBeChecked();
    fireEvent.click(screen.getByLabelText("B-roll"));
    fireEvent.click(screen.getByLabelText("효과음"));
    fireEvent.click(screen.getByLabelText("화면 요소"));
    expect(onAction).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "재생성 범위 미리보기" }));
    expect(onAction).toHaveBeenCalledWith({
      kind: "partial-preflight",
      segmentIds: ["segment-internal-current"],
      fields: ["caption", "broll", "visual_overlay", "music", "sfx"],
    });
  });

  it("keeps B-roll clear-only and preserves hidden BGM controls while saving fade values", () => {
    const onAction = vi.fn();
    const broll: InspectorTarget = {
      assetId: "asset-internal-broll",
      clearOnly: true,
      controls: { crop: "center", speed: 1.2 },
      fields: [],
      id: "clip:broll",
      kind: "media",
      label: "B-roll",
      mediaKind: "broll",
      segmentId: "segment-internal-current",
    };
    const { rerender } = render(
      <InspectorControls
        onAction={onAction}
        selectedSegment={{ cutAction: "keep", endSec: 5, nextSegmentId: null, segmentId: "segment-internal-current", startSec: 1 }}
        target={broll}
      />,
    );

    expect(screen.queryByLabelText("B-roll 페이드 인")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "B-roll 설정 저장" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "B-roll 지우기" }));
    expect(onAction).toHaveBeenLastCalledWith({
      kind: "clear-media",
      mediaKind: "broll",
      segmentId: "segment-internal-current",
    });

    const bgm: InspectorTarget = {
      assetId: "asset-internal-bgm",
      clearOnly: false,
      controls: { ducking: true, fadeInSec: 0.5, fadeOutSec: 1, gainDb: -8 },
      fields: ["fadeInSec", "fadeOutSec"],
      id: "clip:bgm",
      kind: "media",
      label: "배경 음악",
      mediaKind: "bgm",
      segmentId: "segment-internal-current",
    };
    rerender(
      <InspectorControls
        onAction={onAction}
        selectedSegment={{ cutAction: "keep", endSec: 5, nextSegmentId: null, segmentId: "segment-internal-current", startSec: 1 }}
        target={bgm}
      />,
    );
    fireEvent.change(screen.getByLabelText("배경 음악 페이드 인"), { target: { value: "1.25" } });
    fireEvent.change(screen.getByLabelText("배경 음악 페이드 아웃"), { target: { value: "0.75" } });
    rerender(
      <InspectorControls
        onAction={onAction}
        selectedSegment={{ cutAction: "keep", endSec: 5, nextSegmentId: null, segmentId: "segment-internal-current", startSec: 1 }}
        target={{ ...bgm, controls: { ...bgm.controls } }}
      />,
    );
    expect(screen.getByLabelText("배경 음악 페이드 인")).toHaveValue(1.25);
    expect(screen.getByLabelText("배경 음악 페이드 아웃")).toHaveValue(0.75);
    fireEvent.click(screen.getByRole("button", { name: "배경 음악 설정 저장" }));
    fireEvent.click(screen.getByRole("button", { name: "배경 음악 지우기" }));

    expect(onAction).toHaveBeenNthCalledWith(2, {
      assetId: "asset-internal-bgm",
      controls: { ducking: true, fadeInSec: 1.25, fadeOutSec: 0.75, gainDb: -8 },
      kind: "save-media",
      mediaKind: "bgm",
      segmentId: "segment-internal-current",
    });
    expect(onAction).toHaveBeenNthCalledWith(3, {
      kind: "clear-media",
      mediaKind: "bgm",
      segmentId: "segment-internal-current",
    });
    expect(document.body).not.toHaveTextContent(/asset-internal|segment-internal/);
  });

  it("saves the complete current caption style without exposing independent timing", () => {
    const onAction = renderControls({
      target: {
        fields: ["style"],
        id: "caption:current",
        kind: "caption",
        label: "연결 자막",
        segmentId: "segment-internal-current",
        style,
      },
    });

    expect(screen.queryByLabelText(/자막 시작|자막 종료/)).not.toBeInTheDocument();
    expect(screen.queryByText(/voice|effect|keyframe|mask|transition/i)).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("글자 크기"), { target: { value: "32" } });
    fireEvent.change(screen.getByLabelText("가로 정렬"), { target: { value: "left" } });
    fireEvent.click(screen.getByRole("button", { name: "자막 스타일 저장" }));

    expect(onAction).toHaveBeenLastCalledWith({
      kind: "save-caption-style",
      scope: "current_caption",
      segmentIds: ["segment-internal-current"],
      style: { ...style, fontSizePx: 32, horizontalAlign: "left" },
    });
  });

  it.each([
    {
      label: "설명 카드",
      target: {
        fields: ["title", "body", "text"],
        id: "overlay:explanation",
        kind: "overlay",
        label: "설명 카드",
        overlayKind: "explanation-card",
        segmentId: "segment-internal-current",
        value: { body: "본문", text: "설명", title: "제목" },
      } satisfies InspectorTarget,
      expected: {
        body: "본문",
        kind: "save-overlay",
        overlayKind: "explanation-card",
        segmentId: "segment-internal-current",
        text: "설명",
        title: "제목",
      },
    },
    {
      label: "이미지",
      target: {
        fields: ["assetId", "text"],
        id: "overlay:image",
        kind: "overlay",
        label: "이미지",
        overlayKind: "image",
        segmentId: "segment-internal-current",
        value: { assetId: "asset-internal-image", text: "이미지 설명" },
      } satisfies InspectorTarget,
      expected: {
        assetId: "asset-internal-image",
        kind: "save-overlay",
        overlayKind: "image",
        segmentId: "segment-internal-current",
        text: "이미지 설명",
      },
    },
    {
      label: "표",
      target: {
        fields: ["columns", "rows", "text"],
        id: "overlay:table",
        kind: "overlay",
        label: "표",
        overlayKind: "table",
        segmentId: "segment-internal-current",
        value: { columns: ["항목", "값"], rows: [["길이", "10초"]], text: "요약표" },
      } satisfies InspectorTarget,
      expected: {
        columns: ["항목", "값"],
        kind: "save-overlay",
        overlayKind: "table",
        rows: [["길이", "10초"]],
        segmentId: "segment-internal-current",
        text: "요약표",
      },
    },
  ])("edits and clears the supported $label overlay through explicit callbacks", ({ expected, label, target }) => {
    const onAction = renderControls({ target });

    fireEvent.click(screen.getByRole("button", { name: `${label} 저장` }));
    fireEvent.click(screen.getByRole("button", { name: `${label} 지우기` }));

    expect(onAction).toHaveBeenNthCalledWith(1, expected);
    expect(onAction).toHaveBeenNthCalledWith(2, {
      kind: "clear-overlay",
      overlayKind: target.overlayKind,
      segmentId: "segment-internal-current",
    });
    expect(document.body).not.toHaveTextContent(/asset-internal|segment-internal/);
  });
});
