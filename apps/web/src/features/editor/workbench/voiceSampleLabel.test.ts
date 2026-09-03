/**
 * 같은 목소리가 설정 화면과 편집 화면에서 **다른 이름으로 보이면 안 된다.**
 * 채널이 여럿이면 목소리도 여럿이라, 이름이 어긋나면 고를 수가 없다.
 */
import { describe, expect, it } from "vitest";

import { voiceSampleLabel } from "./voiceSampleLabel";

const asset = (extra: Record<string, unknown> = {}) => ({
  asset_id: "asset_one",
  asset_type: "voice_sample_audio",
  storage_uri: "local://voice/6a1f2c3d4e5f60718293-내레이션.wav",
  ...extra,
});

describe("편집 화면 목소리 이름", () => {
  it("창작자가 붙인 이름이 파일 이름보다 먼저다", () => {
    expect(voiceSampleLabel(asset({ metadata: { display_name: "노마드루이스 목소리" } }), 0))
      .toBe("노마드루이스 목소리");
  });

  it("붙인 이름이 비어 있으면 파일 이름으로 돌아간다", () => {
    expect(voiceSampleLabel(asset({ metadata: { display_name: "   " } }), 0)).toBe("내레이션");
    expect(voiceSampleLabel(asset(), 0)).toBe("내레이션");
  });

  it("알아볼 이름이 없으면 번호를 붙인 사람 말로 부른다", () => {
    expect(voiceSampleLabel({ ...asset(), storage_uri: "local://voice/a1.wav" }, 2))
      .toBe("내 목소리 3");
  });
});
