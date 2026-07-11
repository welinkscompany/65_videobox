import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";

import { ProjectOnboarding } from "./ProjectOnboarding";

describe("ProjectOnboarding", () => {
  it("creates an empty-workspace project and registers narration plus script from local paths", async () => {
    const onProjectCreated = vi.fn();
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === "/api/projects") {
        return new Response(
          JSON.stringify({
            project_id: "project_new",
            name: "신규 유튜브 영상",
            status: "active",
            root_storage_uri: "local://projects/project_new",
          }),
          { status: 201 },
        );
      }
      if (url.endsWith("/assets/narration-audio") || url.endsWith("/assets/script-document")) {
        return new Response(JSON.stringify({ asset_id: "asset_001", asset_type: "source", storage_uri: "local://x" }), {
          status: 201,
        });
      }
      throw new Error(`Unexpected request: ${url} ${init?.method ?? "GET"}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<ProjectOnboarding onProjectCreated={onProjectCreated} />);

    fireEvent.change(screen.getByLabelText("프로젝트 이름"), { target: { value: "신규 유튜브 영상" } });
    fireEvent.change(screen.getByLabelText("나레이션 로컬 경로"), { target: { value: "D:\\input\\narration.wav" } });
    fireEvent.change(screen.getByLabelText("스크립트 로컬 경로"), { target: { value: "D:\\input\\script.txt" } });
    fireEvent.click(screen.getByRole("button", { name: "프로젝트 만들고 소스 등록" }));

    await waitFor(() => expect(onProjectCreated).toHaveBeenCalledWith(expect.objectContaining({ project_id: "project_new" })));
    expect(fetchMock).toHaveBeenCalledWith("/api/projects", expect.objectContaining({ method: "POST" }));
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/projects/project_new/assets/narration-audio",
      expect.objectContaining({ method: "POST" }),
    );
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/projects/project_new/assets/script-document",
      expect.objectContaining({ method: "POST" }),
    );
    expect(screen.getByText("나레이션 등록 완료")).toBeInTheDocument();
    expect(screen.getByText("스크립트 등록 완료")).toBeInTheDocument();
  });

  it("keeps the created project and retries only the failed narration ingest", async () => {
    const onProjectCreated = vi.fn();
    let narrationAttempts = 0;
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/api/projects") {
        return new Response(JSON.stringify({
          project_id: "project_retry",
          name: "복구 가능한 첫 영상",
          status: "active",
          root_storage_uri: "local://projects/project_retry",
        }), { status: 201 });
      }
      if (url.endsWith("/assets/narration-audio")) {
        narrationAttempts += 1;
        if (narrationAttempts === 1) {
          return new Response(JSON.stringify({ detail: "나레이션 파일을 찾을 수 없습니다." }), { status: 422 });
        }
        return new Response(JSON.stringify({ asset_id: "narration_ok" }), { status: 201 });
      }
      if (url.endsWith("/assets/script-document")) {
        return new Response(JSON.stringify({ asset_id: "script_ok" }), { status: 201 });
      }
      throw new Error(`Unexpected request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<ProjectOnboarding onProjectCreated={onProjectCreated} />);

    fireEvent.change(screen.getByLabelText("프로젝트 이름"), { target: { value: "복구 가능한 첫 영상" } });
    fireEvent.change(screen.getByLabelText("나레이션 로컬 경로"), { target: { value: "D:\\missing.wav" } });
    fireEvent.change(screen.getByLabelText("스크립트 로컬 경로"), { target: { value: "D:\\script.txt" } });
    fireEvent.click(screen.getByRole("button", { name: "프로젝트 만들고 소스 등록" }));

    expect(await screen.findByText("스크립트 등록 완료")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "나레이션 다시 등록" })).toBeInTheDocument();
    expect(onProjectCreated).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole("button", { name: "나레이션 다시 등록" }));

    expect(await screen.findByText("나레이션 등록 완료")).toBeInTheDocument();
    expect(narrationAttempts).toBe(2);
    expect(onProjectCreated).toHaveBeenCalledTimes(1);
  });
});
