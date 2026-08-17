import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

import { api } from "../../api";
import { VoiceMaterialPanel } from "./VoiceMaterialPanel";

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

function stubVoiceScreen() {
  vi.spyOn(api, "getLatestEditingSession").mockResolvedValue({
    session_id: "session_a", project_id: "project_a", timeline_id: "t", session_revision: 1, segments: [],
  } as never);
  vi.spyOn(api, "listVoiceSamples").mockResolvedValue([] as never);
}

describe("voice material panel", () => {
  it("tells the owner what registering a voice is for", async () => {
    // 아래 화면은 "아직 저장한 목소리가 없어요"까지만 말한다. 처음 온 사람은
    // 무엇을 넣어야 하는지 알 수 없다.
    stubVoiceScreen();

    render(<VoiceMaterialPanel projectId="project_a" />);

    expect(await screen.findByText(
      "내 목소리를 등록하면 대본을 내 목소리로 읽어 줘요. 조용한 곳에서 30초쯤 말한 파일이 좋아요.",
    )).toBeVisible();
  });

  it("offers exactly one way to add a voice, not two", async () => {
    // 처음에 여기에 업로드를 하나 더 붙였다가 같은 화면에 올리는 길이 두 개가 됐다.
    // 같은 일을 두 곳에서 하게 두면 어느 쪽이 진짜인지 알 수 없다.
    stubVoiceScreen();

    render(<VoiceMaterialPanel projectId="project_a" />);
    await screen.findByText("내 목소리 샘플");

    expect(screen.queryByRole("button", { name: "내 목소리 올리기" })).not.toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "파일 업로드" })).toHaveLength(1);
  });

  it("keeps every group on the one heading level the other tabs use", async () => {
    // 여기만 h2 → h3 → h2였다. 화면에서는 티가 안 나지만 화면 낭독기에서는
    // 목차가 거꾸로 올라간다. 탭 이름이 이미 `내레이션`이라 같은 제목을 한 번 더
    // 둘 이유도 없었다.
    stubVoiceScreen();

    render(<VoiceMaterialPanel projectId="project_a" />);
    await screen.findByText("이 영상의 내레이션");

    const levels = screen.getAllByRole("heading").map((heading) => heading.tagName);
    expect(new Set(levels)).toEqual(new Set(["H2"]));
  });

  it("brings the voice work itself, not just a link to it", async () => {
    // 재료 단계에서 만나야 하는 것은 안내가 아니라 실제로 만드는 화면이다.
    stubVoiceScreen();

    render(<VoiceMaterialPanel projectId="project_a" />);

    expect(await screen.findByText("후보에 사용할 목소리")).toBeVisible();
  });
});
