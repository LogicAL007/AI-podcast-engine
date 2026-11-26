import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { envelopeOf } from "./playback";
import { MusicTab } from "./MusicTab";
import { changesBetween, ShowSoundTab } from "./ShowSoundTab";
import { octagonPath } from "./VoiceOctagon";
import { VoiceStudio } from "./VoiceStudio";

const page = (items: unknown[]) => ({
  items,
  total: items.length,
  limit: 20,
  offset: 0,
});
const TRACKS = [
  {
    track_id: "builtin:calm-pad",
    name: "Calm pad",
    role: "bed",
    builtin: true,
    description: "",
    credit: "",
    duration_seconds: 32,
    created_at: null,
    audio: "/v1/music/builtin:calm-pad/audio.wav",
  },
  {
    track_id: "builtin:two-note-sting",
    name: "Two-note sting",
    role: "sting",
    builtin: true,
    description: "",
    credit: "",
    duration_seconds: 1.6,
    created_at: null,
    audio: "/v1/music/builtin:two-note-sting/audio.wav",
  },
];
const SHOW = {
  show_id: "s1",
  topic: "How the Moon makes the tides",
  host_count: 2,
  host_voices: {},
  host_effects: {},
  music: {
    intro: null,
    outro: null,
    sting: null,
    bed: null,
    bed_level_db: -22,
  },
  sources: [],
  created_at: "2026-10-01T10:00:00Z",
};
const PUBLISHED = {
  episode_id: "e1",
  show_id: "s1",
  status: "published",
  revision: 3,
  created_at: "2026-10-02T10:00:00Z",
};

function serve() {
  const calls: { method: string; path: string; body: unknown }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const request =
        input instanceof Request ? input : new Request(String(input), init);
      const path = new URL(request.url, "http://localhost").pathname.replace(
        /^\/api/,
        "",
      );
      const body =
        request.method === "GET"
          ? null
          : await request.text().catch(() => null);
      calls.push({
        method: request.method,
        path,
        body: body ? JSON.parse(body) : null,
      });
      const routes: Record<string, unknown> = {
        "/v1/shows": page([SHOW]),
        "/v1/shows/s1": SHOW,
        "/v1/shows/s1/episodes": page([PUBLISHED]),
        "/v1/voices": page([]),
        "/v1/music": TRACKS,
        "/v1/episodes/e1/remix": { ...PUBLISHED, status: "queued" },
      };
      const found = routes[path];
      const result =
        request.method === "PATCH" && path === "/v1/shows/s1"
          ? { ...SHOW, ...JSON.parse(String(body)) }
          : (found ?? {});
      return new Response(JSON.stringify(result), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }),
  );
  return calls;
}

