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

  it("지우기는 한 번 더 묻고, 그때서야 그 프로젝트로 보낸다", async () => {
    // 목소리는 지우면 파일까지 사라진다(`_store_media_analysis.py`의
    // `delete_asset`은 행을 지우고 `path.unlink()`까지 한다). 휴지통이 없으니
    // 한 번 눌러서 사라지면 안 된다.
    const remove = vi.fn(async () => undefined);
    render(<MyVoicesPage listVoices={async () => [voice()]} deleteVoice={remove} />);

    fireEvent.click(await screen.findByRole("button", { name: /차분한 목소리 지우기/ }));
    expect(remove).not.toHaveBeenCalled();
    expect(screen.getByText(/되돌릴 수 없어요/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /차분한 목소리 정말 지우기/ }));
    await waitFor(() => expect(remove).toHaveBeenCalledWith("project-1", "asset_voice_1"));
  });

  it("그대로 두기를 누르면 안 지운다", async () => {
    const remove = vi.fn(async () => undefined);
    render(<MyVoicesPage listVoices={async () => [voice()]} deleteVoice={remove} />);

    fireEvent.click(await screen.findByRole("button", { name: /차분한 목소리 지우기/ }));
    fireEvent.click(screen.getByRole("button", { name: "그대로 두기" }));

    expect(remove).not.toHaveBeenCalled();
    expect(screen.queryByText(/되돌릴 수 없어요/)).not.toBeInTheDocument();
  });

  it("지운 뒤에는 목록을 다시 읽는다", async () => {
    const remove = vi.fn(async () => undefined);
    const listVoices = vi.fn().mockResolvedValueOnce([voice()]).mockResolvedValue([]);
    render(<MyVoicesPage listVoices={listVoices} deleteVoice={remove} />);

    fireEvent.click(await screen.findByRole("button", { name: /차분한 목소리 지우기/ }));
    fireEvent.click(screen.getByRole("button", { name: /차분한 목소리 정말 지우기/ }));

    expect(await screen.findByText(/아직 녹음한 목소리가 없어요/)).toBeInTheDocument();
    expect(listVoices).toHaveBeenCalledTimes(2);
  });

  it("못 지우면 왜 안 됐는지 말하고 목록을 비우지 않는다", async () => {
    // **조용히 사라지면 안 된다.** 실패했는데 줄이 없어지면 지워진 줄 안다.
    const remove = vi.fn(async () => { throw new Error("boom"); });
    render(<MyVoicesPage listVoices={async () => [voice()]} deleteVoice={remove} />);

    fireEvent.click(await screen.findByRole("button", { name: /차분한 목소리 지우기/ }));
    fireEvent.click(screen.getByRole("button", { name: /차분한 목소리 정말 지우기/ }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/지우지 못했어요/);
    expect(screen.getByText("차분한 목소리")).toBeInTheDocument();
  });
});
