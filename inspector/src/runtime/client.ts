import type { RuntimeProjection } from "../graph/runtime";

export type RuntimeEvent = RuntimeProjection["events"][number];

export type RuntimeRun = RuntimeProjection["run"];

export type RuntimeClientConfig = {
  baseUrl: string;
  namespace: string;
  runId: string;
  token: string;
};

export type SseRecord = {
  id: string | null;
  event: string | null;
  data: string;
};

export type WatchStatus = "connecting" | "live" | "reconnecting" | "polling";

export class RuntimeHttpError extends Error {
  readonly status: number;
  readonly code: string | null;
  readonly requestId: string | null;
  readonly details: unknown;

  constructor(
    message: string,
    status: number,
    code: string | null,
    requestId: string | null,
    details: unknown,
  ) {
    super(message);
    this.name = "RuntimeHttpError";
    this.status = status;
    this.code = code;
    this.requestId = requestId;
    this.details = details;
  }
}

export class RuntimeClient {
  private readonly config: RuntimeClientConfig;
  private readonly fetchImpl: typeof fetch;

  constructor(
    config: RuntimeClientConfig,
    fetchImpl: typeof fetch = globalThis.fetch.bind(globalThis),
  ) {
    this.config = config;
    this.fetchImpl = fetchImpl;
  }

  async getRun(signal?: AbortSignal): Promise<RuntimeRun> {
    return this.request<RuntimeRun>(
      `/api/v1/namespaces/${encodeURIComponent(this.config.namespace)}/runs/${encodeURIComponent(this.config.runId)}`,
      { signal },
    );
  }

  async getGraph(signal?: AbortSignal): Promise<RuntimeProjection> {
    return this.request<RuntimeProjection>(
      `/api/v1/namespaces/${encodeURIComponent(this.config.namespace)}/runs/${encodeURIComponent(this.config.runId)}/graph`,
      { signal },
    );
  }

  async listEvents(
    after: number,
    signal?: AbortSignal,
  ): Promise<{ events: RuntimeEvent[]; nextAfter: number }> {
    return this.request(
      `/api/v1/namespaces/${encodeURIComponent(this.config.namespace)}/runs/${encodeURIComponent(this.config.runId)}/events?after=${after}`,
      { signal },
    );
  }

  async watchRun(options: {
    after: number;
    signal: AbortSignal;
    onSnapshot: (projection: RuntimeProjection) => void;
    onEvent: (event: RuntimeEvent) => void;
    onStatus?: (status: WatchStatus) => void;
    reconnectDelayMs?: number;
    pollIntervalMs?: number;
  }): Promise<void> {
    let cursor = options.after;
    const reconnectDelayMs = options.reconnectDelayMs ?? 1_000;
    const pollIntervalMs = options.pollIntervalMs ?? 2_000;
    let usePolling = false;

    while (!options.signal.aborted) {
      try {
        options.onStatus?.(usePolling ? "polling" : "connecting");
        if (usePolling) {
          const result = await this.listEvents(cursor, options.signal);
          cursor = await this.consumeEvents(result.events, cursor, options);
          await this.wait(pollIntervalMs, options.signal);
          continue;
        }

        const response = await this.openStream(cursor, options.signal);
        if (!response.body) {
          usePolling = true;
          continue;
        }
        options.onStatus?.("live");
        await this.consumeStream(response.body, cursor, options, (nextCursor) => {
          cursor = nextCursor;
        });
        if (options.signal.aborted) break;
        options.onStatus?.("reconnecting");
        await this.wait(reconnectDelayMs, options.signal);
      } catch (error) {
        if (options.signal.aborted) break;
        if (error instanceof RuntimeHttpError && [401, 403].includes(error.status)) {
          throw error;
        }
        usePolling = true;
        options.onStatus?.("polling");
        await this.wait(pollIntervalMs, options.signal);
      }
    }
  }

  private async openStream(after: number, signal: AbortSignal): Promise<Response> {
    return this.requestRaw(
      `/api/v1/namespaces/${encodeURIComponent(this.config.namespace)}/runs/${encodeURIComponent(this.config.runId)}/stream?after=${after}`,
      {
        signal,
        headers: { Accept: "text/event-stream" },
      },
    );
  }

