import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import InfoBanner from "@/components/InfoBanner";

describe("InfoBanner", () => {
  it("renders the message", () => {
    render(<InfoBanner message="Wszystkie pliki są już zaindeksowane." />);
    expect(screen.getByText("Wszystkie pliki są już zaindeksowane.")).toBeInTheDocument();
  });

  it("renders the checkmark icon", () => {
    render(<InfoBanner message="Done" />);
    expect(screen.getByText("✓")).toBeInTheDocument();
  });

  it("shows dismiss button when onDismiss is provided", () => {
    render(<InfoBanner message="Done" onDismiss={() => {}} />);
    expect(screen.getByLabelText("Zamknij")).toBeInTheDocument();
  });

  it("does not render dismiss button when onDismiss is omitted", () => {
    render(<InfoBanner message="Done" />);
    expect(screen.queryByLabelText("Zamknij")).not.toBeInTheDocument();
  });

  it("calls onDismiss when dismiss button is clicked", async () => {
    const onDismiss = vi.fn();
    render(<InfoBanner message="Done" onDismiss={onDismiss} />);
    await userEvent.click(screen.getByLabelText("Zamknij"));
    expect(onDismiss).toHaveBeenCalledTimes(1);
  });
});
