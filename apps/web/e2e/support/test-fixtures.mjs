import { expect, test as base } from "@playwright/test";

import { installBrowserNetworkGate } from "./release-gates.mjs";

export const test = base.extend({
  page: async ({ page }, use) => {
    const gate = await installBrowserNetworkGate(page);
    try {
      await use(page);
      gate.assertNoRemoteRequests();
    } finally {
      await gate.dispose();
    }
  },
});

export { expect };
