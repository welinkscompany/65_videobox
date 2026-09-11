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

  // task-3-brief.md: 실패 이유를 서버 코드 그대로("사유:
  // final_output_requires_review_approval") 찍으면 owner가 할 수 있는 일이
  // 없다. `OutputsPage.tsx`가 이미 쓰는 한국어 할 일 표를 나눠 써서 같은
  // 문장이 나와야 한다 -- 표를 두 번째로 만들면 문구가 갈라진다.
  it("실패한 변형본은 알려진 코드를 owner가 할 수 있는 일로 보여준다", () => {
    render(
      <VariantOutputCard
        projectId="project_a"
        item={{ variant_id: "vertical", variant_kind: "vertical_full", status: "failed", error_code: "final_output_requires_review_approval" }}
        onRetry={() => {}}
      />,
    );
    const status = screen.getByRole("status");
    expect(status).toHaveTextContent("검토");
    expect(status).not.toHaveTextContent("final_output_requires_review_approval");
  });

  // 엔진은 파일 경로가 섞인 예외를 코드 셋으로 바꿔서 보낸다
  // (`packages/core-engine/src/videobox_core_engine/job_error_message.py`의
  // `safe_job_error_message` -- `asset_file_missing`,
  // `asset_file_permission_denied`, `external_command_failed` 셋이 전부다).
  // 그 셋이 표에 없어서 "이 출력을 만들지 못했어요."로 뭉개졌고, 정작
  // owner가 할 일(파일 확인 등)이 화면에서 사라졌다. 예전에는 이 실패가
  // 통째로 `renderer_failed`로 찍혀서 적어도 "다시 만들어 주세요"는
  // 있었으니, 이건 되돌아간 것이다.
  it.each([
    "asset_file_missing",
    "asset_file_permission_denied",
    "external_command_failed",
  ])("엔진이 안전 문구로 바꿔 보내는 실패 사유(%s)도 다음에 할 일을 말한다", (code) => {
    render(
      <VariantOutputCard
        projectId="project_a"
        item={{ variant_id: "vertical", variant_kind: "vertical_full", status: "failed", error_code: code }}
        onRetry={() => {}}
      />,
    );
    const status = screen.getByRole("status");
    expect(status).not.toHaveTextContent(code);
    // 뭉개진 한 줄로 떨어지면 다음에 할 일이 없다.
    expect(status.textContent?.trim()).not.toBe("이 출력을 만들지 못했어요.");
    expect(status.textContent ?? "").toMatch(/확인|다시/);
  });

  // 표에 없는 코드가 와도 코드를 그대로 찍지 않는다(옛 결함 재현 금지) --
  // 동시에 아무 말도 안 하는 것도 아니다. 표가 이미 쓰는 방식(일반화된
  // 안내 문장)을 그대로 따른다.
  it("표에 없는 실패 코드는 코드를 그대로 보여주지 않고 안내 문장으로 대신한다", () => {
    render(
      <VariantOutputCard
        projectId="project_a"
        item={{ variant_id: "vertical", variant_kind: "vertical_full", status: "failed", error_code: "some_never_seen_engine_code" }}
        onRetry={() => {}}
      />,
    );
    const status = screen.getByRole("status");
    expect(status).not.toHaveTextContent("some_never_seen_engine_code");
    expect(status.textContent?.trim()).not.toBe("");
  });
});
