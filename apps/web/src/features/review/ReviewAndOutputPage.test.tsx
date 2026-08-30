import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { api } from "../../api";
import { ReviewAndOutputPage } from "./ReviewAndOutputPage";

beforeEach(() => {
  vi.spyOn(api, "getLatestEditingSession").mockResolvedValue(null);
  vi.spyOn(api, "listJobs").mockResolvedValue([]);
  vi.spyOn(api, "getCapcutHandoffDiagnostics").mockResolvedValue(null as never);
  vi.spyOn(api, "listOutputVariants").mockResolvedValue({ variants: [] } as never);
});

afterEach(() => vi.restoreAllMocks());

it("asks for the shared editing state once, not once per half of the screen", async () => {
  // 두 영역을 그냥 나란히 놓으면 같은 것을 두 번 묻는다. 요청이 두 배가 될 뿐
  // 아니라 두 영역이 서로 다른 시점의 사실을 볼 수 있다.
  render(<ReviewAndOutputPage projectId="project-a" onOpenEditor={() => {}} />);

  await waitFor(() => expect(api.listJobs).toHaveBeenCalled());
  await waitFor(() => expect(screen.getByTestId("review-and-output-page")).toBeInTheDocument());

  expect(api.listJobs).toHaveBeenCalledTimes(1);
  expect(api.getLatestEditingSession).toHaveBeenCalledTimes(1);
});

it("shows both halves on one screen", async () => {
  render(<ReviewAndOutputPage projectId="project-a" onOpenEditor={() => {}} />);

  // 편집본이 없으면 검토는 안내로, 출력은 자기 상태로 각각 응답한다.
  await waitFor(() => expect(screen.getByText("먼저 편집할 초안을 만들어 주세요.")).toBeVisible());
  await waitFor(() => expect(screen.getByTestId("outputs-page")).toBeInTheDocument());
});

it("asks CapCut for handoff status once per screen, not once per re-sync", async () => {
  // 실측(2026-08-30, 브라우저 네트워크 로그): 한 화면을 여는 동안
  // `/api/capcut/handoff-diagnostics`가 두 번 나갔다. 출력 쪽 effect가
  // `shared`가 채워질 때 다시 도는 것 자체는 의도(주석 참고)이지만, 그때
  // CapCut 상태까지 다시 물을 이유는 없다 -- 검토 쪽 승인 여부와 CapCut
  // 상태는 서로 무관하다.
  render(<ReviewAndOutputPage projectId="project-a" onOpenEditor={() => {}} />);

  await waitFor(() => expect(screen.getByTestId("outputs-page")).toBeInTheDocument());
  await waitFor(() => expect(api.listJobs).toHaveBeenCalled());

  expect(api.getCapcutHandoffDiagnostics).toHaveBeenCalledTimes(1);
});

it("has exactly one page-level heading, not one per half", async () => {
  // 실측(2026-08-30, 브라우저): 두 절반이 각자 <h1>을 내서 화면 하나에
  // <h1>이 둘이었다("영상 검토" · "완성본과 CapCut 초안") -- 스크린리더가
  // 헤딩으로 훑을 때 페이지의 최상위 제목이 무엇인지 알 수 없게 만든다.
  render(<ReviewAndOutputPage projectId="project-a" onOpenEditor={() => {}} />);

  await waitFor(() => expect(screen.getByTestId("outputs-page")).toBeInTheDocument());

  expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
});
