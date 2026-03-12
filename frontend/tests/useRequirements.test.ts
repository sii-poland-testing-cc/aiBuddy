import { describe, it, expect, vi, afterEach } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { useRequirements } from "../lib/useRequirements";

// ── SSE stream helpers ────────────────────────────────────────────────────────

/**
 * Builds a mocked fetch Response that streams the given SSE lines as a
 * ReadableStream, then closes.
 */
function sseResponse(lines: string[]) {
  const encoder = new TextEncoder();
  const stream = new ReadableStream({
    start(controller) {
      for (const line of lines) {
        controller.enqueue(encoder.encode(`data: ${line}\n\n`));
      }
      controller.close();
    },
  });
  return Promise.resolve({ ok: true, body: stream, status: 200 } as unknown as Response);
}

/**
 * Builds an SSE Response that sends `lines` then waits for `release()` to be
 * called before closing the stream.  Allows tests to observe intermediate state
 * (e.g. extractionProgress) before the hook's finally-block clears it.
 */
function pausedSseResponse(lines: string[]): { response: Promise<Response>; release: () => void } {
  let release!: () => void;
  const closeSignal = new Promise<void>((resolve) => { release = resolve; });
  const encoder = new TextEncoder();
  const stream = new ReadableStream({
    async start(controller) {
      for (const line of lines) {
        controller.enqueue(encoder.encode(`data: ${line}\n\n`));
      }
      await closeSignal;
      controller.close();
    },
  });
  return {
    response: Promise.resolve({ ok: true, body: stream, status: 200 } as unknown as Response),
    release,
  };
}

function jsonResponse(data: unknown) {
  return Promise.resolve({
    ok: true,
    json: () => Promise.resolve(data),
  } as unknown as Response);
}

// ── Default fetch stub (empty requirements) ───────────────────────────────────

