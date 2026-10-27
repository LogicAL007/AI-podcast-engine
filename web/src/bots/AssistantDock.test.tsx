import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AssistantProvider, useAssistant, type PageAssist } from "./assistant";
import { ASSISTANT_OFF, AssistantDock } from "./AssistantDock";
import { botFor } from "./botMode";

afterEach(() => {
  window.localStorage.clear();
  vi.unstubAllGlobals();
});

const BASE: PageAssist = {
  page: "episode",
  key: "e1",
  moment: "review",
  mode: "reviewing",
  line: "Ready for your review: read the script, then approve it.",
  hint: "Open the Script tab and edit any line, then press Approve to voice and publish.",
  episodeId: "e1",
};

function Page({ assist }: { assist: PageAssist }) {
  useAssistant(assist);
  return (
    <>
      <p data-tour="first">First thing</p>
      <p data-tour="second">Second thing</p>
    </>
  );
}

function renderDock(assist: PageAssist) {
  const client = new QueryClient({
    defaultOptions: { mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <AssistantProvider>
          <Page assist={assist} />
          <AssistantDock />
        </AssistantProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("assistant dock", () => {
  it("explains a moment the first time, then gives the short line", async () => {
    const { unmount } = renderDock(BASE);
    expect(
      screen.getByText(/press Approve to voice and publish/),
    ).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Got it" }));
    expect(screen.getByText(BASE.line)).toBeInTheDocument();
    unmount();
    // The hint stays dismissed, on this and every other episode.
    renderDock({ ...BASE, key: "e2" });
    expect(
      screen.queryByRole("button", { name: "Got it" }),
    ).not.toBeInTheDocument();
  });

  it("remembers being closed for that place only", async () => {
    const { unmount } = renderDock(BASE);
    await userEvent.click(
      screen.getByRole("button", { name: "Hide the assistant" }),
    );
    unmount();
    const again = renderDock(BASE);
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
    renderDock({ ...BASE, key: "e2" });
    expect(
      screen.getByRole("complementary", { name: "Assistant" }),
    ).toBeInTheDocument();
  });

  it("offers the page's next steps, and asks first before one that spends quota", async () => {
    const approve = vi.fn();
    const openScript = vi.fn();
    renderDock({
      ...BASE,
      actions: [
        { id: "open_script", label: "Open the script", run: openScript },
        {
          id: "approve",
          label: "Approve",
          run: approve,
          confirm: {
            title: "Approve this episode?",
            body: "It will be voiced.",
            confirmLabel: "Approve and publish",
          },
        },
        { id: "cancel", label: "Cancel", hidden: true, run: vi.fn() },
      ],
    });
    const dock = screen.getByRole("complementary", { name: "Assistant" });
    expect(
      within(dock).queryByRole("button", { name: "Cancel" }),
    ).not.toBeInTheDocument();
    await userEvent.click(
      within(dock).getByRole("button", { name: "Open the script" }),
    );
    expect(openScript).toHaveBeenCalledOnce();
    await userEvent.click(
      within(dock).getByRole("button", { name: "Approve" }),
    );
    expect(approve).not.toHaveBeenCalled();
    await userEvent.click(
      screen.getByRole("button", { name: "Approve and publish", hidden: true }),
    );
    expect(approve).toHaveBeenCalledOnce();
  });

  it("answers questions in a log, with buttons for what it suggests", async () => {
    const retry = vi.fn();
    const asked: unknown[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const request =
          input instanceof Request ? input : new Request(String(input), init);
        asked.push(JSON.parse(await request.text()));
        return new Response(
          JSON.stringify({
            answer: "It ran out of quota at the voice step.",
            actions: ["retry", "approve"],
            source: "gemini",
            remaining: 19,
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }),
    );
    renderDock({
      ...BASE,
      hint: undefined,
      questions: ["Why did it stop?"],
      actions: [{ id: "retry", label: "Retry", hidden: true, run: retry }],
    });
    await userEvent.click(screen.getByRole("button", { name: /Ask / }));
    await userEvent.click(
      screen.getByRole("button", { name: "Why did it stop?" }),
    );
    const log = screen.getByRole("log");
    expect(
      await within(log).findByText("It ran out of quota at the voice step."),
    ).toBeInTheDocument();
    expect(asked[0]).toMatchObject({
      question: "Why did it stop?",
      page: "episode",
      episode_id: "e1",
    });
    // Only actions the page offers become buttons ("approve" is not one here).
    expect(
      within(log).queryByRole("button", { name: "Approve" }),
    ).not.toBeInTheDocument();
    await userEvent.click(within(log).getByRole("button", { name: "Retry" }));
    expect(retry).toHaveBeenCalledOnce();
    expect(screen.getByText(/19 questions left this hour/)).toBeInTheDocument();
  });

  it("gives a tour of the page, one element at a time", async () => {
    renderDock({
      ...BASE,
      hint: undefined,
      tour: [
        { target: "first", title: "The first", text: "One." },
        { target: "missing", title: "Not here", text: "Skipped." },
        { target: "second", title: "The second", text: "Two." },
      ],
    });
    await userEvent.click(
      screen.getByRole("button", { name: "Show me around" }),
    );
    const tour = screen.getByRole("dialog", { name: "The first" });
    expect(within(tour).getByText("1 of 2")).toBeInTheDocument();
    expect(within(tour).getByRole("heading")).toHaveFocus();
    await userEvent.click(within(tour).getByRole("button", { name: "Next" }));
    expect(
      screen.getByRole("dialog", { name: "The second" }),
    ).toBeInTheDocument();
    await userEvent.keyboard("{Escape}");
    expect(
      screen.queryByRole("dialog", { name: "The second" }),
    ).not.toBeInTheDocument();
  });

  it("reads its line aloud only once you turn that on", async () => {
    const spoken: { text: string; rate: number }[] = [];
    vi.stubGlobal(
      "SpeechSynthesisUtterance",
      class {
        rate = 1;
        pitch = 1;
        voice: unknown = null;
        onboundary: unknown = null;
        onend: unknown = null;
        onerror: unknown = null;
        constructor(public text: string) {}
      },
    );
    const synth = {
      cancel: vi.fn(),
      speak: vi.fn((u: { text: string; rate: number }) => spoken.push(u)),
      getVoices: () => [],
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    };
    Object.defineProperty(window, "speechSynthesis", {
      value: synth,
      configurable: true,
    });
    renderDock({ ...BASE, hint: undefined });
    expect(spoken).toHaveLength(0);
    await userEvent.click(screen.getByRole("button", { name: "Read aloud" }));
    expect(spoken.at(-1)?.text).toBe(BASE.line);
    expect(
      screen.getByRole("button", { name: "Stop reading aloud" }),
    ).toHaveAttribute("aria-pressed", "true");
    delete (window as { speechSynthesis?: unknown }).speechSynthesis;
  });

  it("stays away everywhere when turned off", () => {
    window.localStorage.setItem(ASSISTANT_OFF, "1");
    renderDock(BASE);
    expect(
      screen.queryByRole("complementary", { name: "Assistant" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Show the assistant" }),
    ).not.toBeInTheDocument();
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
