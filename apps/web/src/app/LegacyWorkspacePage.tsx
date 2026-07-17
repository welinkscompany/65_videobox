/**
 * The legacy workspace remains isolated while the route layer owns the active
 * project and section. Keeping this alias lets later slices move the body
 * without changing the route contract.
 */
export { App as LegacyWorkspacePage } from "../App";
export type { LegacyWorkspacePageProps } from "../App";
