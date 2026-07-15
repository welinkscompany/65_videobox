import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MediaReferenceBadge } from "./MediaReferenceBadge";

describe("MediaReferenceBadge", () => {
  it("proposal과 timeline reference를 접근 가능한 한국어 label로 구분한다", () => {
    const { rerender } = render(<MediaReferenceBadge code="P12-B-03" kind="proposal" />);
    expect(screen.getByLabelText("제안 12의 비롤 후보 3번")).toBeVisible();

    rerender(<MediaReferenceBadge code="B-03" kind="timeline" />);
    expect(screen.getByLabelText("타임라인 비롤 배치 3번")).toBeVisible();
  });
});
