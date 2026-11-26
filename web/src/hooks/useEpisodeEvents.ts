import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { API_BASE } from "../api/client";
import { keys } from "../api/queries";
import type { EpisodeProgress, EpisodeRead } from "../api/types";

export type FollowMode = "idle" | "stream" | "polling";

/**
 * Follows an episode while it is being made, through the API's server-sent events. Each event
 * updates the cached episode, so every view of it moves on at once. EventSource sends the
 * sign-in cookie by itself and reconnects after a dropped connection. If the stream cannot be
 * opened at all, this reports "polling", and the caller re-fetches the episode on a timer.
 */
export function useEpisodeEvents(
  episodeId: string,
  running: boolean,
): FollowMode {
  const client = useQueryClient();
  const [mode, setMode] = useState<FollowMode>("idle");

  useEffect(() => {
    if (!running) {
      setMode("idle");
      return;
    }
    if (typeof EventSource === "undefined") {
      setMode("polling");
      return;
    }
    const source = new EventSource(
      `${API_BASE}/v1/episodes/${episodeId}/events`,
    );
    setMode("stream");

    const refreshEverything = () => {
      // Links (audio, notes), the script, claims and runs change when work finishes.
      void client.invalidateQueries({ queryKey: ["episode", episodeId] });
      void client.invalidateQueries({ queryKey: ["show"] });
    };

    source.addEventListener("episode", (event) => {
      const progress = JSON.parse(
        (event as MessageEvent<string>).data,
      ) as EpisodeProgress;
      client.setQueryData<EpisodeRead>(keys.episode(episodeId), (old) =>
        old
          ? {
              ...old,
              status: progress.status,
              stage: progress.stage,
              error: progress.error,
              rewrite_count: progress.rewrite_count,
            }
          : old,
      );
      if (!progress.running) {
        source.close(); // done: don't let EventSource reconnect
        setMode("idle");
        refreshEverything();
      }
    });
    source.addEventListener("gone", () => {
      source.close();
      setMode("idle");
      refreshEverything();
    });
    source.onerror = () => {
      // CONNECTING means the browser is retrying on its own; CLOSED means it gave up.
      if (source.readyState === EventSource.CLOSED) setMode("polling");
    };
    return () => source.close();
  }, [client, episodeId, running]);

  return mode;
}
