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
  it("says what is happening in a word that changes with each step", () => {
    const { rerender } = render(
      <ProgressSteps status="processing" stage="ingest" />,
    );
    expect(screen.getByText("Gathering")).toBeInTheDocument();
    expect(
      screen.getByText(/Step 1 of 8 · Reading your sources/),
    ).toBeInTheDocument();
    rerender(<ProgressSteps status="processing" stage="script" />);
    expect(screen.queryByText("Gathering")).not.toBeInTheDocument();
    expect(screen.getByText("Writing")).toBeInTheDocument();
    rerender(<ProgressSteps status="failed" stage="voice" />);
    expect(screen.getByText("Stopped at Voice")).toBeInTheDocument();
    rerender(<ProgressSteps status="published" stage={null} />);
    expect(screen.getByText("Published")).toBeInTheDocument();
  });
  it("fills the bar to finished steps and creeps across the running one", () => {
    const { container, rerender } = render(
      <ProgressSteps status="processing" stage="script" />,
    );
    const fill = () => container.querySelector<HTMLElement>(".progress-fill")!;
    expect(container.querySelector(".progress-moving")).not.toBeNull();
    expect(fill().style.getPropertyValue("--from")).toBe("37.5%"); // 3 of 8 done
    expect(fill().style.getPropertyValue("--to")).toBe("48.75%"); // 90% across step 4
    rerender(<ProgressSteps status="published" stage={null} />);
    expect(fill().style.getPropertyValue("--to")).toBe("100%");
    expect(container.querySelector(".progress-moving")).toBeNull();
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
