import type { ArtifactFreshness, DirectorActionIntent, DirectorMessageExchange, DirectorReference, EditingSessionHistoryEntry } from "../../api";

export type DirectorWorkspaceState = "script_required" | "idle" | "analysis_running" | "proposal_ready" | "applying" | "blocked" | "error";
export type { ArtifactFreshness, DirectorActionIntent, DirectorMessageExchange, DirectorReference, EditingSessionHistoryEntry };
