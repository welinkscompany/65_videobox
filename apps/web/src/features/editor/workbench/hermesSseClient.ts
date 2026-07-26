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
const backendMaxNonterminalJsonBytes = 256_000;
const maxTextBytes = 200_000;
const maxJsonEscapeExpansion = 6;
const maxSseFrameOverheadBytes = 512;
const maxLineBytes = maxTextBytes * maxJsonEscapeExpansion + maxSseFrameOverheadBytes;
const maxEventBytes = maxLineBytes + maxSseFrameOverheadBytes;
const maxEvents = 257;
// Backend accounting caps cumulative nonterminal JSON. The terminal is exempt,
// so the browser also reserves one worst-case escaped terminal plus SSE framing.
const maxStreamBytes = backendMaxNonterminalJsonBytes
  + maxTextBytes * maxJsonEscapeExpansion
  + maxSseFrameOverheadBytes * maxEvents;
const maxDeltaBytes = 32_000;
const maxBlockedBytes = 4_096;
const protocolErrorMessage = "유진 응답을 이어받지 못했어요.";
const textEncoder = new TextEncoder();

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
  const lineBuffer = new Uint8Array(maxLineBytes + 1);
  let lineBytes = 0;
  let frameLines: string[] = [];
  let frameBytes = 0;
  let streamBytes = 0;
  let eventCount = 0;
  let lastEventId = 0;
  let assembledText = "";
  let assembledTextBytes = 0;
  let deltaCount = 0;
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
    frameBytes = 0;
    if (frame.eventId <= lastEventId) return;
    if (terminal || frame.eventId !== lastEventId + 1) throw protocolError();
    const payload = parsePayload(frame);

    if (!started) {
      if (payload.event_type !== "run_started" || payload.text) throw protocolError();
      started = true;
    } else if (payload.event_type === "run_started") {
      throw protocolError();
    } else if (payload.event_type === "text_delta") {
      const deltaBytes = utf8ByteLength(payload.text);
      if (!payload.text || deltaBytes > maxDeltaBytes) throw protocolError();
      assembledTextBytes += deltaBytes;
      if (assembledTextBytes > maxTextBytes) throw protocolError();
      assembledText += payload.text;
      deltaCount += 1;
    } else if (payload.event_type === "run_completed") {
      const completedBytes = utf8ByteLength(payload.text);
      if (
        !payload.text
        || completedBytes > maxTextBytes
        || (deltaCount > 0 && payload.text !== assembledText)
      ) {
        throw protocolError();
      }
      terminal = true;
    } else {
      if (utf8ByteLength(payload.text) > maxBlockedBytes) throw protocolError();
      terminal = true;
    }

    lastEventId = payload.event_id;
    onEvent(payload);
  };

  const acceptLine = (line: string, contentBytes: number, wireBytes: number) => {
    if (contentBytes > maxLineBytes) throw protocolError();
    if (!line) {
      dispatchFrame();
      return;
    }
    frameBytes += wireBytes;
    if (frameBytes > maxEventBytes) throw protocolError();
    frameLines.push(line);
  };

  const appendLineBytes = (bytes: Uint8Array) => {
    if (!bytes.byteLength) return;
    const nextLineBytes = lineBytes + bytes.byteLength;
    if (nextLineBytes > lineBuffer.byteLength) throw protocolError();
    lineBuffer.set(bytes, lineBytes);
    lineBytes = nextLineBytes;
    const pendingCrBytes = lineBuffer[lineBytes - 1] === 0x0d ? 1 : 0;
    if (lineBytes - pendingCrBytes > maxLineBytes) throw protocolError();
  };

  const finishLine = (newlineBytes: number) => {
    const hasCarriageReturn = lineBytes > 0 && lineBuffer[lineBytes - 1] === 0x0d;
    const contentBytes = lineBytes - (hasCarriageReturn ? 1 : 0);
    let line: string;
    try {
      line = decoder.decode(lineBuffer.subarray(0, contentBytes));
    } catch {
      throw protocolError();
    }
    acceptLine(line, contentBytes, lineBytes + newlineBytes);
    lineBytes = 0;
  };

  const acceptChunk = (value: Uint8Array) => {
    let start = 0;
    let newlineAt = value.indexOf(0x0a, start);
    while (newlineAt >= 0) {
      appendLineBytes(value.subarray(start, newlineAt));
      finishLine(1);
      start = newlineAt + 1;
      newlineAt = value.indexOf(0x0a, start);
    }
    appendLineBytes(value.subarray(start));
  };

  try {
    while (!terminal) {
      abortIfNeeded(signal);
      const { done, value } = await reader.read();
      abortIfNeeded(signal);
      if (done) break;
      streamBytes += value.byteLength;
      if (streamBytes > maxStreamBytes) throw protocolError();
      acceptChunk(value);
    }
    if (!terminal) {
      if (lineBytes) finishLine(0);
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

function utf8ByteLength(value: string) {
  return textEncoder.encode(value).byteLength;
}

function protocolError() {
  return new Error(protocolErrorMessage);
}
