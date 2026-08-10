import { describe, expect, it } from "vitest";

import {
  assetPreferenceChoice,
  canonicalPreferenceTag,
  emptyDirectorPreferences,
  normalizeDirectorPreferences,
  withAssetPreferenceChoice,
  withPreferenceMember,
} from "./directorPreferences";

describe("추천 취향 병합", () => {
  it("한 목록을 바꿔도 나머지 세 목록을 그대로 실어 보낸다", () => {
    // 서버는 요청에 실린 키의 목록을 통째로 갈아끼운다. 방금 누른 값 하나만
    // 보내면 앞서 빼 둔 자산이 조용히 되살아난다.
    const saved = normalizeDirectorPreferences({
      pin_asset: ["asset-pinned"],
      exclude_asset: ["asset-old"],
      exclude_creator: ["Tozan"],
      exclude_tag: ["시끄러운"],
    });

    const next = withPreferenceMember(saved, "exclude_asset", "asset-new", true);

    expect(next.exclude_asset).toEqual(["asset-old", "asset-new"]);
    expect(next.pin_asset).toEqual(["asset-pinned"]);
    expect(next.exclude_creator).toEqual(["Tozan"]);
    expect(next.exclude_tag).toEqual(["시끄러운"]);
  });

  it("빠진 키를 빈 목록으로 채운다", () => {
    // 저장된 적이 없는 프로젝트는 키가 통째로 빠져 온다. 그대로 두면 다음
    // 저장에서 그 목록이 요청에 실리지 않고 화면과 저장된 것이 어긋난다.
    expect(normalizeDirectorPreferences({ pin_asset: ["asset-a"] })).toEqual({
      pin_asset: ["asset-a"],
      exclude_asset: [],
      exclude_creator: [],
      exclude_tag: [],
    });
    expect(normalizeDirectorPreferences(null)).toEqual(emptyDirectorPreferences());
  });

  it("같은 값을 두 번 넣지 않고 빈 값은 무시한다", () => {
    const once = withPreferenceMember(emptyDirectorPreferences(), "pin_asset", "asset-a", true);
    const twice = withPreferenceMember(once, "pin_asset", "asset-a", true);

    expect(twice.pin_asset).toEqual(["asset-a"]);
    expect(withPreferenceMember(twice, "pin_asset", "  ", true).pin_asset).toEqual(["asset-a"]);
  });

  it("항상 쓰기와 쓰지 않기는 같이 서지 않는다", () => {
    // 둘이 함께 저장되면 백엔드는 후보에서 빼 버린다 -- owner가 고른 것과
    // 다른 결과가 나오고 화면은 그 이유를 설명할 수 없다.
    const pinned = withAssetPreferenceChoice(emptyDirectorPreferences(), "asset-a", "always");
    const excluded = withAssetPreferenceChoice(pinned, "asset-a", "never");

    expect(pinned.pin_asset).toEqual(["asset-a"]);
    expect(excluded.pin_asset).toEqual([]);
    expect(excluded.exclude_asset).toEqual(["asset-a"]);
    expect(assetPreferenceChoice(excluded, "asset-a")).toBe("never");
    expect(assetPreferenceChoice(withAssetPreferenceChoice(excluded, "asset-a", "none"), "asset-a"))
      .toBe("none");
  });

  it("태그는 비교되는 모양 그대로 저장한다", () => {
    // 자산의 태그는 비교 전에 소문자로 내려간다. 대문자로 저장하면 owner는
    // 뺐다고 보는데 후보에는 계속 남는다.
    expect(canonicalPreferenceTag("  Calm  ")).toBe("calm");
    expect(canonicalPreferenceTag("밝은")).toBe("밝은");
  });
});
