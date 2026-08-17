import { describe, expect, it } from "vitest";

import { ASSET_DRAG_TYPE, carriesAsset, readAssetDrag, writeAssetDrag } from "./assetDragPayload";

function fakeTransfer(initial: Record<string, string> = {}): DataTransfer {
  const store = new Map(Object.entries(initial));
  return {
    effectAllowed: "none",
    get types() { return [...store.keys()]; },
    setData: (type: string, value: string) => { store.set(type, value); },
    getData: (type: string) => store.get(type) ?? "",
  } as unknown as DataTransfer;
}

describe("asset drag payload", () => {
  it("carries the card that was picked up", () => {
    const transfer = fakeTransfer();

    writeAssetDrag(transfer, "card-7");

    expect(readAssetDrag(transfer)).toBe("card-7");
    expect(carriesAsset(transfer)).toBe(true);
  });

  it("does not mistake someone else's drag for ours", () => {
    // 파일 탐색기나 다른 탭에서 끌어온 것. 여기에 커서를 바꾸거나 받으면 거짓말이 된다.
    const foreign = fakeTransfer({ "text/plain": "card-7", "Files": "" });

    expect(readAssetDrag(foreign)).toBeNull();
    expect(carriesAsset(foreign)).toBe(false);
  });

  it("says no rather than guessing when there is nothing to read", () => {
    expect(readAssetDrag(null)).toBeNull();
    expect(carriesAsset(null)).toBe(false);
    expect(readAssetDrag(fakeTransfer({ [ASSET_DRAG_TYPE]: "" }))).toBeNull();
  });
});
