import { describe, it, expect, vi, beforeEach } from "vitest";

// Mock fetch globally before importing the module
const mockFetch = vi.fn().mockResolvedValue(new Response("ok"));
vi.stubGlobal("fetch", mockFetch);

// Import after mocking
import { apiFetch, API_BASE } from "@/lib/apiFetch";

describe("apiFetch", () => {
  beforeEach(() => {
    mockFetch.mockClear();
  });

  it("prepends API_BASE to path", async () => {
    await apiFetch("/api/projects");
    expect(mockFetch).toHaveBeenCalledWith(
      `${API_BASE}/api/projects`,
      expect.objectContaining({ credentials: "include" })
    );
  });

  it("always includes credentials: include", async () => {
    await apiFetch("/api/test", { method: "POST" });
    const [, init] = mockFetch.mock.calls[0];
    expect(init.credentials).toBe("include");
  });

  it("merges caller RequestInit", async () => {
    await apiFetch("/api/test", { method: "POST", headers: { "X-Custom": "1" } });
    const [, init] = mockFetch.mock.calls[0];
    expect(init.method).toBe("POST");
    expect(init.headers).toEqual({ "X-Custom": "1" });
    expect(init.credentials).toBe("include");
  });

  it("credentials cannot be overridden by caller", async () => {
    await apiFetch("/api/test", { credentials: "omit" } as RequestInit);
    const [, init] = mockFetch.mock.calls[0];
    expect(init.credentials).toBe("include");
  });
});
