import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { ProgressSteps, stepOf } from "./ProgressSteps";
import { StatusBadge } from "./StatusBadge";

describe("StatusBadge", () => {
  it("names each status in plain words", () => {
    render(<StatusBadge status="needs_review" />);
    expect(screen.getByText("Needs review")).toHaveClass("badge-attention");
  });
  it("marks failures and successes differently", () => {
    const { rerender } = render(<StatusBadge status="failed" />);
    expect(screen.getByText("Failed")).toHaveClass("badge-danger");
    rerender(<StatusBadge status="published" />);
    expect(screen.getByText("Published")).toHaveClass("badge-success");
  });
});

describe("ProgressSteps", () => {
  it("counts steps the way the progress stream does", () => {
    expect(stepOf("queued", null)).toBe(0);
    expect(stepOf("processing", "script")).toBe(4);
    expect(stepOf("published", null)).toBe(8);
  });
  it("announces the current step in words", () => {
    render(<ProgressSteps status="processing" stage="factcheck" />);
    expect(screen.getByText("Step 5 of 8: Fact-check")).toHaveAttribute(
      "aria-live",
      "polite",
    );
  });
});

describe("pipeline explainer", () => {
  it("opens a sentence for each of the eight steps, marking the current one", async () => {
    render(<ProgressSteps status="processing" stage="factcheck" />);
    const help = screen.getByRole("button", { name: "What the steps mean" });
    expect(help).toHaveAttribute("aria-expanded", "false");
    await userEvent.click(help);
    expect(help).toHaveAttribute("aria-expanded", "true");
    const items = screen
      .getAllByRole("listitem")
      .filter((li) => li.closest(".step-guide"));
    expect(items).toHaveLength(8);
    expect(items[4]).toHaveTextContent(/Fact-check\s*now/);
  });
});
