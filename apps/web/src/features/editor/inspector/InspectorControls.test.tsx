import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

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
  it("does not fetch approved voices for a scene the creator never asked about", async () => {
    // 초기화를 effect에서 하면 조회 effect가 **같은 commit에서 옛 값을 읽어** 새
    // 장면의 후보를 한 번 불러온다. 부를 때만 부르기로 한 것이 두 번째 장면부터
    // 무너진다.
    const load = vi.fn().mockResolvedValue([]);
    const segment = (id: string) => ({ segmentId: id, startSec: 0, endSec: 1, nextSegmentId: null, cutAction: "keep" });
    const rendered = render(<InspectorControls disabled={false} onAction={vi.fn()} projectId="p" selectedSegment={segment("a")} target={null} loadApprovedTtsCandidates={load} />);

    fireEvent.click(screen.getByRole("button", { name: "승인한 음성 불러오기" }));
    await waitFor(() => expect(load).toHaveBeenCalledTimes(1));

    rendered.rerender(<InspectorControls disabled={false} onAction={vi.fn()} projectId="p" selectedSegment={segment("b")} target={null} loadApprovedTtsCandidates={load} />);
    await waitFor(() => expect(screen.getByRole("button", { name: "승인한 음성 불러오기" })).toBeInTheDocument());

    expect(load).toHaveBeenCalledTimes(1);
    expect(load).not.toHaveBeenCalledWith("b");
  });

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

  it("lets the owner adjust which part of the B-roll take is used, and preserves hidden BGM controls while saving fade values", () => {
    const onAction = vi.fn();
    const broll: InspectorTarget = {
      assetId: "asset-internal-broll",
      clearOnly: false,
      controls: { crop: "center", speed: 1.2, inSec: 8, outSec: 13 },
      fields: ["inSec", "outSec"],
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

    // B-roll is silent by default, so the audio fades stay hidden.
    expect(screen.queryByLabelText("B-roll 페이드 인")).not.toBeInTheDocument();
    // Task 24: the recommendation puts a window here; this is where it is corrected.
    const start = screen.getByLabelText("B-roll 쓸 구간 시작") as HTMLInputElement;
    const end = screen.getByLabelText("B-roll 쓸 구간 끝") as HTMLInputElement;
    expect([start.value, end.value]).toEqual(["8", "13"]);

    fireEvent.change(start, { target: { value: "20" } });
    fireEvent.change(end, { target: { value: "26.5" } });
    fireEvent.click(screen.getByRole("button", { name: "B-roll 설정 저장" }));
    expect(onAction).toHaveBeenLastCalledWith({
      kind: "save-media",
      mediaKind: "broll",
      segmentId: "segment-internal-current",
      assetId: "asset-internal-broll",
      // Unrelated controls must survive the round trip untouched.
      controls: { crop: "center", speed: 1.2, inSec: 20, outSec: 26.5 },
    });

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

    // Calls 1 and 2 are the B-roll save and clear above.
    expect(onAction).toHaveBeenNthCalledWith(3, {
      assetId: "asset-internal-bgm",
      controls: { ducking: true, fadeInSec: 1.25, fadeOutSec: 0.75, gainDb: -8 },
      kind: "save-media",
      mediaKind: "bgm",
      segmentId: "segment-internal-current",
    });
    expect(onAction).toHaveBeenNthCalledWith(4, {
      kind: "clear-media",
      mediaKind: "bgm",
      segmentId: "segment-internal-current",
    });
    expect(document.body).not.toHaveTextContent(/asset-internal|segment-internal/);
  });

  it("shows and saves B-roll fit mode", () => {
    const onAction = vi.fn();
    const broll: InspectorTarget = {
      assetId: "asset-internal-broll",
      clearOnly: false,
      controls: { fit: "crop", speed: 1 },
      fields: ["fit", "speed"],
      id: "clip:broll-fit",
      kind: "media",
      label: "B-roll",
      mediaKind: "broll",
      segmentId: "segment-internal-current",
    };

    render(<InspectorControls onAction={onAction} selectedSegment={{ cutAction: "keep", endSec: 5, nextSegmentId: null, segmentId: "segment-internal-current", startSec: 1 }} target={broll} />);

    const select = screen.getByRole("combobox", { name: "B-roll 화면 맞춤" });
    expect(select).toHaveValue("crop");
    fireEvent.change(select, { target: { value: "fit" } });
    fireEvent.click(screen.getByRole("button", { name: "B-roll 설정 저장" }));
    expect(onAction).toHaveBeenLastCalledWith({
      kind: "save-media",
      mediaKind: "broll",
      segmentId: "segment-internal-current",
      assetId: "asset-internal-broll",
      controls: { fit: "fit", speed: 1 },
    });
  });

  // 캡컷 속도 탭 대조(owner 승인 2026-09-01). **기본이 켜짐인 유일한 스위치다** --
  // 지금까지의 동작이 유지였고(`atempo`), 기본값을 꺼짐으로 두면 예전에 저장한
  // 배속 클립의 소리가 편집기를 여는 것만으로 달라진다.
  it("keeps pitch preservation on by default and only sends it off when the creator unticks it", () => {
    const onAction = vi.fn();
    const segment = { cutAction: "keep", endSec: 5, nextSegmentId: null, segmentId: "segment-pitch", startSec: 1 };
    const broll: InspectorTarget = {
      assetId: "asset-pitch",
      clearOnly: false,
      controls: {},
      fields: ["speed", "preservePitch"],
      id: "clip:broll-pitch",
      kind: "media",
      label: "B-roll",
      mediaKind: "broll",
      segmentId: "segment-pitch",
    };

    render(<InspectorControls onAction={onAction} selectedSegment={segment} target={broll} />);
    const toggle = screen.getByRole("checkbox", { name: "속도를 바꿔도 목소리 높낮이 그대로 두기" });
    expect(toggle).toBeChecked();

    fireEvent.click(screen.getByRole("button", { name: "B-roll 설정 저장" }));
    expect(onAction).toHaveBeenLastCalledWith(expect.objectContaining({
      controls: expect.objectContaining({ preservePitch: true }),
    }));

    fireEvent.click(toggle);
    fireEvent.click(screen.getByRole("button", { name: "B-roll 설정 저장" }));
    expect(onAction).toHaveBeenLastCalledWith(expect.objectContaining({
      controls: expect.objectContaining({ preservePitch: false }),
    }));
  });

  it("carries the CapCut-parity cleanup toggles into the save without leaking filter names", () => {
    // 캡컷 오디오·동영상 탭 대조로 들어온 셋(owner 승인 2026-09-01). 캡컷은
    // 클라우드 AI 유료 기능으로 파는데 우리는 FFmpeg 필터 하나씩이다.
    // §10.13: `loudnorm`·`afftdn`·`deshake` 같은 내부 이름은 화면에 안 쓴다.
    const onAction = vi.fn();
    const segment = { cutAction: "keep", endSec: 5, nextSegmentId: null, segmentId: "segment-internal-current", startSec: 1 };
    const broll: InspectorTarget = {
      assetId: "asset-internal-broll",
      clearOnly: false,
      controls: { stabilize: false },
      fields: ["stabilize"],
      id: "clip:broll-stabilize",
      kind: "media",
      label: "B-roll",
      mediaKind: "broll",
      segmentId: "segment-internal-current",
    };

    const rendered = render(<InspectorControls onAction={onAction} selectedSegment={segment} target={broll} />);
    fireEvent.click(screen.getByRole("checkbox", { name: "흔들린 화면 잡아주기" }));
    fireEvent.click(screen.getByRole("button", { name: "B-roll 설정 저장" }));
    expect(onAction).toHaveBeenLastCalledWith(expect.objectContaining({
      kind: "save-media", mediaKind: "broll", controls: expect.objectContaining({ stabilize: true }),
    }));
    // 소리 정리 둘은 화면이 없는 클립에는 안 붙는다.
    expect(screen.queryByRole("checkbox", { name: "소리 크기를 고르게 맞추기" })).toBeNull();
    rendered.unmount();

    const bgm: InspectorTarget = {
      assetId: "asset-internal-bgm",
      clearOnly: false,
      controls: { normalizeLoudness: false, denoise: false },
      fields: ["normalizeLoudness", "denoise"],
      id: "clip:bgm-cleanup",
      kind: "media",
      label: "배경 음악",
      mediaKind: "bgm",
      segmentId: "segment-internal-current",
    };

    render(<InspectorControls onAction={onAction} selectedSegment={segment} target={bgm} />);
    fireEvent.click(screen.getByRole("checkbox", { name: "소리 크기를 고르게 맞추기" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "웅웅거리는 잡음 줄이기" }));
    fireEvent.click(screen.getByRole("button", { name: "배경 음악 설정 저장" }));
    expect(onAction).toHaveBeenLastCalledWith(expect.objectContaining({
      controls: expect.objectContaining({ normalizeLoudness: true, denoise: true }),
    }));
    // 소리에는 화면이 없으니 손떨림 보정도 없다.
    expect(screen.queryByRole("checkbox", { name: "흔들린 화면 잡아주기" })).toBeNull();
    expect(document.body).not.toHaveTextContent(/loudnorm|afftdn|deshake|LUFS/i);
  });

  it("gives music and effects a loudness slider in creator language and rides gainDb into the save", () => {
    // 렌더러는 처음부터 클립별 gain_db를 반영했다 -- 화면에 입력 자리만 없었다.
    // §10.13: dB는 내부 단위라 화면에 쓰지 않는다. 라벨은 `소리 크기`, 양 끝은
    // `조용히`/`크게`. 중앙(50)=그대로(0dB), 왼쪽 끝=-18dB, 오른쪽 끝=+6dB.
    const onAction = vi.fn();
    const segment = { cutAction: "keep", endSec: 5, nextSegmentId: null, segmentId: "segment-internal-current", startSec: 1 };
    const bgm: InspectorTarget = {
      assetId: "asset-internal-bgm",
      clearOnly: false,
      controls: { ducking: true, fadeInSec: 0.5, fadeOutSec: 1, gainDb: -8 },
      fields: ["fadeInSec", "fadeOutSec", "ducking", "gainDb"],
      id: "clip:bgm",
      kind: "media",
      label: "배경 음악",
      mediaKind: "bgm",
      segmentId: "segment-internal-current",
    };
    const { rerender } = render(<InspectorControls onAction={onAction} selectedSegment={segment} target={bgm} />);

    const slider = screen.getByLabelText("배경 음악 소리 크기") as HTMLInputElement;
    expect(slider.type).toBe("range");
    expect(screen.getByText("조용히")).toBeInTheDocument();
    expect(screen.getByText("크게")).toBeInTheDocument();
    expect(document.body).not.toHaveTextContent(/dB|데시벨|gain/i);

    // 손대지 않은 저장은 저장돼 있던 값을 **정확히 그대로** 돌려보낸다.
    // 슬라이더 눈금으로 반올림해 버리면 페이드만 고친 저장이 음량을 몰래 옮긴다.
    fireEvent.click(screen.getByRole("button", { name: "배경 음악 설정 저장" }));
    expect(onAction).toHaveBeenLastCalledWith({
      assetId: "asset-internal-bgm",
      controls: { ducking: true, fadeInSec: 0.5, fadeOutSec: 1, gainDb: -8 },
      kind: "save-media",
      mediaKind: "bgm",
      segmentId: "segment-internal-current",
    });

    // 오른쪽 끝(크게)=+6dB, 중앙=그대로(0dB), 왼쪽 끝(조용히)=-18dB.
    const expectSavedGain = (position: string, gainDb: number) => {
      fireEvent.change(screen.getByLabelText("배경 음악 소리 크기"), { target: { value: position } });
      fireEvent.click(screen.getByRole("button", { name: "배경 음악 설정 저장" }));
      expect(onAction).toHaveBeenLastCalledWith({
        assetId: "asset-internal-bgm",
        controls: { ducking: true, fadeInSec: 0.5, fadeOutSec: 1, gainDb },
        kind: "save-media",
        mediaKind: "bgm",
        segmentId: "segment-internal-current",
      });
    };
    expectSavedGain("100", 6);
    expectSavedGain("50", 0);
    expectSavedGain("0", -18);

    // 효과음도 같은 자리를 얻는다. 필드가 시키는 대로 그려지는지만 본다.
    const sfx: InspectorTarget = {
      assetId: "asset-internal-sfx",
      clearOnly: false,
      controls: { fadeInSec: 0, fadeOutSec: 0 },
      fields: ["fadeInSec", "fadeOutSec", "gainDb"],
      id: "clip:sfx",
      kind: "media",
      label: "효과음",
      mediaKind: "sfx",
      segmentId: "segment-internal-current",
    };
    rerender(<InspectorControls onAction={onAction} selectedSegment={segment} target={sfx} />);
    fireEvent.change(screen.getByLabelText("효과음 소리 크기"), { target: { value: "75" } });
    fireEvent.click(screen.getByRole("button", { name: "효과음 설정 저장" }));
    expect(onAction).toHaveBeenLastCalledWith({
      assetId: "asset-internal-sfx",
      controls: { fadeInSec: 0, fadeOutSec: 0, gainDb: 3 },
      kind: "save-media",
      mediaKind: "sfx",
      segmentId: "segment-internal-current",
    });
  });

  it("can save a B-roll that has no source window, instead of locking every other control", () => {
    // 2026-08-18 실제 화면에서 찾았다. `쓸 구간`을 따로 정하지 않은 B-roll은
    // 시작·끝이 둘 다 0으로 시작하는데, 저장 단추가 `끝 <= 시작`이면 잠기도록
    // 돼 있어 **0/0에서 영영 잠겨 있었다.** 그래서 배속·음량·페이드·소리
    // 스위치 어느 것도 저장되지 않았다 -- 화면에는 값이 남아 있어서 저장된 줄
    // 알았다(내가 그렇게 잘못 보고했다).
    //
    // 0/0은 잘못된 구간이 아니라 **구간을 안 정했다**는 뜻이다. 그때는 구간을
    // 아예 보내지 않아야 한다 -- 서버는 `끝 > 시작`을 요구하므로 0/0을 실어
    // 보내면 거절당한다.
    const onAction = vi.fn();
    const broll: InspectorTarget = {
      assetId: "asset-internal-broll",
      clearOnly: false,
      controls: { speed: 1, volume: 1 },
      fields: ["inSec", "outSec", "speed", "volume", "preserveSourceAudio"],
      id: "clip:broll",
      kind: "media",
      label: "B-roll",
      mediaKind: "broll",
      segmentId: "segment-internal-current",
    };
    render(
      <InspectorControls
        onAction={onAction}
        selectedSegment={{ cutAction: "keep", endSec: 5, nextSegmentId: null, segmentId: "segment-internal-current", startSec: 1 }}
        target={broll}
      />,
    );

    const save = screen.getByRole("button", { name: "B-roll 설정 저장" });
    expect(save).toBeEnabled();

    fireEvent.click(screen.getByLabelText("이 영상의 원래 소리도 함께 쓰기"));
    fireEvent.click(save);

    const sent = onAction.mock.calls.at(-1)?.[0];
    expect(sent.controls.preserveSourceAudio).toBe(true);
    expect(sent.controls).not.toHaveProperty("inSec");
    expect(sent.controls).not.toHaveProperty("outSec");
  });

  it("sends a B-roll dissolve edit instead of quietly resending the old value", () => {
    // 페이드와 구간이 하나의 삼항으로 묶여 있어서, 구간을 가진 B-roll은
    // 페이드를 고쳐도 옛 값이 실려 나갔다. 화면에서 바꾼 것이 사라진다.
    const onAction = vi.fn();
    const broll: InspectorTarget = {
      assetId: "asset-internal-broll",
      clearOnly: false,
      controls: { inSec: 2, outSec: 6, fadeInSec: 0, fadeOutSec: 0 },
      fields: ["inSec", "outSec", "speed", "volume", "fadeInSec", "fadeOutSec"],
      id: "clip:broll",
      kind: "media",
      label: "B-roll",
      mediaKind: "broll",
      segmentId: "segment-internal-current",
    };
    render(
      <InspectorControls
        onAction={onAction}
        selectedSegment={{ cutAction: "keep", endSec: 5, nextSegmentId: null, segmentId: "segment-internal-current", startSec: 1 }}
        target={broll}
      />,
    );

    fireEvent.change(screen.getByLabelText("B-roll 서서히 나타나기"), { target: { value: "0.75" } });
    fireEvent.click(screen.getByRole("button", { name: "B-roll 설정 저장" }));

    const sent = onAction.mock.calls.at(-1)?.[0];
    expect(sent.controls.fadeInSec).toBe(0.75);
    // 구간은 그대로 살아 있어야 한다.
    expect(sent.controls.inSec).toBe(2);
    expect(sent.controls.outSec).toBe(6);
  });

  it("still refuses a source window that ends before it starts", () => {
    // 구간을 실제로 정했는데 끝이 시작보다 앞이면 그건 잘못된 값이다. 이건 계속 막는다.
    const onAction = vi.fn();
    const broll: InspectorTarget = {
      assetId: "asset-internal-broll",
      clearOnly: false,
      controls: { inSec: 8, outSec: 13 },
      fields: ["inSec", "outSec", "speed", "volume"],
      id: "clip:broll",
      kind: "media",
      label: "B-roll",
      mediaKind: "broll",
      segmentId: "segment-internal-current",
    };
    render(
      <InspectorControls
        onAction={onAction}
        selectedSegment={{ cutAction: "keep", endSec: 5, nextSegmentId: null, segmentId: "segment-internal-current", startSec: 1 }}
        target={broll}
      />,
    );

    fireEvent.change(screen.getByLabelText("B-roll 쓸 구간 끝"), { target: { value: "4" } });

    expect(screen.getByRole("button", { name: "B-roll 설정 저장" })).toBeDisabled();
  });

  it("lets the creator keep a clip's own sound, which is what makes 소리 크기 mean anything", () => {
    // 2026-08-18에 배속을 이어 놓고도 **음량은 여전히 결과에 닿지 않았다.**
    // B-roll 음량은 그 클립의 자체 소리를 살려 둘 때만 섞이는데(렌더러가
    // `preserve_source_audio`로 가른다), 그걸 켜는 자리가 화면에 없었다.
    // 백엔드에서도 이 값을 참으로 만드는 곳이 한 군데도 없었다 -- 읽기만 했다.
    const onAction = vi.fn();
    const broll: InspectorTarget = {
      assetId: "asset-internal-broll",
      clearOnly: false,
      controls: { inSec: 0, outSec: 4, speed: 1, volume: 1, preserveSourceAudio: false },
      fields: ["inSec", "outSec", "speed", "volume", "preserveSourceAudio"],
      id: "clip:broll",
      kind: "media",
      label: "B-roll",
      mediaKind: "broll",
      segmentId: "segment-internal-current",
    };
    render(
      <InspectorControls
        onAction={onAction}
        selectedSegment={{ cutAction: "keep", endSec: 5, nextSegmentId: null, segmentId: "segment-internal-current", startSec: 1 }}
        target={broll}
      />,
    );

    const toggle = screen.getByLabelText("이 영상의 원래 소리도 함께 쓰기");
    expect(toggle).not.toBeChecked();
    fireEvent.click(toggle);
    fireEvent.click(screen.getByRole("button", { name: "B-roll 설정 저장" }));

    expect(onAction).toHaveBeenLastCalledWith({
      assetId: "asset-internal-broll",
      controls: { inSec: 0, outSec: 4, speed: 1, volume: 1, preserveSourceAudio: true },
      kind: "save-media",
      mediaKind: "broll",
      segmentId: "segment-internal-current",
    });
  });

  it("lets the creator turn on music that steps aside for the narration", () => {
    // 백엔드는 2026-08-18 이전부터 사이드체인 압축으로 이걸 실제로 해 왔다
    // (`ffmpeg_final_renderer`). 켜고 끄는 자리가 화면에 없어서 아무도 못 썼을
    // 뿐이다 -- 부품은 있는데 부르는 자리가 없던 그 패턴이다.
    const onAction = vi.fn();
    const bgm: InspectorTarget = {
      assetId: "asset-internal-bgm",
      clearOnly: false,
      controls: { ducking: false, fadeInSec: 0.5, fadeOutSec: 1, gainDb: -8 },
      fields: ["fadeInSec", "fadeOutSec", "ducking"],
      id: "clip:bgm",
      kind: "media",
      label: "배경 음악",
      mediaKind: "bgm",
      segmentId: "segment-internal-current",
    };
    render(
      <InspectorControls
        onAction={onAction}
        selectedSegment={{ cutAction: "keep", endSec: 5, nextSegmentId: null, segmentId: "segment-internal-current", startSec: 1 }}
        target={bgm}
      />,
    );

    const toggle = screen.getByLabelText("말할 때 배경 음악 낮추기");
    expect(toggle).not.toBeChecked();
    fireEvent.click(toggle);
    fireEvent.click(screen.getByRole("button", { name: "배경 음악 설정 저장" }));

    expect(onAction).toHaveBeenLastCalledWith({
      assetId: "asset-internal-bgm",
      controls: { ducking: true, fadeInSec: 0.5, fadeOutSec: 1, gainDb: -8 },
      kind: "save-media",
      mediaKind: "bgm",
      segmentId: "segment-internal-current",
    });
  });

  it("never offers the ducking switch where there is no narration to duck under", () => {
    // 효과음과 B-roll에는 이 개념이 없다. 렌더러도 bgm에만 사이드체인을 건다.
    const onAction = vi.fn();
    const sfx: InspectorTarget = {
      assetId: "asset-internal-sfx",
      clearOnly: false,
      controls: { fadeInSec: 0.2, fadeOutSec: 0.2 },
      fields: ["fadeInSec", "fadeOutSec"],
      id: "clip:sfx",
      kind: "media",
      label: "효과음",
      mediaKind: "sfx",
      segmentId: "segment-internal-current",
    };
    render(
      <InspectorControls
        onAction={onAction}
        selectedSegment={{ cutAction: "keep", endSec: 5, nextSegmentId: null, segmentId: "segment-internal-current", startSec: 1 }}
        target={sfx}
      />,
    );

    expect(screen.queryByLabelText("말할 때 배경 음악 낮추기")).not.toBeInTheDocument();
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
      kind: "preflight-caption-style",
      scope: "current_caption",
      segmentIds: ["segment-internal-current"],
      style: { ...style, fontSizePx: 32, horizontalAlign: "left" },
    });
  });

  it("loads approved TTS choices without auto-applying and exposes explicit apply and clear actions", async () => {
    const onAction = vi.fn();
    const loadApprovedTtsCandidates = vi.fn().mockResolvedValue([
      {
        assetId: "asset-approved",
        candidateId: "tts_candidate_approved",
        sourceText: "승인된 음성",
      },
    ]);

    render(
      <InspectorControls
        loadApprovedTtsCandidates={loadApprovedTtsCandidates}
        onAction={onAction}
        selectedSegment={{
          cutAction: "keep",
          endSec: 5,
          nextSegmentId: null,
          segmentId: "segment-internal-current",
          startSec: 1,
          ttsReplacement: {
            assetId: "asset-current",
            candidateId: "tts_candidate_current",
          },
        }}
        target={null}
        ttsCandidateScopeKey="project-a:session-a"
      />,
    );

    // 청취 승인 음성은 이제 부를 때만 부른다 -- 편집기를 여는 것만으로 조회가
    // 나가지 않게 하기 위해서다.
    fireEvent.click(screen.getByRole("button", { name: "승인한 음성 불러오기" }));
    expect(await screen.findByRole("option", { name: "승인 후보 1 · 승인된 음성" })).toBeVisible();
    expect(loadApprovedTtsCandidates).toHaveBeenCalledWith("segment-internal-current");
    expect(onAction).not.toHaveBeenCalled();
    expect(document.body).not.toHaveTextContent(/asset-approved|tts_candidate_approved/);

    fireEvent.click(screen.getByRole("button", { name: "승인한 음성 적용" }));
    expect(onAction).toHaveBeenLastCalledWith({
      assetId: "asset-approved",
      candidateId: "tts_candidate_approved",
      kind: "apply-tts-candidate",
      segmentId: "segment-internal-current",
    });

    fireEvent.click(screen.getByRole("button", { name: "적용한 음성 해제" }));
    expect(onAction).toHaveBeenLastCalledWith({
      kind: "clear-tts-candidate",
      segmentId: "segment-internal-current",
    });
    await waitFor(() => expect(onAction).toHaveBeenCalledTimes(2));
  });

  it("keeps manual editing available when approved TTS choices cannot be loaded", async () => {
    const onAction = vi.fn();
    render(
      <InspectorControls
        loadApprovedTtsCandidates={vi.fn().mockRejectedValue(new Error("offline"))}
        onAction={onAction}
        selectedSegment={{
          cutAction: "keep",
          endSec: 5,
          nextSegmentId: null,
          segmentId: "segment-internal-current",
          startSec: 1,
          ttsReplacement: null,
        }}
        target={null}
        ttsCandidateScopeKey="project-a:session-a"
      />,
    );

    // 청취 승인 음성은 이제 부를 때만 부른다 -- 편집기를 여는 것만으로 조회가
    // 나가지 않게 하기 위해서다.
    fireEvent.click(screen.getByRole("button", { name: "승인한 음성 불러오기" }));
    expect(await screen.findByText("승인한 음성을 불러오지 못했어요. 직접 편집은 계속할 수 있어요.")).toBeVisible();
    expect(screen.getByRole("button", { name: "컷 저장" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "승인한 음성 다시 불러오기" })).toBeEnabled();
    expect(onAction).not.toHaveBeenCalled();
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

  it("creates a new explanation card without offering to erase what does not exist yet", () => {
    const onAction = renderControls({
      target: {
        fields: ["title", "body", "text"],
        id: "overlay-new:explanation-card:segment-internal-current",
        isNew: true,
        kind: "overlay",
        label: "설명 카드",
        overlayKind: "explanation-card",
        segmentId: "segment-internal-current",
        value: { body: "", text: "", title: "" },
      },
    });

    expect(screen.queryByRole("button", { name: "설명 카드 지우기" })).toBeNull();

    fireEvent.change(screen.getByLabelText("제목"), { target: { value: "새 제목" } });
    fireEvent.change(screen.getByLabelText("본문"), { target: { value: "새 본문" } });
    fireEvent.change(screen.getByLabelText("설명"), { target: { value: "새 설명" } });
    fireEvent.click(screen.getByRole("button", { name: "설명 카드 저장" }));

    expect(onAction).toHaveBeenCalledWith({
      body: "새 본문",
      kind: "save-overlay",
      overlayKind: "explanation-card",
      segmentId: "segment-internal-current",
      text: "새 설명",
      title: "새 제목",
    });
  });

  // 정지 도형("여기를 보세요"). 자유 좌표 대신 프리셋 선택지만 준다 --
  // 자유 좌표·키프레임 편집기는 계획서 §4가 범위 밖으로 못박았다.
  it("saves a static shape overlay from preset choices only", () => {
    const onAction = renderControls({
      target: {
        fields: ["shape", "vertical", "horizontal", "size", "motion"],
        id: "overlay-new:shape:segment-internal-current",
        isNew: true,
        kind: "overlay",
        label: "강조 표시",
        overlayKind: "shape",
        segmentId: "segment-internal-current",
        value: { shape: "highlight_box", vertical: "middle", horizontal: "center", size: "medium", motion: "none" },
      },
    });

    // 아직 없는 도형에는 지우기를 보이지 않는다.
    expect(screen.queryByRole("button", { name: "강조 표시 지우기" })).toBeNull();

    fireEvent.change(screen.getByLabelText("모양"), { target: { value: "underline" } });
    fireEvent.change(screen.getByLabelText("세로 위치"), { target: { value: "bottom" } });
    fireEvent.change(screen.getByLabelText("가로 위치"), { target: { value: "left" } });
    fireEvent.change(screen.getByLabelText("크기"), { target: { value: "large" } });
    fireEvent.click(screen.getByRole("button", { name: "강조 표시 저장" }));

    expect(onAction).toHaveBeenCalledWith({
      kind: "save-overlay",
      overlayKind: "shape",
      segmentId: "segment-internal-current",
      shape: "underline",
      vertical: "bottom",
      horizontal: "left",
      size: "large",
      // 손대지 않은 저장은 움직임을 바꾸지 않는다.
      motion: "none",
    });
  });

  // 등장·퇴장·이동(2026-08-20 승인 5항). 프리셋 몇 가지이고, 타임라인에 점을 찍는
  // 편집기가 아니다 -- 시간·좌표를 입력하는 칸을 주지 않는다.
  it("lets the owner choose how a shape comes and goes, in plain words", () => {
    const onAction = renderControls({
      target: {
        fields: ["shape", "vertical", "horizontal", "size", "motion"],
        id: "overlay-new:shape:segment-internal-current",
        isNew: true,
        kind: "overlay",
        label: "강조 표시",
        overlayKind: "shape",
        segmentId: "segment-internal-current",
        value: { shape: "highlight_box", vertical: "middle", horizontal: "center", size: "medium", motion: "none" },
      },
    });

    const motion = screen.getByLabelText("움직임") as HTMLSelectElement;
    // 기본은 `그대로`. 승인 기록 5항이 정한 값이고, 이미 만들어 둔 표시가
    // 저장만으로 움직이기 시작하면 안 된다.
    expect(motion.value).toBe("none");
    expect(screen.getByRole("option", { name: "그대로" })).toBeTruthy();
    expect(screen.getByRole("option", { name: "천천히 나타나기" })).toBeTruthy();
    expect(screen.getByRole("option", { name: "천천히 사라지기" })).toBeTruthy();
    expect(screen.getByRole("option", { name: "나타났다 사라지기" })).toBeTruthy();
    expect(screen.getByRole("option", { name: "왼쪽에서 밀려 들어오기" })).toBeTruthy();
    expect(screen.getByRole("option", { name: "오른쪽에서 밀려 들어오기" })).toBeTruthy();

    // 화면 문구는 쉬운 말만 쓴다(§10.13) -- 내부 용어를 보이지 않는다.
    expect(screen.queryByRole("option", { name: /alpha|fade|keyframe|slide|opacity|투명도/i })).toBeNull();
    // 시간을 직접 넣는 칸은 없다. 그게 곧 승인 범위 밖인 키프레임 편집기다.
    expect(screen.queryByLabelText(/초|시간|길이/)).toBeNull();

    fireEvent.change(motion, { target: { value: "slide_in_left" } });
    fireEvent.click(screen.getByRole("button", { name: "강조 표시 저장" }));

    expect(onAction).toHaveBeenCalledWith({
      kind: "save-overlay",
      overlayKind: "shape",
      segmentId: "segment-internal-current",
      shape: "highlight_box",
      vertical: "middle",
      horizontal: "center",
      size: "medium",
      motion: "slide_in_left",
    });
  });

  it("starts the motion picker from what was already saved", () => {
    renderControls({
      target: {
        fields: ["shape", "vertical", "horizontal", "size", "motion"],
        id: "overlay:shape-1",
        kind: "overlay",
        label: "강조 표시",
        overlayKind: "shape",
        segmentId: "segment-internal-current",
        value: { shape: "icon_star", vertical: "top", horizontal: "left", size: "small", motion: "fade_in_out" },
      },
    });

    expect((screen.getByLabelText("움직임") as HTMLSelectElement).value).toBe("fade_in_out");
  });

  // 화살표 등 아이콘. drawbox가 사각형만 그려서 못 넣었던 자리를 구워 둔 그림으로
  // 메운다 -- 위치·크기 프리셋은 강조 상자와 똑같은 것을 그대로 쓴다.
  it("offers icons in the same shape picker and saves the chosen one", () => {
    const onAction = renderControls({
      target: {
        fields: ["shape", "vertical", "horizontal", "size", "motion"],
        id: "overlay-new:shape:segment-internal-current",
        isNew: true,
        kind: "overlay",
        label: "강조 표시",
        overlayKind: "shape",
        segmentId: "segment-internal-current",
        value: { shape: "highlight_box", vertical: "middle", horizontal: "center", size: "medium", motion: "none" },
      },
    });

    // 화면 문구는 쉬운 말만 쓴다 -- 내부 이름이나 파일명을 노출하지 않는다.
    expect(screen.getByRole("option", { name: "화살표(오른쪽)" })).toBeTruthy();
    expect(screen.getByRole("option", { name: "손가락" })).toBeTruthy();
    expect(screen.queryByRole("option", { name: /icon_/ })).toBeNull();

    fireEvent.change(screen.getByLabelText("모양"), { target: { value: "icon_arrow_right" } });
    fireEvent.click(screen.getByRole("button", { name: "강조 표시 저장" }));

    expect(onAction).toHaveBeenCalledWith({
      kind: "save-overlay",
      overlayKind: "shape",
      segmentId: "segment-internal-current",
      shape: "icon_arrow_right",
      vertical: "middle",
      horizontal: "center",
      size: "medium",
      motion: "none",
    });
  });

  // 아이콘 글꼴을 얹어 넓힌 몫. 예전에는 컨테이너 글꼴에 없어서 두부로 나왔고,
  // 그래서 목록에 아예 올리지 못하던 것들이다.
  it("offers the icon-font pictures in plain words and saves the chosen one", () => {
    const onAction = renderControls({
      target: {
        fields: ["shape", "vertical", "horizontal", "size"],
        id: "overlay-new:shape:segment-internal-current",
        isNew: true,
        kind: "overlay",
        label: "강조 표시",
        overlayKind: "shape",
        segmentId: "segment-internal-current",
        value: { shape: "highlight_box", vertical: "middle", horizontal: "center", size: "medium" },
      },
    });

    for (const label of ["전구", "돋보기", "물음표", "느낌표", "자물쇠", "장바구니"]) {
      expect(screen.getByRole("option", { name: label })).toBeTruthy();
    }
    // 코드포인트·글꼴 이름은 화면에 나오지 않는다.
    expect(screen.queryByRole("option", { name: /Material|U\+|\\u/i })).toBeNull();

    fireEvent.change(screen.getByLabelText("모양"), { target: { value: "icon_lightbulb" } });
    fireEvent.click(screen.getByRole("button", { name: "강조 표시 저장" }));

    expect(onAction).toHaveBeenCalledWith({
      kind: "save-overlay",
      overlayKind: "shape",
      segmentId: "segment-internal-current",
      shape: "icon_lightbulb",
      vertical: "middle",
      horizontal: "center",
      size: "medium",
    });
  });

  it("erases an existing shape overlay through the shared clear action", () => {
    const onAction = renderControls({
      target: {
        fields: ["shape", "vertical", "horizontal", "size"],
        id: "overlay:shape-1",
        kind: "overlay",
        label: "강조 표시",
        overlayKind: "shape",
        segmentId: "segment-internal-current",
        value: { shape: "underline", vertical: "bottom", horizontal: "center", size: "large" },
      },
    });

    fireEvent.click(screen.getByRole("button", { name: "강조 표시 지우기" }));

    expect(onAction).toHaveBeenCalledWith({
      kind: "clear-overlay",
      overlayKind: "shape",
      segmentId: "segment-internal-current",
    });
  });

  it("lets the owner pick a look, and sends it with the rest of the clip's settings", async () => {
    // 색감이 저장 payload에 안 실리면 고르고 저장해도 아무 일이 없다.
    const onAction = vi.fn();
    const broll = {
      assetId: "asset-broll",
      clearOnly: false,
      controls: { crop: "center", speed: 1, volume: 1 },
      fields: ["speed", "volume", "filter"],
      id: "clip:broll",
      kind: "media",
      label: "B-roll",
      mediaKind: "broll",
      segmentId: "segment-internal-current",
    } as const;

    render(
      <InspectorControls
        onAction={onAction}
        selectedSegment={{ cutAction: "keep", endSec: 5, nextSegmentId: null, segmentId: "segment-internal-current", startSec: 1 }}
        target={broll as never}
      />,
    );

    fireEvent.change(screen.getByLabelText("B-roll 색감"), { target: { value: "vintage" } });
    fireEvent.click(screen.getByRole("button", { name: "B-roll 설정 저장" }));

    expect(onAction.mock.calls[0][0].controls.filter).toEqual({ type: "vintage" });
  });

  it("reads back the look already saved on the clip", async () => {
    // 저장된 것을 되읽지 못하면 고른 적 없는 것처럼 보이고, 다음 저장에서
    // 조용히 지워진다 -- 2026-08-23에 자막 숨김에서 똑같은 자리를 빠뜨렸다.
    const broll = {
      assetId: "asset-broll",
      clearOnly: false,
      controls: { crop: "center", filter: { type: "warm", chosen_by: "owner" } },
      fields: ["filter"],
      id: "clip:broll",
      kind: "media",
      label: "B-roll",
      mediaKind: "broll",
      segmentId: "segment-internal-current",
    } as const;

    render(
      <InspectorControls
        onAction={vi.fn()}
        selectedSegment={{ cutAction: "keep", endSec: 5, nextSegmentId: null, segmentId: "segment-internal-current", startSec: 1 }}
        target={broll as never}
      />,
    );

    expect(screen.getByLabelText("B-roll 색감")).toHaveValue("warm");
  });

  it("turning a look off sends null, not the word none", async () => {
    const onAction = vi.fn();
    const broll = {
      assetId: "asset-broll",
      clearOnly: false,
      controls: { crop: "center", filter: { type: "warm", chosen_by: "owner" } },
      fields: ["filter"],
      id: "clip:broll",
      kind: "media",
      label: "B-roll",
      mediaKind: "broll",
      segmentId: "segment-internal-current",
    } as const;

    render(
      <InspectorControls
        onAction={onAction}
        selectedSegment={{ cutAction: "keep", endSec: 5, nextSegmentId: null, segmentId: "segment-internal-current", startSec: 1 }}
        target={broll as never}
      />,
    );

    fireEvent.change(screen.getByLabelText("B-roll 색감"), { target: { value: "none" } });
    fireEvent.click(screen.getByRole("button", { name: "B-roll 설정 저장" }));

    expect(onAction.mock.calls[0][0].controls.filter).toBeNull();
  });

  it("says up front that CapCut will not show the same look", async () => {
    // 캡컷 필터는 캡컷 서버 자원이라 우리 ffmpeg 그림과 같을 수 없다. 고른
    // 뒤에 캡컷에서 다른 그림을 보는 것보다, 고르는 자리에서 아는 편이 낫다.
    const broll = {
      assetId: "asset-broll",
      clearOnly: false,
      controls: { crop: "center", speed: 1, volume: 1 },
      fields: ["speed", "volume", "filter"],
      id: "clip:broll",
      kind: "media",
      label: "B-roll",
      mediaKind: "broll",
      segmentId: "segment-internal-current",
    } as const;

    render(
      <InspectorControls
        onAction={vi.fn()}
        selectedSegment={{ cutAction: "keep", endSec: 5, nextSegmentId: null, segmentId: "segment-internal-current", startSec: 1 }}
        target={broll as never}
      />,
    );

    expect(screen.getByText("캡컷으로 넘기면 비슷한 색감으로 바뀝니다.")).toBeInTheDocument();
  });

  it("lets the owner set playback speed and loudness on a clip", async () => {
    // Both rode in the command port from the start and no screen ever offered
    // them, so a clip could not be sped up or quietened without leaving
    // VideoBox. B-roll from a phone is often too long and too loud.
    const onAction = vi.fn();
    const broll = {
      assetId: "asset-broll",
      clearOnly: false,
      controls: { crop: "center", speed: 1, volume: 1, inSec: 0, outSec: 4 },
      fields: ["inSec", "outSec", "speed", "volume"],
      id: "clip:broll",
      kind: "media",
      label: "B-roll",
      mediaKind: "broll",
      segmentId: "segment-internal-current",
    } as const;

    render(
      <InspectorControls
        onAction={onAction}
        selectedSegment={{ cutAction: "keep", endSec: 5, nextSegmentId: null, segmentId: "segment-internal-current", startSec: 1 }}
        target={broll as never}
      />,
    );

    fireEvent.change(screen.getByLabelText("B-roll 재생 속도"), { target: { value: "1.5" } });
    fireEvent.change(screen.getByLabelText("B-roll 소리 크기"), { target: { value: "0.3" } });
    fireEvent.click(screen.getByRole("button", { name: "B-roll 설정 저장" }));

    expect(onAction).toHaveBeenCalledTimes(1);
    const sent = onAction.mock.calls[0][0];
    expect(sent.kind).toBe("save-media");
    expect(sent.controls.speed).toBe(1.5);
    expect(sent.controls.volume).toBe(0.3);
    // The range the owner already chose must survive the same save.
    expect(sent.controls.inSec).toBe(0);
    expect(sent.controls.outSec).toBe(4);
  });

  it("lets the owner pick a common speed with one press instead of typing it", async () => {
    // 숏폼에서는 같은 배속을 클립마다 반복해서 건다. 숫자를 지우고 다시 치는
    // 것이 실제로 걸리적거린다는 지적을 받아 자주 쓰는 값만 버튼으로 뒀다.
    const onAction = vi.fn();
    const broll = {
      assetId: "asset-broll",
      clearOnly: false,
      controls: { crop: "center", speed: 1, volume: 1 },
      fields: ["speed", "volume"],
      id: "clip:broll",
      kind: "media",
      label: "B-roll",
      mediaKind: "broll",
      segmentId: "segment-internal-current",
    } as const;

    render(
      <InspectorControls
        onAction={onAction}
        selectedSegment={{ cutAction: "keep", endSec: 5, nextSegmentId: null, segmentId: "segment-internal-current", startSec: 1 }}
        target={broll as never}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "B-roll 2배속" }));
    fireEvent.click(screen.getByRole("button", { name: "B-roll 설정 저장" }));

    expect(onAction.mock.calls[0][0].controls.speed).toBe(2);
    // 버튼은 숫자칸을 대신하는 게 아니라 같이 움직인다. 어긋나면 화면이
    // 보여 주는 값과 저장되는 값이 달라진다.
    expect((screen.getByLabelText("B-roll 재생 속도") as HTMLInputElement).value).toBe("2");
  });

  it("shows which speed is currently chosen", async () => {
    // 어느 배속인지 버튼만 보고 알 수 없으면, 눌러 놓고도 다시 숫자칸을 본다.
    const onAction = vi.fn();
    const broll = {
      assetId: "asset-broll",
      clearOnly: false,
      controls: { crop: "center", speed: 0.5, volume: 1 },
      fields: ["speed", "volume"],
      id: "clip:broll",
      kind: "media",
      label: "B-roll",
      mediaKind: "broll",
      segmentId: "segment-internal-current",
    } as const;

    render(
      <InspectorControls
        onAction={onAction}
        selectedSegment={{ cutAction: "keep", endSec: 5, nextSegmentId: null, segmentId: "segment-internal-current", startSec: 1 }}
        target={broll as never}
      />,
    );

    expect(screen.getByRole("button", { name: "B-roll 0.5배속" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "B-roll 2배속" })).toHaveAttribute("aria-pressed", "false");
  });
});
