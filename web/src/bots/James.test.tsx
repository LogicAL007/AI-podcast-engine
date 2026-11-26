import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AssistantProvider, useAssistant, type PageAssist } from "./assistant";
import { complete } from "./avatar";
import { James } from "./James";

afterEach(() => {
  window.localStorage.clear();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

const BASE: PageAssist = {
  page: "episode",
  key: "e1",
  moment: "making",
  mode: "working",
  line: "Writing the script now.",
  hint: "This takes a few minutes. You can leave the page.",
  episodeId: "e1",
  context: "Episode 3",
  questions: ["How long will it take?"],
};

function Page({
  assist,
  onRetry = () => {},
}: {
  assist: PageAssist;
  onRetry?: () => void;
}) {
  useAssistant({
    ...assist,
    actions: [
      { id: "retry", label: "Retry", run: onRetry },
      { id: "open_listen", label: "Listen", run: () => {}, hidden: true },
      {
        id: "approve",
        label: "Approve",
        run: () => {},
        confirm: {
          title: "Approve this episode?",
          body: "It will be voiced.",
          confirmLabel: "Approve and publish",
        },
      },
    ],
  });
  return <input aria-label="Some field" />;
}

function tree(assist: PageAssist, onRetry?: () => void) {
  return (
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { mutations: { retry: false } } })
      }
    >
      <MemoryRouter>
        <AssistantProvider>
          <Page assist={assist} onRetry={onRetry} />
          <James />
        </AssistantProvider>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

const james = () => screen.getByRole("button", { name: /James \(⌘J\)/ });

describe("James", () => {
  it("rests in the corner, working while the episode is made", () => {
    render(tree(BASE));
    expect(james()).toHaveAttribute("aria-expanded", "false");
    expect(james()).toHaveClass("james-mood-working");
    expect(screen.queryByRole("complementary")).not.toBeInTheDocument();
  });

  it("opens with ⌘J, says what he is looking at, and closes with Escape", async () => {
    render(tree(BASE));
    const user = userEvent.setup();
    await user.keyboard("{Meta>}j{/Meta}");
    const panel = screen.getByRole("complementary", { name: "James" });
    expect(within(panel).getByText("Episode 3")).toBeInTheDocument();
    // The first time, the tip; the page's standing actions under it.
    expect(within(panel).getByText(BASE.hint as string)).toBeInTheDocument();
    expect(
      within(panel).getByRole("button", { name: "Retry" }),
    ).toBeInTheDocument();
    expect(
      within(panel).queryByRole("button", { name: "Listen" }),
    ).not.toBeInTheDocument();
    expect(
      within(panel).getByRole("button", { name: "How long will it take?" }),
    ).toBeInTheDocument();
    expect(within(panel).getByLabelText("Ask James")).toHaveFocus();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("complementary")).not.toBeInTheDocument();
    expect(james()).toHaveFocus();
  });

  it("answers a question, offering only the page's real actions", async () => {
    const asked: unknown[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const request =
          input instanceof Request ? input : new Request(String(input), init);
        asked.push(await request.json());
        return new Response(
          JSON.stringify({
            answer: "It stopped at voicing. Retry carries on.",
            actions: ["retry", "approve", "unknown"],
            remaining: 7,
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }),
    );
    render(tree(BASE));
    const user = userEvent.setup();
    await user.click(james());
    await user.type(screen.getByLabelText("Ask James"), "What happened?");
    await user.click(screen.getByRole("button", { name: "Send" }));
    expect(
      await screen.findByText("It stopped at voicing. Retry carries on."),
    ).toBeInTheDocument();
    expect(asked).toEqual([
      {
        question: "What happened?",
        page: "episode",
        episode_id: "e1",
        show_id: null,
      },
    ]);
    expect(screen.getByText("7 questions left this hour")).toBeInTheDocument();
    // An action that spends quota asks first.
    const approves = screen.getAllByRole("button", { name: "Approve" });
    await user.click(approves[approves.length - 1]);
    expect(screen.getByRole("dialog", { hidden: true })).toHaveTextContent(
      "Approve this episode?",
    );
  });

  it("nudges when something finishes during the visit, never for what was already so", async () => {
    const onRetry = vi.fn();
    const { rerender } = render(
      tree(
        { ...BASE, nudge: { id: "e1:published", text: "Already done." } },
        onRetry,
      ),
    );
    expect(screen.queryByRole("status")).not.toBeInTheDocument(); // the baseline is not news
    rerender(
      tree(
        {
          ...BASE,
          nudge: {
            id: "e1:failed",
            text: "Episode 3 stopped.",
            action: "retry",
            tone: "problem",
          },
        },
        onRetry,
      ),
    );
    const nudge = await screen.findByRole("status");
    expect(nudge).toHaveTextContent("Episode 3 stopped.");
    expect(james()).toHaveClass("james-mood-concerned");
    await userEvent.click(within(nudge).getByRole("button", { name: "Retry" }));
    expect(onRetry).toHaveBeenCalled();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    // Only once a visit.
    rerender(
      tree(
        {
          ...BASE,
          nudge: { id: "e1:published:2", text: "Episode 3 is ready." },
        },
        onRetry,
      ),
    );
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("keeps quiet when asked to, or snoozed", async () => {
    window.localStorage.setItem("pe.james.chattiness", "quiet");
    const { rerender } = render(
      tree({ ...BASE, nudge: { id: "a", text: "One." } }),
    );
    rerender(tree({ ...BASE, nudge: { id: "b", text: "Two." } }));
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    window.localStorage.setItem("pe.james.chattiness", "helpful");
    window.localStorage.setItem("pe.james.snooze", String(Date.now() + 60_000));
    const second = render(
      tree({ ...BASE, key: "e2", nudge: { id: "c", text: "Three." } }),
    );
    second.rerender(
      tree({ ...BASE, key: "e2", nudge: { id: "d", text: "Four." } }),
    );
    expect(screen.queryByText("Four.")).not.toBeInTheDocument();
  });

  it("waits for you to stop typing, then fades after a few seconds", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const { rerender } = render(
      tree({ ...BASE, nudge: { id: "a", text: "One." } }),
    );
    screen.getByLabelText("Some field").focus();
    rerender(
      tree({ ...BASE, nudge: { id: "b", text: "Episode 3 is ready." } }),
    );
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    act(() => {
      screen.getByLabelText("Some field").blur();
      vi.advanceTimersByTime(1100);
    });
    expect(screen.getByRole("status")).toHaveTextContent("Episode 3 is ready.");
    act(() => vi.advanceTimersByTime(8100));
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("is James unless you named him something else", () => {
    expect(complete(null).name).toBe("James");
    expect(complete({ name: "Scout" }).name).toBe("James");
    expect(complete({ name: "Ada" }).name).toBe("Ada");
  });
});
