const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/**
 * Thin wrapper around fetch() that:
 * - Prepends API_BASE to relative paths
 * - Always sends credentials: "include" for httpOnly cookie transport
 *
 * Usage: apiFetch("/api/projects") instead of fetch(`${API_BASE}/api/projects`)
 */
export function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  return fetch(`${API_BASE}${path}`, {
    ...init,
    credentials: "include",
  });
}

/** Re-export for hooks that need the base URL directly (e.g., SSE URL construction). */
export { API_BASE };
