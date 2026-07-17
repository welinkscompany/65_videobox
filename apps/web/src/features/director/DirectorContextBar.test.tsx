import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { DirectorContextBar } from "./DirectorContextBar";

describe("DirectorContextBar user copy", () => {
  it("does not expose an internal revision prop to the operator", () => {
    render(<DirectorContextBar revision={`revision ${1}`} />);

    expect(screen.queryByText(/revision/i)).not.toBeInTheDocument();
  });
});
