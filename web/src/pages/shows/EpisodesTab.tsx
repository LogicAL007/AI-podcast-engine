import { useState } from "react";
import { Link, useNavigate } from "react-router";

import { PAGE_SIZE, useShowEpisodes, useStartEpisode } from "../../api/queries";
import type { ShowRead } from "../../api/types";
import { ErrorAlert } from "../../components/Alert";
import { Button } from "../../components/Button";
import { EmptyState } from "../../components/EmptyState";
import { Pagination } from "../../components/Pagination";
import { stageLabel } from "../../components/ProgressSteps";
import { Skeleton } from "../../components/Skeleton";
import { StatusBadge } from "../../components/StatusBadge";
import { formatDate } from "../format";

export function EpisodesTab({ show }: { show: ShowRead }) {
  const [offset, setOffset] = useState(0);
  const episodes = useShowEpisodes(show.show_id, offset);
  const start = useStartEpisode(show.show_id);
  const navigate = useNavigate();
  const noSources = show.sources.length === 0;

  const generate = (
    <Button
      busy={start.isPending}
      onClick={() =>
        start.mutate(undefined, {
          onSuccess: (e) => navigate(`/episodes/${e.episode_id}`),
        })
      }
    >
      Generate episode
    </Button>
  );

  return (
    <div className="stack">
      <div className="spread">
        <p className="muted">
          Generating reads the sources again; if nothing changed, no new episode
          is made.
          {noSources
            ? " Add source pages in Settings, or upload a PDF, first."
            : ""}
        </p>
        {generate}
      </div>
      <ErrorAlert error={start.error} />
      {episodes.isPending ? (
        <Skeleton label="Loading episodes" rows={2} />
      ) : null}
      <ErrorAlert error={episodes.error} />
      {episodes.data && episodes.data.total === 0 ? (
        <EmptyState title="No episodes yet" action={generate}>
          The first episode is written from this show&apos;s sources,
          fact-checked, voiced and published to its feed.
        </EmptyState>
      ) : null}
      {episodes.data && episodes.data.total > 0 ? (
        <>
          <ul className="list">
            {episodes.data.items.map((episode) => (
              <li key={episode.episode_id}>
                <Link
                  className="list-item"
                  to={`/episodes/${episode.episode_id}`}
                >
                  <span className="stack" style={{ gap: "var(--space-1)" }}>
                    <span className="list-item-title">
                      Episode {episode.revision}
                    </span>
                    <span
                      className="muted"
                      style={{ fontSize: "var(--text-sm)" }}
                    >
                      Started {formatDate(episode.created_at)}
                      {episode.status === "processing"
                        ? ` · ${stageLabel(episode.stage)}`
                        : ""}
                    </span>
                  </span>
                  <StatusBadge status={episode.status} />
                </Link>
              </li>
            ))}
          </ul>
          <Pagination
            offset={offset}
            limit={PAGE_SIZE}
            total={episodes.data.total}
            onChange={setOffset}
          />
        </>
      ) : null}
    </div>
  );
}
