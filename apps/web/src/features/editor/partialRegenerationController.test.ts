import { describe, expect, it } from "vitest";

import {
  canRestorePartialRegenerationResult,
  canRunPartialRegeneration,
  createPartialRegenerationTicket,
  normalizePartialRegenerationFields,
  preflightMatchesPartialRegenerationTicket,
  runMatchesPartialRegenerationTicket,
} from "./partialRegenerationController";

const scope = {
  projectId: "project-a",
  sessionId: "session-a",
  routeEpoch: 3,
  revision: 11,
  segmentId: "segment-a",
  fields: ["caption", "broll"],
} as const;

describe("partial regeneration controller", () => {
  it("normalizes supported fields into canonical stable order and removes duplicates", () => {
    expect(normalizePartialRegenerationFields([
      " sfx ",
      "caption",
      "visual_overlay",
      "caption",
      "tts_replacement",
      "cut_action",
      "broll",
      "music",
      "sfx",
    ])).toEqual([
      "caption",
      "cut_action",
      "broll",
      "visual_overlay",
      "music",
      "sfx",
      "tts_replacement",
    ]);
  });

  it.each([
    { fields: [] },
    { fields: [""] },
    { fields: ["   "] },
    { fields: ["caption", ""] },
    { fields: ["caption", "explanation_card"] },
    { fields: ["caption", "BROLL"] },
  ])("fails closed for blank or unsupported field selections: $fields", ({ fields }) => {
    expect(normalizePartialRegenerationFields(fields)).toBeNull();
  });

  it("captures an immutable preflight ticket for the exact route and session scope", () => {
    const ticket = createPartialRegenerationTicket({
      ...scope,
      fields: [" broll ", "caption", "broll"],
    });

    expect(ticket).toEqual({
      projectId: "project-a",
      sessionId: "session-a",
      routeEpoch: 3,
      revision: 11,
      segmentId: "segment-a",
      fields: ["caption", "broll"],
    });
    expect(Object.isFrozen(ticket)).toBe(true);
    expect(Object.isFrozen(ticket?.fields)).toBe(true);
  });

  it("does not issue a preflight ticket for invalid identity or field input", () => {
    expect(createPartialRegenerationTicket({ ...scope, projectId: " " })).toBeNull();
    expect(createPartialRegenerationTicket({ ...scope, sessionId: "" })).toBeNull();
    expect(createPartialRegenerationTicket({ ...scope, segmentId: " " })).toBeNull();
    expect(createPartialRegenerationTicket({ ...scope, routeEpoch: -1 })).toBeNull();
    expect(createPartialRegenerationTicket({ ...scope, revision: -1 })).toBeNull();
    expect(createPartialRegenerationTicket({ ...scope, fields: ["caption", "unknown"] })).toBeNull();
  });

  it("allows a run only when every current value exactly matches the ticket", () => {
    const ticket = createPartialRegenerationTicket(scope);
    expect(ticket).not.toBeNull();

    expect(canRunPartialRegeneration(ticket, {
      ...scope,
      fields: [" broll ", "caption", "caption"],
    })).toBe(true);
  });

  it("accepts only preflight and run responses bound to the exact prepared ticket", () => {
    const ticket = createPartialRegenerationTicket(scope)!;
    const response = {
      session_id: "session-a",
      segment_ids: ["segment-a"],
      fields: ["broll", "caption"],
    };

    expect(preflightMatchesPartialRegenerationTicket(ticket, response)).toBe(true);
    expect(runMatchesPartialRegenerationTicket(ticket, {
      ...response,
      status: "succeeded",
      job_id: "job-a",
    })).toBe(true);
  });

  it.each([
    { session_id: "session-b" },
    { segment_ids: ["segment-b"] },
    { segment_ids: ["segment-a", "segment-b"] },
    { fields: ["caption"] },
    { fields: ["caption", "unsupported"] },
  ])("rejects a response whose identity differs from the prepared ticket: %j", (change) => {
    const ticket = createPartialRegenerationTicket(scope)!;
    const response = {
      session_id: "session-a",
      segment_ids: ["segment-a"],
      fields: ["caption", "broll"],
      ...change,
    };
    expect(preflightMatchesPartialRegenerationTicket(ticket, response)).toBe(false);
    expect(runMatchesPartialRegenerationTicket(ticket, {
      ...response,
      status: "succeeded",
      job_id: "job-a",
    })).toBe(false);
  });

  it.each([
    { status: "running" },
    { status: null },
    { job_id: "" },
    { job_id: "   " },
    { job_id: null },
  ])("rejects an incomplete or unsuccessful run response: %j", (change) => {
    const ticket = createPartialRegenerationTicket(scope)!;
    expect(runMatchesPartialRegenerationTicket(ticket, {
      session_id: "session-a",
      segment_ids: ["segment-a"],
      fields: ["caption", "broll"],
      status: "succeeded",
      job_id: "job-a",
      ...change,
    })).toBe(false);
  });

  it.each([
    { projectId: "project-b" },
    { sessionId: "session-b" },
    { routeEpoch: 4 },
    { revision: 12 },
    { segmentId: "segment-b" },
    { fields: ["caption"] },
    { fields: ["caption", "sfx"] },
    { fields: ["caption", "unsupported"] },
    { fields: ["caption", ""] },
  ])("rejects a run when current scope differs or fails field validation: %j", (change) => {
    const ticket = createPartialRegenerationTicket(scope);
    expect(canRunPartialRegeneration(ticket, { ...scope, ...change })).toBe(false);
  });

  it("restores a result only for a succeeded same-session job at the current session timestamp", () => {
    expect(canRestorePartialRegenerationResult(
      {
        sessionId: "session-a",
        sessionUpdatedAt: "2026-07-24T00:00:00Z",
        jobId: "job-a",
        segmentId: "segment-a",
        fields: ["caption", "broll"],
      },
      {
        status: "succeeded",
        session_id: "session-a",
        job_id: "job-a",
        session_updated_at: "2026-07-24T00:00:00Z",
        segment_ids: ["segment-a"],
        fields: ["broll", "caption"],
      },
    )).toBe(true);
  });

  it.each([
    { status: "running" },
    { status: "SUCCEEDED" },
    { session_id: "session-b" },
    { session_id: "" },
    { job_id: "job-b" },
    { job_id: "" },
    { job_id: "   " },
    { session_updated_at: "2026-07-24T00:00:01Z" },
    { session_updated_at: "" },
    { session_updated_at: null },
    { segment_ids: ["segment-b"] },
    { segment_ids: ["segment-a", "segment-b"] },
    { fields: ["caption"] },
    { fields: ["caption", "unsupported"] },
  ])("fails closed when a resume result is not current and complete: %j", (change) => {
    expect(canRestorePartialRegenerationResult(
      {
        sessionId: "session-a",
        sessionUpdatedAt: "2026-07-24T00:00:00Z",
        jobId: "job-a",
        segmentId: "segment-a",
        fields: ["caption", "broll"],
      },
      {
        status: "succeeded",
        session_id: "session-a",
        job_id: "job-a",
        session_updated_at: "2026-07-24T00:00:00Z",
        segment_ids: ["segment-a"],
        fields: ["caption", "broll"],
        ...change,
      },
    )).toBe(false);
  });
});
