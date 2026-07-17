export type DeploymentCapabilities = {
  aiExecution: "disabled" | "local" | "managed";
  account: boolean;
  team: boolean;
  billing: boolean;
};

export const localDeploymentCapabilities: DeploymentCapabilities = {
  aiExecution: "local", account: false, team: false, billing: false,
};
