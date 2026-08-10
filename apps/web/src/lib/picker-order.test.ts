import { describe, expect, it } from "vitest";

import { orderByFavouriteThenRecent } from "./pickerOrder";

const items = ["a", "b", "c", "d"].map((id) => ({ id }));
const byId = (item: { id: string }) => item.id;
const alphabetical = (left: { id: string }, right: { id: string }) => left.id.localeCompare(right.id);

describe("고르는 목록의 순서", () => {
  it("즐겨찾기 먼저, 그다음 최근에 쓴 순서로 둔다", () => {
    // 저장소는 최근 쓴 것을 이미 기록하고 있었는데 어느 화면도 다시 읽지
    // 않아서, 방금 쓴 것을 다음에도 아래에서 찾아 내려가야 했다.
    const ordered = orderByFavouriteThenRecent(items, byId, ["c"], ["d", "b"], alphabetical);

    expect(ordered.map(byId)).toEqual(["c", "d", "b", "a"]);
  });

  it("즐겨찾기가 최근 목록에도 있으면 즐겨찾기 자리를 지킨다", () => {
    // 한 번 담아 둔 것을 다시 내려보내면 담아 둔 뜻이 없어진다.
    const ordered = orderByFavouriteThenRecent(items, byId, ["a"], ["b", "a"], alphabetical);

    expect(ordered.map(byId)).toEqual(["a", "b", "c", "d"]);
  });

  it("최근 목록이 없으면 예전 순서 그대로 둔다", () => {
    const ordered = orderByFavouriteThenRecent(items, byId, ["d"], [], alphabetical);

    expect(ordered.map(byId)).toEqual(["d", "a", "b", "c"]);
  });

  it("원래 목록을 뒤집어 두지 않는다", () => {
    const original = [...items];
    orderByFavouriteThenRecent(items, byId, ["d"], ["c"], alphabetical);

    expect(items).toEqual(original);
  });
});
