import { describe, expect, it } from "vitest";
import { candidateIdsForScope } from "./director-apply-scope";

const candidates = [
  { candidate_id: "b-1", media_type: "broll" }, { candidate_id: "m-1", media_type: "bgm" },
  { candidate_id: "b-2", media_type: "broll" }, { candidate_id: "s-1", media_type: "sfx" },
] as const;

describe("candidateIdsForScope", () => {
  it("maps API-named selected_references, broll_only, and all scopes deterministically in proposal order", () => {
    expect(candidateIdsForScope("selected_references", ["b-2", "b-1"], candidates)).toEqual(["b-1", "b-2"]);
    expect(candidateIdsForScope("broll_only", ["m-1"], candidates)).toEqual(["b-1", "b-2"]);
    expect(candidateIdsForScope("all", ["b-1"], candidates)).toEqual(["b-1", "m-1", "b-2", "s-1"]);
  });
});
