/**
 * Regression tests for ProjectPage wiring.
 *
 * Bug 1: Glossary term click must call send() directly — NOT setInputValue.
 *        If it populates the textarea instead, the message is never sent until
 *        the user manually clicks Send.
 *
 * Bug 2: Switching to "context" mode must set tier="rag_chat" so the backend
 *        routes through the RAG pipeline. Using tier="audit" in context mode
 *        returns a fallback/generic response because the wyjaśnij termin:
 *        detection only works with rag_chat tier.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import React from "react";

// ── next/navigation ──────────────────────────────────────────────────────────

let mockSearchParams = new URLSearchParams();

vi.mock("next/navigation", () => ({
  useParams: () => ({ projectId: "test-project" }),
  useSearchParams: () => mockSearchParams,
}));

// ── useAIBuddyChat — capture tier arg and expose send spy ───────────────────

const mockSend = vi.fn().mockResolvedValue(undefined);
let capturedChatConfig: { projectId: string; tier: string } | null = null;

vi.mock("@/lib/useAIBuddyChat", () => ({
  useAIBuddyChat: (config: { projectId: string; tier: string }) => {
    capturedChatConfig = config;
    return {
      messages: [],
      progress: null,
      isLoading: false,
      error: null,
      latestSnapshotId: undefined,
      send: mockSend,
      stop: vi.fn(),
      clearError: vi.fn(),
    };
  },
}));

// ── Other hooks — minimal stubs ───────────────────────────────────────────────

const mockBuildContext = vi.fn().mockResolvedValue(undefined);

vi.mock("@/lib/useContextBuilder", () => ({
  useContextBuilder: () => ({
    result: null,
    status: null,
    isBuilding: false,
    buildContext: mockBuildContext,
    fetchStatus: vi.fn(),
  }),
}));

vi.mock("@/lib/useProjectFiles", () => ({
  useProjectFiles: () => ({ files: [], uploading: false, uploadFiles: vi.fn() }),
}));

vi.mock("@/lib/useHeatmap", () => ({
  useHeatmap: () => ({ heatmap: [], retry: vi.fn() }),
}));

vi.mock("@/lib/useRequirements", () => ({
  useRequirements: () => ({
    requirements: [],
    stats: null,
    loading: false,
    error: null,
    isExtracting: false,
    extractionProgress: null,
    extractRequirements: vi.fn(),
    patchRequirement: vi.fn(),
    refresh: vi.fn(),
  }),
}));

// ── Snapshots — mock fetch ───────────────────────────────────────────────────

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn(() =>
      Promise.resolve({ ok: true, json: () => Promise.resolve([]) })
    )
  );
});

// ── Heavy components — lightweight mocks ─────────────────────────────────────
//
// UtilityPanel exposes a "Click Term" button that fires onTermClick so we can
// test the wiring without fully rendering the panel internals.
// It also renders the current tier via data-testid so tier changes are visible.

vi.mock("@/components/UtilityPanel", () => ({
  default: ({ onTermClick, tier, onBuild, buildMode }: any) => (
    <div data-testid="utility-panel-mock">
      <span data-testid="panel-tier">{tier}</span>
      <button
        data-testid="term-click-btn"
        onClick={() => onTermClick?.("TestTerm")}
      >
        Click Term
      </button>
      <button
        data-testid="build-btn"
        onClick={() => onBuild?.(buildMode ?? "append")}
      >
        Uruchom budowanie
      </button>
    </div>
  ),
}));

vi.mock("@/components/MindMapModal", () => ({
  default: () => null,
  layoutModalNodes: () => [],
}));

vi.mock("@/components/MessageList", () => ({
  default: () => <div data-testid="message-list" />,
}));

vi.mock("@/components/RequirementsView", () => ({
  default: () => <div data-testid="requirements-view" />,
}));

vi.mock("@/components/TopBar", () => ({
  default: () => <div data-testid="top-bar" />,
}));

// ── Import page AFTER all mocks are registered ────────────────────────────────

// eslint-disable-next-line @typescript-eslint/no-var-requires
const { default: ProjectPage } = await import(
  "../app/project/[projectId]/page"
);

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("ProjectPage — regression tests", () => {
  afterEach(() => {
    vi.clearAllMocks();
    capturedChatConfig = null;
    mockSearchParams = new URLSearchParams();
  });

  // ── Bug 1: Glossary term click must call send() immediately ─────────────────

  describe("Bug 1 — glossary term click sends immediately", () => {
    it("clicking a glossary term calls send() with the term message", async () => {
      render(<ProjectPage />);
      await userEvent.click(screen.getByTestId("term-click-btn"));
      expect(mockSend).toHaveBeenCalledTimes(1);
      expect(mockSend).toHaveBeenCalledWith("wyjaśnij termin: TestTerm", []);
    });

    it("clicking a glossary term does NOT just set input value (no extra send needed)", async () => {
      render(<ProjectPage />);
      await userEvent.click(screen.getByTestId("term-click-btn"));
      // send was called exactly once — user didn't have to press Send separately
      expect(mockSend).toHaveBeenCalledTimes(1);
    });
  });

  // ── Bug 2: Tier must match active mode ──────────────────────────────────────

  describe("Bug 2 — tier tracks active mode", () => {
    it("default mode (audit) initializes tier as 'audit'", () => {
      render(<ProjectPage />);
      expect(capturedChatConfig?.tier).toBe("audit");
    });

    it("?mode=context initializes tier as 'rag_chat'", async () => {
      mockSearchParams = new URLSearchParams("mode=context");
      render(<ProjectPage />);
      expect(capturedChatConfig?.tier).toBe("rag_chat");
    });

    it("?mode=requirements initializes tier as 'audit'", async () => {
      mockSearchParams = new URLSearchParams("mode=requirements");
      render(<ProjectPage />);
      expect(capturedChatConfig?.tier).toBe("audit");
    });

    it("switching to context mode via pill updates tier to 'rag_chat'", async () => {
      render(<ProjectPage />);
      // Start in audit mode — tier should be "audit"
      expect(screen.getByTestId("panel-tier").textContent).toBe("audit");

      // Click the "Context Builder" mode pill
      await userEvent.click(screen.getByTestId("mode-pill-context"));

      // UtilityPanel mock renders the current tier — should now be rag_chat
      expect(screen.getByTestId("panel-tier").textContent).toBe("rag_chat");
    });

    it("switching from context back to audit resets tier to 'audit'", async () => {
      mockSearchParams = new URLSearchParams("mode=context");
      render(<ProjectPage />);

      expect(screen.getByTestId("panel-tier").textContent).toBe("rag_chat");

      await userEvent.click(screen.getByTestId("mode-pill-audit"));

      expect(screen.getByTestId("panel-tier").textContent).toBe("audit");
    });

    it("switching to requirements mode sets tier to 'audit' (not rag_chat)", async () => {
      mockSearchParams = new URLSearchParams("mode=context");
      render(<ProjectPage />);

      await userEvent.click(screen.getByTestId("mode-pill-requirements"));

      expect(screen.getByTestId("panel-tier").textContent).toBe("audit");
    });
  });

  // ── Bug fixes: context rebuild ──────────────────────────────────────────────

  describe("Context rebuild", () => {
    afterEach(() => {
      vi.clearAllMocks();
      capturedChatConfig = null;
      mockSearchParams = new URLSearchParams();
    });

    it("'Uruchom budowanie' calls buildContext with empty files array (no file picker)", async () => {
      mockSearchParams = new URLSearchParams("mode=context");
      render(<ProjectPage />);
      await userEvent.click(screen.getByTestId("build-btn"));
      expect(mockBuildContext).toHaveBeenCalledTimes(1);
      expect(mockBuildContext).toHaveBeenCalledWith([], expect.any(String));
    });

    it("typing 'rebuild context' in context mode calls buildContext, not send", async () => {
      mockSearchParams = new URLSearchParams("mode=context");
      render(<ProjectPage />);

      await userEvent.type(screen.getByRole("textbox"), "rebuild context");
      await userEvent.click(screen.getByTestId("send-btn"));

      expect(mockBuildContext).toHaveBeenCalledTimes(1);
      expect(mockBuildContext).toHaveBeenCalledWith([], expect.any(String));
      expect(mockSend).not.toHaveBeenCalled();
    });

    it("typing 'przebuduj kontekst' in context mode calls buildContext, not send", async () => {
      mockSearchParams = new URLSearchParams("mode=context");
      render(<ProjectPage />);

      await userEvent.type(screen.getByRole("textbox"), "przebuduj kontekst");
      await userEvent.click(screen.getByTestId("send-btn"));

      expect(mockBuildContext).toHaveBeenCalledTimes(1);
      expect(mockSend).not.toHaveBeenCalled();
    });

    it("rebuild command in audit mode does NOT trigger buildContext (sent normally)", async () => {
      render(<ProjectPage />); // default = audit mode
      await userEvent.type(screen.getByRole("textbox"), "rebuild context");
      await userEvent.click(screen.getByTestId("send-btn"));

      expect(mockBuildContext).not.toHaveBeenCalled();
      expect(mockSend).toHaveBeenCalledWith("rebuild context", expect.any(Array));
    });

    it("context mode send does NOT include panel file paths", async () => {
      // Override fetch to return a selected panel file
      vi.stubGlobal(
        "fetch",
        vi.fn((url: string) => {
          if (url.includes("audit-selection")) {
            return Promise.resolve({
              ok: true,
              json: () => Promise.resolve([
                { id: "f1", filename: "suite.xlsx", file_path: "/uploads/suite.xlsx", source_type: "file", selected: true, last_used_in_audit_id: null },
              ]),
            });
          }
          return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
        })
      );

      mockSearchParams = new URLSearchParams("mode=context");
      render(<ProjectPage />);

      await userEvent.type(screen.getByRole("textbox"), "explain term");
      await userEvent.click(screen.getByTestId("send-btn"));

      expect(mockSend).toHaveBeenCalledWith("explain term", []);
    });
  });
});
