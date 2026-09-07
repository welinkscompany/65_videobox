import { describe, expect, it } from "vitest"
import { assetDurationLabel } from "./assetDurationLabel"
import type { LibraryAsset } from "../../api"

function asset(overrides: Partial<LibraryAsset> = {}): LibraryAsset {
  return {
    library_asset_id: "user_1",
    media_type: "broll",
    origin: "user",
    lifecycle: "ready",
    ...overrides,
  } as LibraryAsset
}

describe("library asset duration label", () => {
  it("shows the duration when the asset carries one", () => {
    expect(assetDurationLabel(asset({ duration_seconds: 24 }))).toBe("24초")
    expect(assetDurationLabel(asset({ technical_metadata: { duration_seconds: 4 } }))).toBe("4초")
  })

  it("prefers the top-level duration that builtin pack assets use", () => {
    expect(assetDurationLabel(asset({ duration_seconds: 192, technical_metadata: {} }))).toBe("192초")
  })

  it("says it is still checking only while the asset is actually being analysed", () => {
    expect(assetDurationLabel(asset({ lifecycle: "processing" }))).toBe("길이 확인 중")
  })

  it("does not claim to be checking when nothing is analysing the asset", () => {
    // Four pre-probe rows sat at "길이 확인 중" forever because the label ignored
    // lifecycle; a ready asset with no duration is simply unknown.
    expect(assetDurationLabel(asset({ lifecycle: "ready" }))).toBe("길이 정보 없음")
    expect(assetDurationLabel(asset({ lifecycle: "needs_attention" }))).toBe("길이 정보 없음")
  })

  it("ignores a non-finite duration rather than rendering it", () => {
    expect(assetDurationLabel(asset({ duration_seconds: Number.NaN }))).toBe("길이 정보 없음")
  })
})
