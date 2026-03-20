/**
 * Unit tests for useAuditPipeline.
 *
 * The pipeline must:
 *   1. Check /stats — run extractRequirements if has_requirements=false
 *   2. Check /staleness — run runMapping if is_stale=true
 *   3. Always call send() at the end with skipUserMessage:true
 *
 * Bug reported: on a fresh project (no requirements, mapping stale),
 * "uruchom audyt" skipped extraction and mapping and went straight to audit.
 */

import { describe, it, expect, vi, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useAuditPipeline } from "../lib/useAuditPipeline";

// ── Helpers ────────────────────────────────────────────────────────────────────

function makeFetch(statsBody: object, stalenessBody: object) {
  return vi.fn((url: string) => {
    if (url.includes("/stats")) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(statsBody) });
    }
    if (url.includes("/staleness")) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(stalenessBody) });
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
  });
}

function makeHook(overrides: Partial<Parameters<typeof useAuditPipeline>[0]> = {}) {
  const defaults = {
    projectId: "p1",
    extractRequirements: vi.fn().mockResolvedValue(undefined),
    isExtracting: false,
    runMapping: vi.fn().mockResolvedValue(undefined),
    isMappingRunning: false,
    send: vi.fn().mockResolvedValue(undefined),
    addUserMessage: vi.fn(),
    addStatusMessage: vi.fn(),
    getSelectedFilePaths: () => [] as string[],
  };
  return renderHook(() => useAuditPipeline({ ...defaults, ...overrides }));
}

afterEach(() => vi.restoreAllMocks());

// ── Core pipeline scenarios ────────────────────────────────────────────────────

describe("useAuditPipeline — fresh project (no requirements, stale mapping)", () => {
  it("calls extractRequirements then runMapping then send", async () => {
    vi.stubGlobal("fetch", makeFetch({ has_requirements: false }, { is_stale: true }));

    const extractRequirements = vi.fn().mockResolvedValue(undefined);
    const runMapping = vi.fn().mockResolvedValue(undefined);
    const send = vi.fn().mockResolvedValue(undefined);

    const { result } = makeHook({ extractRequirements, runMapping, send });

    await act(async () => {
      await result.current.handleAuditPipeline("Uruchom audyt");
    });

    // Both prerequisites must run before the audit
    expect(extractRequirements).toHaveBeenCalledTimes(1);
    expect(runMapping).toHaveBeenCalledTimes(1);
    expect(send).toHaveBeenCalledTimes(1);
  });

  it("calls extractRequirements before runMapping (sequential order)", async () => {
    vi.stubGlobal("fetch", makeFetch({ has_requirements: false }, { is_stale: true }));

    const order: string[] = [];
    const extractRequirements = vi.fn().mockImplementation(async () => {
      order.push("extract");
    });
    const runMapping = vi.fn().mockImplementation(async () => {
      order.push("mapping");
    });
    const send = vi.fn().mockImplementation(async () => {
      order.push("send");
    });

    const { result } = makeHook({ extractRequirements, runMapping, send });

    await act(async () => {
      await result.current.handleAuditPipeline("Uruchom audyt");
    });

    expect(order).toEqual(["extract", "mapping", "send"]);
  });

  it("shows status messages between pipeline steps", async () => {
    vi.stubGlobal("fetch", makeFetch({ has_requirements: false }, { is_stale: true }));

    const addStatusMessage = vi.fn();
    const { result } = makeHook({ addStatusMessage });

    await act(async () => {
      await result.current.handleAuditPipeline("Uruchom audyt");
    });

    expect(addStatusMessage).toHaveBeenCalledWith("Rozpoczynam ekstrakcję wymagań...");
    expect(addStatusMessage).toHaveBeenCalledWith("Wymagania gotowe. Rozpoczynam mapowanie...");
  });
});

// ── Skipping already-done steps ────────────────────────────────────────────────

describe("useAuditPipeline — requirements exist, mapping stale", () => {
  it("skips extractRequirements, runs runMapping and send", async () => {
    vi.stubGlobal("fetch", makeFetch({ has_requirements: true }, { is_stale: true }));

    const extractRequirements = vi.fn().mockResolvedValue(undefined);
    const runMapping = vi.fn().mockResolvedValue(undefined);
    const send = vi.fn().mockResolvedValue(undefined);

    const { result } = makeHook({ extractRequirements, runMapping, send });

    await act(async () => {
      await result.current.handleAuditPipeline("Uruchom audyt");
    });

    expect(extractRequirements).not.toHaveBeenCalled();
    expect(runMapping).toHaveBeenCalledTimes(1);
    expect(send).toHaveBeenCalledTimes(1);
  });
});

describe("useAuditPipeline — requirements exist, mapping current", () => {
  it("skips both extractRequirements and runMapping, calls only send", async () => {
    vi.stubGlobal("fetch", makeFetch({ has_requirements: true }, { is_stale: false }));

    const extractRequirements = vi.fn().mockResolvedValue(undefined);
    const runMapping = vi.fn().mockResolvedValue(undefined);
    const send = vi.fn().mockResolvedValue(undefined);

    const { result } = makeHook({ extractRequirements, runMapping, send });

    await act(async () => {
      await result.current.handleAuditPipeline("Uruchom audyt");
    });

    expect(extractRequirements).not.toHaveBeenCalled();
    expect(runMapping).not.toHaveBeenCalled();
    expect(send).toHaveBeenCalledTimes(1);
  });
});

