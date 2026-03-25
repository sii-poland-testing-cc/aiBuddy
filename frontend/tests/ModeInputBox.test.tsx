import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ModeInputBox from "../components/ModeInputBox";

// ── Helpers ───────────────────────────────────────────────────────────────────

function renderBox(overrides: Partial<Parameters<typeof ModeInputBox>[0]> = {}) {
  const props = {
    activeMode: "audit" as const,
    onModeChange: vi.fn(),
    lockedModes: [],
    value: "",
    onChange: vi.fn(),
    onSend: vi.fn(),
    attachedFiles: [],
    onRemoveFile: vi.fn(),
    onAttachFiles: vi.fn(),
    ...overrides,
  };
  return { ...render(<ModeInputBox {...props} />), props };
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("ModeInputBox", () => {
  afterEach(() => vi.clearAllMocks());

  // ── Mode pills ──────────────────────────────────────────────────────────────

  it("renders all three mode pills", () => {
    renderBox();
    expect(screen.getByTestId("mode-pill-context")).toBeInTheDocument();
    expect(screen.getByTestId("mode-pill-requirements")).toBeInTheDocument();
    expect(screen.getByTestId("mode-pill-audit")).toBeInTheDocument();
  });

  it("active pill has aria-pressed=true", () => {
    renderBox({ activeMode: "requirements" });
    expect(screen.getByTestId("mode-pill-requirements")).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByTestId("mode-pill-context")).toHaveAttribute("aria-pressed", "false");
  });

  it("clicking an unlocked pill calls onModeChange", async () => {
    const onModeChange = vi.fn();
    renderBox({ activeMode: "audit", onModeChange });
    await userEvent.click(screen.getByTestId("mode-pill-context"));
    expect(onModeChange).toHaveBeenCalledWith("context");
  });

  // ── Locked pills ────────────────────────────────────────────────────────────

  it("locked pill is disabled", () => {
    renderBox({ lockedModes: ["requirements"] });
    expect(screen.getByTestId("mode-pill-requirements")).toBeDisabled();
  });

  it("clicking a locked pill does NOT call onModeChange", async () => {
    const onModeChange = vi.fn();
    renderBox({ lockedModes: ["requirements"], onModeChange });
    await userEvent.click(screen.getByTestId("mode-pill-requirements"));
    expect(onModeChange).not.toHaveBeenCalled();
  });

  it("locked pill renders a lock icon (svg)", () => {
    renderBox({ lockedModes: ["context"] });
    const pill = screen.getByTestId("mode-pill-context");
    expect(pill.querySelector("svg")).toBeTruthy();
  });

  // ── File chips ──────────────────────────────────────────────────────────────

  it("no file chips rendered when attachedFiles is empty", () => {
    renderBox({ attachedFiles: [] });
    expect(screen.queryByTestId("file-chip")).not.toBeInTheDocument();
  });

  it("renders a chip for each attached file", () => {
    renderBox({
      attachedFiles: [
        { name: "suite.xlsx" },
        { name: "scenarios.feature" },
      ],
    });
    expect(screen.getAllByTestId("file-chip")).toHaveLength(2);
    expect(screen.getByText("suite")).toBeInTheDocument();
    expect(screen.getByText("scenarios")).toBeInTheDocument();
  });

  it("× button calls onRemoveFile with correct index", async () => {
    const onRemoveFile = vi.fn();
    renderBox({
      attachedFiles: [{ name: "a.csv" }, { name: "b.json" }],
      onRemoveFile,
    });
    const removeButtons = screen.getAllByRole("button", { name: /remove/i });
    await userEvent.click(removeButtons[0]);
    expect(onRemoveFile).toHaveBeenCalledWith(0);
  });

  // ── Textarea ────────────────────────────────────────────────────────────────

  it("placeholder changes per active mode", () => {
    const { rerender } = renderBox({ activeMode: "context" });
    expect(screen.getByPlaceholderText("Zapytaj o kontekst projektu…")).toBeInTheDocument();

    rerender(
      <ModeInputBox
        activeMode="audit"
        onModeChange={vi.fn()}
        value=""
        onChange={vi.fn()}
        onSend={vi.fn()}
      />
    );
    expect(screen.getByPlaceholderText("Załącz pliki testowe i wpisz polecenie…")).toBeInTheDocument();
  });

  it("typing calls onChange", async () => {
    const onChange = vi.fn();
    renderBox({ onChange });
    await userEvent.type(screen.getByRole("textbox"), "hello");
    expect(onChange).toHaveBeenCalled();
  });

  // ── Send / Stop ─────────────────────────────────────────────────────────────

  it("send button is disabled when value is empty and no files attached", () => {
    renderBox({ value: "", attachedFiles: [] });
    expect(screen.getByTestId("send-btn")).toBeDisabled();
  });

  it("send button is enabled when value is non-empty", () => {
    renderBox({ value: "some text" });
    expect(screen.getByTestId("send-btn")).not.toBeDisabled();
  });

  it("send button is enabled when files are attached even with empty text", () => {
    renderBox({ value: "", attachedFiles: [{ name: "suite.xlsx" }] });
    expect(screen.getByTestId("send-btn")).not.toBeDisabled();
  });

  it("Enter key sends when files are attached but text is empty", async () => {
    const onSend = vi.fn();
    renderBox({ value: "", attachedFiles: [{ name: "suite.xlsx" }], onSend });
    await userEvent.type(screen.getByRole("textbox"), "{Enter}");
    expect(onSend).toHaveBeenCalledTimes(1);
  });

  it("clicking send calls onSend", async () => {
    const onSend = vi.fn();
    renderBox({ value: "go", onSend });
    await userEvent.click(screen.getByTestId("send-btn"));
    expect(onSend).toHaveBeenCalledTimes(1);
  });

  it("shows stop button when loading=true", () => {
    renderBox({ loading: true });
    expect(screen.getByTestId("stop-btn")).toBeInTheDocument();
    expect(screen.queryByTestId("send-btn")).not.toBeInTheDocument();
  });

  it("clicking stop calls onStop", async () => {
    const onStop = vi.fn();
    renderBox({ loading: true, onStop });
    await userEvent.click(screen.getByTestId("stop-btn"));
    expect(onStop).toHaveBeenCalledTimes(1);
  });

  // ── Attach ──────────────────────────────────────────────────────────────────

  it("attach button calls onAttachFiles", async () => {
    const onAttachFiles = vi.fn();
    renderBox({ onAttachFiles });
    await userEvent.click(screen.getByTestId("attach-btn"));
    expect(onAttachFiles).toHaveBeenCalledTimes(1);
  });
});
