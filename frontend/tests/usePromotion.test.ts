import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { usePromotion } from "../lib/usePromotion";

describe("usePromotion", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("preview returns result on 200", async () => {
    const result = { promoted_count: 3, conflict_count: 1, artifact_type_summary: {} };
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      json: async () => result,
    });
    const { result: hook } = renderHook(() => usePromotion("proj1"));
    let res: unknown;
    await act(async () => { res = await hook.current.preview("ctx1"); });
    expect(res).toEqual(result);
    expect(hook.current.loading).toBe(false);
    expect(hook.current.error).toBeNull();
  });

  it("preview sets error on non-200", async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: false,
      json: async () => ({ detail: "Context not found" }),
    });
    const { result: hook } = renderHook(() => usePromotion("proj1"));
    await act(async () => {
      try { await hook.current.preview("ctx1"); } catch { /* expected */ }
    });
    expect(hook.current.error).toBe("Context not found");
  });

  it("promote calls POST and returns result", async () => {
    const result = { promoted_count: 5, conflict_count: 0, artifact_type_summary: {} };
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      json: async () => result,
    });
    const { result: hook } = renderHook(() => usePromotion("proj1"));
    let res: unknown;
    await act(async () => { res = await hook.current.promote("ctx1"); });
    expect(res).toEqual(result);
    const [url, opts] = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(url).toContain("/promote");
    expect(opts.method).toBe("POST");
  });

  it("clearError resets error to null", async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: false,
      json: async () => ({ detail: "error" }),
    });
    const { result: hook } = renderHook(() => usePromotion("proj1"));
    await act(async () => { try { await hook.current.preview("ctx1"); } catch { /* expected */ } });
    expect(hook.current.error).not.toBeNull();
    act(() => { hook.current.clearError(); });
    expect(hook.current.error).toBeNull();
  });
});
