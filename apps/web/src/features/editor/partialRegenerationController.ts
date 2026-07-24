export const PARTIAL_REGENERATION_FIELDS = [
  "caption",
  "cut_action",
  "broll",
  "visual_overlay",
  "music",
  "sfx",
  "tts_replacement",
] as const;

export type PartialRegenerationField = typeof PARTIAL_REGENERATION_FIELDS[number];

export type PartialRegenerationScope = Readonly<{
  projectId: string;
  sessionId: string;
  routeEpoch: number;
  revision: number;
  segmentId: string;
  fields: readonly string[];
}>;

export type PartialRegenerationTicket = Readonly<{
  projectId: string;
  sessionId: string;
  routeEpoch: number;
  revision: number;
  segmentId: string;
  fields: readonly PartialRegenerationField[];
}>;

export type PartialRegenerationResumeResult = Readonly<{
  status: string | null;
  session_id: string | null;
  job_id: string | null;
  session_updated_at?: string | null;
  segment_ids: readonly string[];
  fields: readonly string[];
}>;

export type PartialRegenerationResponseIdentity = Readonly<{
  session_id: string | null;
  segment_ids: readonly string[];
  fields: readonly string[];
}>;

export type PartialRegenerationRunIdentity = PartialRegenerationResponseIdentity & Readonly<{
  status: string | null;
  job_id: string | null;
}>;

const partialRegenerationFieldSet = new Set<string>(PARTIAL_REGENERATION_FIELDS);

function isNonblank(value: string) {
  return value.trim().length > 0;
}

function isValidScopeIdentity(scope: Omit<PartialRegenerationScope, "fields">) {
  return (
    isNonblank(scope.projectId)
    && isNonblank(scope.sessionId)
    && isNonblank(scope.segmentId)
    && Number.isInteger(scope.routeEpoch)
    && scope.routeEpoch >= 0
    && Number.isInteger(scope.revision)
    && scope.revision >= 0
  );
}

function sameFields(
  left: readonly PartialRegenerationField[],
  right: readonly PartialRegenerationField[],
) {
  return left.length === right.length && left.every((field, index) => field === right[index]);
}

export function normalizePartialRegenerationFields(
  fields: readonly string[],
): PartialRegenerationField[] | null {
  if (fields.length === 0) return null;
  const selected = new Set<PartialRegenerationField>();
  for (const field of fields) {
    const normalized = field.trim();
    if (!normalized || !partialRegenerationFieldSet.has(normalized)) return null;
    selected.add(normalized as PartialRegenerationField);
  }
  return PARTIAL_REGENERATION_FIELDS.filter((field) => selected.has(field));
}

export function createPartialRegenerationTicket(
  scope: PartialRegenerationScope,
): PartialRegenerationTicket | null {
  const fields = normalizePartialRegenerationFields(scope.fields);
  if (!fields || !isValidScopeIdentity(scope)) return null;
  return Object.freeze({
    projectId: scope.projectId,
    sessionId: scope.sessionId,
    routeEpoch: scope.routeEpoch,
    revision: scope.revision,
    segmentId: scope.segmentId,
    fields: Object.freeze(fields),
  });
}

export function canRunPartialRegeneration(
  ticket: PartialRegenerationTicket | null,
  current: PartialRegenerationScope,
): boolean {
  if (!ticket || !isValidScopeIdentity(ticket) || !isValidScopeIdentity(current)) return false;
  const ticketFields = normalizePartialRegenerationFields(ticket.fields);
  const currentFields = normalizePartialRegenerationFields(current.fields);
  if (
    !ticketFields
    || !currentFields
    || !sameFields(ticketFields, ticket.fields)
    || !sameFields(ticketFields, currentFields)
  ) return false;
  return (
    ticket.projectId === current.projectId
    && ticket.sessionId === current.sessionId
    && ticket.routeEpoch === current.routeEpoch
    && ticket.revision === current.revision
    && ticket.segmentId === current.segmentId
  );
}

export function preflightMatchesPartialRegenerationTicket(
  ticket: PartialRegenerationTicket,
  result: PartialRegenerationResponseIdentity,
): boolean {
  const resultFields = normalizePartialRegenerationFields(result.fields);
  return (
    result.session_id === ticket.sessionId
    && result.segment_ids.length === 1
    && result.segment_ids[0] === ticket.segmentId
    && resultFields !== null
    && sameFields(ticket.fields, resultFields)
  );
}

export function runMatchesPartialRegenerationTicket(
  ticket: PartialRegenerationTicket,
  result: PartialRegenerationRunIdentity,
): boolean {
  return (
    result.status === "succeeded"
    && typeof result.job_id === "string"
    && isNonblank(result.job_id)
    && preflightMatchesPartialRegenerationTicket(ticket, result)
  );
}

export function canRestorePartialRegenerationResult(
  current: Readonly<{
    sessionId: string;
    sessionUpdatedAt: string;
    jobId: string;
    segmentId: string;
    fields: readonly string[];
  }>,
  result: PartialRegenerationResumeResult,
): boolean {
  const currentFields = normalizePartialRegenerationFields(current.fields);
  const resultFields = normalizePartialRegenerationFields(result.fields);
  return (
    isNonblank(current.sessionId)
    && isNonblank(current.sessionUpdatedAt)
    && isNonblank(current.jobId)
    && isNonblank(current.segmentId)
    && result.status === "succeeded"
    && result.session_id === current.sessionId
    && typeof result.job_id === "string"
    && isNonblank(result.job_id)
    && result.job_id === current.jobId
    && result.session_updated_at === current.sessionUpdatedAt
    && result.segment_ids.length === 1
    && result.segment_ids[0] === current.segmentId
    && currentFields !== null
    && resultFields !== null
    && sameFields(currentFields, resultFields)
  );
}
