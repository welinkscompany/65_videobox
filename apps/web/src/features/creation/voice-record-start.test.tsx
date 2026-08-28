import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

import { api, ApiRequestError, type SourceVoiceStart } from "../../api";
import { VoiceRecordStart } from "./VoiceRecordStart";

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

class FakeRecorder {
  ondataavailable: ((event: { data: Blob }) => void) | null = null;
  onstop: (() => void) | null = null;
  start() {}
  stop() {
    this.ondataavailable?.({ data: new Blob(["audio"], { type: "audio/webm" }) });
    this.onstop?.();
  }
}

function stubMicrophone(recorder: typeof FakeRecorder = FakeRecorder) {
  Object.defineProperty(navigator, "mediaDevices", {
    configurable: true,
    value: { getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [{ stop: vi.fn() }] }) },
  });
  vi.stubGlobal("MediaRecorder", recorder);
}

async function recordAndStop() {
  fireEvent.click(await screen.findByRole("button", { name: "마이크로 대본 녹음 시작" }));
  fireEvent.click(await screen.findByRole("button", { name: "대본 녹음 마치기" }));
}

const heard: SourceVoiceStart = {
  asset_id: "asset_1",
  script_text: "오늘은 라면을 끓여볼게요. 므러 므럴 물을 준비해요. 아 잠깐 다시 할게요. 뜨거운 물을 준비해요.",
  spoken_segment_count: 4,
  segments: [
    { segment_index: 0, text: "오늘은 라면을 끓여볼게요." },
    { segment_index: 1, text: "므러 므럴 물을 준비해요." },
    { segment_index: 2, text: "아 잠깐 다시 할게요." },
    { segment_index: 3, text: "뜨거운 물을 준비해요." },
  ],
  retake_candidates: [
    { segment_index: 1, start_sec: 2.0, end_sec: 4.0, text: "므러 므럴 물을 준비해요.", reason: "low_confidence" },
    { segment_index: 2, start_sec: 4.0, end_sec: 5.5, text: "아 잠깐 다시 할게요.", reason: "retry_cue" },
  ],
};

/** 목소리만 녹음해서 시작하는 길(owner 요청 2026-08-29).
 *
 *  여기서 지키는 것은 셋이다.
 *  1. **잘못 발음한 곳을 조용히 지우지 않는다.** 후보만 보여주고, 뺄지 남길지
 *     owner가 하나씩 고른다 -- 기본은 빼는 쪽이지만 되돌릴 수 있다.
 *  2. **받아쓴 글을 그대로 확정하지 않는다.** owner가 고칠 칸을 먼저 보여주고,
 *     확인을 눌러야 기획으로 넘어간다.
 *  3. **마이크 권한·무음 녹음의 실패 이유를 구분해서 말한다.** */
describe("목소리 녹음으로 시작", () => {
  it("녹음을 마치면 다시 들어볼 구간이 기본으로 빠진 대본을 보여준다", async () => {
    vi.spyOn(api, "uploadSourceVoice").mockResolvedValue(heard);
    stubMicrophone();
    const onReady = vi.fn();
    render(<VoiceRecordStart projectId="project_1" onReady={onReady} />);

    await recordAndStop();

    const script = await screen.findByLabelText("대본으로 쓸 글");
    // low_confidence·retry_cue 두 구간은 기본으로 빠져 있어야 한다.
    expect(script).toHaveValue("오늘은 라면을 끓여볼게요. 뜨거운 물을 준비해요.");
    expect(onReady).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "이 대본으로 기획 시작" }));
    expect(onReady).toHaveBeenCalledWith({ assetId: "asset_1", scriptText: "오늘은 라면을 끓여볼게요. 뜨거운 물을 준비해요." });
  });

  it("후보 구간의 체크를 풀면 그 구간이 대본에 다시 들어온다", async () => {
    vi.spyOn(api, "uploadSourceVoice").mockResolvedValue(heard);
    stubMicrophone();
    render(<VoiceRecordStart projectId="project_1" onReady={vi.fn()} />);

    await recordAndStop();
    await screen.findByLabelText("대본으로 쓸 글");

    const checkboxes = screen.getAllByRole("checkbox");
    fireEvent.click(checkboxes[0]); // "므러 므럴 물을 준비해요." 되살리기

    expect(screen.getByLabelText("대본으로 쓸 글")).toHaveValue(
      "오늘은 라면을 끓여볼게요. 므러 므럴 물을 준비해요. 뜨거운 물을 준비해요.",
    );
  });

  it("후보가 없는 깨끗한 녹음은 구간 목록을 보여주지 않는다", async () => {
    vi.spyOn(api, "uploadSourceVoice").mockResolvedValue({
      asset_id: "asset_2",
      script_text: "안녕하세요. 오늘 영상 시작할게요.",
      spoken_segment_count: 2,
      segments: [
        { segment_index: 0, text: "안녕하세요." },
        { segment_index: 1, text: "오늘 영상 시작할게요." },
      ],
      retake_candidates: [],
    });
    stubMicrophone();
    render(<VoiceRecordStart projectId="project_1" onReady={vi.fn()} />);

    await recordAndStop();
    await screen.findByLabelText("대본으로 쓸 글");

    expect(screen.queryByRole("region", { name: "다시 들어볼 구간" })).toBeNull();
  });

  it("마이크 권한이 없으면 이유를 말한다", async () => {
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: { getUserMedia: vi.fn().mockRejectedValue(new Error("denied")) },
    });
    render(<VoiceRecordStart projectId="project_1" onReady={vi.fn()} />);

    fireEvent.click(await screen.findByRole("button", { name: "마이크로 대본 녹음 시작" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("마이크를 사용할 수 없어요");
  });

  it("무음 녹음은 빈 대본을 만드는 대신 이유를 말한다", async () => {
    vi.spyOn(api, "uploadSourceVoice").mockRejectedValue(new ApiRequestError("source_voice_has_no_speech", 422, "/api/x"));
    stubMicrophone();
    render(<VoiceRecordStart projectId="project_1" onReady={vi.fn()} />);

    await recordAndStop();

    expect(await screen.findByRole("alert")).toHaveTextContent(/말소리가 없어요/);
  });

  it("대본을 다 지우거나 전부 빼면 그 글로는 시작할 수 없다", async () => {
    vi.spyOn(api, "uploadSourceVoice").mockResolvedValue(heard);
    stubMicrophone();
    const onReady = vi.fn();
    render(<VoiceRecordStart projectId="project_1" onReady={onReady} />);

    await recordAndStop();
    const script = await screen.findByLabelText("대본으로 쓸 글");
    fireEvent.change(script, { target: { value: "   " } });

    expect(screen.getByRole("button", { name: "이 대본으로 기획 시작" })).toBeDisabled();
    expect(onReady).not.toHaveBeenCalled();
  });

  it("다시 녹음하기를 누르면 처음 화면으로 돌아간다", async () => {
    vi.spyOn(api, "uploadSourceVoice").mockResolvedValue(heard);
    stubMicrophone();
    render(<VoiceRecordStart projectId="project_1" onReady={vi.fn()} />);

    await recordAndStop();
    await screen.findByLabelText("대본으로 쓸 글");

    fireEvent.click(screen.getByRole("button", { name: "다시 녹음하기" }));

    await waitFor(() => expect(screen.getByRole("button", { name: "마이크로 대본 녹음 시작" })).toBeVisible());
  });
});
