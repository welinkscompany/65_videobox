import { describe, expect, it } from "vitest";
import { filterEditorAssets, projectEditorAssets } from "./editorAssetProjection";

describe("editor asset projection", () => {
  it("projects B-roll image metadata and a verified BGM into honest cards", () => {
    const cards = projectEditorAssets({
      projectId: "p",
      brollAssets: [{ asset_id: "image-1", asset_type: "broll_image", storage_uri: "x", created_at: "now", metadata: { title: "제품 사진", duration_seconds: 4, analysis_status: "succeeded", review_required: false } }],
      libraryAssets: [{ library_asset_id: "bgm-1", asset_id: "starter-bgm", media_type: "music", duration_seconds: 12, version: "v1", verified: true, available: true, tags: [], source: "Starter", creator: "Creator", official_license_url: "https://license.invalid", attribution_required: false, attribution_text: "" }],
    });

    expect(cards.map((card) => [card.kind, card.label, card.canApply])).toEqual([["broll", "이미지 B-roll", true], ["bgm", "BGM", true]]);
    expect(cards[0].status).toBe("준비됨 · 검토 불필요");
  });

  it("filters a normalized list by type and query without losing unavailable license truth", () => {
    const cards = projectEditorAssets({ projectId: "p", brollAssets: [], libraryAssets: [{ library_asset_id: "sfx-1", asset_id: "sfx", media_type: "sfx", duration_seconds: 2, version: "v1", verified: false, available: false, tags: ["license"], source: "Starter", creator: "Creator", official_license_url: "", attribution_required: false, attribution_text: "" }] });

    expect(filterEditorAssets(cards, { type: "sfx", query: "license" })).toEqual([expect.objectContaining({ canApply: false, license: "검증 또는 이용 가능 상태 확인 필요" })]);
  });

  it("reports B-roll audio only from explicit metadata and reports supported library audio truthfully", () => {
    const cards = projectEditorAssets({
      projectId: "p",
      brollAssets: [
        { asset_id: "with-audio", asset_type: "broll_video", storage_uri: "x", created_at: "now", metadata: { audio_present: true } },
        { asset_id: "without-audio", asset_type: "broll_image", storage_uri: "x", created_at: "now", metadata: { has_audio: false } },
        { asset_id: "audio-unknown", asset_type: "broll_video", storage_uri: "x", created_at: "now", metadata: {} },
      ],
      libraryAssets: [
        { library_asset_id: "bgm-1", asset_id: "bgm", media_type: "music", duration_seconds: 2, version: "v1", verified: true, available: true, tags: [], source: "Starter", creator: "Creator", official_license_url: "", attribution_required: false, attribution_text: "" },
        { library_asset_id: "sfx-1", asset_id: "sfx", media_type: "sfx", duration_seconds: 2, version: "v1", verified: true, available: true, tags: [], source: "Starter", creator: "Creator", official_license_url: "", attribution_required: false, attribution_text: "" },
      ],
    });

    expect(cards.map((card) => card.audioPresence)).toEqual(["오디오 있음", "오디오 없음", "오디오 정보 확인 중", "오디오 있음", "오디오 있음"]);
  });

  it("projects preview kinds from concrete B-roll types and library media types", () => {
    const cards = projectEditorAssets({
      projectId: "p",
      brollAssets: [
        { asset_id: "image-1", asset_type: "broll_image", storage_uri: "x", created_at: "now", metadata: {} },
        { asset_id: "audio-1", asset_type: "broll_audio", storage_uri: "x", created_at: "now", metadata: {} },
        { asset_id: "video-1", asset_type: "broll_video", storage_uri: "x", created_at: "now", metadata: {} },
        { asset_id: "unknown-1", asset_type: "unrecognized", storage_uri: "x", created_at: "now", metadata: {} },
      ],
      libraryAssets: [{ library_asset_id: "bgm-1", asset_id: "bgm", media_type: "music", duration_seconds: 2, version: "v1", verified: true, available: true, tags: [], source: "Starter", creator: "Creator", official_license_url: "", attribution_required: false, attribution_text: "" }],
    });

    expect(cards.map((card) => card.previewKind)).toEqual(["image", "audio", "video", "video", "audio"]);
  });

  it("keeps unknown B-roll metadata honest and marks review explicitly", () => {
    const [card] = projectEditorAssets({
      projectId: "p",
      brollAssets: [{ asset_id: "other-1", asset_type: "unexpected", storage_uri: "x", created_at: "now", metadata: { title: "   ", duration_seconds: Number.NaN, review_required: true, tags: ["현장"] } }],
      libraryAssets: [],
    });

    expect(card).toMatchObject({
      kind: "broll",
      label: "기타 B-roll",
      title: "B-roll 1",
      durationLabel: "길이 정보 없음",
      status: "확인 중 · 검토 필요",
      canApply: true,
      previewUrl: "/api/projects/p/assets/other-1/content",
    });
    expect(filterEditorAssets([card], { type: "broll", query: "현장" })).toEqual([card]);
  });

  it("preserves B-roll and library identity while projecting review and licence truth", () => {
    const cards = projectEditorAssets({
      projectId: "p",
      brollAssets: [
        { asset_id: "video-1", asset_type: "broll_video", storage_uri: "x", created_at: "now", metadata: { review_required: true } },
        { asset_id: "audio-1", asset_type: "broll_audio", storage_uri: "x", created_at: "now", metadata: { review_required: false } },
        { asset_id: "unknown-1", asset_type: "broll_image", storage_uri: "x", created_at: "now", metadata: {} },
        { asset_id: "unknown-2", asset_type: "broll_image", storage_uri: "x", created_at: "now", metadata: { review_required: "yes" } },
      ],
      libraryAssets: [
        { library_asset_id: "music-1", asset_id: "starter-music", media_type: "music", duration_seconds: 12, version: "v1", verified: true, available: true, tags: [], source: "Starter", creator: "Creator", official_license_url: "https://license.invalid/music", attribution_required: true, attribution_text: "Creator 표기" },
        { library_asset_id: "sfx-unavailable", asset_id: "starter-sfx-unavailable", media_type: "sfx", duration_seconds: 2, version: "v1", verified: true, available: false, tags: [], source: "Starter", creator: "Creator", official_license_url: "", attribution_required: false, attribution_text: "" },
        { library_asset_id: "music-unverified", asset_id: "starter-music-unverified", media_type: "music", duration_seconds: 8, version: "v1", verified: false, available: true, tags: [], source: "Starter", creator: "Creator", official_license_url: "", attribution_required: false, attribution_text: "" },
      ],
    });

    expect(cards.slice(0, 4).map((card) => [card.id, card.label, card.status])).toEqual([
      ["broll:video-1", "영상 B-roll", "확인 중 · 검토 필요"],
      ["broll:audio-1", "오디오 B-roll", "확인 중 · 검토 불필요"],
      ["broll:unknown-1", "이미지 B-roll", "확인 중 · 검토 상태 확인 중"],
      ["broll:unknown-2", "이미지 B-roll", "확인 중 · 검토 상태 확인 중"],
    ]);
    expect(cards.slice(4)).toEqual([
      expect.objectContaining({ id: "library:music-1", assetId: "starter-music", libraryAssetId: "music-1", previewUrl: "/api/media-library/assets/music-1/preview", canApply: true, license: "라이선스: https://license.invalid/music · 출처 표기 필요: Creator 표기" }),
      expect.objectContaining({ id: "library:sfx-unavailable", libraryAssetId: "sfx-unavailable", canApply: false, license: "검증 또는 이용 가능 상태 확인 필요" }),
      expect.objectContaining({ id: "library:music-unverified", libraryAssetId: "music-unverified", canApply: false, license: "검증 또는 이용 가능 상태 확인 필요" }),
    ]);
  });

  it("keeps unavailable library licence truth inspectable without inventing a manual B-roll source", () => {
    const cards = projectEditorAssets({
      projectId: "p",
      brollAssets: [{ asset_id: "local-1", asset_type: "broll_video", storage_uri: "x", created_at: "now", metadata: { tags: ["현장"] } }],
      libraryAssets: [
        { library_asset_id: "unavailable-verified", asset_id: "sfx-1", media_type: "sfx", duration_seconds: 2, version: "v1", verified: true, available: false, tags: [], source: "Starter", creator: "Creator", official_license_url: "https://license.invalid/unavailable", attribution_required: true, attribution_text: "Unavailable Creator 표기" },
        { library_asset_id: "available-unverified", asset_id: "music-1", media_type: "music", duration_seconds: 4, version: "v1", verified: false, available: true, tags: [], source: "Starter", creator: "Creator", official_license_url: "https://license.invalid/unverified", attribution_required: true, attribution_text: "Unverified Creator 표기" },
      ],
    });

    expect(cards[0]).toMatchObject({ license: "프로젝트 로컬 B-roll", sourceMetadata: expect.objectContaining({ source: "프로젝트 로컬 B-roll" }) });
    expect(`${cards[0].license} ${cards[0].sourceMetadata.source}`).not.toContain("manual source");
    expect(cards.slice(1)).toEqual([
      expect.objectContaining({
        canApply: false,
        status: "이용 불가 · 검증됨",
        license: expect.stringContaining("https://license.invalid/unavailable"),
        sourceMetadata: expect.objectContaining({ officialLicenseUrl: "https://license.invalid/unavailable", attributionRequired: true, attributionText: "Unavailable Creator 표기" }),
      }),
      expect.objectContaining({
        canApply: false,
        status: "이용 가능 · 검증 필요",
        license: expect.stringContaining("https://license.invalid/unverified"),
        sourceMetadata: expect.objectContaining({ officialLicenseUrl: "https://license.invalid/unverified", attributionRequired: true, attributionText: "Unverified Creator 표기" }),
      }),
    ]);
    expect(cards[1].license).toContain("출처 표기 필요: Unavailable Creator 표기");
    expect(cards[2].license).toContain("출처 표기 필요: Unverified Creator 표기");
  });
});
