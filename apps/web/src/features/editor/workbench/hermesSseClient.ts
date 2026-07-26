export type HermesSseEvent = Readonly<{
  event_id: number;
  event_type: "run_started" | "text_delta" | "blocked" | "run_completed";
  text: string;
  retryable: boolean;
}>;

const allowedEventTypes = new Set<HermesSseEvent["event_type"]>([
  "run_started",
  "text_delta",
  "blocked",
  "run_completed",
]);
const maxLineCharacters = 256_000;
const maxEventCharacters = 260_000;
const maxStreamBytes = 600_000;
const maxEvents = 256;
const maxDeltaCharacters = 32_000;
const maxTextCharacters = 200_000;
const maxBlockedCharacters = 4_096;
const protocolErrorMessage = "유진 응답을 이어받지 못했어요.";

type ParseHermesSseOptions = Readonly<{
  signal: AbortSignal;
  onEvent: (event: HermesSseEvent) => void;
}>;

export async function parseHermesSse(
  response: Response,
  { signal, onEvent }: ParseHermesSseOptions,
): Promise<void> {
  abortIfNeeded(signal);
  const mediaType = response.headers.get("content-type")
    ?.split(";", 1)[0]
    .trim()
    .toLowerCase();
  if (
    !response.ok
    || !response.body
    || mediaType !== "text/event-stream"
  ) {
    throw protocolError();
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8", { fatal: true });
  let buffered = "";
  let frameLines: string[] = [];
  let frameCharacters = 0;
  let streamBytes = 0;
  let eventCount = 0;
  let lastEventId = 0;
  let assembledText = "";
  let started = false;
  let terminal = false;
  let readerCancelled = false;
  const cancelReader = async () => {
    if (readerCancelled) return;
    readerCancelled = true;
    await reader.cancel();
  };
  const abortReader = () => {
    void cancelReader().catch(() => undefined);
  };
  signal.addEventListener("abort", abortReader, { once: true });

  const dispatchFrame = () => {
    if (!frameLines.length) return;
    eventCount += 1;
    if (eventCount > maxEvents) throw protocolError();
    const frame = parseFrame(frameLines);
    frameLines = [];
    frameCharacters = 0;
    if (frame.eventId <= lastEventId) return;
    if (terminal || frame.eventId !== lastEventId + 1) throw protocolError();
    const payload = parsePayload(frame);

    if (!started) {
      if (payload.event_type !== "run_started" || payload.text) throw protocolError();
      started = true;
    } else if (payload.event_type === "run_started") {
      throw protocolError();
    } else if (payload.event_type === "text_delta") {
      if (!payload.text || payload.text.length > maxDeltaCharacters) throw protocolError();
      assembledText += payload.text;
      if (assembledText.length > maxTextCharacters) throw protocolError();
    } else if (payload.event_type === "run_completed") {
      if (
        !payload.text
        || payload.text.length > maxTextCharacters
        || payload.text !== assembledText
      ) {
        throw protocolError();
      }
      terminal = true;
    } else {
      if (payload.text.length > maxBlockedCharacters) throw protocolError();
      terminal = true;
    }

    lastEventId = payload.event_id;
    onEvent(payload);
  };

  const acceptLine = (rawLine: string) => {
    const line = rawLine.endsWith("\r") ? rawLine.slice(0, -1) : rawLine;
    if (line.length > maxLineCharacters) throw protocolError();
    if (!line) {
      dispatchFrame();
      return;
    }
    frameCharacters += line.length;
    if (frameCharacters > maxEventCharacters) throw protocolError();
    frameLines.push(line);
  };

  try {
    while (!terminal) {
      abortIfNeeded(signal);
      const { done, value } = await reader.read();
      abortIfNeeded(signal);
      if (done) break;
      streamBytes += value.byteLength;
      if (streamBytes > maxStreamBytes) throw protocolError();
      try {
        buffered += decoder.decode(value, { stream: true });
      } catch {
        throw protocolError();
      }
      let newlineAt = buffered.indexOf("\n");
      while (newlineAt >= 0) {
        acceptLine(buffered.slice(0, newlineAt));
        buffered = buffered.slice(newlineAt + 1);
        newlineAt = buffered.indexOf("\n");
      }
      if (buffered.length > maxLineCharacters) throw protocolError();
    }
    if (!terminal) {
      try {
        buffered += decoder.decode();
      } catch {
        throw protocolError();
      }
      if (buffered) acceptLine(buffered);
      dispatchFrame();
    }
    if (!terminal) throw protocolError();
    await cancelReader();
  } catch (error) {
    await cancelReader().catch(() => undefined);
    throw error;
  } finally {
    signal.removeEventListener("abort", abortReader);
    reader.releaseLock();
  }
}

function parseFrame(lines: readonly string[]) {
  let id: string | null = null;
  let eventType: string | null = null;
  let data: string | null = null;
  for (const line of lines) {
    if (line.startsWith(":")) continue;
    const separatorAt = line.indexOf(":");
    if (separatorAt < 1) throw protocolError();
    const field = line.slice(0, separatorAt);
    const value = line.slice(separatorAt + 1).replace(/^ /, "");
    if (field === "id" && id === null) id = value;
    else if (field === "event" && eventType === null) eventType = value;
    else if (field === "data" && data === null) data = value;
    else throw protocolError();
  }
  if (!id || !/^[1-9][0-9]*$/.test(id) || !eventType || data === null) throw protocolError();
  const eventId = Number(id);
  if (!Number.isSafeInteger(eventId)) throw protocolError();
  return { eventId, eventType, data };
}

function parsePayload(frame: ReturnType<typeof parseFrame>): HermesSseEvent {
  let candidate: unknown;
  try {
    candidate = JSON.parse(frame.data);
  } catch {
    throw protocolError();
  }
  if (!candidate || typeof candidate !== "object" || Array.isArray(candidate)) {
    throw protocolError();
  }
  const payload = candidate as Record<string, unknown>;
  if (
    Object.keys(payload).length !== 4
    || typeof payload.event_id !== "number"
    || payload.event_id !== frame.eventId
    || typeof payload.event_type !== "string"
    || payload.event_type !== frame.eventType
    || !allowedEventTypes.has(payload.event_type as HermesSseEvent["event_type"])
    || typeof payload.text !== "string"
    || typeof payload.retryable !== "boolean"
  ) {
    throw protocolError();
  }
  return payload as HermesSseEvent;
}

function abortIfNeeded(signal: AbortSignal) {
  if (signal.aborted) throw new DOMException("Aborted", "AbortError");
}

function protocolError() {
  return new Error(protocolErrorMessage);
}
