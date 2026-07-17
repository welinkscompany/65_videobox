import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MediaReferenceBadge } from "./MediaReferenceBadge";

describe("MediaReferenceBadge", () => {
  it("proposal과 timeline reference를 접근 가능한 한국어 label로 구분한다", () => {
    const { rerender } = render(<MediaReferenceBadge code="P12-B-03" kind="proposal" />);
    expect(screen.getByLabelText("루미 추천 12의 비롤 3번")).toBeVisible();
    expect(screen.queryByText("P12-B-03")).not.toBeInTheDocument();

    rerender(<MediaReferenceBadge code="B-03" kind="timeline" />);
    expect(screen.getByLabelText("편집 순서의 비롤 3번")).toBeVisible();

    rerender(<MediaReferenceBadge code="PR-1-B-01" kind="proposal" />);
    expect(screen.getByLabelText("루미 추천 1의 비롤 1번")).toBeVisible();
    expect(screen.queryByText("PR-1-B-01")).not.toBeInTheDocument();

    rerender(<MediaReferenceBadge code="PR-B-01" kind="proposal" />);
    expect(screen.getByLabelText("루미 추천의 비롤 1번")).toBeVisible();
    expect(screen.queryByText("PR-B-01")).not.toBeInTheDocument();
  });
});
