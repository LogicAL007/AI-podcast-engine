import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";

import { AssistantDock } from "./AssistantDock";
import { botFor } from "./botMode";

afterEach(() => window.localStorage.clear());

describe("assistant dock", () => {
  it("explains a moment the first time, then gives the short line", async () => {
    const { unmount } = render(
      <AssistantDock episodeId="e1" status="needs_review" stage="factcheck" />,
    );
    expect(
      screen.getByText(/press Approve to voice and publish/),
    ).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Got it" }));
    expect(
      screen.getByText(
        "Ready for your review: read the script, then approve it.",
      ),
    ).toBeInTheDocument();
    unmount();
    // The hint stays dismissed, on this and every other episode.
    render(
      <AssistantDock episodeId="e2" status="needs_review" stage="factcheck" />,
    );
    expect(
      screen.queryByRole("button", { name: "Got it" }),
    ).not.toBeInTheDocument();
  });

  it("remembers being closed for that episode only", async () => {
    const { unmount } = render(
      <AssistantDock episodeId="e1" status="queued" stage={null} />,
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Hide the assistant" }),
    );
    expect(
      screen.getByRole("button", { name: "Show the assistant" }),
    ).toBeInTheDocument();
    unmount();

    const again = render(
      <AssistantDock episodeId="e1" status="queued" stage={null} />,
    );
    expect(
      screen.queryByRole("complementary", { name: "Assistant" }),
    ).not.toBeInTheDocument();
    await userEvent.click(
      screen.getByRole("button", { name: "Show the assistant" }),
    );
    expect(
      screen.getByRole("complementary", { name: "Assistant" }),
    ).toBeInTheDocument();
    again.unmount();

    render(<AssistantDock episodeId="e2" status="queued" stage={null} />);
    expect(
      screen.getByRole("complementary", { name: "Assistant" }),
    ).toBeInTheDocument();
  });

  it("has a hint for every moment it appears in", () => {
    for (const [status, stage] of [
      ["queued", null],
      ["processing", "script"],
      ["processing", "factcheck"],
      ["needs_review", null],
      ["published", null],
    ] as const)
      expect(botFor(status, stage)?.hint.length).toBeGreaterThan(40);
  });
});
