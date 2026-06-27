import { render, screen } from "@testing-library/react";

import { App } from "./App";

describe("App", () => {
  it("shows the VideoBox review dashboard heading", () => {
    render(<App />);

    expect(
      screen.getByRole("heading", { name: /videobox review dashboard/i }),
    ).toBeInTheDocument();
  });
});