function stubEmptyRequirements() {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => {
      if (url.includes("/flat")) return jsonResponse({ requirements: [] });
      if (url.includes("/stats")) return jsonResponse({ has_requirements: false });
      return jsonResponse({});
    })
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("useRequirements — extractRequirements", () => {
  it("starts with isExtracting=false and no progress", () => {
    stubEmptyRequirements();
    const { result } = renderHook(() => useRequirements("proj-1"));
    expect(result.current.isExtracting).toBe(false);
    expect(result.current.extractionProgress).toBeNull();
  });

  it("sets isExtracting=true while streaming and false after completion", async () => {
    stubEmptyRequirements();
    const { result } = renderHook(() => useRequirements("proj-1"));

    // Wait for initial fetch to settle
    await waitFor(() => expect(result.current.loading).toBe(false));

    const progressEvent = JSON.stringify({
      type: "progress",
      data: { message: "Extracting…", progress: 0.5, stage: "extract" },
    });
    const resultEvent = JSON.stringify({
      type: "result",
      data: { requirements: [], stats: {} },
    });

    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        if (url.includes("/extract")) return sseResponse([progressEvent, resultEvent]);
        if (url.includes("/flat")) return jsonResponse({ requirements: [] });
        if (url.includes("/stats")) return jsonResponse({ has_requirements: false });
        return jsonResponse({});
      })
    );

    act(() => {
      result.current.extractRequirements();
    });

    await waitFor(() => expect(result.current.isExtracting).toBe(true));
    await waitFor(() => expect(result.current.isExtracting).toBe(false));
  });

  it("updates extractionProgress from SSE progress events", async () => {
    stubEmptyRequirements();
    const { result } = renderHook(() => useRequirements("proj-1"));
    await waitFor(() => expect(result.current.loading).toBe(false));

    const progressEvent = JSON.stringify({
      type: "progress",
      data: { message: "Analizowanie dokumentów…", progress: 0.4, stage: "extract" },
    });

    // Use a paused stream so the hook's finally-block doesn't clear extractionProgress
    // before our waitFor assertion can observe it.
    const { response: pausedResponse, release } = pausedSseResponse([progressEvent]);

    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        if (url.includes("/extract")) return pausedResponse;
        if (url.includes("/flat")) return jsonResponse({ requirements: [] });
        if (url.includes("/stats")) return jsonResponse({ has_requirements: false });
        return jsonResponse({});
      })
    );

    act(() => { result.current.extractRequirements(); });

    await waitFor(() => {
      expect(result.current.extractionProgress?.message).toBe("Analizowanie dokumentów…");
      expect(result.current.extractionProgress?.progress).toBe(0.4);
      expect(result.current.extractionProgress?.stage).toBe("extract");
    });

    // Let the stream finish so the hook's async function can settle
    release();
  });

  it("POSTs to the correct endpoint", async () => {
    stubEmptyRequirements();
    const { result } = renderHook(() => useRequirements("proj-abc"));
    await waitFor(() => expect(result.current.loading).toBe(false));

    const fetchMock = vi.fn((url: string) => {
      if (url.includes("/extract")) return sseResponse([]);
      if (url.includes("/flat")) return jsonResponse({ requirements: [] });
      if (url.includes("/stats")) return jsonResponse({ has_requirements: false });
      return jsonResponse({});
    });
    vi.stubGlobal("fetch", fetchMock);

    await act(async () => {
      await result.current.extractRequirements("focus on payments");
    });

    const extractCall = fetchMock.mock.calls.find(([url]) =>
      String(url).includes("/extract")
    );
    expect(extractCall).toBeTruthy();
    expect(String(extractCall![0])).toContain("/api/requirements/proj-abc/extract");
    const body = JSON.parse(extractCall![1]?.body as string);
    expect(body.message).toBe("focus on payments");
  });

  it("calls fetchAll after receiving a result event", async () => {
    stubEmptyRequirements();
    const { result } = renderHook(() => useRequirements("proj-1"));
    await waitFor(() => expect(result.current.loading).toBe(false));

    const REQ = { id: "r1", title: "FR-001", level: "functional_req", confidence: 0.9,
      human_reviewed: false, needs_review: false, description: "", source_type: "explicit",
      parent_id: null, external_id: "FR-001", review_reason: null, taxonomy: null };

    const resultEvent = JSON.stringify({ type: "result", data: {} });

    const fetchMock = vi.fn((url: string) => {
      if (url.includes("/extract")) return sseResponse([resultEvent]);
      if (url.includes("/flat")) return jsonResponse({ requirements: [REQ] });
      if (url.includes("/stats")) return jsonResponse({ total: 1, needs_review_count: 0, human_reviewed_count: 0, by_level: {}, by_source_type: {} });
      return jsonResponse({});
    });
    vi.stubGlobal("fetch", fetchMock);

    await act(async () => {
      await result.current.extractRequirements();
    });

    await waitFor(() => expect(result.current.requirements).toHaveLength(1));
    expect(result.current.requirements[0].external_id).toBe("FR-001");
  });

  it("sets error state when SSE returns an error event", async () => {
    stubEmptyRequirements();
    const { result } = renderHook(() => useRequirements("proj-1"));
    await waitFor(() => expect(result.current.loading).toBe(false));

    const errorEvent = JSON.stringify({
      type: "error",
      data: { message: "No context indexed for this project." },
    });

    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        if (url.includes("/extract")) return sseResponse([errorEvent]);
        if (url.includes("/flat")) return jsonResponse({ requirements: [] });
        if (url.includes("/stats")) return jsonResponse({ has_requirements: false });
        return jsonResponse({});
      })
    );

    await act(async () => {
      await result.current.extractRequirements();
    });

    expect(result.current.error).toBe("No context indexed for this project.");
  });

  it("sets error state on network failure", async () => {
    stubEmptyRequirements();
    const { result } = renderHook(() => useRequirements("proj-1"));
    await waitFor(() => expect(result.current.loading).toBe(false));

    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        if (url.includes("/extract")) return Promise.reject(new Error("network down"));
        if (url.includes("/flat")) return jsonResponse({ requirements: [] });
        if (url.includes("/stats")) return jsonResponse({ has_requirements: false });
        return jsonResponse({});
      })
    );

    await act(async () => {
      await result.current.extractRequirements();
    });

    expect(result.current.error).toBeTruthy();
    expect(result.current.isExtracting).toBe(false);
  });
});
