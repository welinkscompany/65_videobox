import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

import { api, ApiRequestError } from "../../api";
import { YujinScriptStart } from "./YujinScriptStart";

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

const draft = {
  title: "집에서 만드는 라면 세 가지",
  script_text: "오늘은 라면을 세 가지로 끓여 볼게요.\n첫 번째는 계란을 마지막에 넣습니다.",
  scenes: [
    { scene_number: 1, narration: "오늘은 라면을 세 가지로 끓여 볼게요.", visual: "끓는 냄비 가까이" },
    { scene_number: 2, narration: "첫 번째는 계란을 마지막에 넣습니다.", visual: "" },
  ],
};

const typeTopic = (value = "집에서 라면 맛있게 끓이는 법") =>
  fireEvent.change(screen.getByLabelText("무엇에 대한 영상인가요"), { target: { value } });

/** 대본도 찍어 둔 영상도 없는 사람이 첫 걸음을 떼는 길.
 *
 *  여기서 지키는 것은 셋이다.
 *  1. **받은 대본을 그대로 확정하지 않는다.** 유진이도 틀린다 -- owner가 고칠
 *     칸을 먼저 보여 주고, 확인을 눌러야 기획으로 넘어간다.
 *  2. **기다리는 동안 화면이 멈춘 것처럼 보이지 않는다.** 그동안 두 번 눌리지 않게 막는다.
 *  3. **답 못 한 이유를 구분해서 말한다.** 닿지 못한 것과 쓸 수 없는 대본이 온
 *     것은 owner가 할 다음 행동이 다르다. */
