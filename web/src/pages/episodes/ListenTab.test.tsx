import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { EpisodeRead } from "../../api/types";
import { ListenTab } from "./ListenTab";

function episode(voice_provider: string | null): EpisodeRead {
  return {
    episode_id: "e1",
    show_id: "s1",
    status: "published",
    stage: "publish",
    error: null,
    revision: 1,
    rewrite_count: 0,
    created_at: "2026-10-24T09:00:00Z",
    published_at: "2026-10-24T09:06:00Z",
    approved_at: null,
    voice_provider,
    links: {
      self: "/v1/episodes/e1",
      script: "/v1/episodes/e1/script",
      runs: "/v1/episodes/e1/runs",
      audio: "/v1/episodes/e1/audio.wav",
      notes: null,
      feed: "/v1/feeds/s1/rss.xml",
    },
  };
}

function renderTab(voice: string | null) {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <ListenTab episode={episode(voice)} />
    </QueryClientProvider>,
  );
}

describe("listen tab", () => {
  it("says plainly when the audio is placeholder tones", () => {
    renderTab("placeholder-tones");
    expect(
      screen.getByText(/placeholder tones, not speech/),
    ).toBeInTheDocument();
  });
  it("says nothing extra for a real voice", () => {
    renderTab("gemini-tts");
    expect(screen.queryByText(/placeholder tones/)).not.toBeInTheDocument();
  });
});