  private async consumeStream(
    body: ReadableStream<Uint8Array>,
    cursor: number,
    options: {
      signal: AbortSignal;
      onSnapshot: (projection: RuntimeProjection) => void;
      onEvent: (event: RuntimeEvent) => void;
    },
    setCursor: (cursor: number) => void,
  ): Promise<void> {
    const reader = body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let currentCursor = cursor;

    try {
      while (!options.signal.aborted) {
        const chunk = await reader.read();
        buffer += decoder.decode(chunk.value ?? new Uint8Array(), {
          stream: !chunk.done,
        });
        const boundary = buffer.lastIndexOf("\n\n");
        if (boundary >= 0) {
          const complete = buffer.slice(0, boundary + 2);
          buffer = buffer.slice(boundary + 2);
          currentCursor = await this.consumeRecords(
            parseSseText(complete),
            currentCursor,
            options,
          );
          setCursor(currentCursor);
        }
        if (chunk.done) break;
      }
    } finally {
      reader.releaseLock();
    }
  }

  private async consumeEvents(
    events: RuntimeEvent[],
    cursor: number,
    options: {
      signal: AbortSignal;
      onSnapshot: (projection: RuntimeProjection) => void;
      onEvent: (event: RuntimeEvent) => void;
    },
  ): Promise<number> {
    const merged = mergeRuntimeEvents([], events);
    for (const event of merged.events) {
      if (event.seq <= cursor) continue;
      options.onEvent(event);
      options.onSnapshot(await this.getGraph(options.signal));
      cursor = event.seq;
    }
    return cursor;
  }

  private async consumeRecords(
    records: SseRecord[],
    cursor: number,
    options: {
      signal: AbortSignal;
      onSnapshot: (projection: RuntimeProjection) => void;
      onEvent: (event: RuntimeEvent) => void;
    },
  ): Promise<number> {
    for (const record of records) {
      if (!record.data) continue;
      const event = JSON.parse(record.data) as RuntimeEvent;
      if (!Number.isInteger(event.seq) || event.seq <= cursor) continue;
      options.onEvent(event);
      options.onSnapshot(await this.getGraph(options.signal));
      cursor = event.seq;
    }
    return cursor;
  }

  private async request<T>(path: string, init: RequestInit): Promise<T> {
    const response = await this.requestRaw(path, init);
    return (await response.json()) as T;
  }

  private async requestRaw(path: string, init: RequestInit): Promise<Response> {
    const headers = new Headers(init.headers);
    headers.set("Accept", headers.get("Accept") ?? "application/json");
    headers.set("Authorization", `Bearer ${this.config.token}`);
    const response = await this.fetchImpl(`${this.config.baseUrl.replace(/\/+$/, "")}${path}`, {
      ...init,
      headers,
    });
    if (response.ok) return response;
    let body: {
      error?: { code?: string; message?: string; details?: unknown };
      requestId?: string;
    } = {};
    try {
      body = (await response.json()) as typeof body;
    } catch {
      // Keep the HTTP status as the stable error when the server did not return JSON.
    }
    throw new RuntimeHttpError(
      body.error?.message ?? `Runtime 请求失败（HTTP ${response.status}）`,
      response.status,
      body.error?.code ?? null,
      body.requestId ?? null,
      body.error?.details ?? null,
    );
  }

  private async wait(delayMs: number, signal: AbortSignal): Promise<void> {
    await new Promise<void>((resolve, reject) => {
      if (signal.aborted) {
        reject(signal.reason ?? new DOMException("Aborted", "AbortError"));
        return;
      }
      const timer = setTimeout(resolve, delayMs);
      signal.addEventListener(
        "abort",
        () => {
          clearTimeout(timer);
          reject(signal.reason ?? new DOMException("Aborted", "AbortError"));
        },
        { once: true },
      );
    });
  }
}

export function parseSseText(text: string): SseRecord[] {
  return text
    .split(/\r?\n\r?\n/)
    .map(parseSseRecord)
    .filter((record): record is SseRecord => record !== null);
}

function parseSseRecord(block: string): SseRecord | null {
  let id: string | null = null;
  let event: string | null = null;
  const data: string[] = [];
  for (const line of block.split(/\r?\n/)) {
    if (!line || line.startsWith(":")) continue;
    const separator = line.indexOf(":");
    const field = separator >= 0 ? line.slice(0, separator) : line;
    const value = separator >= 0 ? line.slice(separator + 1).replace(/^ /, "") : "";
    if (field === "id") id = value;
    if (field === "event") event = value;
    if (field === "data") data.push(value);
  }
  if (data.length === 0) return null;
  return { id, event, data: data.join("\n") };
}

export function mergeRuntimeEvents(
  current: RuntimeEvent[],
  incoming: RuntimeEvent[],
): { events: RuntimeEvent[]; lastSeq: number } {
  const bySeq = new Map<number, RuntimeEvent>();
  [...current, ...incoming].forEach((event) => {
    if (Number.isInteger(event.seq)) bySeq.set(event.seq, event);
  });
  const events = [...bySeq.values()].sort((left, right) => left.seq - right.seq);
  return { events, lastSeq: events.at(-1)?.seq ?? 0 };
}
