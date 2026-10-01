import { render, screen } from "@testing-library/react";

import { ErrorBoundary } from "./ErrorBoundary";

function BrokenWorkspace(): never {
  throw new Error("timeline payload is invalid");
}

describe("ErrorBoundary", () => {
  it("keeps a recoverable error message on screen when a workspace subtree throws", () => {
    render(
      <ErrorBoundary>
        <BrokenWorkspace />
      </ErrorBoundary>,
    );

    expect(screen.getByRole("alert")).toHaveTextContent("화면을 불러오지 못했어요");
    expect(screen.getByText(/timeline payload is invalid/)).toBeInTheDocument();
  });
});
