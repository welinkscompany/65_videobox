import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ProposalCandidateCard } from "./ProposalCandidateCard";

describe("ProposalCandidateCard", () => {
  it("추천 상태와 권리 정보를 사용자 언어로 표시한다", () => {
    render(<ProposalCandidateCard candidate={{ candidate_id: "candidate-1", visible_reference_code: "P01-B-01", media_type: "broll", asset_id: "asset-1", library_asset_id: null, reason_chips: [], scores: {}, availability: "available", review_status: "approved", preview_uri: null, controls: {}, expected_content_sha256: "sha", media_revision: "1", canonical_metadata: {}, license_policy: "unknown_user_owned", warning_provenance: [] }} selected onToggle={vi.fn()} />);

    expect(screen.getByText("사용할 수 있어요 · 권리 확인 필요 · 확인됨")).toBeVisible();
    expect(screen.queryByText(/available|unknown_user_owned|approved/i)).not.toBeInTheDocument();
  });

  it("추천 이유의 내부 태그를 노출하지 않고 짧은 안내로 표시한다", () => {
    render(<ProposalCandidateCard candidate={{ candidate_id: "candidate-1", visible_reference_code: "P01-B-01", media_type: "broll", asset_id: "asset-1", library_asset_id: null, reason_chips: ["metadata:creator=internal", "raw_tag_42"], scores: {}, availability: "available", review_status: "approved", preview_uri: null, controls: {}, expected_content_sha256: "sha", media_revision: "1", canonical_metadata: {}, license_policy: "verified", warning_provenance: [] }} selected onToggle={vi.fn()} />);

    expect(screen.getByText("장면에 어울리는 추천이에요.")).toBeVisible();
    expect(screen.queryByText(/metadata:creator=internal|raw_tag_42/i)).not.toBeInTheDocument();
  });

  it.each(["PR-1-B-01", "PR-B-01"])("keeps the raw reference %s out of accessible names", (visibleReferenceCode) => {
    render(<ProposalCandidateCard candidate={{ candidate_id: "candidate-1", visible_reference_code: visibleReferenceCode, media_type: "broll", asset_id: "asset-1", library_asset_id: null, reason_chips: [], scores: {}, availability: "available", review_status: "approved", preview_uri: null, controls: {}, expected_content_sha256: "sha", media_revision: "1", canonical_metadata: {}, license_policy: "verified", warning_provenance: [] }} selected={false} onToggle={vi.fn()} />);

    expect(screen.getByRole("article", { name: /유진 추천/i })).toBeVisible();
    expect(screen.getByRole("checkbox", { name: /유진 추천/i })).toBeVisible();
    expect(screen.queryByRole("article", { name: visibleReferenceCode })).not.toBeInTheDocument();
    expect(screen.queryByRole("checkbox", { name: visibleReferenceCode })).not.toBeInTheDocument();
  });

  it("distinguishes non-numbered proposal references without exposing raw codes", () => {
    const candidate = (candidateId: string, visibleReferenceCode: string) => ({ candidate_id: candidateId, visible_reference_code: visibleReferenceCode, media_type: "broll" as const, asset_id: candidateId, library_asset_id: null, reason_chips: [], scores: {}, availability: "available", review_status: "approved", preview_uri: null, controls: {}, expected_content_sha256: "sha", media_revision: "1", canonical_metadata: {}, license_policy: "verified", warning_provenance: [] });
    render(<><ProposalCandidateCard candidate={candidate("candidate-b", "PR-B-01")} selected={false} onToggle={vi.fn()} /><ProposalCandidateCard candidate={candidate("candidate-m", "PR-M-01")} selected={false} onToggle={vi.fn()} /></>);

    expect(screen.getByRole("checkbox", { name: "유진 추천의 비롤 1번 고르기" })).toBeVisible();
    expect(screen.getByRole("checkbox", { name: "유진 추천의 배경음악 1번 고르기" })).toBeVisible();
    expect(screen.queryByText("PR-B-01")).not.toBeInTheDocument();
    expect(screen.queryByText("PR-M-01")).not.toBeInTheDocument();
  });

  it("renders an operator copyright warning for an unknown-rights candidate", () => {
    render(<ProposalCandidateCard candidate={{ candidate_id: "candidate-1", visible_reference_code: "P01-B-01", media_type: "broll", asset_id: "asset-1", library_asset_id: null, reason_chips: ["office"], scores: {}, availability: "available", review_status: "approved", preview_uri: null, controls: {}, expected_content_sha256: "sha", media_revision: "1", canonical_metadata: {}, license_policy: "unknown_user_owned", warning_provenance: ["copyright_confirmation_required"] }} selected onToggle={vi.fn()} />);

    expect(screen.getByRole("alert")).toHaveTextContent("사용하기 전에 이 미디어를 쓸 권리가 있는지 확인해 주세요.");
  });
});
