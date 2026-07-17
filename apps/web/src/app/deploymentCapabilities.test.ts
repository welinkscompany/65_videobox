import { describe, expect, it } from "vitest";

import { localDeploymentCapabilities } from "./deploymentCapabilities";

describe("localDeploymentCapabilities", () => {
  it("keeps execution local or disabled and never advertises account billing features", () => {
    expect(localDeploymentCapabilities).toMatchObject({
      aiExecution: "local",
      account: false,
      team: false,
      billing: false,
    });
  });
});
