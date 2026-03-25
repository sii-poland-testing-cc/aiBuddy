/**
 * consumeSSE
 * ==========
 * Reads an SSE (Server-Sent Events) ReadableStream line by line and calls
 * `onEvent` for each parsed `data:` payload until the stream is exhausted
 * or `[DONE]` is received.
 *
 * Usage:
 *   await consumeSSE(res.body, (ev) => {
 *     if (ev.type === "progress") ...
 *     else if (ev.type === "result") ...
 *   });
 */

export interface SSEEvent {
  type: string;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  data: any;
}

export async function consumeSSE(
  body: ReadableStream<Uint8Array>,
  onEvent: (event: SSEEvent) => void
): Promise<void> {
  const reader = body.getReader();
  const decoder = new TextDecoder();

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    const chunk = decoder.decode(value, { stream: true });
    for (const line of chunk.split("\n")) {
      if (!line.startsWith("data: ")) continue;
      const payload = line.slice(6).trim();
      if (payload === "[DONE]") return;
      try {
        const ev = JSON.parse(payload) as SSEEvent;
        onEvent(ev);
      } catch {
        // malformed line — skip
      }
    }
  }
}
