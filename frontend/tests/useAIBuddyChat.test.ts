/**
 * Tests for useAIBuddyChat — localStorage persistence.
 *
 * Covers:
 *   1. Messages are loaded from localStorage on mount (per projectId).
 *   2. Messages are saved to localStorage when added.
 *   3. Status messages (isStatus:true) are excluded from persistence.
 *   4. clear() removes the entry from localStorage.
 *   5. Separate storage keys are used per projectId.
 *   6. Empty-message guard prevents wiping storage during initialisation.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { useAIBuddyChat, buildAuditData } from "../lib/useAIBuddyChat";

// ── localStorage mock ─────────────────────────────────────────────────────────

const store: Record<string, string> = {};

const localStorageMock = {
  getItem:    vi.fn((key: string) => store[key] ?? null),
  setItem:    vi.fn((key: string, value: string) => { store[key] = value; }),
  removeItem: vi.fn((key: string) => { delete store[key]; }),
};

Object.defineProperty(global, "localStorage", {
  value: localStorageMock,
  writable: true,
});

// ── Helpers ───────────────────────────────────────────────────────────────────

const STORAGE_KEY = (id: string) => `ai-buddy-chat-${id}`;

function storedMessages(projectId = "p1") {
  const raw = store[STORAGE_KEY(projectId)];
  return raw ? JSON.parse(raw) : null;
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("useAIBuddyChat — chat persistence", () => {
  beforeEach(() => {
    // Reset store and call-history before each test
    Object.keys(store).forEach((k) => delete store[k]);
    vi.clearAllMocks();
  });

  afterEach(() => vi.restoreAllMocks());

  // ── Load from localStorage ─────────────────────────────────────────────────

  it("loads persisted messages from localStorage on mount", () => {
    const stored = [
      { id: "m1", role: "user",      content: "hello",   timestamp: "2026-03-20T10:00:00.000Z" },
      { id: "m2", role: "assistant", content: "world",   timestamp: "2026-03-20T10:01:00.000Z" },
    ];
    store[STORAGE_KEY("p1")] = JSON.stringify(stored);

    const { result } = renderHook(() => useAIBuddyChat({ projectId: "p1" }));

    expect(result.current.messages).toHaveLength(2);
    expect(result.current.messages[0].content).toBe("hello");
    expect(result.current.messages[1].content).toBe("world");
  });

  it("converts timestamp strings back to Date objects on load", () => {
    const stored = [
      { id: "m1", role: "user", content: "hi", timestamp: "2026-03-20T10:00:00.000Z" },
    ];
    store[STORAGE_KEY("p1")] = JSON.stringify(stored);

    const { result } = renderHook(() => useAIBuddyChat({ projectId: "p1" }));

    expect(result.current.messages[0].timestamp).toBeInstanceOf(Date);
  });

  it("starts with empty messages when localStorage has no entry", () => {
    const { result } = renderHook(() => useAIBuddyChat({ projectId: "p1" }));
    expect(result.current.messages).toHaveLength(0);
  });

  it("starts with empty messages when localStorage entry is malformed JSON", () => {
    store[STORAGE_KEY("p1")] = "{ not valid json";

    const { result } = renderHook(() => useAIBuddyChat({ projectId: "p1" }));
    expect(result.current.messages).toHaveLength(0);
  });

  // ── Save to localStorage ───────────────────────────────────────────────────

  it("saves messages to localStorage after addUserMessage", async () => {
    const { result } = renderHook(() => useAIBuddyChat({ projectId: "p1" }));

    act(() => { result.current.addUserMessage("test message"); });

    await waitFor(() => {
      expect(localStorageMock.setItem).toHaveBeenCalledWith(
        STORAGE_KEY("p1"),
        expect.stringContaining("test message"),
      );
    });
  });

  it("persisted payload is valid JSON with correct role and content", async () => {
    const { result } = renderHook(() => useAIBuddyChat({ projectId: "p1" }));

    act(() => { result.current.addUserMessage("my message"); });

    await waitFor(() => {
      const saved = storedMessages();
      expect(saved).not.toBeNull();
      expect(saved[0].role).toBe("user");
      expect(saved[0].content).toBe("my message");
    });
  });

  it("does not call setItem when messages are empty (init guard)", () => {
    renderHook(() => useAIBuddyChat({ projectId: "p1" }));
    // No messages → save effect should bail out early
    expect(localStorageMock.setItem).not.toHaveBeenCalled();
  });

  // ── Status messages excluded ───────────────────────────────────────────────

  it("excludes status messages (isStatus:true) from persisted payload", async () => {
    const { result } = renderHook(() => useAIBuddyChat({ projectId: "p1" }));

    act(() => {
      result.current.addUserMessage("real message");
      result.current.addStatusMessage("building context…");
    });

    await waitFor(() => {
      const saved = storedMessages();
      expect(saved).not.toBeNull();
      expect(saved.some((m: any) => m.isStatus)).toBe(false);
    });
  });

  it("persists the non-status message alongside excluded status messages", async () => {
    const { result } = renderHook(() => useAIBuddyChat({ projectId: "p1" }));

    act(() => {
      result.current.addUserMessage("keep me");
      result.current.addStatusMessage("drop me");
    });

    await waitFor(() => {
      const saved = storedMessages();
      expect(saved).toHaveLength(1);
      expect(saved[0].content).toBe("keep me");
    });
  });

  // ── clear() ───────────────────────────────────────────────────────────────

  it("clear() removes the localStorage entry", async () => {
    const { result } = renderHook(() => useAIBuddyChat({ projectId: "p1" }));

    act(() => { result.current.addUserMessage("hello"); });
    await waitFor(() => { expect(storedMessages()).not.toBeNull(); });

    act(() => { result.current.clear(); });

    expect(localStorageMock.removeItem).toHaveBeenCalledWith(STORAGE_KEY("p1"));
    expect(result.current.messages).toHaveLength(0);
  });

  it("clear() resets in-memory messages to empty array", () => {
    store[STORAGE_KEY("p1")] = JSON.stringify([
      { id: "m1", role: "user", content: "hi", timestamp: "2026-03-20T10:00:00.000Z" },
    ]);

    const { result } = renderHook(() => useAIBuddyChat({ projectId: "p1" }));
    expect(result.current.messages).toHaveLength(1);

    act(() => { result.current.clear(); });

    expect(result.current.messages).toHaveLength(0);
  });

  // ── Per-project isolation ─────────────────────────────────────────────────

  it("uses separate storage key per projectId", () => {
    store[STORAGE_KEY("projectA")] = JSON.stringify([
      { id: "m1", role: "user", content: "only in A", timestamp: "2026-03-20T10:00:00.000Z" },
    ]);

    const { result: rA } = renderHook(() => useAIBuddyChat({ projectId: "projectA" }));
    const { result: rB } = renderHook(() => useAIBuddyChat({ projectId: "projectB" }));

    expect(rA.current.messages).toHaveLength(1);
    expect(rB.current.messages).toHaveLength(0);
  });

  it("re-loads messages when projectId changes", async () => {
    store[STORAGE_KEY("p1")] = JSON.stringify([
      { id: "m1", role: "user", content: "p1 message", timestamp: "2026-03-20T10:00:00.000Z" },
    ]);
    store[STORAGE_KEY("p2")] = JSON.stringify([
      { id: "m2", role: "user", content: "p2 message", timestamp: "2026-03-20T10:00:00.000Z" },
      { id: "m3", role: "user", content: "p2 second",  timestamp: "2026-03-20T10:01:00.000Z" },
    ]);

    const { result, rerender } = renderHook(
      ({ projectId }: { projectId: string }) => useAIBuddyChat({ projectId }),
      { initialProps: { projectId: "p1" } },
    );

    expect(result.current.messages).toHaveLength(1);
    expect(result.current.messages[0].content).toBe("p1 message");

    rerender({ projectId: "p2" });
    await waitFor(() => {
      expect(result.current.messages).toHaveLength(2);
      expect(result.current.messages[0].content).toBe("p2 message");
    });
  });
});

// ── buildAuditData ────────────────────────────────────────────────────────────

describe("buildAuditData", () => {
  const BASE_DATA = {
    summary: {
      coverage_pct: 75,
      duplicates_found: 2,
      untagged_cases: 3,
      requirements_total: 10,
      requirements_covered: 7,
      requirements_uncovered: ["FR-003", "FR-009"],
    },
    recommendations: ["Add negative tests"],
    duplicates: [{ tc_a: "TC-1", tc_b: "TC-2", similarity: 0.95 }],
    next_tier: "optimize",
  };

  it("maps all summary fields correctly", () => {
    const result = buildAuditData(BASE_DATA, null);
    expect(result.summary.coverage_pct).toBe(75);
    expect(result.summary.duplicates_found).toBe(2);
    expect(result.summary.untagged_cases).toBe(3);
    expect(result.summary.requirements_total).toBe(10);
    expect(result.summary.requirements_covered).toBe(7);
  });

  it("maps uncovered requirements from summary.requirements_uncovered", () => {
    const result = buildAuditData(BASE_DATA, null);
    expect(result.uncovered).toEqual(["FR-003", "FR-009"]);
  });

  it("maps recommendations and duplicates", () => {
    const result = buildAuditData(BASE_DATA, null);
    expect(result.recommendations).toEqual(["Add negative tests"]);
    expect(result.duplicates).toHaveLength(1);
    expect(result.duplicates[0].tc_a).toBe("TC-1");
  });

  it("sets next_tier", () => {
    expect(buildAuditData(BASE_DATA, null).next_tier).toBe("optimize");
  });

  it("attaches the provided diff", () => {
    const diff = { coverage_delta: 5, new_covered: ["FR-001"] };
    expect(buildAuditData(BASE_DATA, diff).diff).toEqual(diff);
  });

  it("diff=null means first audit (no previous snapshot)", () => {
    expect(buildAuditData(BASE_DATA, null).diff).toBeNull();
  });

  it("diff=undefined means diff not fetched yet", () => {
    expect(buildAuditData(BASE_DATA, undefined).diff).toBeUndefined();
  });

  it("defaults missing summary fields to 0", () => {
    const sparse = { summary: {}, recommendations: [], duplicates: [] };
    const result = buildAuditData(sparse, null);
    expect(result.summary.coverage_pct).toBe(0);
    expect(result.summary.duplicates_found).toBe(0);
    expect(result.summary.untagged_cases).toBe(0);
    expect(result.summary.requirements_total).toBe(0);
    expect(result.summary.requirements_covered).toBe(0);
  });

  it("defaults missing recommendations/duplicates/uncovered to empty arrays", () => {
    const sparse = { summary: {} };
    const result = buildAuditData(sparse, null);
    expect(result.recommendations).toEqual([]);
    expect(result.duplicates).toEqual([]);
    expect(result.uncovered).toEqual([]);
  });
});
