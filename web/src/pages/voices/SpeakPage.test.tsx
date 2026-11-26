import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SpeakPage } from "./SpeakPage";

const ENGINE: Record<string, unknown> = {
  backend: "chatterbox",
  recorded_voices: true,
  engine_voices: [
    { host: "Alex", label: "Alex" },
    { host: "Sam", label: "Sam" },
  ],
  uses_quota: false,
  clips_left_today: null,
  max_characters: 600,
  deliveries: ["neutral", "warm"],
  presets: {},
};
const VOICE = {
  voice_id: "v1",
  name: "My voice",
  speaker: "Ada",
  duration_seconds: 12,
  created_at: "2026-10-05T10:00:00Z",
};
const clip = (status: string, extra: object = {}) => ({
  clip_id: "c1",
  voice: { kind: "recorded", voice_id: "v1" },
  text: "Hello there.",
  delivery: "warm",
  effects: { deepen: 40, warmth: 20, broadcast: false },
  status,
  duration_s: null,
  error: null,
  created_at: "2026-11-13T10:00:00Z",
  finished_at: null,
  audio: status === "done" ? "/v1/speech/c1/audio.wav" : null,
  ...extra,
});

/** The API: the engine, one voice, and a clip that is queued once, then `finished`. */
function serve({
  engine = ENGINE,
  finished = clip("done"),
  create = 202,
}: {
  engine?: Record<string, unknown>;
  finished?: object;
  create?: number;
} = {}) {
  const posted: unknown[] = [];
  let polls = 0;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const request =
        input instanceof Request ? input : new Request(String(input), init);
      const url = new URL(request.url, "http://localhost");
      const json = (
        body: unknown,
        status = 200,
        headers: Record<string, string> = {},
      ) =>
        new Response(JSON.stringify(body), {
          status,
          headers: { "Content-Type": "application/json", ...headers },
        });
      if (url.pathname.endsWith("/v1/speech/engine")) return json(engine);
      if (url.pathname.endsWith("/v1/voices"))
        return json({ items: [VOICE], total: 1, limit: 100, offset: 0 });
      if (url.pathname.endsWith("/v1/speech") && request.method === "POST") {
        posted.push(await request.json());
        return create === 429
          ? json({ detail: "You have made 30 clips this hour" }, 429, {
              "Retry-After": "600",
            })
          : json(clip("queued"), 202);
      }
      if (url.pathname.endsWith("/v1/speech/c1"))
        return json(polls++ === 0 ? clip("queued") : finished);
      return new Response(new Blob([]), { status: 200 });
    }),
  );
  return posted;
}

function renderPage(path = "/voices/speak") {
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <MemoryRouter initialEntries={[path]}>
        <SpeakPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("type to speech", () => {
  it("voices a line in a recorded voice with an effect, then has it ready", async () => {
    const posted = serve();
    renderPage("/voices/speak?voice=v1");
    const user = userEvent.setup();
    await screen.findByRole("option", { name: "My voice" });
    expect(
      screen.getByRole("img", { name: "Voice, idle" }),
    ).toBeInTheDocument();
    await user.type(screen.getByLabelText(/Text/), "Hello there.");
    await user.selectOptions(screen.getByLabelText("Style"), "warm");
    await user.click(screen.getByRole("radio", { name: "Deeper" }));
    await user.click(screen.getByRole("button", { name: "Speak" }));

    expect(await screen.findByText("Preparing the voice…")).toBeInTheDocument();
    expect(posted).toEqual([
      {
        text: "Hello there.",
        voice: { kind: "recorded", voice_id: "v1" },
        delivery: "warm",
        effects: { deepen: 40, warmth: 20, broadcast: false },
      },
    ]);
    expect(
      await screen.findByRole("link", { name: "Download" }, { timeout: 4000 }),
    ).toHaveAttribute("href", "/api/v1/speech/c1/audio.wav?download=true");
    expect(
      screen.getByRole("link", { name: "Use in Show sound" }),
    ).toBeInTheDocument();
  });

  it("says when a clip fails, and offers to try again", async () => {
    serve({ finished: clip("failed", { error: "That voice was deleted." }) });
    renderPage();
    const user = userEvent.setup();
    await screen.findByRole("option", { name: "My voice" });
    await user.type(screen.getByLabelText(/Text/), "Hi.");
    await user.click(screen.getByRole("button", { name: "Speak" }));
    expect(
      await screen.findByText("That voice was deleted.", {}, { timeout: 4000 }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Couldn't create" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Try again" }),
    ).toBeInTheDocument();
  });

  it("offers only the engine's voices where it can't clone, without naming the engine", async () => {
    serve({
      engine: {
        ...ENGINE,
        backend: "gemini",
        recorded_voices: false,
        uses_quota: true,
        clips_left_today: 3,
      },
    });
    renderPage();
    expect(await screen.findByText("3 left today")).toBeInTheDocument();
    expect(
      screen.queryByRole("option", { name: "My voice" }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Alex" })).toBeInTheDocument();
    expect(screen.queryByText(/chatterbox|gemini/i)).not.toBeInTheDocument();
  });

  it("shows the hourly limit plainly", async () => {
    serve({ create: 429 });
    renderPage();
    const user = userEvent.setup();
    await screen.findByRole("option", { name: "My voice" });
    await user.type(screen.getByLabelText(/Text/), "Hi.");
    await user.click(screen.getByRole("button", { name: "Speak" }));
    expect(
      await screen.findByRole("heading", { name: "Limit reached" }),
    ).toBeInTheDocument();
    expect(screen.getByText(/Try again at/)).toBeInTheDocument();
  });
});
