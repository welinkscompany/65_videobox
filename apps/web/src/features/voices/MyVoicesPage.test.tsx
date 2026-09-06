import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { MyVoicesPage } from "./MyVoicesPage";

const voice = (overrides: Record<string, unknown> = {}) => ({
  asset_id: "asset_voice_1",
  asset_type: "voice_sample_audio",
  project_id: "project-1",
  project_name: "셀러 교육 1화",
  display_name: "차분한 목소리",
  created_at: "2026-09-01T10:00:00+00:00",
  duration_sec: 12.5,
  mime_type: "audio/wav",
  content_url: "/api/projects/project-1/assets/asset_voice_1/content",
  metadata: {},
  ...overrides,
});

afterEach(cleanup);

describe("내 목소리", () => {
  it("녹음한 목소리를 이름과 함께 보여 준다", async () => {
    render(<MyVoicesPage listVoices={async () => [voice()]} />);

    expect(await screen.findByText("차분한 목소리")).toBeInTheDocument();
    expect(screen.getByText(/셀러 교육 1화/)).toBeInTheDocument();
  });

  it("이름을 안 붙인 목소리도 목록에서 빼지 않는다", async () => {
    // 이름은 나중에 붙일 수 있다. 이름이 없다고 안 보이면 **있는데 없는 것**이
    // 된다 -- 그 목소리는 영영 이름을 못 받는다.
    render(<MyVoicesPage listVoices={async () => [voice({ display_name: null })]} />);

    expect(await screen.findByText("이름 없는 목소리")).toBeInTheDocument();
  });

  it("바로 들어 볼 수 있다", async () => {
    const { container } = render(<MyVoicesPage listVoices={async () => [voice()]} />);

    await screen.findByText("차분한 목소리");
    const player = container.querySelector("audio");
    expect(player).toHaveAttribute("src", "/api/projects/project-1/assets/asset_voice_1/content");
  });

  it("이름을 바꾸면 그 프로젝트로 보낸다", async () => {
    // 목소리는 프로젝트에 묶여 있다. 줄마다 어느 프로젝트 것인지 들고 있어야
    // 이름 바꾸기가 엉뚱한 곳으로 가지 않는다.
    const rename = vi.fn(async () => voice({ display_name: "새 이름" }));
    render(<MyVoicesPage listVoices={async () => [voice()]} renameVoice={rename} />);

    fireEvent.click(await screen.findByRole("button", { name: /이름 바꾸기/ }));
    fireEvent.change(screen.getByRole("textbox", { name: /목소리 이름/ }), { target: { value: "새 이름" } });
    fireEvent.click(screen.getByRole("button", { name: "저장" }));

    await waitFor(() => expect(rename).toHaveBeenCalledWith("project-1", "asset_voice_1", "새 이름"));
  });

  it("아직 녹음이 없으면 무엇을 하면 되는지 알려 준다", async () => {
    render(<MyVoicesPage listVoices={async () => []} />);

    expect(await screen.findByText(/편집기 왼쪽 `오디오`|아직 녹음한 목소리가 없어요/)).toBeInTheDocument();
  });

  it("못 읽으면 조용히 비우지 않는다", async () => {
    render(<MyVoicesPage listVoices={async () => { throw new Error("boom"); }} />);

    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});
