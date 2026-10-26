import { Link, useSearchParams } from "react-router";

import { PAGE_SIZE, useShows } from "../../api/queries";
import { ErrorAlert } from "../../components/Alert";
import { LinkButton } from "../../components/Button";
import { EmptyState } from "../../components/EmptyState";
import { Pagination } from "../../components/Pagination";
import { Skeleton } from "../../components/Skeleton";
import { useRememberedFlag } from "../../hooks/useRememberedFlag";
import { Welcome } from "./Welcome";
import { usePageTitle } from "../../hooks/usePageTitle";

export function ShowsPage() {
  usePageTitle("Shows");
  const [params, setParams] = useSearchParams();
  const offset = Math.max(0, Number(params.get("offset")) || 0);
  const shows = useShows(offset);
  const [welcomeSkipped, skipWelcome] = useRememberedFlag("pe.welcome.skipped");

  return (
    <>
      <div className="page-header">
        <div>
          <h1>Shows</h1>
          <p className="muted">Each show turns its sources into episodes.</p>
        </div>
        <LinkButton to="/shows/new">New show</LinkButton>
      </div>
      {shows.isPending ? <Skeleton label="Loading your shows" /> : null}
      <ErrorAlert error={shows.error} />
      {shows.data && shows.data.total === 0 && !welcomeSkipped ? (
        <Welcome onSkip={() => skipWelcome(true)} />
      ) : null}
      {shows.data && shows.data.total === 0 && welcomeSkipped ? (
        <EmptyState
          title="No shows yet"
          action={
            <LinkButton to="/shows/new">Create your first show</LinkButton>
          }
        >
          A show has a topic and a set of sources. Episodes are written from
          those sources and checked against them.
        </EmptyState>
      ) : null}
      {shows.data && shows.data.total > 0 ? (
        <div className="stack">
          <ul className="list">
            {shows.data.items.map((show) => (
              <li key={show.show_id}>
                <Link className="list-item" to={`/shows/${show.show_id}`}>
                  <span className="stack" style={{ gap: "var(--space-1)" }}>
                    <span className="list-item-title">{show.topic}</span>
                    <span
                      className="muted"
                      style={{ fontSize: "var(--text-sm)" }}
                    >
                      {show.sources.length} source page
                      {show.sources.length === 1 ? "" : "s"} ·{" "}
                      {show.target_minutes} min · {show.host_count} host
                      {show.host_count === 1 ? "" : "s"}
                      {show.review_before_voice
                        ? " · reviewed before voicing"
                        : ""}
                    </span>
                  </span>
                  <span aria-hidden="true" className="muted">
                    →
                  </span>
                </Link>
              </li>
            ))}
          </ul>
          <Pagination
            offset={offset}
            limit={PAGE_SIZE}
            total={shows.data.total}
            onChange={(next) => setParams(next ? { offset: String(next) } : {})}
          />
        </div>
      ) : null}
    </>
  );
}
