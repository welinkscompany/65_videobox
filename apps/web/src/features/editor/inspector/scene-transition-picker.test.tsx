/**
 * 편집기에서 장면 사이 넘기기를 고를 수 있는가.
 *
 * **만든 것만 보여 준다.** 캡컷의 1,137개를 흉내 내지 않는다 — 없는 기능의
 * 자리를 만들어 두면 배치가 거짓말을 한다.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

import { InspectorControls, type InspectorAction } from "./InspectorControls";
import { SCENE_TRANSITION_CHOICES } from "./sceneTransitions";

afterEach(cleanup);

type Segment = Parameters<typeof InspectorControls>[0]["selectedSegment"];

const middleScene: Segment = {
  segmentId: "scene-2",
  startSec: 4,
  endSec: 8,
  nextSegmentId: "scene-3",
  previousSegmentId: "scene-1",
  cutAction: "keep",
};

function renderScene(segment: Segment, onAction: (action: InspectorAction) => void = vi.fn()) {
  render(<InspectorControls onAction={onAction} selectedSegment={segment} target={null} />);
  return onAction;
}

describe("장면 넘기기 고르기", () => {
  it("첫 장면에는 넘기기 칸이 아예 없다", () => {
    // 앞에 붙은 장면이 없으면 넘어올 경계가 없다. 고를 수 있는 척하지 않는다.
    renderScene({ ...middleScene, segmentId: "scene-1", previousSegmentId: null, startSec: 0, endSec: 4 });

    expect(screen.queryByLabelText("넘기는 방법")).not.toBeInTheDocument();
  });

  it("앞 장면이 있으면 만든 여섯 개와 '바로 넘기기'만 보여 준다", () => {
    renderScene(middleScene);

    const options = screen.getAllByRole("option").filter((option) =>
      screen.getByLabelText("넘기는 방법").contains(option),
    );
    expect(options.map((option) => (option as HTMLOptionElement).value)).toEqual([
      "none",
      ...SCENE_TRANSITION_CHOICES.map((choice) => choice.value),
    ]);
  });

  it("고르기만 해서는 저장되지 않는다 — 저장 단추를 눌러야 나간다", () => {
    const onAction = renderScene(middleScene);

    fireEvent.change(screen.getByLabelText("넘기는 방법"), { target: { value: "wipeleft" } });
    expect(onAction).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "넘기기 저장" }));
    expect(onAction).toHaveBeenCalledWith({
      kind: "set-transition",
      segmentId: "scene-2",
      transition: { type: "wipeleft", durationSec: 0.5 },
    });
  });

  it("이미 걸린 넘기기가 칸에 그대로 뜬다", () => {
    renderScene({ ...middleScene, transitionIn: { type: "circleopen", durationSec: 0.8 } });

    expect((screen.getByLabelText("넘기는 방법") as HTMLSelectElement).value).toBe("circleopen");
  });

  it("'바로 넘기기'로 되돌리면 전환을 끈다", () => {
    const onAction = renderScene({ ...middleScene, transitionIn: { type: "fade", durationSec: 0.5 } });

    fireEvent.change(screen.getByLabelText("넘기는 방법"), { target: { value: "none" } });
    fireEvent.click(screen.getByRole("button", { name: "넘기기 저장" }));

    expect(onAction).toHaveBeenCalledWith({
      kind: "set-transition",
      segmentId: "scene-2",
      transition: null,
    });
  });

  it("고른 길이를 그대로 지킨다 — 저장할 때 기본값으로 되돌리지 않는다", () => {
    const onAction = renderScene({ ...middleScene, transitionIn: { type: "fade", durationSec: 1.2 } });

    fireEvent.change(screen.getByLabelText("넘기는 방법"), { target: { value: "slideup" } });
    fireEvent.click(screen.getByRole("button", { name: "넘기기 저장" }));

    expect(onAction).toHaveBeenCalledWith({
      kind: "set-transition",
      segmentId: "scene-2",
      transition: { type: "slideup", durationSec: 1.2 },
    });
  });

  it("다른 장면을 고르면 앞 장면에서 고르던 값이 남지 않는다", () => {
    const rendered = render(
      <InspectorControls onAction={vi.fn()} selectedSegment={{ ...middleScene, transitionIn: { type: "fade", durationSec: 0.5 } }} target={null} />,
    );
    expect((screen.getByLabelText("넘기는 방법") as HTMLSelectElement).value).toBe("fade");

    rendered.rerender(
      <InspectorControls onAction={vi.fn()} selectedSegment={{ ...middleScene, segmentId: "scene-3", previousSegmentId: "scene-2" }} target={null} />,
    );

    expect((screen.getByLabelText("넘기는 방법") as HTMLSelectElement).value).toBe("none");
  });
});
