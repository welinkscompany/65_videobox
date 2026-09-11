import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

import { VariantOutputCard } from "./VariantOutputCard";

afterEach(() => {
  cleanup();
});

// task-2-brief.md: 가로·세로 변형본은 만들고 재생까지 되는데 "가져가는 마지막
// 한 줄"이 없어서 owner가 만든 파일을 화면 밖으로 꺼낼 수 없었다. 같은 화면의
// `완성본 영상 내려받기`/`SRT 자막 파일 내려받기`와 같은 모양(`<a download>`)을
// 기대한다.
describe("VariantOutputCard", () => {
  it("성공한 변형본은 파일로 내려받을 수 있다", () => {
    render(
      <VariantOutputCard
        projectId="project_a"
        item={{ variant_id: "vertical", variant_kind: "vertical_full", job_id: "job-1", status: "succeeded" }}
        onRetry={() => {}}
      />,
    );
    const link = screen.getByRole("link", { name: "세로 영상 내려받기" });
    expect(link).toHaveAttribute("href", "/api/projects/project_a/final-renders/job-1/content");
    // href만 보면 `download` 속성이 빠져도 시험이 통과할 수 있다(OutputsPage.test.tsx의
    // 완성본 시험이 이미 같은 함정을 짚었다) -- 그냥 이동 링크가 되는 것과
    // 파일로 내려받는 것은 다른 동작이라 둘 다 확인한다.
    expect(link).toHaveAttribute("download");
  });

  // 변형 탐침: 세 종류(가로·세로 전체·세로 하이라이트) 모두 자기 이름으로
  // 내려받기 문이 나오는지 확인한다. 한 종류만 확인하면 label 분기를
  // 잘못 짜도(예: 모두 같은 문구) 안 잡힌다.
  it.each([
    ["horizontal", "가로 영상"],
    ["vertical_full", "세로 영상"],
    ["vertical_highlight", "세로 하이라이트"],
  ] as const)("변형 종류(%s)마다 자기 이름으로 내려받는다", (kind, label) => {
    render(
      <VariantOutputCard
        projectId="project_a"
        item={{ variant_id: kind, variant_kind: kind, job_id: `job-${kind}`, status: "succeeded" }}
        onRetry={() => {}}
      />,
    );
    const link = screen.getByRole("link", { name: `${label} 내려받기` });
    expect(link).toHaveAttribute("href", `/api/projects/project_a/final-renders/job-${kind}/content`);
    expect(link).toHaveAttribute("download");
  });

  it("아직 완성되지 않은 변형본은 내려받기 문이 없다", () => {
    render(
      <VariantOutputCard
        projectId="project_a"
        item={{ variant_id: "vertical", variant_kind: "vertical_full", status: "running" }}
        onRetry={() => {}}
      />,
    );
    expect(screen.queryByRole("link", { name: /내려받기/ })).not.toBeInTheDocument();
  });
});