function renderAt(path: string) {
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/voices" element={<VoiceStudio />}>
            <Route index element={<p>Voices tab</p>} />
            <Route path="music" element={<MusicTab />} />
            <Route path="show-sound" element={<ShowSoundTab />} />
          </Route>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("voice studio", () => {
  it("is one page with four tabs, the current one marked", () => {
    serve();
    renderAt("/voices");
    const tabs = within(
      screen.getByRole("navigation", { name: "Voice studio" }),
    );
    expect(tabs.getAllByRole("link").map((l) => l.textContent)).toEqual([
      "Voices",
      "Type to speech",
      "Music",
      "Show sound",
    ]);
    expect(tabs.getByRole("link", { name: "Voices" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(screen.getByRole("link", { name: "Add voice" })).toHaveAttribute(
      "href",
      "/voices/new",
    );
  });

  it("asks for the rights before uploading music", async () => {
    const calls = serve();
    renderAt("/voices/music");
    expect(await screen.findByText("Calm pad")).toBeInTheDocument();
    await userEvent.upload(
      screen.getByLabelText("Audio file"),
      new File([new Uint8Array([1, 2, 3])], "theme.mp3", {
        type: "audio/mpeg",
      }),
    );
    expect(screen.getByLabelText("Name")).toHaveValue("theme");
    await userEvent.click(screen.getByRole("button", { name: "Upload" }));
    expect(
      screen.getByText("Confirm that you have the rights to this music."),
    ).toBeInTheDocument();
    expect(calls.some((c) => c.method === "POST")).toBe(false);
  });

  it("saves a show's sound, then offers to remix the latest episode", async () => {
    const calls = serve();
    renderAt("/voices/show-sound");
    const user = userEvent.setup();
    const alex = await screen.findByRole("article", { name: "Alex" });
    await user.click(
      within(alex).getByRole("radio", { name: "Deep broadcast" }),
    );
    await user.selectOptions(
      await screen.findByLabelText("Background"),
      "builtin:calm-pad",
    );
    await user.click(screen.getByRole("button", { name: "Save" }));

    const saved = calls.find((c) => c.method === "PATCH");
    expect(saved?.body).toEqual({
      host_voices: {},
      host_effects: { Alex: { deepen: 40, warmth: 40, broadcast: true } },
      music: {
        intro: null,
        sting: null,
        bed: "builtin:calm-pad",
        outro: null,
        bed_level_db: -22,
      },
    });
    const dialog = await screen.findByRole("dialog", { hidden: true });
    expect(
      within(dialog).getByText("Alex: Deep broadcast"),
    ).toBeInTheDocument();
    expect(
      within(dialog).getByText("Background: Calm pad"),
    ).toBeInTheDocument();
    await user.click(
      within(dialog).getByRole("button", { name: "Remix", hidden: true }),
    );
    expect(
      calls.some(
        (c) => c.method === "POST" && c.path === "/v1/episodes/e1/remix",
      ),
    ).toBe(true);
    expect(await screen.findByText(/Remixing/)).toBeInTheDocument();
  });

  it("carries a voice and effect over from Type to speech to a host", async () => {
    serve();
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter
          initialEntries={[
            {
              pathname: "/voices/show-sound",
              state: {
                use: {
                  voice: "engine:Alex",
                  effects: { deepen: 40, warmth: 20, broadcast: false },
                },
              },
            },
          ]}
        >
          <Routes>
            <Route path="/voices/show-sound" element={<ShowSoundTab />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    const carried = await screen.findByRole("region", {
      name: "Use from Type to speech",
    });
    await userEvent.click(within(carried).getByRole("button", { name: "Sam" }));
    const sam = screen.getByRole("article", { name: "Sam" });
    expect(within(sam).getByRole("radio", { name: "Deeper" })).toBeChecked();
    expect(
      screen.queryByRole("region", { name: "Use from Type to speech" }),
    ).not.toBeInTheDocument();
  });
});

describe("pieces", () => {
  it("draws a closed, rounded octagon that moves with the level", () => {
    const still = octagonPath(260, 260, 170);
    expect(still.startsWith("M")).toBe(true);
    expect(still.endsWith("Z")).toBe(true);
    expect(still.match(/Q/g)).toHaveLength(8);
    expect(octagonPath(260, 260, 170, 1, 0.1)).not.toEqual(still);
  });

  it("measures a clip's loudness over time", () => {
    const samples = new Float32Array(24_000);
    samples.fill(0.5, 12_000);
    const envelope = envelopeOf(samples, 24_000);
    expect(envelope).toHaveLength(50);
    expect(envelope[10]).toBe(0);
    expect(envelope[40]).toBeCloseTo(1);
  });

  it("lists what changed, by name", () => {
    const base = {
      voices: {},
      effects: {},
      music: { intro: "", sting: "", bed: "", outro: "", level: -22 },
    };
    const after = {
      ...base,
      effects: { Sam: { deepen: 0, warmth: 60, broadcast: false } },
      music: { ...base.music, sting: "builtin:two-note-sting", level: -26 },
    };
    expect(
      changesBetween(base, after, ["Alex", "Sam"], [], TRACKS as never),
    ).toEqual([
      "Sam: Warm",
      "Between segments: Two-note sting",
      "Background level: Quiet",
    ]);
  });
});