// ── Guard: operation already in flight ────────────────────────────────────────

describe("useAuditPipeline — isExtracting=true (extraction already running)", () => {
  it("skips extractRequirements block, still checks staleness and runs mapping", async () => {
    vi.stubGlobal("fetch", makeFetch({ has_requirements: false }, { is_stale: true }));

    const extractRequirements = vi.fn().mockResolvedValue(undefined);
    const runMapping = vi.fn().mockResolvedValue(undefined);
    const send = vi.fn().mockResolvedValue(undefined);

    const { result } = makeHook({
      extractRequirements,
      isExtracting: true,
      runMapping,
      send,
    });

    await act(async () => {
      await result.current.handleAuditPipeline("Uruchom audyt");
    });

    expect(extractRequirements).not.toHaveBeenCalled(); // already running
    expect(runMapping).toHaveBeenCalledTimes(1);
    expect(send).toHaveBeenCalledTimes(1);
  });
});

describe("useAuditPipeline — isMappingRunning=true (mapping already running)", () => {
  it("skips runMapping block, but still runs extractRequirements and send", async () => {
    vi.stubGlobal("fetch", makeFetch({ has_requirements: false }, { is_stale: true }));

    const extractRequirements = vi.fn().mockResolvedValue(undefined);
    const runMapping = vi.fn().mockResolvedValue(undefined);
    const send = vi.fn().mockResolvedValue(undefined);

    const { result } = makeHook({
      extractRequirements,
      runMapping,
      isMappingRunning: true,
      send,
    });

    await act(async () => {
      await result.current.handleAuditPipeline("Uruchom audyt");
    });

    expect(extractRequirements).toHaveBeenCalledTimes(1);
    expect(runMapping).not.toHaveBeenCalled(); // already running
    expect(send).toHaveBeenCalledTimes(1);
  });
});

// ── Resilience: fetch failures ────────────────────────────────────────────────

describe("useAuditPipeline — stats fetch fails", () => {
  it("skips extraction gracefully and still runs mapping and send", async () => {
    vi.stubGlobal("fetch", vi.fn((url: string) => {
      if (url.includes("/stats")) return Promise.reject(new Error("Network error"));
      if (url.includes("/staleness")) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ is_stale: true }) });
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
    }));

    const extractRequirements = vi.fn().mockResolvedValue(undefined);
    const runMapping = vi.fn().mockResolvedValue(undefined);
    const send = vi.fn().mockResolvedValue(undefined);

    const { result } = makeHook({ extractRequirements, runMapping, send });

    await act(async () => {
      await result.current.handleAuditPipeline("Uruchom audyt");
    });

    expect(extractRequirements).not.toHaveBeenCalled(); // skipped due to error
    expect(runMapping).toHaveBeenCalledTimes(1);
    expect(send).toHaveBeenCalledTimes(1);
  });
});

describe("useAuditPipeline — both fetches fail", () => {
  it("skips extraction and mapping, but still calls send", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("Network error")));

    const extractRequirements = vi.fn().mockResolvedValue(undefined);
    const runMapping = vi.fn().mockResolvedValue(undefined);
    const send = vi.fn().mockResolvedValue(undefined);

    const { result } = makeHook({ extractRequirements, runMapping, send });

    await act(async () => {
      await result.current.handleAuditPipeline("Uruchom audyt");
    });

    expect(extractRequirements).not.toHaveBeenCalled();
    expect(runMapping).not.toHaveBeenCalled();
    expect(send).toHaveBeenCalledTimes(1);
  });
});

// ── send() arguments ──────────────────────────────────────────────────────────

describe("useAuditPipeline — send arguments", () => {
  it("passes userMessage and selected file paths to send with skipUserMessage:true", async () => {
    vi.stubGlobal("fetch", makeFetch({ has_requirements: true }, { is_stale: false }));

    const send = vi.fn().mockResolvedValue(undefined);

    const { result } = makeHook({
      send,
      getSelectedFilePaths: () => ["/uploads/test1.xlsx", "/uploads/test2.csv"],
    });

    await act(async () => {
      await result.current.handleAuditPipeline("custom message");
    });

    expect(send).toHaveBeenCalledWith(
      "custom message",
      ["/uploads/test1.xlsx", "/uploads/test2.csv"],
      { skipUserMessage: true }
    );
  });

  it("merges selected paths with extraPaths passed to the pipeline", async () => {
    vi.stubGlobal("fetch", makeFetch({ has_requirements: true }, { is_stale: false }));

    const send = vi.fn().mockResolvedValue(undefined);

    const { result } = makeHook({
      send,
      getSelectedFilePaths: () => ["/uploads/selected.xlsx"],
    });

    await act(async () => {
      await result.current.handleAuditPipeline("Uruchom audyt", ["/tmp/extra.csv"]);
    });

    expect(send).toHaveBeenCalledWith(
      "Uruchom audyt",
      ["/uploads/selected.xlsx", "/tmp/extra.csv"],
      { skipUserMessage: true }
    );
  });

  it("calls addUserMessage immediately with the user message", async () => {
    vi.stubGlobal("fetch", makeFetch({ has_requirements: true }, { is_stale: false }));

    const addUserMessage = vi.fn();
    const send = vi.fn().mockResolvedValue(undefined);

    const { result } = makeHook({ addUserMessage, send });

    await act(async () => {
      await result.current.handleAuditPipeline("my audit message");
    });

    expect(addUserMessage).toHaveBeenCalledWith("my audit message");
  });
});
