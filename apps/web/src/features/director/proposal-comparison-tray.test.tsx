import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { DirectorProposal } from "../../api";
import { ProposalComparisonTray } from "./ProposalComparisonTray";

const base = { proposal_id: "p", revision_code: "P1", revision: 1, base_session_revision: 1, asset_index_revision: 1, source_session_id: "s", target_segment_ids: [], source_script_segment_ids: [], status: "ready", diff: {}, expires_at: null };
const candidate = { candidate_id: "c", visible_reference_code: "P1-B-01", media_type: "broll", asset_id: "a", library_asset_id: null, reason_chips: [], scores: {}, availability: "available", review_status: "verified", preview_uri: null, controls: {}, expected_content_sha256: null, media_revision: "1", canonical_metadata: {}, license_policy: "ok", warning_provenance: [] };
describe("ProposalComparisonTray", () => {
  it("후보가 부족할 때만 비교 불가 안내를 보인다", () => {
    const one = { ...base, candidates: [candidate] } satisfies DirectorProposal;
    const view = render(<ProposalComparisonTray proposal={one} selectedIds={["c"]} preflight={{ status: "ready", diff: {} }} />);
    expect(screen.getByText(/비교할 후보가 부족/)).toBeVisible();
    view.rerender(<ProposalComparisonTray proposal={{ ...base, candidates: [candidate, { ...candidate, candidate_id: "c2" }] }} selectedIds={["c"]} preflight={{ status: "ready", diff: {} }} />);
    expect(screen.queryByText(/비교할 후보가 부족/)).not.toBeInTheDocument();
  });
});
