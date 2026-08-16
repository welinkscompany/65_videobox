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
