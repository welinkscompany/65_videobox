import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ProposalCandidateCard } from "./ProposalCandidateCard";

describe("ProposalCandidateCard", () => {
  it("renders an operator copyright warning for an unknown-rights candidate", () => {
    render(<ProposalCandidateCard candidate={{ candidate_id: "candidate-1", visible_reference_code: "P01-B-01", media_type: "broll", asset_id: "asset-1", library_asset_id: null, reason_chips: ["office"], scores: {}, availability: "available", review_status: "approved", preview_uri: null, controls: {}, expected_content_sha256: "sha", media_revision: "1", canonical_metadata: {}, license_policy: "unknown_user_owned", warning_provenance: ["copyright_confirmation_required"] }} selected onToggle={vi.fn()} />);

    expect(screen.getByRole("alert")).toHaveTextContent(/저작권 확인 필요/);
  });
});
