import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { keys } from "../api/queries";
import type { EpisodeProgress, EpisodeRead } from "../api/types";
import { useEpisodeEvents } from "./useEpisodeEvents";

class FakeEventSource {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSED = 2;
  static last: FakeEventSource | null = null;
  readyState = FakeEventSource.OPEN;
  onerror: (() => void) | null = null;
  private listeners: Record<string, ((event: MessageEvent) => void)[]> = {};

  constructor(readonly url: string) {
    FakeEventSource.last = this;
  }
  addEventListener(type: string, listener: (event: MessageEvent) => void) {
    (this.listeners[type] ??= []).push(listener);
  }
  close() {
    this.readyState = FakeEventSource.CLOSED;
  }
  emit(type: string, data: unknown) {
    for (const listener of this.listeners[type] ?? []) {
      listener(new MessageEvent(type, { data: JSON.stringify(data) }));
    }
  }
}

const EPISODE = {
  episode_id: "e1",
  show_id: "s1",
  status: "queued",
  stage: null,
  error: null,
  revision: 1,
  rewrite_count: 0,
  created_at: "2026-10-22T10:00:00Z",
  published_at: null,
  approved_at: null,
  links: {
    self: "/v1/episodes/e1",
    script: "",
    runs: "",
    audio: null,
    notes: null,
    feed: "",
  },
} as EpisodeRead;

function progress(overrides: Partial<EpisodeProgress>): EpisodeProgress {
  return {
    episode_id: "e1",
    status: "processing",
    stage: "script",
    step: 4,
    steps: 8,
    error: null,
    rewrite_count: 0,
    running: true,
    ...overrides,
  };
}

describe("useEpisodeEvents", () => {
  let client: QueryClient;
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );

  beforeEach(() => {
    client = new QueryClient();
    client.setQueryData(keys.episode("e1"), EPISODE);
    vi.stubGlobal("EventSource", FakeEventSource);
  });
  afterEach(() => vi.unstubAllGlobals());

  it("opens the stream for a running episode and updates the cached episode", () => {
    const { result } = renderHook(() => useEpisodeEvents("e1", true), {
      wrapper,
    });
    expect(FakeEventSource.last?.url).toBe("/api/v1/episodes/e1/events");
    expect(result.current).toBe("stream");
    act(() =>
      FakeEventSource.last?.emit(
        "episode",
        progress({ stage: "factcheck", rewrite_count: 1 }),
      ),
    );
    expect(client.getQueryData<EpisodeRead>(keys.episode("e1"))).toMatchObject({
      status: "processing",
      stage: "factcheck",
      rewrite_count: 1,
    });
  });

  it("closes the stream when nothing is running any more", () => {
    const { result } = renderHook(() => useEpisodeEvents("e1", true), {
      wrapper,
    });
    const source = FakeEventSource.last!;
    act(() =>
      source.emit(
        "episode",
        progress({ status: "published", stage: null, step: 8, running: false }),
      ),
    );
    expect(source.readyState).toBe(FakeEventSource.CLOSED);
    expect(result.current).toBe("idle");
    expect(client.getQueryData<EpisodeRead>(keys.episode("e1"))?.status).toBe(
      "published",
    );
  });

  it("falls back to polling when the stream cannot be opened", () => {
    const { result } = renderHook(() => useEpisodeEvents("e1", true), {
      wrapper,
    });
    const source = FakeEventSource.last!;
    act(() => {
      source.readyState = FakeEventSource.CLOSED;
      source.onerror?.();
    });
    expect(result.current).toBe("polling");
  });

  it("does nothing for an episode that is not running", () => {
    FakeEventSource.last = null;
    const { result } = renderHook(() => useEpisodeEvents("e1", false), {
      wrapper,
    });
    expect(FakeEventSource.last).toBeNull();
    expect(result.current).toBe("idle");
  });
});
