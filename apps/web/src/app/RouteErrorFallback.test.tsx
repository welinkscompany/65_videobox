import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { RouteErrorFallback } from "./RouteErrorFallback";
import { createAppRouter } from "./AppRouter";

describe("라우트 오류 화면", () => {
  it("영어 대신 한국어로 말하고 다시 그리기를 준다 (2026-10-08 §3-6 React #185)", () => {
    const reset = vi.fn();
    render(<RouteErrorFallback error={new Error("Minified React error #185")} reset={reset} />);
    expect(screen.getByRole("heading", { name: "화면을 그리다 멈췄어요" })).toBeVisible();
    expect(screen.queryByText(/Something went wrong|Show Error/)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "다시 그리기" }));
    expect(reset).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("link", { name: "프로젝트 목록으로" })).toHaveAttribute("href", "/projects");
  });
  it("라우터 기본 오류 화면으로 걸려 있다", () => {
    expect(createAppRouter().options.defaultErrorComponent).toBe(RouteErrorFallback);
  });
});