describe("유진이 대본 초안 쓰기", () => {
  it("받은 초안을 고칠 수 있는 칸에 보여 주고, 확인해야 넘어간다", async () => {
    vi.spyOn(api, "createScriptDraft").mockResolvedValue(draft);
    const onReady = vi.fn();
    render(<YujinScriptStart projectId="project_1" onReady={onReady} />);

    typeTopic();
    fireEvent.click(screen.getByRole("button", { name: "유진에게 대본 부탁하기" }));

    const edited = await screen.findByLabelText("유진이 쓴 대본");
    expect(edited).toHaveValue(draft.script_text);
    // 유진이도 틀린다. 확인 전에는 아무것도 확정하지 않는다.
    expect(onReady).not.toHaveBeenCalled();

    fireEvent.change(edited, { target: { value: "오늘은 라면을 두 가지로 끓여 볼게요." } });
    fireEvent.click(screen.getByRole("button", { name: "이 대본으로 기획 시작" }));

    expect(onReady).toHaveBeenCalledWith({ scriptText: "오늘은 라면을 두 가지로 끓여 볼게요." });
  });

  it("장면마다 무엇을 보여 줄지도 함께 보여 준다", async () => {
    // 이 제품의 차별점은 자산이 아니라 **고르는 일**이다(계획서 §4.2). 대본만
    // 주고 장면을 감추면 유진이 한 일의 절반이 안 보인다.
    vi.spyOn(api, "createScriptDraft").mockResolvedValue(draft);
    render(<YujinScriptStart projectId="project_1" onReady={vi.fn()} />);

    typeTopic();
    fireEvent.click(screen.getByRole("button", { name: "유진에게 대본 부탁하기" }));

    const scenes = await screen.findByRole("list", { name: "유진이 생각한 장면" });
    expect(scenes).toHaveTextContent("끓는 냄비 가까이");
  });

  it("길이와 장면 수를 골라 보낸다", async () => {
    const write = vi.spyOn(api, "createScriptDraft").mockResolvedValue(draft);
    render(<YujinScriptStart projectId="project_1" onReady={vi.fn()} />);

    typeTopic();
    fireEvent.change(screen.getByLabelText("영상 길이"), { target: { value: "180" } });
    fireEvent.change(screen.getByLabelText("장면 수"), { target: { value: "8" } });
    fireEvent.click(screen.getByRole("button", { name: "유진에게 대본 부탁하기" }));

    await waitFor(() => expect(write).toHaveBeenCalledWith("project_1", {
      topic: "집에서 라면 맛있게 끓이는 법", duration_sec: 180, scene_count: 8,
    }));
  });

  it("쓰는 동안 무엇을 하고 있는지 말하고, 그 사이 다시 눌리지 않는다", async () => {
    let finish: ((value: typeof draft) => void) | null = null;
    const write = vi.spyOn(api, "createScriptDraft").mockReturnValue(new Promise((resolve) => { finish = resolve; }));
    render(<YujinScriptStart projectId="project_1" onReady={vi.fn()} />);

    typeTopic();
    fireEvent.click(screen.getByRole("button", { name: "유진에게 대본 부탁하기" }));

    const busy = await screen.findByRole("button", { name: "유진이 대본을 쓰고 있어요" });
    expect(busy).toBeDisabled();

    fireEvent.click(busy);
    expect(write).toHaveBeenCalledTimes(1);

    finish!(draft);
    await screen.findByLabelText("유진이 쓴 대본");
  });

  it("닿지 못한 것과 쓸 수 없는 대본이 온 것을 다르게 말한다", async () => {
    const write = vi.spyOn(api, "createScriptDraft")
      .mockRejectedValueOnce(new ApiRequestError("script_draft_writer_unavailable", 503, "/api/x"))
      .mockRejectedValueOnce(new ApiRequestError("script_draft_empty", 502, "/api/x"));
    render(<YujinScriptStart projectId="project_1" onReady={vi.fn()} />);

    typeTopic();
    fireEvent.click(screen.getByRole("button", { name: "유진에게 대본 부탁하기" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/잠시 뒤 다시/);

    fireEvent.click(screen.getByRole("button", { name: "유진에게 대본 부탁하기" }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/주제를 조금 더 자세히/));
    expect(write).toHaveBeenCalledTimes(2);
  });

  it("제 시간에 못 끝냈으면 짧게 부탁하라고 말한다", async () => {
    // "다시 시도해 주세요"라고 하면 owner는 같은 길이로 몇 번이고 다시 누른다.
    // 2026-08-21 실측으로 5분·12장면이 28.7초였고 상한이 30초다.
    vi.spyOn(api, "createScriptDraft")
      .mockRejectedValue(new ApiRequestError("script_draft_took_too_long", 504, "/api/x"));
    render(<YujinScriptStart projectId="project_1" onReady={vi.fn()} />);

    typeTopic();
    fireEvent.click(screen.getByRole("button", { name: "유진에게 대본 부탁하기" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/길이나 장면 수를 줄여서/);
  });

  it("주제를 적지 않았으면 부탁하지 않는다", () => {
    const write = vi.spyOn(api, "createScriptDraft");
    render(<YujinScriptStart projectId="project_1" onReady={vi.fn()} />);

    fireEvent.click(screen.getByRole("button", { name: "유진에게 대본 부탁하기" }));

    expect(write).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent(/무엇에 대한 영상인지/);
  });

  it("받은 대본을 다 지우면 그 글로는 시작할 수 없다", async () => {
    vi.spyOn(api, "createScriptDraft").mockResolvedValue(draft);
    const onReady = vi.fn();
    render(<YujinScriptStart projectId="project_1" onReady={onReady} />);

    typeTopic();
    fireEvent.click(screen.getByRole("button", { name: "유진에게 대본 부탁하기" }));

    const edited = await screen.findByLabelText("유진이 쓴 대본");
    fireEvent.change(edited, { target: { value: "   " } });

    expect(screen.getByRole("button", { name: "이 대본으로 기획 시작" })).toBeDisabled();
    expect(onReady).not.toHaveBeenCalled();
  });

  it("대본을 받으면 주제로 어울리는 소재 세트도 함께 보여준다", async () => {
    // owner 요청(2026-08-28, 필수): "주제 하나로 BGM+이미지스타일+AI보이스까지
    // 세트로 추천." 대본이 먼저 뜨고, 소재 세트는 뒤이어 채워진다.
    vi.spyOn(api, "createScriptDraft").mockResolvedValue(draft);
    vi.spyOn(api, "createCreationRecommendationSet").mockResolvedValue({
      bgm: [{ library_asset_id: "asset-1", description: "잔잔한 피아노", duration_seconds: 120, score: 0.8 }],
      image_style: { style_id: "cinematic_realistic", name: "실사 시네마틱", prompt_suffix: "cinematic realistic photo", reason: '"브이로그" 낱말이 있어 추천했어요.' },
      voice: { asset_id: "voice-1", filename: "my-voice.wav", note: "이미 등록한 목소리 중 가장 최근 것을 추천했어요." },
      bgm_semantic: true,
    });
    render(<YujinScriptStart projectId="project_1" onReady={vi.fn()} />);

    typeTopic();
    fireEvent.click(screen.getByRole("button", { name: "유진에게 대본 부탁하기" }));
    await screen.findByLabelText("유진이 쓴 대본");

    const recommendationSection = await screen.findByRole("region", { name: "주제로 미리 본 소재 세트" });
    expect(recommendationSection).toHaveTextContent("잔잔한 피아노");
    expect(recommendationSection).toHaveTextContent("실사 시네마틱");
    expect(recommendationSection).toHaveTextContent("my-voice.wav");
  });

  it("소재 세트를 못 받아도 대본 확정은 막지 않는다", async () => {
    vi.spyOn(api, "createScriptDraft").mockResolvedValue(draft);
    vi.spyOn(api, "createCreationRecommendationSet").mockRejectedValue(new Error("network"));
    const onReady = vi.fn();
    render(<YujinScriptStart projectId="project_1" onReady={onReady} />);

    typeTopic();
    fireEvent.click(screen.getByRole("button", { name: "유진에게 대본 부탁하기" }));
    await screen.findByLabelText("유진이 쓴 대본");
    await screen.findByText("소재 추천을 지금 불러오지 못했어요. 미디어 단계에서 직접 골라도 괜찮아요.");

    fireEvent.click(screen.getByRole("button", { name: "이 대본으로 기획 시작" }));
    expect(onReady).toHaveBeenCalledWith({ scriptText: draft.script_text });
  });

  it("마음에 안 들면 주제를 다시 적을 수 있다", async () => {
    vi.spyOn(api, "createScriptDraft").mockResolvedValue(draft);
    render(<YujinScriptStart projectId="project_1" onReady={vi.fn()} />);

    typeTopic();
    fireEvent.click(screen.getByRole("button", { name: "유진에게 대본 부탁하기" }));
    await screen.findByLabelText("유진이 쓴 대본");

    fireEvent.click(screen.getByRole("button", { name: "주제 다시 적기" }));

    expect(screen.getByLabelText("무엇에 대한 영상인가요")).toBeVisible();
  });
});
