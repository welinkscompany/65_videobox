import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render } from "@testing-library/react";

vi.mock("./AppRouter", () => ({ AppRouter: () => <main>화면</main> }));

import { AppRoot } from "./AppRoot";

afterEach(cleanup);

vi.stubGlobal("matchMedia", (query: string) => ({ matches: false, media: query, onchange: null, addEventListener: () => {}, removeEventListener: () => {}, addListener: () => {}, removeListener: () => {}, dispatchEvent: () => false }));

describe("AppRoot", () => {
  it("편집 알림이 뜰 자리(Toaster)를 앱 맨 위에 한 번 둔다", () => {
    const { container } = render(<AppRoot />);
    expect(container.querySelectorAll("section[aria-label^='Notifications']")).toHaveLength(1);
  });
});
