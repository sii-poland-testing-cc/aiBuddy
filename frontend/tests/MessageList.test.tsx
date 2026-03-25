import { describe, it, expect, vi, beforeAll } from "vitest";
import { render, screen } from "@testing-library/react";

beforeAll(() => {
  window.HTMLElement.prototype.scrollIntoView = vi.fn();
});
import userEvent from "@testing-library/user-event";
import MessageList from "../components/MessageList";
import type { ChatMessage } from "../lib/useAIBuddyChat";
import type { GlossaryTerm } from "../components/Glossary";

const GLOSSARY: GlossaryTerm[] = [
  { term: "Settlement", definition: "Transfer of funds.", related_terms: [] },
  { term: "Reconciliation", definition: "Matching of records.", related_terms: [] },
];

const MSG_WITH_TERMS: ChatMessage = {
  id: "1",
  role: "assistant",
  content: "**Powiązane terminy** — Settlement, Reconciliation",
  timestamp: new Date(),
};

const MSG_PLAIN: ChatMessage = {
  id: "2",
  role: "assistant",
  content: "Hello world",
  timestamp: new Date(),
};

describe("MessageList", () => {
  it("renders plain messages without crashing", () => {
    render(<MessageList messages={[MSG_PLAIN]} isLoading={false} />);
    expect(screen.getByText("Hello world")).toBeTruthy();
  });

  it("test_related_terms_rendered_as_chips", async () => {
    const handler = vi.fn();
    const { container } = render(
      <MessageList
        messages={[MSG_WITH_TERMS]}
        isLoading={false}
        onTermClick={handler}
        glossary={GLOSSARY}
      />,
    );

    // Both terms should appear as clickable spans (cursor: pointer)
    const chips = container.querySelectorAll<HTMLElement>("span[style*='pointer']");
    expect(chips.length).toBe(2);

    // Clicking first chip calls handler with Settlement glossary item
    await userEvent.click(screen.getByText("Settlement"));
    expect(handler).toHaveBeenCalledOnce();
    expect(handler).toHaveBeenCalledWith(GLOSSARY[0]);
  });

  it("detects marker with capital T (Powiązane Terminy)", () => {
    const handler = vi.fn();
    const msg: ChatMessage = {
      id: "3", role: "assistant",
      content: "**Powiązane Terminy** — Settlement",
      timestamp: new Date(),
    };
    render(
      <MessageList messages={[msg]} isLoading={false} onTermClick={handler} glossary={GLOSSARY} />,
    );
    // Settlement should be rendered as a chip
    expect(screen.getByText("Settlement")).toBeTruthy();
  });

  it("detects marker followed by colon (Powiązane terminy:)", () => {
    const msg: ChatMessage = {
      id: "4", role: "assistant",
      content: "**Powiązane terminy:** Settlement",
      timestamp: new Date(),
    };
    render(<MessageList messages={[msg]} isLoading={false} glossary={GLOSSARY} />);
    expect(screen.getByText("Settlement")).toBeTruthy();
  });

  it("test_unknown_terms_not_clickable", () => {
    const { container } = render(
      <MessageList
        messages={[MSG_WITH_TERMS]}
        isLoading={false}
        glossary={[]}
      />,
    );

    // No chips — empty glossary means no matches
    const chips = container.querySelectorAll<HTMLElement>("span[style*='pointer']");
    expect(chips.length).toBe(0);
  });
});
